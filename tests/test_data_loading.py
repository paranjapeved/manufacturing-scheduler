import pytest

from manufacturing_scheduler.data import Company, Items, Process, Worker
from manufacturing_scheduler.scheduler_input_data import SchedulerInputData, load_sample_data


def test_load_sample_data_populates_dataclasses_from_default_yaml():
    data = load_sample_data()

    assert isinstance(data, SchedulerInputData)
    assert data.company == Company(shift_hours=8, hours_per_week=40)
    assert data.items == [
        Items(
            name="Sampler",
            required_qty=1000,
            processes=[
                "Glass tube cutting",
                "Ejection",
                "Assembly",
                "Head and tube fixing",
            ],
        )
    ]
    assert data.processes == [
        Process(name="Glass tube cutting", process_code="P1"),
        Process(name="Ejection", process_code="P2"),
        Process(name="Assembly", process_code="P3"),
        Process(name="Head and tube fixing", process_code="P4"),
    ]
    assert data.workers[0] == Worker(
        name="Worker1",
        process_output_per_hour={"P1": 20, "P2": 20, "P3": 20, "P4": 10},
    )
    assert len(data.workers) == 9


def test_load_sample_data_accepts_custom_yaml_path(tmp_path):
    yaml_path = tmp_path / "sample_data.yaml"
    yaml_path.write_text(
        """
Company:
  shift_hours: 6
  hours_per_week: 30
Items:
  - name: Widget
    required_qty: 25
    processes:
      - Cutting
      - Assembly
Processes:
  - name: Cutting
    process_code: P1
  - name: Assembly
    process_code: P2
Workers:
  - name: WorkerA
    process_output_per_hour:
      - P1: 4
      - P2: 2
"""
    )

    data = load_sample_data(yaml_path)

    assert data.company == Company(shift_hours=6, hours_per_week=30)
    assert data.items == [
        Items(name="Widget", required_qty=25, processes=["Cutting", "Assembly"])
    ]
    assert data.processes == [
        Process(name="Cutting", process_code="P1"),
        Process(name="Assembly", process_code="P2"),
    ]
    assert data.workers == [Worker(name="WorkerA", process_output_per_hour={"P1": 4, "P2": 2})]


def test_load_sample_data_rejects_non_mapping_yaml(tmp_path):
    yaml_path = tmp_path / "sample_data.yaml"
    yaml_path.write_text("- not-a-mapping\n")

    with pytest.raises(ValueError, match="Sample data must be a YAML mapping"):
        load_sample_data(yaml_path)
