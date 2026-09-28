"""Corporate customers: packs of prepaid sessions, invoiced with payment terms.

Life of a pack (accounting policy, sections 1 and 3):
    invoiced, due in 15 days
    -> employees request sessions over the pack's usage span; each session is attended or a no-show
    -> the invoice is paid on time, late or never; no new sessions while it is more than 30 days overdue
    -> the pack ends when all its sessions are used, when it expires after 12 months (breakage)
       or when its invoice is written off 90 days after the due date
    -> after a pack is used up or expires, the company may buy another one (never after a write-off)

Every random decision about a pack is drawn when it is invoiced, from the company's own stream.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from simulator.business_calendar import add_months
from simulator.config import Currency
from simulator.demand import demand_level, poisson
from simulator.engine import Engine
from simulator.events import EventType, deterministic_id
from simulator.identities import fake_company
from simulator.recording import outcome_recorded_at

BUSINESS_HOURS = (9, 17)  # companies buy, pay and request sessions during office hours, Company time
EXPIRY_TIME = time(0, 0)  # a pack expires at the start of its expiry date


@dataclass
class Company:
    customer_id: str
    name: str
    email: str
    country: str
    currency: Currency
    packs: int = 0
    in_stripe: bool = False


@dataclass(frozen=True)
class PackPlan:
    """Every random decision about one pack, drawn up front."""

    sessions_to_use: int
    usage_span_months: int
    request_positions: tuple[float, ...]  # where each request falls in the usage window (0 to 1)
    request_times: tuple[time, ...]
    lead_days: tuple[int, ...]
    no_shows: tuple[bool, ...]
    pays: bool
    days_after_due: int
    payment_time: time
    repurchase: bool
    repurchase_delay_days: int
    repurchase_time: time


@dataclass
class Pack:
    company: Company
    pack_id: str
    invoice_id: str
    amount: int
    invoiced_on: date
    due_on: date
    expires_on: date
    plan: PackPlan
    sessions_booked: int = 0
    sessions_used: int = 0  # attended or no-show: both consume a session
    paid: bool = False
    written_off: bool = False
    ended: bool = False


class CompaniesFlow:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.config = engine.config
        self.settings = engine.config.companies
        self._demand = engine.random.stream("companies", "demand")
        self._created = 0
        self._business_days_in_month: dict[tuple[int, int], int] = {}

    def on_day(self, day: date) -> None:
        if not self.engine.calendar.is_business_day(day):
            return
        for _ in range(poisson(self._demand, self._expected_new_companies(day))):
            company, rng = self._new_company()
            self._invoice_pack(company, self.engine.calendar.to_utc(day, _office_time(rng)))

    def _expected_new_companies(self, day: date) -> float:
        monthly = (
            self.settings.new_companies_per_month
            * self.config.demand.seasonality.companies.for_month(day.month)
            * demand_level(self.config.demand, self.config.run.start_date, day)
        )
        return monthly / self._business_days(day.year, day.month)

    def _business_days(self, year: int, month: int) -> int:
        if (year, month) not in self._business_days_in_month:
            first = date(year, month, 1)
            last = add_months(first, 1) - timedelta(days=1)
            self._business_days_in_month[(year, month)] = len(list(self.engine.calendar.business_days(first, last)))
        return self._business_days_in_month[(year, month)]

    def _new_company(self) -> tuple[Company, random.Random]:
        self._created += 1
        customer_id = deterministic_id("cust", f"company:{self._created}")
        rng = self.engine.random.stream("company", customer_id)
        markets = self.settings.markets
        market = rng.choices(markets, weights=[m.share for m in markets])[0]
        name, email = fake_company(market.country, rng)
        return Company(customer_id, name, email, market.country, market.currency), rng

    def _invoice_pack(self, company: Company, invoiced_at: datetime) -> None:
        engine, calendar = self.engine, self.engine.calendar
        plan = self._draw_plan(engine.random.stream("company", company.customer_id))
        pack_id = deterministic_id("pack", f"{company.customer_id}:{company.packs}")
        company.packs += 1
        invoiced_on = calendar.local_date(invoiced_at)
        pack = Pack(
            company=company,
            pack_id=pack_id,
            invoice_id=deterministic_id("inv", pack_id),
            amount=self.config.price("corporate_pack", company.currency, invoiced_on),
            invoiced_on=invoiced_on,
            due_on=invoiced_on + timedelta(days=self.settings.payment_terms_days),
            expires_on=add_months(invoiced_on, self.settings.pack_validity_months),
            plan=plan,
        )

        if not company.in_stripe:
            company.in_stripe = True
            engine.emit(
                EventType.CUSTOMER_CREATED, "stripe", company.customer_id, invoiced_at,
                {"segment": "company", "name": company.name, "email": company.email,
                 "country": company.country, "currency": company.currency},
            )
        engine.emit(
            EventType.PACK_INVOICED, "stripe", pack_id, invoiced_at,
            self._invoice_payload(pack) | {"sessions": self.settings.pack_sessions,
                                          "due_date": pack.due_on, "expires_on": pack.expires_on},
        )

        self._schedule_requests(pack)
        if plan.pays:
            paid_on = calendar.roll_forward(pack.due_on + timedelta(days=plan.days_after_due))
            engine.schedule(calendar.to_utc(paid_on, plan.payment_time), lambda when: self._pay(pack, when))
        else:
            write_off_on = calendar.roll_forward(pack.due_on + timedelta(days=self.settings.write_off_after_days_overdue))
            engine.schedule(calendar.to_utc(write_off_on, plan.payment_time), lambda when: self._write_off(pack, when))
        engine.schedule(calendar.to_utc(pack.expires_on, EXPIRY_TIME), lambda when: self._expire(pack, when))

    def _schedule_requests(self, pack: Pack) -> None:
        calendar, plan = self.engine.calendar, pack.plan
        first = pack.invoiced_on + timedelta(days=1)
        # The last request must leave room for the longest lead time before the pack expires
        last = min(
            add_months(pack.invoiced_on, plan.usage_span_months),
            pack.expires_on - timedelta(days=self.settings.lead_time_days.max + 1),
        )
        span = max(0, (last - first).days)
        for index, position in enumerate(plan.request_positions):
            day = calendar.roll_forward(first + timedelta(days=round(span * position)))
            when = calendar.to_utc(day, plan.request_times[index])
            self.engine.schedule(when, lambda at, i=index: self._request_session(pack, i, at))

    def _request_session(self, pack: Pack, index: int, when: datetime) -> None:
        engine, calendar = self.engine, self.engine.calendar
        today = calendar.local_date(when)
        if pack.ended:
            return
        if self._on_hold(pack, today):
            if pack.plan.pays:  # try again the day after the company pays
                paid_on = calendar.roll_forward(pack.due_on + timedelta(days=pack.plan.days_after_due))
                retry = calendar.to_utc(calendar.roll_forward(paid_on + timedelta(days=1)), pack.plan.request_times[index])
                engine.schedule(retry, lambda at: self._request_session(pack, index, at))
            return  # a company that never pays loses the session

        preferred = today + timedelta(days=pack.plan.lead_days[index])
        slot = engine.capacity.book(today, preferred) if preferred < pack.expires_on else None
        if slot is not None and slot.day >= pack.expires_on:
            engine.capacity.release(slot)
            slot = None
        if slot is None:
            engine.emit(
                EventType.SALE_LOST, "scheduling", pack.pack_id, when,
                {"segment": "company", "customer_id": pack.company.customer_id, "reason": "no_slot_before_expiry"},
            )
            return

        pack.sessions_booked += 1
        session_id = deterministic_id("ses", f"{pack.pack_id}:{pack.sessions_booked}")
        start = calendar.to_utc(slot.day, slot.start)
        payload = {"segment": "company", "pack_id": pack.pack_id, "customer_id": pack.company.customer_id,
                   "advisor": slot.advisor, "scheduled_start": start}
        engine.emit(EventType.SESSION_BOOKED, "scheduling", session_id, when, payload)
        outcome = EventType.SESSION_NO_SHOW if pack.plan.no_shows[index] else EventType.SESSION_ATTENDED
        engine.schedule(start, lambda at: self._hold_session(pack, session_id, outcome, payload, at))

    def _hold_session(self, pack: Pack, session_id: str, outcome: EventType, payload: dict, when: datetime) -> None:
        self.engine.emit(
            outcome, "scheduling", session_id, when, payload,
            recorded_at=outcome_recorded_at(self.engine, session_id, when),
        )
        pack.sessions_used += 1
        if pack.sessions_used == self.settings.pack_sessions:
            self._end(pack, self.engine.calendar.local_date(when))

    def _pay(self, pack: Pack, when: datetime) -> None:
        pack.paid = True
        self.engine.emit(
            EventType.INVOICE_PAID, "stripe", pack.invoice_id, when,
            self._invoice_payload(pack) | {"card_country": pack.company.country},
        )

    def _write_off(self, pack: Pack, when: datetime) -> None:
        pack.written_off = pack.ended = True  # the pack is cancelled and the company is not sold again
        self.engine.emit(
            EventType.INVOICE_UNCOLLECTIBLE, "stripe", pack.invoice_id, when,
            self._invoice_payload(pack) | {"sessions_used": pack.sessions_used,
                                          "sessions_unused": self.settings.pack_sessions - pack.sessions_used},
        )

    def _expire(self, pack: Pack, when: datetime) -> None:
        if pack.ended:
            return
        self.engine.emit(
            EventType.PACK_EXPIRED, "scheduling", pack.pack_id, when,
            {"customer_id": pack.company.customer_id, "invoice_id": pack.invoice_id,
             "sessions_used": pack.sessions_used, "sessions_unused": self.settings.pack_sessions - pack.sessions_used},
        )
        self._end(pack, pack.expires_on)

    def _end(self, pack: Pack, day: date) -> None:
        pack.ended = True
        plan = pack.plan
        if plan.repurchase:
            calendar = self.engine.calendar
            buy_on = calendar.roll_forward(day + timedelta(days=plan.repurchase_delay_days))
            self.engine.schedule(
                calendar.to_utc(buy_on, plan.repurchase_time), lambda at: self._invoice_pack(pack.company, at)
            )

    def _on_hold(self, pack: Pack, today: date) -> bool:
        overdue_days = (today - pack.due_on).days
        return not pack.paid and overdue_days > self.settings.service_hold_after_days_overdue

    def _invoice_payload(self, pack: Pack) -> dict:
        return {"customer_id": pack.company.customer_id, "pack_id": pack.pack_id, "invoice_id": pack.invoice_id,
                "amount": pack.amount, "currency": pack.company.currency}

    def _draw_plan(self, rng: random.Random) -> PackPlan:
        s = self.settings
        profile = rng.choices(s.usage_profiles, weights=[p.share for p in s.usage_profiles])[0]
        behavior = rng.choices(s.payment_behavior, weights=[b.share for b in s.payment_behavior])[0]
        sessions = rng.randint(profile.sessions_used.min, profile.sessions_used.max)
        lead = s.lead_time_days
        return PackPlan(
            sessions_to_use=sessions,
            usage_span_months=rng.randint(s.usage_span_months.min, s.usage_span_months.max),
            request_positions=tuple(sorted(rng.random() for _ in range(sessions))),
            request_times=tuple(_office_time(rng) for _ in range(sessions)),
            lead_days=tuple(round(rng.triangular(lead.min, lead.max, lead.mode)) for _ in range(sessions)),
            no_shows=tuple(rng.random() < s.no_show_rate for _ in range(sessions)),
            pays=behavior.pays,
            days_after_due=rng.randint(behavior.days_after_due.min, behavior.days_after_due.max) if behavior.pays else 0,
            payment_time=_office_time(rng),
            repurchase=rng.random() < s.repurchase_probability,
            repurchase_delay_days=rng.randint(s.repurchase_delay_days.min, s.repurchase_delay_days.max),
            repurchase_time=_office_time(rng),
        )


def _office_time(rng: random.Random) -> time:
    minute = rng.randrange(BUSINESS_HOURS[0] * 60, BUSINESS_HOURS[1] * 60)
    return time(minute // 60, minute % 60)
