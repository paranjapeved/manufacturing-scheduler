import pytest

from manufacturing_scheduler import DEFAULT_DATA, InfeasibleScheduleError, ScheduleConfig, build_schedule


def test_single_shift_capacity_returns_best_possible_schedule_and_shortages():
    result = build_schedule(
        DEFAULT_DATA,
        ScheduleConfig(worker_hours_per_week=40, machine_hours_per_week=40),
    )

    assert result.is_feasible is False
    assert sum(result.machine_hours_used.values()) == 350.0
    assert result.shortage_report["additional_worker_hours_lower_bound"] == 210.0
    assert result.shortage_report["additional_workers_lower_bound"] == 6
    assert result.shortage_report["additional_worker_hours_to_complete_quota"] == 220.0
    assert result.shortage_report["additional_workers_to_complete_quota_lower_bound"] == 6
    assert result.shortage_report["additional_machines_by_type"] == {"Machine4": 2}
    assert result.shortage_report["qualified_worker_hour_shortage_by_machine"] == {
        "Machine2": 80.0
    }
    assert result.unassigned_machine_hours


def test_schedule_meets_item_throughput_when_capacity_is_available():
    result = build_schedule(
        DEFAULT_DATA,
        ScheduleConfig(worker_hours_per_week=80, machine_hours_per_week=168),
    )

    assert result.item_output == {
        "Item1": 10000.0,
        "Item2": 20000.0,
        "Item3": 15000.0,
        "Item4": 12000.0,
    }
    assert result.machine_hours_used == {
        "Machine1": 100.0,
        "Machine2": 200.0,
        "Machine3": 150.0,
        "Machine4": 120.0,
    }
    assert result.unassigned_machine_hours == {}
    assert result.shortage_report["additional_workers_lower_bound"] == 0
    assert result.shortage_report["additional_machines_by_type"] == {}


def test_worker_assignments_respect_skills_and_weekly_hours():
    config = ScheduleConfig(worker_hours_per_week=80, machine_hours_per_week=168)
    result = build_schedule(DEFAULT_DATA, config)
    worker_skills = {
        worker: set(skills) for worker, skills in DEFAULT_DATA["Workers"].items()
    }

    for assignment in result.assignments:
        assert assignment.machine in worker_skills[assignment.worker]

    assert max(result.worker_hours_used.values()) <= config.worker_hours_per_week


def test_can_still_raise_with_partial_result_for_strict_callers():
    with pytest.raises(InfeasibleScheduleError) as exc_info:
        build_schedule(
            DEFAULT_DATA,
            ScheduleConfig(worker_hours_per_week=40, machine_hours_per_week=40),
            raise_on_infeasible=True,
        )

    assert exc_info.value.partial_result is not None
    assert exc_info.value.partial_result.is_feasible is False
