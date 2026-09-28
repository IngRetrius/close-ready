"""A summary of a simulated history, compared with the estimates in docs/simulation.md.

If a volume differs from its estimate, either the parameters or the estimate are adjusted, and the
reason is documented in docs/simulation.md.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from simulator.business_calendar import add_months
from simulator.engine import Engine
from simulator.events import Event, EventType

# An approximate figure ("about 470") is met within this relative margin
TOLERANCE = 0.15
RECORDED_BY_ADVISORS = (EventType.SESSION_ATTENDED, EventType.SESSION_NO_SHOW)


@dataclass(frozen=True)
class Estimate:
    label: str
    low: float
    high: float
    unit: str = ""


def _about(value: float, unit: str = "") -> Estimate:
    return Estimate(f"~{value:g}{unit}", value * (1 - TOLERANCE), value * (1 + TOLERANCE), unit)


# docs/simulation.md, "Expected volumes, first 12 months"
DOCUMENTED = {
    "Individual customers": _about(470),
    "Individual bookings": _about(600),
    "Companies": _about(24),
    "Corporate packs": _about(31),
    "Card charges": _about(650),
    "Disputes": Estimate("2–3", 2, 3),
    "Utilization, first month": _about(7, "%"),
    "Utilization, twelfth month": _about(75, "%"),
}


@dataclass(frozen=True)
class Check:
    metric: str
    documented: Estimate
    simulated: int

    @property
    def ok(self) -> bool:
        return self.documented.low <= self.simulated <= self.documented.high


def first_year_checks(engine: Engine) -> list[Check]:
    """The first 12 months of the history against the documented estimates."""
    start = engine.config.run.start_date
    end = add_months(start, 12) - timedelta(days=1)
    events = [e for e in engine.events if start <= engine.calendar.local_date(e.occurred_at) <= end]
    count = Counter(e.event_type for e in events)
    new_customers = Counter(e.payload["segment"] for e in events if e.event_type == EventType.CUSTOMER_CREATED)
    utilization = engine.capacity.utilization

    simulated = {
        "Individual customers": new_customers["individual"],
        "Individual bookings": count[EventType.BOOKING_PAID],
        "Companies": new_customers["company"],
        "Corporate packs": count[EventType.PACK_INVOICED],
        # Every card payment attempt creates a Stripe charge, including the declined ones
        "Card charges": count[EventType.BOOKING_PAID] + count[EventType.CHECKOUT_DECLINED] + count[EventType.INVOICE_PAID],
        "Disputes": count[EventType.DISPUTE_OPENED],
        "Utilization, first month": round(100 * utilization(start, add_months(start, 1) - timedelta(days=1))),
        "Utilization, twelfth month": round(100 * utilization(add_months(start, 11), end)),
    }
    return [Check(metric, DOCUMENTED[metric], value) for metric, value in simulated.items()]


def recorded_after_close(engine: Engine, event: Event) -> bool:
    """Whether the event's source system recorded it after the event's month had closed."""
    calendar = engine.calendar
    closed_on = calendar.close_date(calendar.local_date(event.occurred_at), engine.config.company.close_business_day)
    return calendar.local_date(event.recorded_at) > closed_on


def report(engine: Engine, until: date) -> str:
    start = engine.config.run.start_date
    events = engine.events
    lines = [f"Simulated history: {start} to {until} (seed {engine.config.run.seed})", ""]

    if until >= add_months(start, 12) - timedelta(days=1):
        lines += ["First 12 months against docs/simulation.md", f"  {'Metric':32}{'Documented':>12}{'Simulated':>12}"]
        for check in first_year_checks(engine):
            status = "ok" if check.ok else "CHECK"
            simulated = f"{check.simulated:,}{check.documented.unit}"
            lines.append(f"  {check.metric:32}{check.documented.label:>12}{simulated:>12}   {status}")
    else:
        lines.append("The run is shorter than 12 months: no comparison with docs/simulation.md.")

    count = Counter(e.event_type for e in events)
    lines += ["", f"Events: {len(events):,}"]
    lines += [f"  {event_type.value:32}{count[event_type]:>12,}" for event_type in EventType if count[event_type]]

    outcomes = [e for e in events if e.event_type in RECORDED_BY_ADVISORS]
    late = [e for e in outcomes if engine.calendar.local_date(e.recorded_at) > engine.calendar.local_date(e.occurred_at)]
    after_close = [e for e in late if recorded_after_close(engine, e)]
    lines += [
        "",
        f"Session outcomes recorded on a later day: {len(late):,} of {len(outcomes):,}; "
        f"after their month closed: {len(after_close):,}",
    ]
    return "\n".join(lines)
