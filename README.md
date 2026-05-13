# Manufacturing Scheduler 
This project can be used as a starting point for any manufacturing companies
to create a schedule for workers based on their skill level, number of items to be
produced in a week, different types of machines available, etc. It is useful
to understand gaps in the manufacturing process such as need for additional
workers, more machines, skill building in the workforce, etc.

Note: This is a hobby project and would need additional tweaking and testing 
to make it production ready

## What It Models

- Items with a weekly requirement and production rate.
- Processes: each item production consists of a number of processes.
- Workers who each have an process_output_per_hour, it is the number of process instances completed by them in an hour
- Weekly company hours and shift hours per day


## Run The Example

```bash
python -m manufacturing_scheduler
```


## Tests

```bash
python -m pytest -q
```


## V1
IT1 - Only sampler (12 people - 6 sampler, 6 random)
Machine + Process - Induction, paper tube
Worker skill (6 people) - glass tube cutting, ejection, assembly, head and tube fixing
Item - required qty

Max people per process will be hardcoded
User inputs reqd qty per SKU (item)
Code should output raw materials qty required
Input who is not available