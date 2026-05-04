"""CP-SAT formulation of the weekly lab schedule.

Tasks are scheduled directly. Each task locks a multiset of physical
resource units for `hours` contiguous hours. The model minimises the
makespan and softly prefers slots the task marked green; slots marked
red for a task forbid that task from occupying them.
"""
from __future__ import annotations

import time

from ortools.sat.python import cp_model

from .models import (
    HORIZON,
    Assignment,
    Resource,
    ScheduleResult,
    Task,
    expand_units,
    non_work_slots,
)


_MAKESPAN_W = 10_000  # dominating: shortest schedule wins
_PREF_W = 100         # secondary: prefer green slots strongly
_PRIORITY_W = 1       # tertiary tie-break: high-priority tasks pull earlier


def _effective_unavailable(task: Task) -> set[int]:
    """Union of the task's own unavailable slots and (if work_hours_only) every off-hour slot."""
    blocked = set(task.unavailable_slots)
    if task.work_hours_only:
        blocked |= non_work_slots()
    return blocked


def _validate(tasks: list[Task], resources: list[Resource]) -> str | None:
    res_by_name = {r.name: r for r in resources}
    for ti, task in enumerate(tasks):
        for res_name, qty in task.requirements.items():
            if res_name not in res_by_name:
                return (f"Task #{ti} {task.name!r}: unknown resource "
                        f"{res_name!r}")
            if qty > res_by_name[res_name].units:
                return (f"Task #{ti} {task.name!r}: requires {qty} "
                        f"of {res_name} but pool only has "
                        f"{res_by_name[res_name].units}")
        blocked = _effective_unavailable(task)
        available = HORIZON - len(blocked)
        if task.hours > available:
            extra = " (work-hours-only)" if task.work_hours_only else ""
            return (f"Task #{ti} {task.name!r}: needs {task.hours}h "
                    f"but only {available}h are available"
                    f"{extra} after unavailable slots are removed.")
        if task.deadline is not None and task.deadline < task.hours:
            return (f"Task #{ti} {task.name!r}: deadline {task.deadline} "
                    f"is earlier than the required {task.hours}h.")
    return None


