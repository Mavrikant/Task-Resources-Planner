# Task-Resources Planner

A desktop tool that builds a tight one-week schedule for shared lab
equipment. The constraint-programming engine (Google OR-Tools CP-SAT)
minimises total span, respects per-task unavailable hours, and prefers
slots each task marks as favourite. The result is shown as a Gantt
chart in a tkinter GUI.

## Features

- **Tasks are first-class.** Each task declares **multiple resource
  requirements at once** (e.g. *2× VSG + 1× OBB + 1× OSC*) and locks
  every required physical unit together for its duration.
- **Priority by list order.** The Tasks tab is a draggable priority
  list — the row at the top has the highest priority and is pulled
  toward earlier starts when otherwise tied with another task. Drag
  rows up or down to reorder.
- **Deadlines.** Each task can have an optional deadline — pick a
  day-of-week and an hour-of-day; the task's end-slot must fall at or
  before that point. Solver hard-fails (`INFEASIBLE`) if no schedule
  meets every deadline.
- **One-week horizon** — 7 days × 24 one-hour slots = 168 slots.
- **Equipment pool** — defined in `equipment_pool.json` at the project
  root (loaded on startup, fallback to a hardcoded list if missing).
  Default pool is VSG×3, VSGRS×1, OBB×1, IFF×2, IFR×1, 1553×2,
  RFCU×2, ADF T×1, Fırın×2, CT94×1, OSC×1, AA×2 (19 physical units).
  The Resources tab supports **Add / Edit / Delete** for individual
  equipment types and **Import pool / Export pool** to load or save
  whole pool files independently of project files.
- **Per-task slot grid.** A 7×24 click-to-cycle grid marks
  **preferred** (green) and **unavailable** (red) hours for the task.
  The grid background already shades **work hours** (Mon-Fri 08-18),
  **off-hours** (light grey), and **weekends** (darker grey) so you
  can see at a glance which slots are inside business time.
- **Work hours only.** Each task has a checkbox that, when on,
  restricts the task to Mon-Fri 08-18 — a hard constraint enforced by
  the solver. Off-hours-friendly tasks (e.g. ovens, long bake-outs)
  leave it off so they can run overnight or on weekends.
- **Optimisation objective**
  `10000·makespan + 100·preferred_misses + 1·priority_weighted_starts`,
  in lexicographic order:
  1. **Makespan** — the schedule is as short as possible.
  2. **Preferred slots** — tasks drift toward green hours when there is slack.
  3. **Priority** — among otherwise tied solutions, tasks higher in
     the list start earlier.
- **Hard constraints** — unavailable hours, per-unit no-overlap (a
  single physical unit serves one task at a time), task contiguity.
- **Save / load** projects as UTF-8 JSON (schema v2).

## Requirements

- Python 3.11 or newer (3.14 is what we test on).
- The packages in `requirements.txt`: `ortools`, `matplotlib`, `pytest`.

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

A pre-built sample is included — open **File → Open…** and pick
`sample_project.json` to see seven tasks already wired up. It solves
to `OPTIMAL` in well under a second.

## How to use

1. **Resources tab** — view the equipment pool. Click **Add…** to
   register a new equipment type, **Edit…** to rename or change the
   unit count, **Delete** to remove a type that no task uses, or
   **Import pool…** / **Export pool…** to load and save standalone
   equipment-pool JSON files.
2. **Tasks tab**
   - Click **Add task** to create a task. The new task starts with one
     unit of the first resource for one hour.
   - Select a task on the left and use the right pane to edit its
     name, hours, required-resources table (Add / Edit / Delete rows),
     and the 7×24 slot grid.
     Left-click in the grid cycles **None → Preferred (green) → Unavailable (red) → None**.
     Right-click clears.
   - The task list shows a one-line summary like
     `Radar integration  |  VSG×2 + OBB + OSC  |  4`.
3. **Click Solve schedule** — the solver runs in a background thread
   and switches to the Schedule tab on success. On infeasibility you
   get a diagnostic dialog (e.g. *"Task #2 needs 5× OBB but only 1
   exists"*).
4. **Schedule tab** — Gantt chart. Y-axis = physical unit. X-axis =
   hour of the week with day separators. **Off-hours and weekend
   columns are shaded in the background** so you can see at a glance
   which bars run during business time. Pan/zoom with the matplotlib
   toolbar.

Use **File → Save** to write the project to JSON for later editing.

## Project layout

```
lab_planner/
  models.py            data classes + the default resource pool
  solver.py            CP-SAT formulation
  persistence.py       JSON save/load (schema v2)
  gui/
    main_window.py     App + Resources/Tasks/Schedule tabs
    task_editor.py     task detail pane + 7×24 SlotGridWidget
    gantt_view.py      matplotlib Gantt embedded in tkinter
tests/                 unit tests for models, solver, persistence
main.py                entry point
sample_project.json    example with 7 multi-resource tasks
```

## Run tests

```bash
pytest -q
```

The 25 tests cover:

- model validation (slot range, resource pool, task hours, requirement quantities);
- solver correctness — single task, multi-unit (2× VSG), unit no-overlap,
  unavailable-hour blocking, preferred-window pull, infeasibility,
  unknown-resource and over-quantity diagnostics;
- JSON round-trip including non-ASCII names (Türkçe characters).

## Tuning notes

- Default solver budget is **20 seconds** with **8 search workers**.
  Realistic instances (≤ 30 tasks) typically reach `OPTIMAL` in well
  under a second; longer-running solves return the best `FEASIBLE`
  solution found so far.
- Total weekly capacity = 19 units × 168 h = **3192 unit-hours**. If
  aggregate demand exceeds about 80 % of that, expect tighter
  schedules and longer solve times — relax unavailable hours or
  reduce task hours.

## Licence

Private project — no licence applied.
