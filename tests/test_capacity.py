from collections import Counter
from datetime import date, time

import pytest

from simulator.business_calendar import BusinessCalendar
from simulator.capacity import Capacity, Slot
from simulator.config import load_config

BOOKED_ON = date(2026, 9, 1)
TUESDAY = date(2026, 9, 8)


@pytest.fixture
def capacity() -> Capacity:
    config = load_config()
    return Capacity(BusinessCalendar.from_config(config), config.company)


def test_three_advisors_with_two_sessions_give_six_slots_a_day(capacity):
    assert capacity.slots_per_day == 6


def test_a_full_day_spreads_sessions_across_advisors(capacity):
    slots = [capacity.book(BOOKED_ON, TUESDAY) for _ in range(6)]

    assert all(slot.day == TUESDAY for slot in slots)
    assert Counter(slot.advisor for slot in slots) == {"adv_01": 2, "adv_02": 2, "adv_03": 2}


def test_when_the_day_is_full_the_session_moves_to_the_next_business_day(capacity):
    for _ in range(6):
        capacity.book(BOOKED_ON, TUESDAY)

    assert capacity.book(BOOKED_ON, TUESDAY) == Slot(date(2026, 9, 9), time(9, 0), "adv_01")


def test_a_holiday_is_skipped(capacity):
    slot = capacity.book(BOOKED_ON, date(2026, 9, 7))  # Labor Day

    assert slot.day == TUESDAY


def test_no_free_slot_within_the_wait_limit_is_a_lost_sale(capacity):
    # From 2 to 22 September (21 days after booking) there are 14 business days: 84 slots
    booked = 0
    while capacity.book(BOOKED_ON, date(2026, 9, 2)) is not None:
        booked += 1

    assert booked == 84


def test_a_released_slot_can_be_booked_again(capacity):
    slots = [capacity.book(BOOKED_ON, TUESDAY) for _ in range(6)]
    capacity.release(slots[3])

    assert capacity.book(BOOKED_ON, TUESDAY) == slots[3]


def test_utilization(capacity):
    for _ in range(3):
        capacity.book(BOOKED_ON, TUESDAY)

    assert capacity.utilization(TUESDAY, TUESDAY) == 0.5
    assert capacity.utilization(date(2026, 9, 12), date(2026, 9, 13)) == 0.0  # weekend: no slots


def test_a_session_cannot_be_booked_for_the_same_day(capacity):
    with pytest.raises(ValueError):
        capacity.book(TUESDAY, TUESDAY)
