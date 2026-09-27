"""Individual customers: arrival, booking and payment, and what finally happens to each session.

Life of a booking (accounting policy, sections 1 and 3):
    booked and paid by card (a first attempt may be declined)
    -> possibly rescheduled, always 48 hours or more before the session
    -> attended, no-show, cancelled in time (full refund) or cancelled late (forfeited)
    -> after an attended session: possibly a goodwill refund, possibly a return visit

Each customer has its own random stream, and every random decision about a booking is drawn when
the booking is made, so one customer's story never depends on the order other events run in.
"""

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from simulator.business_calendar import add_months
from simulator.capacity import Slot
from simulator.config import Currency
from simulator.demand import demand_level, poisson
from simulator.engine import Engine
from simulator.events import EventType, deterministic_id
from simulator.identities import fake_person

SESSION_LENGTH = timedelta(hours=4)
FREE_CANCELLATION_NOTICE = timedelta(hours=48)
BOOKING_HOURS = (7, 23)  # customers book online between 07:00 and 23:00, Company time
GOODWILL_REFUND_TIME = time(11, 0)

ATTENDED = "attended"
CANCELLED_WITH_REFUND = "cancelled_with_refund"
CANCELLED_LATE = "cancelled_late"
NO_SHOW = "no_show"


@dataclass
class Individual:
    customer_id: str
    name: str
    email: str
    country: str
    currency: Currency
    bookings: int = 0
    in_stripe: bool = False  # created in Stripe at the first checkout
    last_attended: date | None = None


@dataclass(frozen=True)
class BookingPlan:
    """Every random decision about one booking, drawn up front."""

    lead_days: int
    declined_first: bool
    retry_succeeds: bool
    retry_delay: timedelta
    outcome: str
    reschedule: bool
    reschedule_position: float  # where in the free-change window the reschedule happens (0 to 1)
    reschedule_days: int
    cancel_position: float  # where in its window the cancellation happens (0 to 1)
    refund_delay: timedelta
    goodwill_refund: bool
    goodwill_delay_days: int
    returns: bool
    days_to_return: int
    return_time: time


@dataclass
class Booking:
    customer: Individual
    booking_id: str
    session_id: str
    amount: int
    slot: Slot
    start: datetime
    last_change: datetime  # payment or latest reschedule: cancellations happen after it
    plan: BookingPlan


