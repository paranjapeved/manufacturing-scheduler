"""Worker data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Worker:
    """Manufacturing worker with process-specific skill levels."""

    process_output_per_hour: dict[str, int]
    name: str
