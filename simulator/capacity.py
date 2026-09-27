"""Advisor capacity: which session slots are free, and when a sale is lost for lack of them."""

from dataclasses import dataclass
from datetime import date, time, timedelta

from simulator.business_calendar import BusinessCalendar
from simulator.config import CompanyConfig


@dataclass(frozen=True, order=True)
class Slot:
    day: date
    start: time
    advisor: str


class Capacity:
    """Session slots of all advisors. Individuals and companies share the same capacity."""

    def __init__(self, calendar: BusinessCalendar, company: CompanyConfig) -> None:
        self._calendar = calendar
        self.advisors = [f"adv_{number:02d}" for number in range(1, company.advisors + 1)]
        self._start_times = sorted(company.session_start_times)
        self._max_wait = timedelta(days=company.max_wait_days)
        self._booked: set[Slot] = set()

    @property
    def slots_per_day(self) -> int:
        return len(self.advisors) * len(self._start_times)

    def book(self, booked_on: date, preferred_day: date) -> Slot | None:
        """Book the first free slot from the preferred day on; None if nothing is free in time (lost sale)."""
        if preferred_day <= booked_on:
            raise ValueError("a session must take place after the day it is booked")
        last_day = booked_on + self._max_wait
        day = preferred_day
        while day <= last_day:
            if self._calendar.is_business_day(day):
                slot = self._first_free_slot(day)
                if slot is not None:
                    self._booked.add(slot)
                    return slot
            day += timedelta(days=1)
        return None

    def release(self, slot: Slot) -> None:
        """Free a slot, when a session is cancelled in time or rescheduled."""
        self._booked.remove(slot)

    def utilization(self, start: date, end: date) -> float:
        """Share of the slots between two dates (both included) that are booked."""
        days = set(self._calendar.business_days(start, end))
        available = len(days) * self.slots_per_day
        booked = sum(1 for slot in self._booked if slot.day in days)
        return booked / available if available else 0.0

    def _first_free_slot(self, day: date) -> Slot | None:
        for start in self._start_times:
            free = [advisor for advisor in self.advisors if Slot(day, start, advisor) not in self._booked]
            if free:
                # Spread the work: the advisor with fewest sessions that day, then the lowest ID
                advisor = min(free, key=lambda a: (self._sessions_on(day, a), a))
                return Slot(day, start, advisor)
        return None

    def _sessions_on(self, day: date, advisor: str) -> int:
        return sum(1 for start in self._start_times if Slot(day, start, advisor) in self._booked)
