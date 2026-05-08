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
from math import ceil
from typing import Any


DEFAULT_DATA: dict[str, Any] = {
    "Items": {
        "Item1": {
            "Machine": "Machine1",
            "Weekly_requirement": 10000,
            "Items_produced_per_hour": 100,
        },
        "Item2": {
            "Machine": "Machine2",
            "Weekly_requirement": 20000,
            "Items_produced_per_hour": 100,
        },
        "Item3": {
            "Machine": "Machine3",
            "Weekly_requirement": 15000,
            "Items_produced_per_hour": 100,
        },
        "Item4": {
            "Machine": "Machine4",
            "Weekly_requirement": 12000,
            "Items_produced_per_hour": 100,
        },
    },
    "Machine_counts": {
        "Machine1": 3,
        "Machine2": 5,
        "Machine3": 4,
        "Machine4": 1,
    },
    "Workers": {
        "Worker1": ["Machine1", "Machine2"],
        "Worker2": ["Machine3", "Machine4"],
        "Worker3": ["Machine4"],
        "Worker4": ["Machine3"],
        "Worker5": ["Machine1", "Machine2"],
        "Worker6": ["Machine3", "Machine4"],
        "Worker7": ["Machine3"],
        "Worker8": ["Machine1", "Machine4"],
        "Worker9": ["Machine3", "Machine2"],
    },
}


@dataclass(frozen=True)
class ScheduleConfig:
    """Capacity knobs for a weekly schedule."""

    worker_hours_per_week: float = 40.0
    machine_hours_per_week: float = 168.0
    round_hours_to_int: bool = False


@dataclass(frozen=True)
class Assignment:
    worker: str
    machine: str
    item: str
    hours: float
    expected_output: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "machine": self.machine,
            "item": self.item,
            "hours": self.hours,
            "expected_output": self.expected_output,
        }


@dataclass(frozen=True)
class ScheduleResult:
    assignments: list[Assignment]
    required_machine_hours: dict[str, float]
    worker_hours_used: dict[str, float]
    machine_hours_used: dict[str, float]
    item_output: dict[str, float]
    is_feasible: bool
    shortage_report: dict[str, Any]
    unassigned_machine_hours: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "assignments": [assignment.as_dict() for assignment in self.assignments],
            "required_machine_hours": self.required_machine_hours,
            "worker_hours_used": self.worker_hours_used,
            "machine_hours_used": self.machine_hours_used,
            "item_output": self.item_output,
            "is_feasible": self.is_feasible,
            "shortage_report": self.shortage_report,
            "unassigned_machine_hours": self.unassigned_machine_hours,
            "warnings": self.warnings,
        }


class InfeasibleScheduleError(ValueError):
    """Raised when the provided demand cannot fit the configured capacity."""

    def __init__(self, reasons: list[str], partial_result: ScheduleResult | None = None):
        super().__init__("\n".join(reasons))
        self.reasons = reasons
        self.partial_result = partial_result


def build_schedule(
    data: dict[str, Any],
    config: ScheduleConfig | None = None,
    *,
    raise_on_infeasible: bool = False,
) -> ScheduleResult:
    """Build the best possible weekly schedule from item, machine, and worker data.

    If the full quota is impossible, the returned result still contains the
    optimal partial schedule by total assigned production hours, plus a shortage
    report. Set ``raise_on_infeasible=True`` to raise an exception after the
    partial result is built.
    """

    config = config or ScheduleConfig()
    _validate_data(data)

    items = data["Items"]
    machine_counts = data["Machine_counts"]
    workers = {worker: set(skills) for worker, skills in data["Workers"].items()}

    item_by_machine = _item_by_machine(items)
    required_machine_hours = _required_machine_hours(items, config.round_hours_to_int)
    worker_machine_hours = _max_worker_machine_hours(
        required_machine_hours=required_machine_hours,
        machine_counts=machine_counts,
        workers=workers,
        config=config,
    )
    assignments = _assignments_from_flow(
        worker_machine_hours=worker_machine_hours,
        items=items,
        item_by_machine=item_by_machine,
    )

    result = _build_result(
        assignments=assignments,
        items=items,
        required_machine_hours=required_machine_hours,
        machine_counts=machine_counts,
        workers=workers,
        config=config,
    )

    if not result.is_feasible and raise_on_infeasible:
        reasons = [
            f"{machine} still needs {hours} machine-hours."
            for machine, hours in result.unassigned_machine_hours.items()
        ]
        raise InfeasibleScheduleError(reasons, partial_result=result)

    return result


