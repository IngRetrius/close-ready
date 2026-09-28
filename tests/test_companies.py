"""Business rules checked on simulated corporate customers.

The run goes to mid-2027: packs expire 12 months after purchase, so the first year has no expiries.
"""

from collections import Counter, defaultdict
from datetime import date, time, timedelta

import pytest

from simulator.business_calendar import add_months
from simulator.companies import CompaniesFlow
from simulator.config import load_config
from simulator.engine import Engine
from simulator.events import EventType as T

END = date(2027, 6, 30)
FIRST_YEAR_END = date(2026, 9, 30)
PACK_SESSIONS = 10


@pytest.fixture(scope="module")
def engine() -> Engine:
    engine = Engine(load_config())
    engine.flows.append(CompaniesFlow(engine))
    engine.run(until=END)
    return engine


@pytest.fixture(scope="module")
def by_type(engine) -> dict:
    grouped = defaultdict(list)
    for event in engine.events:
        grouped[event.event_type].append(event)
    return grouped


@pytest.fixture(scope="module")
def packs(by_type) -> dict:
    return {e.subject_id: e for e in by_type[T.PACK_INVOICED]}


@pytest.fixture(scope="module")
def sessions_by_pack(by_type) -> dict:
    grouped = defaultdict(list)
    for event_type in (T.SESSION_ATTENDED, T.SESSION_NO_SHOW):
        for event in by_type[event_type]:
            grouped[event.payload["pack_id"]].append(event)
    return grouped


def _local(engine, event) -> date:
    return engine.calendar.local_date(event.occurred_at)


def test_packs_are_priced_and_dated_from_the_invoice(engine, packs):
    for pack in packs.values():
        day = _local(engine, pack)
        payload = pack.payload
        assert payload["amount"] == engine.config.price("corporate_pack", payload["currency"], day)
        assert payload["due_date"] == day + timedelta(days=15)
        assert payload["expires_on"] == add_months(day, 12)


def test_sessions_take_place_before_expiry_on_business_days(engine, packs, by_type):
    booked = Counter()
    for event in by_type[T.SESSION_BOOKED]:
        pack = packs[event.payload["pack_id"]].payload
        start = event.payload["scheduled_start"].astimezone(engine.calendar.tz)
        booked[event.payload["pack_id"]] += 1
        assert start.date() < pack["expires_on"]
        assert engine.calendar.is_business_day(start.date())
        assert start.time() in (time(9, 0), time(14, 0))
    assert max(booked.values()) <= PACK_SESSIONS


def test_every_invoice_is_settled_once(engine, packs, by_type):
    paid = Counter(e.payload["pack_id"] for e in by_type[T.INVOICE_PAID])
    written_off = Counter(e.payload["pack_id"] for e in by_type[T.INVOICE_UNCOLLECTIBLE])

    for pack_id, pack in packs.items():
        assert paid[pack_id] + written_off[pack_id] <= 1
        # 60 days is the latest a paying company pays; 90 days overdue triggers the write-off
        if pack.payload["due_date"] + timedelta(days=95) < END:
            assert paid[pack_id] + written_off[pack_id] == 1, pack_id


def test_payments_follow_the_payment_behaviors(engine, packs, by_type):
    lateness = [(_local(engine, e) - packs[e.payload["pack_id"]].payload["due_date"]).days for e in by_type[T.INVOICE_PAID]]

    assert min(lateness) >= -10
    assert max(lateness) <= 60 + 3  # plus up to a long weekend when the day is rolled forward
    assert sum(1 for days in lateness if days <= 0) / len(lateness) == pytest.approx(0.70 / 0.97, abs=0.15)


def test_no_new_sessions_while_more_than_30_days_overdue(engine, packs, by_type):
    paid_on = {e.payload["pack_id"]: _local(engine, e) for e in by_type[T.INVOICE_PAID]}
    for event in by_type[T.SESSION_BOOKED]:
        pack_id = event.payload["pack_id"]
        requested_on = _local(engine, event)
        overdue = (requested_on - packs[pack_id].payload["due_date"]).days
        assert overdue <= 30 or (pack_id in paid_on and paid_on[pack_id] <= requested_on)


def test_write_offs_split_used_and_unused_sessions(engine, packs, by_type, sessions_by_pack):
    assert by_type[T.INVOICE_UNCOLLECTIBLE], "expected at least one write-off"
    for event in by_type[T.INVOICE_UNCOLLECTIBLE]:
        pack_id = event.payload["pack_id"]
        due = packs[pack_id].payload["due_date"]
        assert _local(engine, event) == engine.calendar.roll_forward(due + timedelta(days=90))
        assert event.payload["sessions_used"] == len(sessions_by_pack[pack_id])
        assert event.payload["sessions_used"] + event.payload["sessions_unused"] == PACK_SESSIONS


def test_expired_packs_report_their_unused_sessions(engine, packs, by_type, sessions_by_pack):
    assert by_type[T.PACK_EXPIRED], "expected expiries before mid-2027"
    for event in by_type[T.PACK_EXPIRED]:
        pack_id = event.subject_id
        assert _local(engine, event) == packs[pack_id].payload["expires_on"]
        assert event.payload["sessions_used"] == len(sessions_by_pack[pack_id])
        assert event.payload["sessions_unused"] == PACK_SESSIONS - event.payload["sessions_used"] > 0


def test_breakage_is_material(by_type, sessions_by_pack):
    # Among packs that have ended by use or expiry, about 16% of sessions go unused (docs/simulation.md)
    ended = {e.subject_id for e in by_type[T.PACK_EXPIRED]}
    ended |= {pack_id for pack_id, sessions in sessions_by_pack.items() if len(sessions) == PACK_SESSIONS}
    unused = sum(PACK_SESSIONS - len(sessions_by_pack[pack_id]) for pack_id in ended)

    assert unused / (PACK_SESSIONS * len(ended)) == pytest.approx(0.165, abs=0.08)


def test_companies_buy_again_but_never_after_a_write_off(engine, by_type):
    written_off_at = {e.payload["customer_id"]: e.occurred_at for e in by_type[T.INVOICE_UNCOLLECTIBLE]}
    packs_per_company = Counter(e.payload["customer_id"] for e in by_type[T.PACK_INVOICED])

    assert sum(1 for count in packs_per_company.values() if count >= 2) >= 3
    for event in by_type[T.PACK_INVOICED]:
        customer_id = event.payload["customer_id"]
        assert customer_id not in written_off_at or event.occurred_at < written_off_at[customer_id]


def test_no_show_share(by_type):
    attended, no_show = len(by_type[T.SESSION_ATTENDED]), len(by_type[T.SESSION_NO_SHOW])

    assert no_show / (attended + no_show) == pytest.approx(0.03, abs=0.03)


def test_first_year_volumes_are_close_to_the_documented_estimate(engine, by_type):
    # docs/simulation.md: about 24 companies and 31 packs in the first 12 months
    first_year = [e for e in by_type[T.PACK_INVOICED] if _local(engine, e) <= FIRST_YEAR_END]
    companies = {e.payload["customer_id"] for e in first_year}

    assert 17 <= len(companies) <= 31
    assert 22 <= len(first_year) <= 40
