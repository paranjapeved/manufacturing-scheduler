# Manufacturing Scheduler 
This project cane be used as a starting point for any manufacturing companies
to create a schedule for workers based on their skill level, number of items to be
produced in a week, different types of machines available, etc. It is useful
to understand gaps in the manufacturing process such as need for additional
workers, more machines, skill building in the workforce, etc.

Note: This is a hobby project and would need additional tweaking and testing 
to make it production ready

## What It Models

- Items with a weekly requirement and production rate.
- Machine types with a count of physical machines.
- Workers with binary skills for operating machine types.
- Weekly worker-hour and machine-hour capacity.

The scheduler first converts item demand into required machine hours:

```text
required hours = weekly requirement / items produced per hour
```

It then uses a max-flow allocator to assign qualified workers to machines. This
maximizes scheduled production hours under the current constraints.

## Run The Example

```bash
python -m manufacturing_scheduler
```

The packaged example uses the seed data from the prompt and assumes a
single-shift setup:

- `40` available hours per worker per week
- `40` available hours per physical machine per week

Those assumptions make the provided demand infeasible, so the output includes
the best possible schedule plus a shortage report. For the seed data, the
single-shift setup needs `570` machine/worker-hours but only `350` hours can be
assigned with the current skill and machine constraints.

## Use As A Library

```python
from manufacturing_scheduler import DEFAULT_DATA, ScheduleConfig, build_schedule

result = build_schedule(
    DEFAULT_DATA,
    ScheduleConfig(worker_hours_per_week=40, machine_hours_per_week=40),
)

print(result.as_dict())
```

Important result fields:

- `is_feasible`: whether the full production quota was scheduled.
- `assignments`: worker-to-machine schedule.
- `item_output`: expected output from the schedule.
- `unassigned_machine_hours`: remaining machine-hours by machine type.
- `shortage_report`: additional workers, hours, qualified coverage, and machines
  required.

Set `raise_on_infeasible=True` if a strict API caller should receive an
`InfeasibleScheduleError`. The exception includes the partial result.

## Tests

```bash
python -m pytest -q
```
