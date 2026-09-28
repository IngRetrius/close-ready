"""Recording delays: when the scheduling system learns what happened to each session."""

from collections import Counter
from datetime import date, timedelta

import pytest

from simulator.companies import CompaniesFlow
from simulator.config import load_config
from simulator.engine import Engine
from simulator.events import EventType as T
from simulator.individuals import IndividualsFlow
from simulator.recording import SESSION_LENGTH

END = date(2026, 9, 30)
RECORDED_BY_ADVISORS = (T.SESSION_ATTENDED, T.SESSION_NO_SHOW)


@pytest.fixture(scope="module")
def engine() -> Engine:
    engine = Engine(load_config())
    engine.flows += [IndividualsFlow(engine), CompaniesFlow(engine)]
    engine.run(until=END)
    return engine


@pytest.fixture(scope="module")
def outcomes(engine) -> list:
    return [e for e in engine.events if e.event_type in RECORDED_BY_ADVISORS]


def _delay_days(engine, event) -> int:
    return (engine.calendar.local_date(event.recorded_at) - engine.calendar.local_date(event.occurred_at)).days


def test_only_advisors_record_late(engine):
    for event in engine.events:
        if event.event_type not in RECORDED_BY_ADVISORS:
            assert event.recorded_at == event.occurred_at, event.event_type


def test_outcomes_are_recorded_after_the_session_ends_within_15_days(engine, outcomes):
    for event in outcomes:
        assert event.recorded_at >= event.occurred_at + SESSION_LENGTH
        assert 0 <= _delay_days(engine, event) <= 15


def test_delay_shares_match_the_config(engine, outcomes):
    delays = Counter()
    for event in outcomes:
        days = _delay_days(engine, event)
        delays["same_day" if days == 0 else "late" if days <= 5 else "very_late"] += 1

    for delay in engine.config.recording_delays:
        assert delays[delay.name] / len(outcomes) == pytest.approx(delay.share, abs=0.03), delay.name


def test_some_outcomes_are_recorded_after_their_month_closed(engine, outcomes):
    # The case the late-entry rule exists for (accounting policy, section 6)
    close_day = engine.config.company.close_business_day
    after_close = [
        e for e in outcomes
        if engine.calendar.local_date(e.recorded_at)
        > engine.calendar.close_date(engine.calendar.local_date(e.occurred_at), close_day)
    ]

    assert after_close
