"""Item data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Items:
    """Manufacturing item."""

    name: str
    required_qty: int
    processes: list[str]
