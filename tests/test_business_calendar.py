from datetime import UTC, date, datetime, time

import pytest

from simulator.business_calendar import BusinessCalendar
from simulator.config import load_config


@pytest.fixture(scope="module")
def calendar() -> BusinessCalendar:
    return BusinessCalendar.from_config(load_config())


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 8), True),    # an ordinary Tuesday
        (date(2026, 9, 12), False),  # Saturday
        (date(2026, 9, 7), False),   # Labor Day
        (date(2026, 7, 3), False),   # Independence Day (4 July) falls on a Saturday: observed on Friday
        (date(2026, 6, 19), False),  # Juneteenth
    ],
)
def test_is_business_day(calendar, day, expected):
    assert calendar.is_business_day(day) is expected


def test_holiday_name(calendar):
    assert calendar.holiday_name(date(2026, 9, 7)) == "Labor Day"
    assert calendar.holiday_name(date(2026, 9, 8)) is None


@pytest.mark.parametrize(
    ("year", "month", "n", "expected"),
    [
        (2026, 9, 5, date(2026, 9, 8)),  # Labor Day pushes the fifth business day to 8 September
        (2026, 1, 5, date(2026, 1, 8)),  # 1 January is a holiday
        (2026, 9, 1, date(2026, 9, 1)),
    ],
)
def test_nth_business_day(calendar, year, month, n, expected):
    assert calendar.nth_business_day(year, month, n) == expected


def test_nth_business_day_beyond_the_month_is_an_error(calendar):
    with pytest.raises(ValueError):
        calendar.nth_business_day(2026, 9, 25)


def test_add_business_days_skips_weekends_and_holidays(calendar):
    friday = date(2026, 9, 4)
    assert calendar.add_business_days(friday, 2) == date(2026, 9, 9)  # skips the weekend and Labor Day
    assert calendar.add_business_days(friday, 0) == friday


def test_to_utc_follows_daylight_saving_time(calendar):
    # New York moves to daylight saving time on 8 March 2026
    assert calendar.to_utc(date(2026, 3, 6), time(9, 0)) == datetime(2026, 3, 6, 14, 0, tzinfo=UTC)
    assert calendar.to_utc(date(2026, 3, 9), time(9, 0)) == datetime(2026, 3, 9, 13, 0, tzinfo=UTC)


def test_local_date_assigns_late_evening_payments_to_the_local_day(calendar):
    # 22:00 on 31 March in New York is already 1 April in UTC; it is a March event
    assert calendar.local_date(datetime(2026, 4, 1, 2, 0, tzinfo=UTC)) == date(2026, 3, 31)


def test_local_date_rejects_naive_timestamps(calendar):
    with pytest.raises(ValueError):
        calendar.local_date(datetime(2026, 4, 1, 2, 0))