class IndividualsFlow:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.config = engine.config
        self.settings = engine.config.individuals
        self._demand = engine.random.stream("individuals", "demand")
        self._created = 0

    def on_day(self, day: date) -> None:
        for _ in range(poisson(self._demand, self._expected_new_customers(day))):
            customer, rng = self._new_customer()
            self._book(customer, self.engine.calendar.to_utc(day, _time_of_day(rng)))

    def _expected_new_customers(self, day: date) -> float:
        return (
            self.settings.new_customers_per_week / 7
            * self.settings.booking_weekday_weights.for_weekday(day.weekday())
            * self.config.demand.seasonality.individuals.for_month(day.month)
            * demand_level(self.config.demand, self.config.run.start_date, day)
        )

    def _new_customer(self) -> tuple[Individual, random.Random]:
        self._created += 1
        customer_id = deterministic_id("cust", f"individual:{self._created}")
        rng = self.engine.random.stream("individual", customer_id)
        markets = self.settings.markets
        market = rng.choices(markets, weights=[m.share for m in markets])[0]
        name, email = fake_person(market.country, rng)
        return Individual(customer_id, name, email, market.country, market.currency), rng

    def _book(self, customer: Individual, booked_at: datetime) -> None:
        engine, calendar = self.engine, self.engine.calendar
        plan = self._draw_plan(engine.random.stream("individual", customer.customer_id))
        booking_id = deterministic_id("bkg", f"{customer.customer_id}:{customer.bookings}")
        customer.bookings += 1
        booked_on = calendar.local_date(booked_at)

        slot = engine.capacity.book(booked_on, booked_on + timedelta(days=plan.lead_days))
        if slot is None:
            engine.emit(
                EventType.SALE_LOST, "scheduling", customer.customer_id, booked_at,
                {"segment": "individual", "booking_id": booking_id, "first_booking": not customer.in_stripe},
            )
            return

        if not customer.in_stripe:
            customer.in_stripe = True
            engine.emit(
                EventType.CUSTOMER_CREATED, "stripe", customer.customer_id, booked_at,
                {"segment": "individual", "name": customer.name, "email": customer.email,
                 "country": customer.country, "currency": customer.currency},
            )

        list_price = self.config.price("individual_session", customer.currency, booked_on)
        discount = self._loyalty_discount(customer, booked_on)
        charge = {
            "customer_id": customer.customer_id, "booking_id": booking_id, "amount": list_price - discount,
            "list_price": list_price, "discount": discount, "currency": customer.currency,
            "card_country": customer.country,
        }
        paid_at = booked_at
        if plan.declined_first:
            engine.emit(EventType.CHECKOUT_DECLINED, "stripe", booking_id, booked_at, charge)
            if not plan.retry_succeeds:
                engine.capacity.release(slot)
                return
            paid_at = booked_at + plan.retry_delay

        session_id = deterministic_id("ses", booking_id)
        start = calendar.to_utc(slot.day, slot.start)
        engine.emit(EventType.BOOKING_PAID, "stripe", booking_id, paid_at, charge | {"session_id": session_id})
        engine.emit(
            EventType.SESSION_BOOKED, "scheduling", session_id, paid_at,
            {"segment": "individual", "booking_id": booking_id, "customer_id": customer.customer_id,
             "advisor": slot.advisor, "scheduled_start": start},
        )
        booking = Booking(customer, booking_id, session_id, charge["amount"], slot, start, paid_at, plan)

        window = start - FREE_CANCELLATION_NOTICE - paid_at
        if plan.reschedule and window > timedelta(0):
            reschedule_at = _point_between(paid_at, paid_at + window, plan.reschedule_position)
            engine.schedule(reschedule_at, lambda when: self._reschedule(booking, when))
        else:
            self._plan_outcome(booking)

    def _reschedule(self, booking: Booking, when: datetime) -> None:
        engine = self.engine
        new_slot = engine.capacity.book(
            engine.calendar.local_date(when), booking.slot.day + timedelta(days=booking.plan.reschedule_days)
        )
        if new_slot is not None:
            engine.capacity.release(booking.slot)
            new_start = engine.calendar.to_utc(new_slot.day, new_slot.start)
            engine.emit(
                EventType.SESSION_RESCHEDULED, "scheduling", booking.session_id, when,
                {"previous_start": booking.start, "scheduled_start": new_start, "advisor": new_slot.advisor},
            )
            booking.slot, booking.start, booking.last_change = new_slot, new_start, when
        self._plan_outcome(booking)

    def _plan_outcome(self, booking: Booking) -> None:
        engine, plan = self.engine, booking.plan
        free_until = booking.start - FREE_CANCELLATION_NOTICE
        outcome = plan.outcome
        if outcome == CANCELLED_WITH_REFUND and free_until <= booking.last_change:
            outcome = CANCELLED_LATE  # booked or moved too close to the session to cancel for free

        if outcome == CANCELLED_WITH_REFUND:
            cancel_at = _point_between(booking.last_change, free_until, plan.cancel_position)
            engine.schedule(cancel_at, lambda when: self._cancel_in_time(booking, when))
        elif outcome == CANCELLED_LATE:
            # "Less than 48 hours" before: the window starts one second after the free-cancellation limit
            earliest = max(free_until + timedelta(seconds=1), booking.last_change)
            cancel_at = _point_between(earliest, booking.start, plan.cancel_position)
            engine.schedule(cancel_at, lambda when: self._cancel_late(booking, when))
        elif outcome == NO_SHOW:
            engine.schedule(booking.start, lambda when: self._no_show(booking, when))
        else:
            engine.schedule(booking.start, lambda when: self._attend(booking, when))

    def _cancel_in_time(self, booking: Booking, when: datetime) -> None:
        self.engine.capacity.release(booking.slot)
        self._emit_session(EventType.SESSION_CANCELLED, booking, when, {"late": False})
        refund_at = when + booking.plan.refund_delay
        self.engine.schedule(refund_at, lambda at: self._refund(booking, at, "cancelled_in_time"))

    def _cancel_late(self, booking: Booking, when: datetime) -> None:
        # The slot stays taken: it is too late to offer it to another customer
        self._emit_session(EventType.SESSION_CANCELLED, booking, when, {"late": True})

    def _no_show(self, booking: Booking, when: datetime) -> None:
        self._emit_session(EventType.SESSION_NO_SHOW, booking, when)

    def _attend(self, booking: Booking, when: datetime) -> None:
        engine, plan, customer = self.engine, booking.plan, booking.customer
        self._emit_session(EventType.SESSION_ATTENDED, booking, when)
        session_day = engine.calendar.local_date(when)
        customer.last_attended = session_day

        if plan.goodwill_refund:
            refund_at = engine.calendar.to_utc(session_day + timedelta(days=plan.goodwill_delay_days), GOODWILL_REFUND_TIME)
            engine.schedule(refund_at, lambda at: self._refund(booking, at, "goodwill"))
        if plan.returns:
            return_at = engine.calendar.to_utc(session_day + timedelta(days=plan.days_to_return), plan.return_time)
            engine.schedule(return_at, lambda at: self._book(customer, at))

    def _refund(self, booking: Booking, when: datetime, reason: str) -> None:
        self.engine.emit(
            EventType.REFUND_ISSUED, "stripe", booking.booking_id, when,
            {"customer_id": booking.customer.customer_id, "session_id": booking.session_id,
             "amount": booking.amount, "currency": booking.customer.currency, "reason": reason},
        )

    def _emit_session(self, event_type: EventType, booking: Booking, when: datetime, extra: dict | None = None) -> None:
        self.engine.emit(
            event_type, "scheduling", booking.session_id, when,
            {"segment": "individual", "booking_id": booking.booking_id,
             "customer_id": booking.customer.customer_id, "advisor": booking.slot.advisor,
             "scheduled_start": booking.start} | (extra or {}),
        )

    def _loyalty_discount(self, customer: Individual, booked_on: date) -> int:
        loyalty = self.config.loyalty_discount
        if booked_on < loyalty.effective_from or customer.last_attended is None:
            return 0
        if booked_on > add_months(customer.last_attended, loyalty.window_months):
            return 0
        return getattr(loyalty, customer.currency)

    def _draw_plan(self, rng: random.Random) -> BookingPlan:
        # Every value is drawn on every booking, used or not, so each booking consumes the same numbers
        s = self.settings
        lead = s.lead_time_days
        outcomes = s.outcomes.model_dump()
        back = s.days_to_return
        return BookingPlan(
            lead_days=max(lead.min, round(rng.triangular(lead.min, lead.max, lead.mode))),
            declined_first=rng.random() < s.checkout_decline_rate,
            retry_succeeds=rng.random() < s.decline_retry_success_rate,
            retry_delay=timedelta(minutes=rng.randint(2, 10)),
            outcome=rng.choices(list(outcomes), weights=list(outcomes.values()))[0],
            reschedule=rng.random() < s.reschedule_rate,
            reschedule_position=rng.random(),
            reschedule_days=rng.randint(1, 14),
            cancel_position=rng.random(),
            refund_delay=timedelta(minutes=rng.randint(5, 240)),
            goodwill_refund=rng.random() < s.goodwill_refund_rate,
            goodwill_delay_days=rng.randint(1, 14),
            returns=rng.random() < s.return_probability,
            days_to_return=min(back.max, max(back.min, round(rng.lognormvariate(math.log(back.median), back.sigma)))),
            return_time=_time_of_day(rng),
        )


def _point_between(start: datetime, end: datetime, position: float) -> datetime:
    """A moment between start and end, at a whole second: Stripe timestamps have no fractions."""
    return start + timedelta(seconds=int((end - start).total_seconds() * position))


def _time_of_day(rng: random.Random) -> time:
    minute = rng.randrange(BOOKING_HOURS[0] * 60, BOOKING_HOURS[1] * 60)
    return time(minute // 60, minute % 60)
