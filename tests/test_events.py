import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from simulator.events import Event, EventType, deterministic_id, write_jsonl

OCCURRED = datetime(2026, 8, 29, 18, 0, tzinfo=UTC)


def _event(**overrides) -> Event:
    fields = {
        "event_id": "ev_test",
        "event_type": EventType.SESSION_NO_SHOW,
        "source": "scheduling",
        "subject_id": "ses_1",
        "occurred_at": OCCURRED,
        "recorded_at": OCCURRED,
    }
    return Event(**(fields | overrides))


def test_deterministic_id_is_stable_and_distinct():
    assert deterministic_id("ev", "a") == deterministic_id("ev", "a")
    assert deterministic_id("ev", "a") != deterministic_id("ev", "b")
    assert deterministic_id("ev", "a").startswith("ev_")


def test_an_event_can_be_recorded_later_than_it_occurred():
    # The policy example: a no-show on 29 August recorded by the advisor on 10 September
    event = _event(recorded_at=datetime(2026, 9, 10, 15, 0, tzinfo=UTC))

    assert event.recorded_at - event.occurred_at > timedelta(days=11)


def test_an_event_cannot_be_recorded_before_it_occurred():
    with pytest.raises(ValueError, match="recorded before it occurs"):
        _event(recorded_at=OCCURRED - timedelta(minutes=1))


@pytest.mark.parametrize(
    "timestamp",
    [datetime(2026, 8, 29, 18, 0), datetime(2026, 8, 29, 14, 0, tzinfo=timezone(timedelta(hours=-4)))],
    ids=["naive", "not UTC"],
)
def test_timestamps_must_be_utc(timestamp):
    with pytest.raises(ValueError, match="must be a UTC timestamp"):
        _event(occurred_at=timestamp, recorded_at=timestamp)


def test_write_jsonl(tmp_path):
    path = tmp_path / "simulation" / "events.jsonl"

    count = write_jsonl([_event(payload={"amount": 16_500})], path)

    lines = path.read_text().splitlines()
    assert count == 1
    assert json.loads(lines[0]) == {
        "event_id": "ev_test",
        "event_type": "session_no_show",
        "source": "scheduling",
        "subject_id": "ses_1",
        "occurred_at": "2026-08-29T18:00:00Z",
        "recorded_at": "2026-08-29T18:00:00Z",
        "payload": {"amount": 16_500},
    }


def test_timestamps_must_be_whole_seconds():
    with pytest.raises(ValueError, match="whole second"):
        _event(occurred_at=OCCURRED.replace(microsecond=5), recorded_at=OCCURRED.replace(microsecond=5))