def _validate_data(data: dict[str, Any]) -> None:
    required_top_level = {"Items", "Machine_counts", "Workers"}
    missing = required_top_level - set(data)
    if missing:
        raise ValueError(f"Missing top-level keys: {sorted(missing)}")

    machines = set(data["Machine_counts"])
    for item_name, item in data["Items"].items():
        for key in ("Machine", "Weekly_requirement", "Items_produced_per_hour"):
            if key not in item:
                raise ValueError(f"{item_name} is missing {key}")
        if item["Machine"] not in machines:
            raise ValueError(f"{item_name} references unknown machine {item['Machine']}")
        if item["Weekly_requirement"] < 0:
            raise ValueError(f"{item_name} has a negative weekly requirement")
        if item["Items_produced_per_hour"] <= 0:
            raise ValueError(f"{item_name} must have a positive production rate")

    for machine, count in data["Machine_counts"].items():
        if count <= 0:
            raise ValueError(f"{machine} must have at least one physical machine")

    for worker, skills in data["Workers"].items():
        unknown_skills = set(skills) - machines
        if unknown_skills:
            raise ValueError(f"{worker} has unknown machine skills: {sorted(unknown_skills)}")


def _item_by_machine(items: dict[str, dict[str, Any]]) -> dict[str, str]:
    item_by_machine: dict[str, str] = {}
    for item_name, item in items.items():
        machine = item["Machine"]
        if machine in item_by_machine:
            raise ValueError(
                "This simple scheduler expects one item per machine. "
                f"{machine} is used by both {item_by_machine[machine]} and {item_name}."
            )
        item_by_machine[machine] = item_name
    return item_by_machine


def _required_machine_hours(
    items: dict[str, dict[str, Any]],
    round_hours_to_int: bool,
) -> dict[str, float]:
    required: dict[str, float] = {}
    for item in items.values():
        hours = item["Weekly_requirement"] / item["Items_produced_per_hour"]
        if round_hours_to_int:
            hours = float(ceil(hours))
        required[item["Machine"]] = round(float(hours), 4)
    return required


def _capacity_preflight(
    required_machine_hours: dict[str, float],
    machine_counts: dict[str, int],
    workers: dict[str, set[str]],
    config: ScheduleConfig,
) -> list[str]:
    errors: list[str] = []
    total_required = sum(required_machine_hours.values())
    total_worker_capacity = len(workers) * config.worker_hours_per_week

    if total_required > total_worker_capacity + 1e-9:
        errors.append(
            f"Total demand needs {total_required} worker-hours, but only "
            f"{total_worker_capacity} worker-hours are available."
        )

    for machine, required_hours in required_machine_hours.items():
        machine_capacity = machine_counts[machine] * config.machine_hours_per_week
        qualified_capacity = sum(
            config.worker_hours_per_week
            for skills in workers.values()
            if machine in skills
        )

        if required_hours > machine_capacity + 1e-9:
            errors.append(
                f"{machine} needs {required_hours} hours, but physical machine "
                f"capacity is {machine_capacity} hours."
            )
        if qualified_capacity <= 0:
            errors.append(f"{machine} has no qualified workers.")
        elif required_hours > qualified_capacity + 1e-9:
            errors.append(
                f"{machine} needs {required_hours} hours, but qualified workers "
                f"can cover only {qualified_capacity} hours."
            )

    return errors


class _FlowEdge:
    def __init__(self, to_node: str, reverse_index: int, capacity: float) -> None:
        self.to_node = to_node
        self.reverse_index = reverse_index
        self.capacity = capacity
        self.original_capacity = capacity


class _MaxFlow:
    def __init__(self) -> None:
        self.graph: dict[str, list[_FlowEdge]] = {}

    def add_edge(self, from_node: str, to_node: str, capacity: float) -> None:
        self.graph.setdefault(from_node, [])
        self.graph.setdefault(to_node, [])
        forward = _FlowEdge(to_node, len(self.graph[to_node]), capacity)
        backward = _FlowEdge(from_node, len(self.graph[from_node]), 0.0)
        self.graph[from_node].append(forward)
        self.graph[to_node].append(backward)

    def max_flow(self, source: str, sink: str) -> float:
        flow = 0.0
        while True:
            parent = self._find_path(source, sink)
            if sink not in parent:
                return round(flow, 4)

            path_capacity = float("inf")
            node = sink
            while node != source:
                previous, edge_index = parent[node]
                edge = self.graph[previous][edge_index]
                path_capacity = min(path_capacity, edge.capacity)
                node = previous

            node = sink
            while node != source:
                previous, edge_index = parent[node]
                edge = self.graph[previous][edge_index]
                reverse = self.graph[edge.to_node][edge.reverse_index]
                edge.capacity -= path_capacity
                reverse.capacity += path_capacity
                node = previous

            flow += path_capacity

    def _find_path(
        self,
        source: str,
        sink: str,
    ) -> dict[str, tuple[str, int]]:
        parent: dict[str, tuple[str, int]] = {}
        visited = {source}
        queue: deque[str] = deque([source])

        while queue:
            node = queue.popleft()
            for edge_index, edge in enumerate(self.graph[node]):
                if edge.to_node in visited or edge.capacity <= 1e-9:
                    continue
                visited.add(edge.to_node)
                parent[edge.to_node] = (node, edge_index)
                if edge.to_node == sink:
                    return parent
                queue.append(edge.to_node)

        return parent


