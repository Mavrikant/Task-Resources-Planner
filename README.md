# Lab Equipment Weekly Scheduler

A desktop tool that builds a tight one-week schedule for shared lab
equipment. The constraint-programming engine (Google OR-Tools CP-SAT)
minimises the schedule's total span, packs each team's work tightly,
respects per-team unavailable hours, and prefers each team's
self-declared favourite hours. The result is shown as a Gantt chart in
a tkinter GUI.

## Features

- **One-week horizon** — 7 days × 24 one-hour slots = 168 slots.
- **Resource pool** — VSG×3, VSGRS×1, OBB×1, IFF×2, IFR×1, 1553×2,
  RFCU×2, ADF T×1, Fırın×2, CT94×1, OSC×1, AA×2 (19 physical units).
  Counts can be edited per project.
- **Per-team configuration**
  - List of tasks (resource type + hours + *allow split* flag).
  - 7×24 click-grid for **preferred** (green) and **unavailable** (red) hours.
- **Optimisation objective**
  `100·makespan + 5·gap_penalty − 1·preferred_hits`, so:
  1. The schedule is as short as possible.
  2. Each team's tasks are packed tightly (small gaps between them).
  3. Tasks drift toward green hours when there is slack.
- **Hard constraints** — unavailable hours, per-unit no-overlap,
  per-team no-overlap (a team can only run one task at a time),
  optional task contiguity per task.
- **Save / load** projects as UTF-8 JSON.

## Requirements

- Python 3.11 or newer (3.14 is what we test on).
- The packages in `requirements.txt`: `ortools`, `matplotlib`, `pytest`.

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

A pre-built sample is included — open **File → Open…** and pick
`sample_project.json` to see five teams with 16 tasks already wired up.

## How to use

1. **Resources tab** — review or edit the unit count for each resource type.
2. **Teams tab**
   - Click **Add team** to create a team.
   - With a team selected on the left, edit its name, add/edit/delete its
     tasks, and click cells in the 7×24 grid to mark them
     *preferred* (green) or *unavailable* (red).
     Right-click clears a cell.
   - Each task has a checkbox **Allow split**. When ON the task can be
     spread across the week one hour at a time; when OFF the task must
     occupy contiguous hours on one physical unit.
3. **Click Solve schedule** — solver runs in a background thread and
   switches to the Schedule tab on success. On infeasibility you get a
   diagnostic dialog (e.g. *"Team Foo task #2 needs 25 h on OBB but
   only 20 h are available"*).
4. **Schedule tab** — Gantt chart. Y-axis = physical unit. X-axis = hour
   of the week with day separators. Pan/zoom with the matplotlib toolbar.

Use **File → Save** to write the project to JSON for later editing.

## Project layout

```
lab_planner/
  models.py            data classes + the default resource pool
  solver.py            CP-SAT formulation
  persistence.py       JSON save/load
  gui/
    main_window.py     App + Resources/Teams/Schedule tabs
    team_editor.py     team detail pane + 7×24 SlotGridWidget
    gantt_view.py      matplotlib Gantt embedded in tkinter
tests/                 unit tests for models, solver, persistence
main.py                entry point
sample_project.json    example with 5 teams, 16 tasks
```

## Run tests

```bash
pytest -q
```

The suite covers:

- model validation (slot range, resource pool, task hours);
- solver correctness (no-overlap, unavailable hours, preferred-bias, infeasibility,
  splittable tasks);
- JSON round-trip including non-ASCII names (Türkçe characters).

## Tuning notes

- Default solver budget is **20 seconds** with **8 search workers**.
  Realistic instances (≤ 50 tasks) typically reach OPTIMAL in under a
  second; longer-running solves return the best `FEASIBLE` solution
  found so far.
- Total weekly capacity = 19 units × 168 h = **3192 unit-hours**. If
  aggregate demand exceeds about 80 % of that, expect tighter
  schedules and longer solve times — relax unavailable hours or split
  long tasks to stay under that ceiling.

## Licence

Private project — no licence applied.
