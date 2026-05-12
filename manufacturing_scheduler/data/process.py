"""Process data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Process:
    """Manufacturing process."""

    name: str
    process_code: str
