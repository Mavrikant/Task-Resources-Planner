"""CP-SAT formulation of the weekly lab schedule.

Tasks are scheduled directly. Each task locks a multiset of physical
resource units. By default the task occupies `hours` contiguous hours;
a `work_hours_only` task is restricted to Mon-Fri 08-18; a task that
also has `continue_next_day` may pause overnight and resume at the
start of the next work-day's window (work-hours space). The model
minimises the makespan and softly prefers slots the task marked green;
slots marked red for a task forbid that task from occupying them.
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
    work_hour_slots,
)


_MAKESPAN_W = 10_000  # dominating: shortest schedule wins
_PREF_W = 100         # secondary: prefer green slots strongly
_PRIORITY_W = 1       # tertiary tie-break: high-priority tasks pull earlier


def _effective_unavailable(task: Task) -> set[int]:
    """Union of the task's own unavailable slots and (if work_hours_only) every off-hour slot.

    NOTE: for `continue_next_day` tasks the off-hours are *not* added here —
    work-hour-only is enforced by construction (chunks live in work-hour space)
    and so unavailable_slots is the only blocker.
    """
    blocked = set(task.unavailable_slots)
    if task.work_hours_only and not task.continue_next_day:
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
        if task.continue_next_day and task.work_hours_only:
            # Hours measured in work-hours space (50 work-hours per week).
            wh = len([s for s in work_hour_slots()
                      if s not in task.unavailable_slots])
            if task.hours > wh:
                return (f"Task #{ti} {task.name!r}: needs {task.hours}h "
                        f"but only {wh}h of work-hours are available "
                        f"after unavailable slots are removed.")
        else:
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


def _build_contiguous(model, ti: int, task: Task,
                       unit_vars: dict, horizon: int):
    """Single-interval task. Returns task-record dict or None if no legal placement."""
    d = task.hours
    latest_end = task.deadline if task.deadline is not None else horizon
    if d > latest_end:
        return None

    start = model.NewIntVar(0, latest_end - d, f"t{ti}_start")
    end = model.NewIntVar(d, latest_end, f"t{ti}_end")
    model.Add(end == start + d)

    per_unit_iv = {}
    for uid, v in unit_vars.items():
        per_unit_iv[uid] = model.NewOptionalIntervalVar(
            start, d, end, v, f"t{ti}_iv_u{uid}",
        )

    blocked = _effective_unavailable(task)
    if blocked:
        allowed = [v for v in range(latest_end - d + 1)
                   if all((v + i) not in blocked for i in range(d))]
        if not allowed:
            return None
        model.AddAllowedAssignments([start], [(v,) for v in allowed])

    chunks = [{"start": start, "end": end, "per_unit_iv": per_unit_iv}]
    return {
        "task_idx": ti, "task": task,
        "task_start": start, "task_end": end,
        "unit_vars": unit_vars, "chunks": chunks,
    }


def _build_workhours_split(model, ti: int, task: Task,
                            unit_vars: dict, horizon: int):
    """Multi-chunk task aligned to consecutive work-hours-of-week. Returns task-record or None."""
    d = task.hours
    latest_end = task.deadline if task.deadline is not None else horizon

    whs = work_hour_slots()
    n_w = len(whs)
    if d > n_w:
        return None

    unavail = task.unavailable_slots
    allowed_starts_w = []
    for w in range(n_w - d + 1):
        if any(whs[w + i] in unavail for i in range(d)):
            continue
        if whs[w + d - 1] + 1 > latest_end:
            continue
        allowed_starts_w.append(w)
    if not allowed_starts_w:
        return None

    start_w = model.NewIntVar(allowed_starts_w[0], allowed_starts_w[-1],
                               f"t{ti}_start_w")
    model.AddAllowedAssignments([start_w], [(w,) for w in allowed_starts_w])

    chunks = []
    for c in range(d):
        chunk_slot = model.NewIntVar(0, horizon - 1, f"t{ti}_c{c}_slot")
        chunk_end = model.NewIntVar(1, horizon, f"t{ti}_c{c}_end")
        # idx = start_w + c, then chunk_slot = whs[idx]
        idx = model.NewIntVar(c, n_w - d + c, f"t{ti}_c{c}_idx")
        model.Add(idx == start_w + c)
        model.AddElement(idx, whs, chunk_slot)
        model.Add(chunk_end == chunk_slot + 1)

        per_unit_iv = {}
        for uid, v in unit_vars.items():
            per_unit_iv[uid] = model.NewOptionalIntervalVar(
                chunk_slot, 1, chunk_end, v,
                f"t{ti}_c{c}_u{uid}_iv",
            )
        chunks.append({"start": chunk_slot, "end": chunk_end,
                        "per_unit_iv": per_unit_iv})

    return {
        "task_idx": ti, "task": task,
        "task_start": chunks[0]["start"],
        "task_end": chunks[-1]["end"],
        "unit_vars": unit_vars, "chunks": chunks,
    }


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
        unit_vars: dict[int, "cp_model.IntVar"] = {}
        for res_name, qty in task.requirements.items():
            choices = units_by_type.get(res_name, [])
            type_vars = {}
            for uid in choices:
                v = model.NewBoolVar(f"t{ti}_u{uid}")
                unit_vars[uid] = v
                type_vars[uid] = v
            model.Add(sum(type_vars.values()) == qty)

        if task.continue_next_day and task.work_hours_only:
            tr = _build_workhours_split(model, ti, task, unit_vars, horizon)
        else:
            tr = _build_contiguous(model, ti, task, unit_vars, horizon)

        if tr is None:
            return ScheduleResult(
                status_name="INFEASIBLE", feasible=False, makespan=None,
                solve_time_s=0.0, assignments=[],
                diagnostic=_infeasibility_hint(tasks, resources),
            )
        task_records.append(tr)

    # Per-physical-unit no-overlap (collected from chunks).
    for uid, _, _ in units:
        intervals = []
        for tr in task_records:
            for ch in tr["chunks"]:
                if uid in ch["per_unit_iv"]:
                    intervals.append(ch["per_unit_iv"][uid])
        if intervals:
            model.AddNoOverlap(intervals)

    # Objective.
    all_ends = [tr["task_end"] for tr in task_records]
    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, all_ends)

    pref_terms = _build_preferred_terms(model, task_records)
    if pref_terms:
        total_pref = model.NewIntVar(0, len(pref_terms), "total_pref")
        model.Add(total_pref == sum(pref_terms))
    else:
        total_pref = model.NewConstant(0)

    n = len(task_records)
    priority_term = sum(
        (n - tr["task_idx"]) * tr["task_start"] for tr in task_records
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
            chosen_uids = [uid for uid, var in tr["unit_vars"].items()
                           if solver.Value(var) == 1]
            first = tr["chunks"][0]
            chunk_dur = int(solver.Value(first["end"])) - int(solver.Value(first["start"]))
            chunk_starts = sorted(int(solver.Value(ch["start"]))
                                   for ch in tr["chunks"])
            runs = _coalesce_runs(chunk_starts, chunk_dur)
            for uid in chosen_uids:
                res_name = next(name for u, name, _ in units if u == uid)
                for s, e in runs:
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


def _coalesce_runs(chunk_starts: list[int], chunk_dur: int) -> list[tuple[int, int]]:
    """Group consecutive chunks into (start, end) runs."""
    runs: list[tuple[int, int]] = []
    cur_s = cur_e = None
    for s in chunk_starts:
        if cur_s is None:
            cur_s, cur_e = s, s + chunk_dur
        elif s == cur_e:
            cur_e = s + chunk_dur
        else:
            runs.append((cur_s, cur_e))
            cur_s, cur_e = s, s + chunk_dur
    if cur_s is not None:
        runs.append((cur_s, cur_e))
    return runs


# --- helpers --------------------------------------------------------------

def _build_preferred_terms(model, task_records) -> list:
    """For each task and each preferred slot, count chunks that cover it."""
    pref_terms = []
    for tr in task_records:
        task = tr["task"]
        if not task.preferred_slots:
            continue
        for v in task.preferred_slots:
            for ch_idx, ch in enumerate(tr["chunks"]):
                cov = model.NewBoolVar(
                    f"t{tr['task_idx']}_c{ch_idx}_cov_{v}"
                )
                # cov  iff  ch.start <= v  AND  ch.end > v
                model.Add(ch["start"] <= v).OnlyEnforceIf(cov)
                model.Add(ch["end"] > v).OnlyEnforceIf(cov)
                lo_bad = model.NewBoolVar(
                    f"t{tr['task_idx']}_c{ch_idx}_lo_{v}"
                )
                hi_bad = model.NewBoolVar(
                    f"t{tr['task_idx']}_c{ch_idx}_hi_{v}"
                )
                model.Add(ch["start"] > v).OnlyEnforceIf(lo_bad)
                model.Add(ch["start"] <= v).OnlyEnforceIf(lo_bad.Not())
                model.Add(ch["end"] <= v).OnlyEnforceIf(hi_bad)
                model.Add(ch["end"] > v).OnlyEnforceIf(hi_bad.Not())
                model.AddBoolOr([lo_bad, hi_bad]).OnlyEnforceIf(cov.Not())
                pref_terms.append(cov)
    return pref_terms


def _infeasibility_hint(tasks: list[Task], resources: list[Resource]) -> str:
    res_units = {r.name: r.units for r in resources}
    hints: list[str] = []
    for ti, task in enumerate(tasks):
        if task.continue_next_day and task.work_hours_only:
            wh = len([s for s in work_hour_slots()
                      if s not in task.unavailable_slots])
            if task.hours > wh:
                hints.append(
                    f"Task #{ti} {task.name!r} needs {task.hours}h of "
                    f"work-hours but only {wh}h are available."
                )
        else:
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