def _max_worker_machine_hours(
    required_machine_hours: dict[str, float],
    machine_counts: dict[str, int],
    workers: dict[str, set[str]],
    config: ScheduleConfig,
) -> dict[tuple[str, str], float]:
    source = "__source__"
    sink = "__sink__"
    flow = _MaxFlow()
    worker_nodes = {worker: f"worker:{worker}" for worker in workers}
    machine_nodes = {machine: f"machine:{machine}" for machine in required_machine_hours}

    for worker, worker_node in worker_nodes.items():
        flow.add_edge(source, worker_node, float(config.worker_hours_per_week))
        for machine in sorted(workers[worker]):
            if machine not in required_machine_hours:
                continue
            machine_capacity = machine_counts[machine] * config.machine_hours_per_week
            flow.add_edge(worker_node, machine_nodes[machine], float(machine_capacity))

    for machine, machine_node in machine_nodes.items():
        usable_machine_hours = min(
            required_machine_hours[machine],
            machine_counts[machine] * config.machine_hours_per_week,
        )
        flow.add_edge(machine_node, sink, float(usable_machine_hours))

    flow.max_flow(source, sink)

    worker_machine_hours: dict[tuple[str, str], float] = {}
    reverse_worker_nodes = {node: worker for worker, node in worker_nodes.items()}
    reverse_machine_nodes = {node: machine for machine, node in machine_nodes.items()}

    for worker_node, worker in reverse_worker_nodes.items():
        for edge in flow.graph[worker_node]:
            machine = reverse_machine_nodes.get(edge.to_node)
            if machine is None:
                continue
            used = edge.original_capacity - edge.capacity
            if used > 1e-9:
                worker_machine_hours[(worker, machine)] = round(used, 4)

    return worker_machine_hours


def _assignments_from_flow(
    worker_machine_hours: dict[tuple[str, str], float],
    items: dict[str, dict[str, Any]],
    item_by_machine: dict[str, str],
) -> list[Assignment]:
    assignments: list[Assignment] = []
    for worker, machine in sorted(worker_machine_hours):
        hours = worker_machine_hours[(worker, machine)]
        item_name = item_by_machine[machine]
        item_rate = float(items[item_name]["Items_produced_per_hour"])
        assignments.append(
            Assignment(
                worker=worker,
                machine=machine,
                item=item_name,
                hours=hours,
                expected_output=round(hours * item_rate, 4),
            )
        )
    return assignments


def _build_result(
    assignments: list[Assignment],
    items: dict[str, dict[str, Any]],
    required_machine_hours: dict[str, float],
    machine_counts: dict[str, int],
    workers: dict[str, set[str]],
    config: ScheduleConfig,
) -> ScheduleResult:
    worker_hours_used = {worker: 0.0 for worker in workers}
    machine_hours_used = {machine: 0.0 for machine in required_machine_hours}
    item_output = {item_name: 0.0 for item_name in items}

    for assignment in assignments:
        worker_hours_used[assignment.worker] += assignment.hours
        machine_hours_used[assignment.machine] += assignment.hours
        item_output[assignment.item] += assignment.expected_output

    rounded_machine_hours_used = {
        machine: round(hours, 4) for machine, hours in machine_hours_used.items()
    }
    unassigned_machine_hours = {
        machine: round(required - rounded_machine_hours_used[machine], 4)
        for machine, required in required_machine_hours.items()
        if required - rounded_machine_hours_used[machine] > 1e-9
    }
    shortage_report = _shortage_report(
        items=items,
        required_machine_hours=required_machine_hours,
        machine_counts=machine_counts,
        workers=workers,
        config=config,
        unassigned_machine_hours=unassigned_machine_hours,
    )

    return ScheduleResult(
        assignments=assignments,
        required_machine_hours=required_machine_hours,
        worker_hours_used={
            worker: round(hours, 4) for worker, hours in worker_hours_used.items()
        },
        machine_hours_used=rounded_machine_hours_used,
        item_output={item: round(output, 4) for item, output in item_output.items()},
        is_feasible=not unassigned_machine_hours,
        shortage_report=shortage_report,
        unassigned_machine_hours=unassigned_machine_hours,
        warnings=shortage_report["warnings"],
    )