def build_and_solve(
    tasks: list[Task],
    resources: list[Resource],
    horizon: int = HORIZON,
    time_limit_s: float = 30.0,
    workers: int = 8,
) -> ScheduleResult:
    err = _validate(tasks, resources)
    if err:
        return ScheduleResult(
            status_name="INVALID", feasible=False, makespan=None,
            solve_time_s=0.0, assignments=[], diagnostic=err,
        )
    if not tasks:
        return ScheduleResult(
            status_name="OPTIMAL", feasible=True, makespan=0,
            solve_time_s=0.0, assignments=[], diagnostic="",
        )

    units = expand_units(resources)
    units_by_type: dict[str, list[int]] = {}
    for uid, name, _ in units:
        units_by_type.setdefault(name, []).append(uid)

    model = cp_model.CpModel()
    task_records: list[dict] = []

    for ti, task in enumerate(tasks):
        d = task.hours
        # If a deadline is set, the latest legal end is the deadline.
        latest_end = task.deadline if task.deadline is not None else horizon
        start = model.NewIntVar(0, latest_end - d, f"t{ti}_start")
        end = model.NewIntVar(d, latest_end, f"t{ti}_end")
        model.Add(end == start + d)

        # For each required resource type, pick exactly `qty` distinct units.
        unit_vars: dict[int, "cp_model.IntVar"] = {}
        per_unit_iv: dict[int, "cp_model.IntervalVar"] = {}
        for res_name, qty in task.requirements.items():
            choices = units_by_type.get(res_name, [])
            type_vars = {}
            for uid in choices:
                v = model.NewBoolVar(f"t{ti}_u{uid}")
                unit_vars[uid] = v
                type_vars[uid] = v
            model.Add(sum(type_vars.values()) == qty)

            # Optional interval per chosen unit; the unit's no-overlap pile
            # later collects these.
            for uid, v in type_vars.items():
                per_unit_iv[uid] = model.NewOptionalIntervalVar(
                    start, d, end, v, f"t{ti}_iv_u{uid}",
                )

        # Hard unavailable: any v ∈ [start, start+d) cannot be in blocked.
        blocked = _effective_unavailable(task)
        if blocked:
            allowed = [v for v in range(horizon - d + 1)
                       if all((v + i) not in blocked for i in range(d))]
            if not allowed:
                model.Add(start >= horizon)  # contradicts domain → infeasible
            else:
                model.AddAllowedAssignments([start], [(v,) for v in allowed])

        task_records.append({
            "task_idx": ti,
            "task": task,
            "start": start,
            "end": end,
            "unit_vars": unit_vars,
            "per_unit_iv": per_unit_iv,
        })

    # Per-physical-unit no-overlap.
    for uid, _, _ in units:
        intervals = [tr["per_unit_iv"][uid] for tr in task_records
                     if uid in tr["per_unit_iv"]]
        if intervals:
            model.AddNoOverlap(intervals)

    # Objective.
    all_ends = [tr["end"] for tr in task_records]
    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, all_ends)

    pref_terms = _build_preferred_terms(model, task_records)
    if pref_terms:
        total_pref = model.NewIntVar(0, len(pref_terms), "total_pref")
        model.Add(total_pref == sum(pref_terms))
    else:
        total_pref = model.NewConstant(0)

    # Priority objective: list-position determines weight (first task
    # = highest priority). Pulling high-priority tasks to early starts
    # is enforced by minimising sum(weight[t] * start[t]).
    n = len(task_records)
    priority_term = sum(
        (n - tr["task_idx"]) * tr["start"] for tr in task_records
    )

    model.Minimize(
        _MAKESPAN_W * makespan
        + _PRIORITY_W * priority_term
        - _PREF_W * total_pref
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_search_workers = int(workers)
    t0 = time.perf_counter()
    status = solver.Solve(model)
    elapsed = time.perf_counter() - t0

    status_name = solver.StatusName(status)
    feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    assignments: list[Assignment] = []
    makespan_value: int | None = None
    diagnostic = ""

    if feasible:
        makespan_value = int(solver.Value(makespan))
        for tr in task_records:
            s = int(solver.Value(tr["start"]))
            e = int(solver.Value(tr["end"]))
            for uid, var in tr["unit_vars"].items():
                if solver.Value(var) == 1:
                    res_name = next(name for u, name, _ in units if u == uid)
                    assignments.append(Assignment(
                        task_name=tr["task"].name,
                        task_index=tr["task_idx"],
                        resource_name=res_name,
                        unit_id=uid,
                        start_slot=s,
                        end_slot=e,
                    ))
        assignments.sort(key=lambda a: (a.start_slot, a.unit_id))
    else:
        diagnostic = _infeasibility_hint(tasks, resources)

    return ScheduleResult(
        status_name=status_name,
        feasible=feasible,
        makespan=makespan_value,
        solve_time_s=elapsed,
        assignments=assignments,
        diagnostic=diagnostic,
    )


# --- helpers --------------------------------------------------------------

def _build_preferred_terms(model, task_records) -> list:
    """For each task, count preferred slots that fall within [start, end)."""
    pref_terms = []
    for tr in task_records:
        task = tr["task"]
        if not task.preferred_slots:
            continue
        d = task.hours
        for v in task.preferred_slots:
            cov = model.NewBoolVar(f"t{tr['task_idx']}_cov_{v}")
            # cov  iff  start <= v  AND  end > v
            model.Add(tr["start"] <= v).OnlyEnforceIf(cov)
            model.Add(tr["end"] > v).OnlyEnforceIf(cov)
            lo_bad = model.NewBoolVar(f"t{tr['task_idx']}_lo_{v}")
            hi_bad = model.NewBoolVar(f"t{tr['task_idx']}_hi_{v}")
            model.Add(tr["start"] > v).OnlyEnforceIf(lo_bad)
            model.Add(tr["start"] <= v).OnlyEnforceIf(lo_bad.Not())
            model.Add(tr["end"] <= v).OnlyEnforceIf(hi_bad)
            model.Add(tr["end"] > v).OnlyEnforceIf(hi_bad.Not())
            model.AddBoolOr([lo_bad, hi_bad]).OnlyEnforceIf(cov.Not())
            pref_terms.append(cov)
    return pref_terms


def _infeasibility_hint(tasks: list[Task], resources: list[Resource]) -> str:
    res_units = {r.name: r.units for r in resources}
    hints: list[str] = []
    for ti, task in enumerate(tasks):
        blocked = _effective_unavailable(task)
        free = HORIZON - len(blocked)
        if task.hours > free:
            extra = " (work-hours-only)" if task.work_hours_only else ""
            hints.append(
                f"Task #{ti} {task.name!r} needs {task.hours}h "
                f"but only {free}h available{extra}."
            )
        if task.deadline is not None and task.deadline < task.hours:
            hints.append(
                f"Task #{ti} {task.name!r}: deadline {task.deadline}h "
                f"is shorter than the required {task.hours}h."
            )
        for res, qty in task.requirements.items():
            avail = res_units.get(res, 0)
            if avail == 0:
                hints.append(
                    f"Task #{ti} {task.name!r} needs {res} "
                    f"which is not in the pool."
                )
            elif qty > avail:
                hints.append(
                    f"Task #{ti} {task.name!r} needs {qty}× {res} "
                    f"but only {avail} units exist."
                )
    if not hints:
        # Capacity check per resource type.
        demand: dict[str, int] = {}
        for task in tasks:
            for res, qty in task.requirements.items():
                demand[res] = demand.get(res, 0) + qty * task.hours
        for name, hours in demand.items():
            cap = HORIZON * res_units.get(name, 0)
            if hours > cap:
                hints.append(
                    f"Total demand for {name} ({hours} unit-hours) "
                    f"exceeds weekly capacity ({cap})."
                )
    if not hints:
        return ("Constraints conflict in a non-obvious way; try relaxing "
                "unavailable slots or reducing task hours.")
    return " | ".join(hints)
