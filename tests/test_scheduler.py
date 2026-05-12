from manufacturing_scheduler.data import Company, Items, Process, Worker
import json
import subprocess
import sys

from manufacturing_scheduler.scheduler import Scheduler
from manufacturing_scheduler.scheduler_input_data import SchedulerInputData, load_sample_data


def test_scheduler_assigns_workers_roughly_equally_across_processes():
    schedule = Scheduler(load_sample_data()).create_schedule()

    worker_counts = [len(assignments) for assignments in schedule.values()]

    assert sum(worker_counts) == 9
    assert max(worker_counts) - min(worker_counts) <= 1


def test_scheduler_prefers_highest_output_workers_for_processes():
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


def test_scheduler_output_reports_whether_required_quantities_are_met():
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
