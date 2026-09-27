"""Demand: how many new customers arrive in a period."""

import math
import random
from datetime import date

from simulator.config import DemandConfig


def months_since(start: date, day: date) -> int:
    """Whole calendar months from the start month to the day's month (0 in the first month)."""
    return (day.year - start.year) * 12 + day.month - start.month


def demand_level(demand: DemandConfig, start: date, day: date) -> float:
    """Share of full demand the Company has reached: a linear ramp-up, then steady monthly growth."""
    month = months_since(start, day)
    if month < demand.ramp_up_months:
        return demand.ramp_start_level + (1 - demand.ramp_start_level) * month / demand.ramp_up_months
    return (1 + demand.monthly_growth_after_ramp) ** (month - demand.ramp_up_months)


def poisson(rng: random.Random, mean: float) -> int:
    """Random number of arrivals when `mean` arrivals are expected (Knuth's method, for small means).

    Arrivals of independent customers follow a Poisson distribution: on a day with 2 expected
    bookings there may be 0, 1, 2, 5... but 2 on average.
    """
    if not 0 <= mean <= 30:
        raise ValueError(f"mean must be between 0 and 30, got {mean}")
    limit = math.exp(-mean)
    count, product = 0, rng.random()
    while product > limit:
        count += 1
        product *= rng.random()
    return count
