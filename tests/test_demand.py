import random
from datetime import date

import pytest

from simulator.config import load_config
from simulator.demand import demand_level, months_since, poisson

START = date(2025, 10, 1)


def test_months_since():
    assert months_since(START, date(2025, 10, 31)) == 0
    assert months_since(START, date(2026, 1, 1)) == 3


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2025, 10, 15), 0.30),    # first month: 30% of full demand
        (date(2026, 1, 15), 0.65),     # halfway through the 6-month ramp-up
        (date(2026, 4, 15), 1.00),     # full demand
        (date(2026, 5, 15), 1.03),     # then 3% growth a month
        (date(2026, 6, 15), 1.0609),
    ],
)
def test_demand_level(day, expected):
    assert demand_level(load_config().demand, START, day) == pytest.approx(expected)


def test_poisson_averages_its_mean():
    rng = random.Random(1)
    draws = [poisson(rng, 2.0) for _ in range(20_000)]

    assert sum(draws) / len(draws) == pytest.approx(2.0, abs=0.05)
    assert min(draws) == 0


def test_poisson_rejects_a_negative_mean():
    with pytest.raises(ValueError):
        poisson(random.Random(1), -1)
