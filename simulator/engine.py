"""The simulation engine: advances day by day and collects the business events.

Flows (individuals, companies...) plug into the engine. Each day the engine:
1. lets every flow create that day's new activity (e.g., new bookings);
2. runs the actions scheduled for that day (e.g., a session that takes place today).
Actions can emit events and schedule further actions.
"""

import heapq
import itertools
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol

from simulator.business_calendar import BusinessCalendar
from simulator.capacity import Capacity
from simulator.config import SimulatorConfig
from simulator.events import Event, EventType, Source, deterministic_id
from simulator.randomness import RandomStreams

Action = Callable[[datetime], None]

CAPITAL_CONTRIBUTION_TIME = time(9, 0)


class Flow(Protocol):
    def on_day(self, day: date) -> None: ...


@dataclass(order=True)
class _ScheduledAction:
    when: datetime
    order: int  # tie-breaker: actions due at the same instant run in the order they were scheduled
    action: Action = field(compare=False)


class Engine:
    def __init__(self, config: SimulatorConfig) -> None:
        self.config = config
        self.calendar = BusinessCalendar.from_config(config)
        self.capacity = Capacity(self.calendar, config.company)
        self.random = RandomStreams(config.run.seed)
        self.flows: list[Flow] = []
        self.today: date | None = None
        self._events: list[Event] = []
        self._queue: list[_ScheduledAction] = []
        self._order = itertools.count()
        self._occurrences: Counter[tuple[str, str]] = Counter()
        self._next_day = config.run.start_date

    @property
    def events(self) -> list[Event]:
        """All events so far, in the order they occurred."""
        return sorted(self._events, key=lambda e: (e.occurred_at, e.event_id))

    def run(self, until: date) -> list[Event]:
        """Simulate every day up to `until` (included). Can be called again to continue."""
        while self._next_day <= until:
            self.today = self._next_day
            if self.today == self.config.run.start_date:
                self._contribute_capital()
            for flow in self.flows:
                flow.on_day(self.today)
            self._run_actions_due(self.today)
            self._next_day += timedelta(days=1)
        return self.events

    def schedule(self, when: datetime, action: Action) -> None:
        """Run `action(when)` on the day `when` falls on, in the Company's timezone."""
        if self.today is not None and self.calendar.local_date(when) < self.today:
            raise ValueError(f"cannot schedule an action in the past ({when})")
        heapq.heappush(self._queue, _ScheduledAction(when, next(self._order), action))

    def emit(
        self,
        event_type: EventType,
        source: Source,
        subject_id: str,
        occurred_at: datetime,
        payload: Mapping[str, Any] | None = None,
        recorded_at: datetime | None = None,
    ) -> Event:
        """Record a business event. Its ID depends only on its type, subject and occurrence number."""
        occurrence = self._occurrences[(event_type, subject_id)]
        self._occurrences[(event_type, subject_id)] += 1
        event = Event(
            event_id=deterministic_id("ev", f"{event_type}|{subject_id}|{occurrence}"),
            event_type=event_type,
            source=source,
            subject_id=subject_id,
            occurred_at=occurred_at,
            recorded_at=recorded_at or occurred_at,
            payload=payload or {},
        )
        self._events.append(event)
        return event

    def _run_actions_due(self, day: date) -> None:
        while self._queue and self.calendar.local_date(self._queue[0].when) <= day:
            scheduled = heapq.heappop(self._queue)
            scheduled.action(scheduled.when)

    def _contribute_capital(self) -> None:
        """The owner funds the Company's bank account on its first day (accounting policy, rule 16)."""
        self.emit(
            EventType.CAPITAL_CONTRIBUTED,
            source="bank",
            subject_id="company",
            occurred_at=self.calendar.to_utc(self.config.run.start_date, CAPITAL_CONTRIBUTION_TIME),
            payload={"amount": self.config.company.opening_bank_balance_usd, "currency": "usd"},
        )
