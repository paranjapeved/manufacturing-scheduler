"""Worker-to-process scheduler."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import heapq
import json
from pathlib import Path
from typing import Any

from .scheduler_input_data import SchedulerInputData, load_sample_data


@dataclass(frozen=True)
class WorkerProcessAssignment:
    """Assignment of one worker to one manufacturing process."""

    worker_name: str
    process_name: str
    process_code: str
    process_output_per_hour: int


@dataclass(frozen=True)
class ItemProductionCheck:
    """Whether the schedule can manufacture the required quantity for one item."""

    item_name: str
    required_qty: int
    possible_qty: int
    is_enough: bool
    process_capacities: dict[str, int]
    missing_processes: list[str]


class Scheduler:
    """Create balanced worker assignments based on process output ratings."""

    def __init__(self, input_data: SchedulerInputData):
        """Store the structured company, item, process, and worker input data."""

        self.input_data = input_data

    def create_schedule(self) -> dict[str, list[WorkerProcessAssignment]]:
        """Assign each worker to a process while keeping process counts balanced."""

        def assign_worker(
            worker_name: str,
            process_name: str,
            process_code: str,
            output_per_hour: int,
        ) -> None:
            """Add one worker assignment to the schedule and mark the worker assigned."""

            schedule[process_name].append(
                WorkerProcessAssignment(
                    worker_name=worker_name,
                    process_name=process_name,
                    process_code=process_code,
                    process_output_per_hour=output_per_hour,
                )
            )
            unassigned_worker_names.remove(worker_name)

        def top_worker_for_process(
            process_name: str,
        ) -> tuple[int, str, str, str] | None:
            """Return the best unassigned worker option for a process, if any."""

            worker_heap = best_workers_for_process_sorted[process_name]

            while worker_heap and worker_heap[0][1] not in unassigned_worker_names:
                heapq.heappop(worker_heap)

            if not worker_heap:
                return None

            output_per_hour, worker_name, process_name, process_code = worker_heap[0]
            return -output_per_hour, worker_name, process_name, process_code

        def top_process_for_worker(worker_name: str) -> tuple[int, str, str] | None:
            """Return a worker's best process that still has an open slot, if any."""

            process_heap = best_process_for_worker[worker_name]

            while (
                process_heap
                and len(schedule[process_heap[0][1]]) >= process_slots[process_heap[0][1]]
            ):
                heapq.heappop(process_heap)

            if not process_heap:
                return None

            output_per_hour, process_name, process_code = process_heap[0]
            return -output_per_hour, process_name, process_code


        processes = self.input_data.processes
        workers = self.input_data.workers

        if not processes:
            raise ValueError("At least one process is required to create a schedule")
        if not workers:
            return {process.name: [] for process in processes}

        process_slots = self._target_worker_counts()
        schedule = {process.name: [] for process in processes}
        unassigned_worker_names = {worker.name for worker in workers}

        best_workers_for_process_sorted: dict[str, list[tuple[int, str, str, str]]] = {
            process.name: [] for process in processes
        }
        best_process_for_worker: dict[str, list[tuple[int, str, str]]] = {
            worker.name: [] for worker in workers
        }

        # Build max-heaps for both views of the same ratings: workers ranked by
        # process, and processes ranked by worker.
        for process in processes:
            for worker in workers:
                output_per_hour = worker.process_output_per_hour.get(process.process_code, 0)
                heapq.heappush(
                    best_workers_for_process_sorted[process.name],
                    (-output_per_hour, worker.name, process.name, process.process_code),
                )
                heapq.heappush(
                    best_process_for_worker[worker.name],
                    (-output_per_hour, process.name, process.process_code),
                )

        # First assign only mutual best matches so a process does not take a
        # worker whose strongest available fit is somewhere else.
        for process in processes:
            if len(schedule[process.name]) >= process_slots[process.name]:
                continue

            worker_option = top_worker_for_process(process.name)
            if worker_option is None:
                continue

            output_per_hour, worker_name, process_name, process_code = worker_option
            worker_top_process = top_process_for_worker(worker_name)
            if worker_top_process is None:
                continue

            _, best_process_name, _ = worker_top_process
            if best_process_name == process_name:
                assign_worker(worker_name, process_name, process_code, output_per_hour)

        # Fill the remaining slots one process at a time, preserving round-robin
        # fairness while still choosing each process's best available worker.
        while unassigned_worker_names:
            assigned_this_round = False

            for process in processes:
                if not unassigned_worker_names:
                    break
                if len(schedule[process.name]) >= process_slots[process.name]:
                    continue

                worker_option = top_worker_for_process(process.name)
                if worker_option is None:
                    continue

                output_per_hour, worker_name, process_name, process_code = worker_option
                assign_worker(worker_name, process_name, process_code, output_per_hour)
                assigned_this_round = True

            if not assigned_this_round:
                break

        return schedule

    def check_required_quantities(
        self,
        schedule: dict[str, list[WorkerProcessAssignment]],
    ) -> list[ItemProductionCheck]:
        """Check whether a schedule can satisfy each item's required quantity."""

        hours_per_week = self.input_data.company.hours_per_week
        item_checks: list[ItemProductionCheck] = []

        for item in self.input_data.items:
            process_capacities = {
                process_name: sum(
                    assignment.process_output_per_hour * hours_per_week
                    for assignment in schedule.get(process_name, [])
                )
                for process_name in item.processes
            }
            missing_processes = [
                process_name
                for process_name in item.processes
                if process_name not in schedule or not schedule[process_name]
            ]
            possible_qty = min(process_capacities.values(), default=0)

            item_checks.append(
                ItemProductionCheck(
                    item_name=item.name,
                    required_qty=item.required_qty,
                    possible_qty=possible_qty,
                    is_enough=possible_qty >= item.required_qty and not missing_processes,
                    process_capacities=process_capacities,
                    missing_processes=missing_processes,
                )
            )

        return item_checks

    def create_schedule_output(self) -> dict[str, Any]:
        """Create a schedule plus required-quantity feasibility output."""

        schedule = self.create_schedule()
        item_checks = self.check_required_quantities(schedule)

        return {
            "schedule": {
                process_name: [
                    {
                        "worker_name": assignment.worker_name,
                        "process_name": assignment.process_name,
                        "process_code": assignment.process_code,
                        "process_output_per_hour": assignment.process_output_per_hour,
                    }
                    for assignment in assignments
                ]
                for process_name, assignments in schedule.items()
            },
            "items": [
                {
                    "item_name": check.item_name,
                    "required_qty": check.required_qty,
                    "possible_qty": check.possible_qty,
                    "is_enough": check.is_enough,
                    "process_capacities": check.process_capacities,
                    "missing_processes": check.missing_processes,
                }
                for check in item_checks
            ],
            "is_enough": all(check.is_enough for check in item_checks),
        }

    def _target_worker_counts(self) -> dict[str, int]:
        """Calculate the balanced number of worker slots available per process."""

        process_count = len(self.input_data.processes)
        worker_count = len(self.input_data.workers)
        workers_per_process, extra_workers = divmod(worker_count, process_count)

        return {
            process.name: workers_per_process + (index < extra_workers)
            for index, process in enumerate(self.input_data.processes)
        }


def main() -> None:
    """Run the scheduler from the command line."""

    parser = argparse.ArgumentParser(description="Create a manufacturing worker schedule.")
    parser.add_argument(
        "data_path",
        nargs="?",
        type=Path,
        help="Optional path to a scheduler YAML input file.",
    )
    args = parser.parse_args()

    input_data = load_sample_data(args.data_path) if args.data_path else load_sample_data()
    output = Scheduler(input_data).create_schedule_output()

    print(json.dumps(output, indent=2))
