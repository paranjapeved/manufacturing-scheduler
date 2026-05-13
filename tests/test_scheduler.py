from manufacturing_scheduler.data import Company, Items, Process, Worker
import json
import subprocess
import sys

from manufacturing_scheduler.scheduler import Scheduler
from manufacturing_scheduler.scheduler_input_data import SchedulerInputData, load_sample_data


def test_scheduler_assigns_workers_roughly_equally_across_processes():
    """Scheduler spreads workers across processes with at most one extra worker."""

    schedule = Scheduler(load_sample_data()).create_schedule()

    worker_counts = [len(assignments) for assignments in schedule.values()]

    assert sum(worker_counts) == 9
    assert max(worker_counts) - min(worker_counts) <= 1


def test_scheduler_prefers_highest_output_workers_for_processes():
    """Scheduler assigns specialists to the processes where they output the most."""

    input_data = SchedulerInputData(
        company=Company(shift_hours=8, hours_per_week=40),
        items=[Items(name="Widget", required_qty=10, processes=["Cutting", "Assembly"])],
        processes=[
            Process(name="Cutting", process_code="P1"),
            Process(name="Assembly", process_code="P2"),
        ],
        workers=[
            Worker(name="CuttingSpecialist", process_output_per_hour={"P1": 50, "P2": 1}),
            Worker(name="AssemblySpecialist", process_output_per_hour={"P1": 1, "P2": 40}),
        ],
    )

    schedule = Scheduler(input_data).create_schedule()

    assert schedule["Cutting"][0].worker_name == "CuttingSpecialist"
    assert schedule["Cutting"][0].process_output_per_hour == 50
    assert schedule["Assembly"][0].worker_name == "AssemblySpecialist"
    assert schedule["Assembly"][0].process_output_per_hour == 40


def test_scheduler_does_not_take_worker_from_their_best_process():
    """Scheduler skips a process's top worker when that worker is stronger elsewhere."""

    input_data = SchedulerInputData(
        company=Company(shift_hours=8, hours_per_week=40),
        items=[
            Items(
                name="Widget",
                required_qty=10,
                processes=["Cutting", "Assembly", "Polishing"],
            )
        ],
        processes=[
            Process(name="Cutting", process_code="P1"),
            Process(name="Assembly", process_code="P2"),
            Process(name="Polishing", process_code="P3"),
        ],
        workers=[
            Worker(name="AssemblyLead", process_output_per_hour={"P1": 99, "P2": 100, "P3": 0}),
            Worker(name="CuttingLead", process_output_per_hour={"P1": 80, "P2": 1, "P3": 0}),
            Worker(name="PolishingLead", process_output_per_hour={"P1": 0, "P2": 0, "P3": 50}),
        ],
    )

    schedule = Scheduler(input_data).create_schedule()

    assert schedule["Cutting"][0].worker_name == "CuttingLead"
    assert schedule["Assembly"][0].worker_name == "AssemblyLead"
    assert schedule["Polishing"][0].worker_name == "PolishingLead"


def test_scheduler_output_reports_whether_required_quantities_are_met():
    """Schedule output reports enough capacity when all required quantities can be met."""

    input_data = SchedulerInputData(
        company=Company(shift_hours=8, hours_per_week=40),
        items=[Items(name="Widget", required_qty=1000, processes=["Cutting", "Assembly"])],
        processes=[
            Process(name="Cutting", process_code="P1"),
            Process(name="Assembly", process_code="P2"),
        ],
        workers=[
            Worker(name="CuttingSpecialist", process_output_per_hour={"P1": 50, "P2": 1}),
            Worker(name="AssemblySpecialist", process_output_per_hour={"P1": 1, "P2": 40}),
        ],
    )

    output = Scheduler(input_data).create_schedule_output()

    assert output["is_enough"] is True
    assert output["items"] == [
        {
            "item_name": "Widget",
            "required_qty": 1000,
            "possible_qty": 1600,
            "is_enough": True,
            "process_capacities": {"Cutting": 2000, "Assembly": 1600},
            "missing_processes": [],
        }
    ]


def test_scheduler_output_reports_insufficient_required_quantities():
    """Schedule output reports insufficient capacity when production is below demand."""

    input_data = SchedulerInputData(
        company=Company(shift_hours=8, hours_per_week=40),
        items=[Items(name="Widget", required_qty=2000, processes=["Cutting", "Assembly"])],
        processes=[
            Process(name="Cutting", process_code="P1"),
            Process(name="Assembly", process_code="P2"),
        ],
        workers=[
            Worker(name="CuttingSpecialist", process_output_per_hour={"P1": 50, "P2": 1}),
            Worker(name="AssemblySpecialist", process_output_per_hour={"P1": 1, "P2": 40}),
        ],
    )

    output = Scheduler(input_data).create_schedule_output()

    assert output["is_enough"] is False
    assert output["items"][0]["possible_qty"] == 1600
    assert output["items"][0]["is_enough"] is False


def test_package_can_run_as_module():
    """Package entry point prints JSON output with schedule and item feasibility data."""

    result = subprocess.run(
        [sys.executable, "-m", "manufacturing_scheduler"],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)

    assert "schedule" in output
    assert output["items"][0]["item_name"] == "Sampler"
    assert "is_enough" in output
