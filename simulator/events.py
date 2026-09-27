"""Business events: the simulator's output, before it is translated into Stripe objects or API calls.

Every event carries two timestamps (bitemporal model, accounting policy section 6):
- occurred_at: when it happened in the business;
- recorded_at: when the source system learned about it.
"""

import json
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

Source = Literal["stripe", "scheduling", "bank"]

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/IngRetrius/close-ready")


def deterministic_id(prefix: str, key: str) -> str:
    """Same prefix and key, same ID, on every run (UUID5 is a hash of its name)."""
    return f"{prefix}_{uuid.uuid5(_NAMESPACE, f'{prefix}:{key}').hex[:24]}"


class EventType(StrEnum):
    """The simulator's vocabulary. Comments give the posting rule each event feeds (accounting policy)."""

    CAPITAL_CONTRIBUTED = "capital_contributed"        # rule 16
    CUSTOMER_CREATED = "customer_created"              # no entry
    SALE_LOST = "sale_lost"                            # no entry: no free slot within max_wait_days
    CHECKOUT_DECLINED = "checkout_declined"            # no entry: failed card payment
    BOOKING_PAID = "booking_paid"                      # rule 1
    SESSION_BOOKED = "session_booked"                  # no entry
    SESSION_RESCHEDULED = "session_rescheduled"        # no entry, but can move revenue to another month
    SESSION_ATTENDED = "session_attended"              # rules 2 and 8
    SESSION_NO_SHOW = "session_no_show"                # rule 3
    SESSION_CANCELLED = "session_cancelled"            # rule 3 if late; otherwise a refund follows
    REFUND_ISSUED = "refund_issued"                    # rules 4 and 5
    DISPUTE_OPENED = "dispute_opened"                  # rule 12
    DISPUTE_WON = "dispute_won"                        # rule 13
    DISPUTE_LOST = "dispute_lost"                      # no new entry: the loss was booked when opened
    PACK_INVOICED = "pack_invoiced"                    # rule 6
    INVOICE_PAID = "invoice_paid"                      # rule 7
    INVOICE_UNCOLLECTIBLE = "invoice_uncollectible"    # rule 10
    PACK_EXPIRED = "pack_expired"                      # rule 9


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: EventType
    source: Source
    subject_id: str  # the business object the event is about: a customer, booking, session, pack...
    occurred_at: datetime
    recorded_at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("occurred_at", "recorded_at"):
            value = getattr(self, name)
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must be a UTC timestamp")
            if value.microsecond:
                raise ValueError(f"{name} must be a whole second, like Stripe timestamps")
        if self.recorded_at < self.occurred_at:
            raise ValueError("an event cannot be recorded before it occurs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "subject_id": self.subject_id,
            "occurred_at": _iso(self.occurred_at),
            "recorded_at": _iso(self.recorded_at),
            "payload": dict(self.payload),
        }


def _iso(value: datetime | date) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat()


def write_jsonl(events: Iterable[Event], path: Path) -> int:
    """Write events as JSON Lines (one event per line); returns how many were written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event.to_dict(), default=_iso) + "\n")
            count += 1
    return count
