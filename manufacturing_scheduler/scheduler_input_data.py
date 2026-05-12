"""Manufacturing worker-to-machine scheduling backend.

The scheduler converts weekly item requirements into required machine hours,
then assigns qualified workers to those machine types while respecting:

* worker weekly hour limits
* physical machine availability
* binary worker-machine skills

The output is intentionally backend-friendly plain Python data that can be
returned from an API, serialized as JSON, or written to a database.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
from math import ceil
from pathlib import Path
from typing import Any

import yaml

from .data import Company, Items, Process, Worker


DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "input.json"
DEFAULT_DATA: dict[str, Any] = json.loads(DEFAULT_DATA_PATH.read_text())
SAMPLE_DATA_PATH = Path(__file__).resolve().parent / "data" / "sample_data.yaml"


@dataclass(frozen=True)
class SchedulerInputData:
    """Structured scheduler input loaded from YAML."""

    company: Company
    items: list[Items]
    processes: list[Process]
    workers: list[Worker]


def load_sample_data(path: str | Path = SAMPLE_DATA_PATH) -> SchedulerInputData:
    """Load sample YAML data into scheduler data classes."""

    with Path(path).open() as data_file:
        raw_data = yaml.safe_load(data_file)

    if not isinstance(raw_data, dict):
        raise ValueError("Sample data must be a YAML mapping")

    company_config = raw_data.get("Company", {})

    return SchedulerInputData(
        company=Company(
            shift_hours=company_config["shift_hours"],
            hours_per_week=company_config["hours_per_week"],
        ),
        items=[
            Items(
                name=item["name"],
                required_qty=item["required_qty"],
                processes=item["processes"],
            )
            for item in raw_data.get("Items", [])
        ],
        processes=[
            Process(
                name=process["name"],
                process_code=process["process_code"],
            )
            for process in raw_data.get("Processes", [])
        ],
        workers=[
            Worker(
                name=worker["name"],
                process_output_per_hour=_process_output_per_hour_to_dict(worker["process_output_per_hour"]),
            )
            for worker in raw_data.get("Workers", [])
        ],
    )


def _process_output_per_hour_to_dict(process_output_per_hour: list[dict[str, int]]) -> dict[str, int]:
    return {
        process_code: output
        for process_output_per_hour in process_output_per_hour
        for process_code, output in process_output_per_hour.items()
    }

