from datetime import date, time, timedelta

import pytest

from simulator.config import load_config
from simulator.engine import Engine
from simulator.events import EventType

START = date(2025, 10, 1)


@pytest.fixture
def engine() -> Engine:
    return Engine(load_config())


class _FollowUpFlow:
    """A test flow: on its first day it schedules a session for the next Monday."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def on_day(self, day: date) -> None:
        if day == START:
            when = self.engine.calendar.to_utc(day + timedelta(days=5), time(14, 0))
            self.engine.schedule(when, self._follow_up)

    def _follow_up(self, when) -> None:
        self.engine.emit(EventType.SESSION_ATTENDED, "scheduling", "ses_test", when)


def test_the_first_day_funds_the_company(engine):
    events = engine.run(until=START)

    assert [e.event_type for e in events] == [EventType.CAPITAL_CONTRIBUTED]
    assert events[0].source == "bank"
    assert events[0].payload == {"amount": 2_500_000, "currency": "usd"}
    assert engine.calendar.local_date(events[0].occurred_at) == START


def test_a_scheduled_action_runs_on_its_day(engine):
    engine.flows.append(_FollowUpFlow(engine))

    assert len(engine.run(until=START + timedelta(days=4))) == 1  # not yet
    events = engine.run(until=START + timedelta(days=5))  # the run continues where it stopped

    assert [e.event_type for e in events] == [EventType.CAPITAL_CONTRIBUTED, EventType.SESSION_ATTENDED]
    assert engine.calendar.local_date(events[1].occurred_at) == date(2025, 10, 6)  # Monday


def test_scheduling_in_the_past_is_an_error(engine):
    engine.run(until=START + timedelta(days=5))

    with pytest.raises(ValueError, match="in the past"):
        engine.schedule(engine.calendar.to_utc(START, time(9, 0)), lambda when: None)


def test_repeated_events_get_distinct_but_reproducible_ids(engine):
    engine.run(until=START)
    when = engine.calendar.to_utc(START, time(10, 0))
    first = engine.emit(EventType.SESSION_RESCHEDULED, "scheduling", "ses_1", when)
    second = engine.emit(EventType.SESSION_RESCHEDULED, "scheduling", "ses_1", when)

    other = Engine(load_config())
    other.run(until=START)
    again = other.emit(EventType.SESSION_RESCHEDULED, "scheduling", "ses_1", when)

    assert first.event_id != second.event_id
    assert first.event_id == again.event_id


def test_two_runs_with_the_same_config_are_identical():
    first = Engine(load_config()).run(until=date(2025, 10, 31))
    second = Engine(load_config()).run(until=date(2025, 10, 31))

    assert [e.to_dict() for e in first] == [e.to_dict() for e in second]