def _shortage_report(
    items: dict[str, dict[str, Any]],
    required_machine_hours: dict[str, float],
    machine_counts: dict[str, int],
    workers: dict[str, set[str]],
    config: ScheduleConfig,
    unassigned_machine_hours: dict[str, float],
) -> dict[str, Any]:
    additional_machines: dict[str, int] = {}
    physical_machine_hour_shortage: dict[str, float] = {}
    qualified_worker_hour_shortage: dict[str, float] = {}
    unmet_items: dict[str, float] = {}

    total_required_hours = round(sum(required_machine_hours.values()), 4)
    total_worker_capacity = round(len(workers) * config.worker_hours_per_week, 4)
    total_worker_hour_shortage = round(
        max(0.0, total_required_hours - total_worker_capacity),
        4,
    )
    additional_worker_hours_to_complete = round(
        sum(unassigned_machine_hours.values()),
        4,
    )

    for item_name, item in items.items():
        machine = item["Machine"]
        required_hours = required_machine_hours[machine]
        machine_capacity = machine_counts[machine] * config.machine_hours_per_week
        machine_shortage = max(0.0, required_hours - machine_capacity)
        if machine_shortage > 1e-9:
            physical_machine_hour_shortage[machine] = round(machine_shortage, 4)
            additional_machines[machine] = ceil(
                machine_shortage / config.machine_hours_per_week
            )

        qualified_capacity = sum(
            config.worker_hours_per_week
            for skills in workers.values()
            if machine in skills
        )
        qualified_shortage = max(0.0, required_hours - qualified_capacity)
        if qualified_shortage > 1e-9:
            qualified_worker_hour_shortage[machine] = round(qualified_shortage, 4)

        unmet_hours = unassigned_machine_hours.get(machine, 0.0)
        if unmet_hours > 1e-9:
            unmet_items[item_name] = round(
                unmet_hours * item["Items_produced_per_hour"],
                4,
            )

    warnings: list[str] = []
    if unassigned_machine_hours:
        warnings.append("Production quota is not fully achievable with current capacity.")
    if total_worker_hour_shortage > 0:
        warnings.append(
            f"At least {total_worker_hour_shortage} additional worker-hours are needed."
        )
    if additional_machines:
        warnings.append(
            "Additional physical machines are required for: "
            + ", ".join(
                f"{machine}={count}" for machine, count in sorted(additional_machines.items())
            )
        )
    if qualified_worker_hour_shortage:
        warnings.append(
            "Additional qualified worker-hours are required for: "
            + ", ".join(
                f"{machine}={hours}"
                for machine, hours in sorted(qualified_worker_hour_shortage.items())
            )
        )

    return {
        "total_required_worker_hours": total_required_hours,
        "total_available_worker_hours": total_worker_capacity,
        "additional_worker_hours_lower_bound": total_worker_hour_shortage,
        "additional_workers_lower_bound": (
            ceil(total_worker_hour_shortage / config.worker_hours_per_week)
            if total_worker_hour_shortage > 0
            else 0
        ),
        "additional_worker_hours_to_complete_quota": additional_worker_hours_to_complete,
        "additional_workers_to_complete_quota_lower_bound": (
            ceil(additional_worker_hours_to_complete / config.worker_hours_per_week)
            if additional_worker_hours_to_complete > 0
            else 0
        ),
        "additional_qualified_worker_hours_to_cover_unmet_by_machine": (
            unassigned_machine_hours
        ),
        "unassigned_machine_hours": unassigned_machine_hours,
        "unmet_items": unmet_items,
        "physical_machine_hour_shortage": physical_machine_hour_shortage,
        "additional_machines_by_type": additional_machines,
        "qualified_worker_hour_shortage_by_machine": qualified_worker_hour_shortage,
        "warnings": warnings,
    }


def main() -> None:
    import json

    try:
        schedule = build_schedule(
            DEFAULT_DATA,
            ScheduleConfig(worker_hours_per_week=40, machine_hours_per_week=40),
        )
    except InfeasibleScheduleError as exc:
        print("Schedule is infeasible:")
        print(json.dumps(exc.reasons, indent=2))
    else:
        print(json.dumps(schedule.as_dict(), indent=2))


if __name__ == "__main__":
    main()
