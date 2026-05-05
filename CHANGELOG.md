# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- App icon — bundled at `assets/icon.png`, applied to the window via
  `iconphoto` and (on macOS) the Dock via PyObjC/AppKit. On Windows the
  multi-resolution `assets/icon.ico` drives the title bar and taskbar
  via `iconbitmap`, and a `SetCurrentProcessExplicitAppUserModelID` call
  before the first window is realised replaces Python's default taskbar
  identity so the taskbar groups under the app's own icon.
- Default equipment pool grown to 25 types / 48 units — adds generic
  bench gear (Power Supply, Bench Multimeter, Function/Spectrum/Network/
  Logic Analyzers, Frequency Counter, Soldering Station, DC Electronic
  Load, Workstation PC, Microscope, LCR Meter, Calibration Kit) on top
  of the original avionics-specific testers.
- Sample project grown to 32 tasks — adds 10 tasks exercising the
  generic bench gear (PCB rework, DC characterization, logic analyzer
  capture, S-parameter sweep, frequency stability soak, component-level
  inspection, firmware regression, calibration verification, LCR
  characterization, soldering qualification).
- `Task.continue_next_day`: when paired with `work_hours_only`, long tasks
  may span multiple consecutive work-day windows (e.g. 18 h becomes Mon
  08-18 + Tue 08-16 with the equipment released overnight). Solver
  models this in work-hour-index space using `AddElement`.
- `Task.deadline` (1..168): hard end-by constraint enforced by the solver,
  with a friendly day-and-hour picker on the task editor.
- Drag-to-reorder priority list: drag rows in the Tasks tab; the row at
  the top has the highest priority and is pulled toward earlier starts.
  New `#` and `Deadline` columns reflect this.
- Equipment pool persistence: `equipment_pool.json` at the project root
  + `Add` / `Edit` / `Delete` and `Import pool…` / `Export pool…` on the
  Resources tab. Renaming equipment cascades to every task that
  references it.
- Drag-to-paint slot grid: left-drag = unavailable, right-drag =
  preferred, middle-drag = clear.
- Help → About dialog with version + tooling info.
- Hour-of-day labels every 6 hours on the Gantt with bold day
  separators.
- Duplicate-task button on the Tasks tab (deep copy, auto-numbered name).
- Work-hours model (Mon-Fri 08-18) — `Task.work_hours_only` plus visual
  shading on both the slot grid and the Gantt.
- Sample project (`sample_project.json`) showcasing the feature set.

### Changed
- **Breaking** — Schema bumped to v2: tasks are top-level (no more
  Teams). Each task carries its own slot grid and a multi-resource
  requirements dict (e.g. `{VSG: 2, OBB: 1}`). Files written under v1
  are explicitly rejected on load.
- Solver objective is now lexicographic: `10000·makespan +
  100·preferred_misses + 1·priority_weighted_starts`.
- Renamed product to **Task-Resources Planner** (was *Lab Equipment
  Weekly Scheduler*). Version is shown in the window title.

### Fixed
- `plan.json` (user data) was inadvertently committed once and is now
  gitignored.

## [0.1.0] — initial scaffold (2026-05-04)

- Project skeleton, OR-Tools + matplotlib + pytest dependencies.
- CP-SAT solver, JSON persistence, tkinter GUI with three tabs
  (Resources / Tasks / Schedule), matplotlib Gantt embedded in tk.

[Unreleased]: https://github.com/Mavrikant/Task-Resources-Planner/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Mavrikant/Task-Resources-Planner/releases/tag/v0.1.0
