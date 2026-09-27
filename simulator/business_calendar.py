"""Business days, holidays and time zones for the simulated Company.

Timestamps are stored in UTC. Business dates — the day of a session, the month an event belongs to,
the close date — follow the Company's timezone (accounting policy, section 6).
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import holidays

from simulator.config import SimulatorConfig


class BusinessCalendar:
    def __init__(self, timezone: str, country: str = "US") -> None:
        self.tz = ZoneInfo(timezone)
        # Federal holidays, including the weekday a weekend holiday is observed on
        self._holidays = holidays.country_holidays(country)

    @classmethod
    def from_config(cls, config: SimulatorConfig) -> "BusinessCalendar":
        return cls(config.run.timezone, config.company.holiday_calendar)

    def holiday_name(self, day: date) -> str | None:
        return self._holidays.get(day)

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self._holidays

    def business_days(self, start: date, end: date) -> Iterator[date]:
        """Business days from start to end, both included."""
        day = start
        while day <= end:
            if self.is_business_day(day):
                yield day
            day += timedelta(days=1)

    def add_business_days(self, day: date, count: int) -> date:
        """The date `count` business days after `day` (e.g., when Stripe funds become available)."""
        if count < 0:
            raise ValueError("count must not be negative")
        while count > 0:
            day += timedelta(days=1)
            if self.is_business_day(day):
                count -= 1
        return day

    def nth_business_day(self, year: int, month: int, n: int) -> date:
        """The n-th business day of a month (the close date is the 5th of the following month)."""
        if n < 1:
            raise ValueError("n must be at least 1")
        first = date(year, month, 1)
        last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        for position, day in enumerate(self.business_days(first, last), start=1):
            if position == n:
                return day
        raise ValueError(f"{year}-{month:02d} has fewer than {n} business days")

    def to_utc(self, day: date, at: time) -> datetime:
        """A local date and time of the Company as a UTC timestamp (daylight saving time included)."""
        return datetime.combine(day, at, tzinfo=self.tz).astimezone(UTC)

    def local_date(self, timestamp: datetime) -> date:
        """The Company's business date for a timestamp, e.g. to assign an event to a month."""
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return timestamp.astimezone(self.tz).date()
