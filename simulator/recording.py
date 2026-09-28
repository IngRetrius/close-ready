"""When the scheduling system learns what happened to a session.

Advisors record attendance and no-shows themselves: usually on the day of the session, sometimes days
later (config: recording_delays). A late record can arrive after its month has closed, which exercises
the late-entry rule (accounting policy, section 6). Every other event is recorded the moment it occurs.
"""

from datetime import datetime, timedelta

from simulator.engine import Engine

SESSION_LENGTH = timedelta(hours=4)
# Advisors record within 4 hours of the time the session ends, so a same-day record never crosses midnight
RECORDING_WINDOW = timedelta(hours=4)


def outcome_recorded_at(engine: Engine, session_id: str, session_start: datetime) -> datetime:
    """When the advisor records whether the session was attended or a no-show."""
    rng = engine.random.stream("recording", session_id)
    delays = engine.config.recording_delays
    delay = rng.choices(delays, weights=[d.share for d in delays])[0]
    days = rng.randint(delay.days.min, delay.days.max)
    seconds = rng.randrange(int(RECORDING_WINDOW.total_seconds()))
    return session_start + SESSION_LENGTH + timedelta(days=days, seconds=seconds)
