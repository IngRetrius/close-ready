"""Chargeback disputes on individual card charges.

The run goes to mid-2027: at 0.5% of attended sessions, a single year has only two or three disputes.
"""

from collections import defaultdict
from datetime import date, timedelta

import pytest

from simulator.config import load_config
from simulator.engine import Engine
from simulator.events import EventType as T
from simulator.individuals import IndividualsFlow

END = date(2027, 6, 30)
FIRST_YEAR_END = date(2026, 9, 30)
DECISIONS = (T.DISPUTE_WON, T.DISPUTE_LOST)


@pytest.fixture(scope="module")
def engine() -> Engine:
    engine = Engine(load_config())
    engine.flows.append(IndividualsFlow(engine))
    engine.run(until=END)
    return engine


@pytest.fixture(scope="module")
def by_type(engine) -> dict:
    grouped = defaultdict(list)
    for event in engine.events:
        grouped[event.event_type].append(event)
    return grouped


def _local(engine, timestamp) -> date:
    return engine.calendar.local_date(timestamp)


def test_only_attended_sessions_without_a_goodwill_refund_are_disputed(by_type):
    attended = {e.payload["booking_id"] for e in by_type[T.SESSION_ATTENDED]}
    goodwill = {e.subject_id for e in by_type[T.REFUND_ISSUED] if e.payload["reason"] == "goodwill"}

    for dispute in by_type[T.DISPUTE_OPENED]:
        assert dispute.payload["booking_id"] in attended - goodwill


def test_disputes_open_after_the_session_and_15_to_75_days_after_the_charge(engine, by_type):
    charged_on = {e.subject_id: _local(engine, e.occurred_at) for e in by_type[T.BOOKING_PAID]}
    session_on = {e.payload["booking_id"]: _local(engine, e.occurred_at) for e in by_type[T.SESSION_ATTENDED]}

    for dispute in by_type[T.DISPUTE_OPENED]:
        booking_id = dispute.payload["booking_id"]
        opened_on = _local(engine, dispute.occurred_at)
        assert opened_on > session_on[booking_id]
        assert opened_on >= charged_on[booking_id] + timedelta(days=15)
        assert opened_on <= max(charged_on[booking_id] + timedelta(days=75), session_on[booking_id] + timedelta(days=1))


def test_disputed_amount_is_the_charge(by_type):
    paid = {e.subject_id: (e.payload["amount"], e.payload["currency"]) for e in by_type[T.BOOKING_PAID]}

    for dispute in by_type[T.DISPUTE_OPENED]:
        assert (dispute.payload["amount"], dispute.payload["currency"]) == paid[dispute.payload["booking_id"]]


def test_every_dispute_is_decided_once_60_to_75_days_after_opening(engine, by_type):
    decisions = defaultdict(list)
    for event_type in DECISIONS:
        for event in by_type[event_type]:
            decisions[event.subject_id].append(event)

    for dispute in by_type[T.DISPUTE_OPENED]:
        decided = decisions[dispute.subject_id]
        if _local(engine, dispute.occurred_at) + timedelta(days=75) <= END:
            assert len(decided) == 1, dispute.subject_id
        else:  # opened near the end of the run: the decision may still be waiting in the queue
            assert len(decided) <= 1, dispute.subject_id
        for decision in decided:
            assert timedelta(days=60) <= decision.occurred_at - dispute.occurred_at <= timedelta(days=75)


def test_disputes_are_rare_but_both_decisions_occur(engine, by_type):
    # docs/simulation.md: 2-3 disputes in the first 12 months
    first_year = [e for e in by_type[T.DISPUTE_OPENED] if _local(engine, e.occurred_at) <= FIRST_YEAR_END]

    assert 1 <= len(first_year) <= 6
    assert by_type[T.DISPUTE_WON] and by_type[T.DISPUTE_LOST]
