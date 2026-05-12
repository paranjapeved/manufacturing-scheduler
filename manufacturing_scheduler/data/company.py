"""Company data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    """Manufacturing company operating constraints."""

    shift_hours: int
    hours_per_week: int
