"""Business rules checked on one simulated year of individual customers."""

from collections import Counter, defaultdict
from datetime import date, time, timedelta

import pytest

from simulator.business_calendar import add_months
from simulator.config import load_config
from simulator.engine import Engine
from simulator.events import EventType as T
from simulator.individuals import FREE_CANCELLATION_NOTICE, IndividualsFlow

END = date(2026, 9, 30)
OUTCOMES = (T.SESSION_ATTENDED, T.SESSION_NO_SHOW, T.SESSION_CANCELLED)


def _run(until: date) -> Engine:
    engine = Engine(load_config())
    engine.flows.append(IndividualsFlow(engine))
    engine.run(until=until)
    return engine


@pytest.fixture(scope="module")
def engine() -> Engine:
    return _run(END)


@pytest.fixture(scope="module")
def by_type(engine) -> dict:
    grouped = defaultdict(list)
    for event in engine.events:
        grouped[event.event_type].append(event)
    return grouped


@pytest.fixture(scope="module")
def final_start(by_type) -> dict:
    """Scheduled start of every session, after any reschedule."""
    starts = {e.subject_id: e.payload["scheduled_start"] for e in by_type[T.SESSION_BOOKED]}
    for event in by_type[T.SESSION_RESCHEDULED]:
        starts[event.subject_id] = event.payload["scheduled_start"]
    return starts


@pytest.fixture(scope="module")
def outcome_of(by_type) -> dict:
    outcomes = defaultdict(list)
    for event_type in OUTCOMES:
        for event in by_type[event_type]:
            outcomes[event.subject_id].append(event)
    return outcomes


def test_every_paid_booking_has_one_booked_session(by_type):
    paid = [e.payload["session_id"] for e in by_type[T.BOOKING_PAID]]

    assert len(paid) == len(set(paid))
    assert set(paid) == {e.subject_id for e in by_type[T.SESSION_BOOKED]}


def test_every_past_session_has_exactly_one_outcome(engine, final_start, outcome_of):
    for session_id, start in final_start.items():
        count = len(outcome_of[session_id])
        if engine.calendar.local_date(start) <= END:
            assert count == 1, session_id
        else:
            assert count <= 1, session_id


def test_sessions_take_place_on_business_days_at_slot_times(engine, final_start):
    for start in final_start.values():
        local = start.astimezone(engine.calendar.tz)
        assert engine.calendar.is_business_day(local.date())
        assert local.time() in (time(9, 0), time(14, 0))


def test_cancellations_follow_the_48_hour_policy(engine, by_type, final_start):
    refunds = {e.subject_id: e for e in by_type[T.REFUND_ISSUED] if e.payload["reason"] == "cancelled_in_time"}
    paid = {e.subject_id: e.payload["amount"] for e in by_type[T.BOOKING_PAID]}

    for cancel in by_type[T.SESSION_CANCELLED]:
        booking_id = cancel.payload["booking_id"]
        notice = final_start[cancel.subject_id] - cancel.occurred_at
        if cancel.payload["late"]:
            assert timedelta(0) <= notice < FREE_CANCELLATION_NOTICE
            assert booking_id not in refunds
        else:
            assert notice >= FREE_CANCELLATION_NOTICE
            if booking_id in refunds:
                assert refunds[booking_id].payload["amount"] == paid[booking_id]
            else:  # cancelled on the last simulated day: the refund is still waiting in the queue
                assert engine.calendar.local_date(cancel.occurred_at) == END


def test_prices_follow_the_price_list_and_the_loyalty_rules(engine, by_type):
    config = engine.config
    last_attended: dict[str, date] = {}
    for event in engine.events:
        payload = event.payload
        if event.event_type == T.SESSION_ATTENDED:
            last_attended[payload["customer_id"]] = engine.calendar.local_date(event.occurred_at)
        elif event.event_type == T.BOOKING_PAID:
            day = engine.calendar.local_date(event.occurred_at)
            assert payload["list_price"] == config.price("individual_session", payload["currency"], day)
            assert payload["amount"] == payload["list_price"] - payload["discount"]
            previous = last_attended.get(payload["customer_id"])
            eligible = (
                day >= config.loyalty_discount.effective_from
                and previous is not None
                and day <= add_months(previous, config.loyalty_discount.window_months)
            )
            assert (payload["discount"] > 0) == eligible


def test_some_customers_return_with_the_loyalty_discount(by_type):
    assert sum(1 for e in by_type[T.BOOKING_PAID] if e.payload["discount"] > 0) >= 10


def test_outcome_shares_match_the_config(engine, outcome_of):
    finals = Counter()
    for (event,) in (events for events in outcome_of.values() if len(events) == 1):
        if event.event_type == T.SESSION_CANCELLED:
            finals["cancelled_late" if event.payload["late"] else "cancelled_with_refund"] += 1
        else:
            finals[event.event_type.value.removeprefix("session_")] += 1
    total = sum(finals.values())
    expected = engine.config.individuals.outcomes.model_dump()

    for outcome, share in expected.items():
        assert finals[outcome] / total == pytest.approx(share, abs=0.04), outcome


def test_yearly_volumes_are_close_to_the_documented_estimate(by_type):
    # docs/simulation.md: about 470 individual customers and 600 bookings in the first 12 months
    assert 375 <= len(by_type[T.CUSTOMER_CREATED]) <= 565
    assert 480 <= len(by_type[T.BOOKING_PAID]) <= 720


def test_some_checkouts_are_declined_and_most_are_retried(by_type):
    declined = {e.subject_id for e in by_type[T.CHECKOUT_DECLINED]}
    paid = {e.subject_id for e in by_type[T.BOOKING_PAID]}
    attempts = len(declined | paid)

    assert len(declined) / attempts == pytest.approx(0.03, abs=0.015)
    assert len(declined & paid) > len(declined - paid)  # 70% of declined customers retry successfully


def test_two_runs_are_identical():
    first = [e.to_dict() for e in _run(date(2025, 11, 30)).events]
    second = [e.to_dict() for e in _run(date(2025, 11, 30)).events]

    assert first == second
