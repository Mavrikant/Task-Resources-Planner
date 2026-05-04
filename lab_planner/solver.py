"""CP-SAT formulation of the weekly lab schedule.

Given a list of `Team`s and a `Resource` pool, produce a `ScheduleResult`
that minimises makespan, packs each team's tasks tightly, and prefers
slots the team marked green while never using slots they marked red.
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
    Team,
    expand_units,
)


_MAKESPAN_W = 100   # dominating: shortest schedule wins
_GAP_W = 5          # secondary: pack each team
_PREF_W = 1         # tie-break: prefer green slots


def _validate(teams: list[Team], resources: list[Resource]) -> str | None:
    """Return None if valid, else an error message describing the first problem."""
    res_by_name = {r.name: r for r in resources}
    for team in teams:
        for ti, task in enumerate(team.tasks):
            if task.resource not in res_by_name:
                return f"Team {team.name!r} task #{ti}: unknown resource {task.resource!r}"
            available = HORIZON - len(team.unavailable_slots)
            if task.hours > available:
                return (f"Team {team.name!r} task #{ti}: needs {task.hours}h on "
                        f"{task.resource}, but only {available}h are available "
                        f"after unavailable slots are removed.")
    return None


def build_and_solve(
    teams: list[Team],
    resources: list[Resource],
    horizon: int = HORIZON,
    time_limit_s: float = 30.0,
    workers: int = 8,
) -> ScheduleResult:
    """Build the CP-SAT model and solve it. Returns a `ScheduleResult`."""
    err = _validate(teams, resources)
    if err:
        return ScheduleResult(
            status_name="INVALID",
            feasible=False,
            makespan=None,
            solve_time_s=0.0,
            assignments=[],
            diagnostic=err,
        )

    units = expand_units(resources)
    model = cp_model.CpModel()

    task_records: list[dict] = []

    for k, team in enumerate(teams):
        for ti, task in enumerate(team.tasks):
            compat_unit_ids = [uid for (uid, name, _) in units if name == task.resource]

            unit_vars = {
                uid: model.NewBoolVar(f"t{k}_{ti}_u{uid}")
                for uid in compat_unit_ids
            }
            model.Add(sum(unit_vars.values()) == 1)

            chunk_count = task.hours if task.allow_split else 1
            chunk_dur = 1 if task.allow_split else task.hours

            chunk_records: list[dict] = []
            for c in range(chunk_count):
                start = model.NewIntVar(0, horizon - chunk_dur, f"t{k}_{ti}_c{c}_start")
                end = model.NewIntVar(chunk_dur, horizon, f"t{k}_{ti}_c{c}_end")
                model.Add(end == start + chunk_dur)

                team_iv = model.NewIntervalVar(
                    start, chunk_dur, end, f"t{k}_{ti}_c{c}_team_iv",
                )
                per_unit_iv = {
                    uid: model.NewOptionalIntervalVar(
                        start, chunk_dur, end, unit_vars[uid],
                        f"t{k}_{ti}_c{c}_u{uid}_iv",
                    )
                    for uid in compat_unit_ids
                }
                chunk_records.append({
                    "start": start, "end": end,
                    "team_iv": team_iv, "per_unit_iv": per_unit_iv,
                })

            _add_unavailable_constraints(model, chunk_records, team.unavailable_slots,
                                         chunk_dur, horizon)

            task_records.append({
                "team_idx": k, "task_idx": ti, "task": task,
                "compat_unit_ids": compat_unit_ids,
                "unit_vars": unit_vars,
                "chunks": chunk_records,
                "chunk_count": chunk_count,
                "chunk_dur": chunk_dur,
            })

    _add_unit_no_overlap(model, units, task_records)
    _add_team_no_overlap(model, teams, task_records)

    makespan, total_gap, total_pref = _build_objective_terms(
        model, teams, task_records, horizon,
    )
    model.Minimize(_MAKESPAN_W * makespan + _GAP_W * total_gap - _PREF_W * total_pref)

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
            chosen_uid = next(uid for uid, v in tr["unit_vars"].items()
                              if solver.Value(v) == 1)
            for cr in tr["chunks"]:
                s = int(solver.Value(cr["start"]))
                e = int(solver.Value(cr["end"]))
                assignments.append(Assignment(
                    team_name=teams[tr["team_idx"]].name,
                    task_index=tr["task_idx"],
                    resource_name=tr["task"].resource,
                    unit_id=chosen_uid,
                    start_slot=s,
                    end_slot=e,
                ))
        assignments.sort(key=lambda a: (a.start_slot, a.unit_id))
    else:
        diagnostic = _infeasibility_hint(teams, resources)

    return ScheduleResult(
        status_name=status_name,
        feasible=feasible,
        makespan=makespan_value,
        solve_time_s=elapsed,
        assignments=assignments,
        diagnostic=diagnostic,
    )


# --- Helpers ----------------------------------------------------------------

def _add_unavailable_constraints(model, chunk_records, unavailable: set[int],
                                  chunk_dur: int, horizon: int) -> None:
    """Forbid a chunk from occupying any unavailable slot."""
    if not unavailable:
        return
    if chunk_dur == 1:
        allowed = [v for v in range(horizon) if v not in unavailable]
    else:
        allowed = [v for v in range(horizon - chunk_dur + 1)
                   if all((v + i) not in unavailable for i in range(chunk_dur))]
    for cr in chunk_records:
        if not allowed:
            # No legal start exists -> force infeasibility cleanly
            model.Add(cr["start"] >= horizon)  # contradicts domain [0, horizon-chunk_dur]
            continue
        model.AddAllowedAssignments([cr["start"]], [(v,) for v in allowed])


def _add_unit_no_overlap(model, units, task_records) -> None:
    for uid, _, _ in units:
        intervals = []
        for tr in task_records:
            if uid in tr["unit_vars"]:
                for cr in tr["chunks"]:
                    intervals.append(cr["per_unit_iv"][uid])
        if intervals:
            model.AddNoOverlap(intervals)


def _add_team_no_overlap(model, teams, task_records) -> None:
    for k in range(len(teams)):
        intervals = [cr["team_iv"]
                     for tr in task_records if tr["team_idx"] == k
                     for cr in tr["chunks"]]
        if intervals:
            model.AddNoOverlap(intervals)


def _build_objective_terms(model, teams, task_records, horizon):
    """Return (makespan, total_gap, total_pref_hits) IntVars / sums."""
    all_ends = [cr["end"] for tr in task_records for cr in tr["chunks"]]
    if all_ends:
        makespan = model.NewIntVar(0, horizon, "makespan")
        model.AddMaxEquality(makespan, all_ends)
    else:
        makespan = model.NewConstant(0)

    # Per-team gap: max_end - min_start - total_hours.
    gap_vars = []
    for k, team in enumerate(teams):
        starts = [cr["start"] for tr in task_records if tr["team_idx"] == k
                  for cr in tr["chunks"]]
        ends = [cr["end"] for tr in task_records if tr["team_idx"] == k
                for cr in tr["chunks"]]
        if not starts:
            continue
        team_total_hours = sum(tr["task"].hours
                               for tr in task_records if tr["team_idx"] == k)
        ms = model.NewIntVar(0, horizon, f"team{k}_minstart")
        me = model.NewIntVar(0, horizon, f"team{k}_maxend")
        model.AddMinEquality(ms, starts)
        model.AddMaxEquality(me, ends)
        gap = model.NewIntVar(0, horizon, f"team{k}_gap")
        model.Add(gap == me - ms - team_total_hours)
        gap_vars.append(gap)
    total_gap = model.NewIntVar(0, horizon * max(1, len(teams)), "total_gap")
    if gap_vars:
        model.Add(total_gap == sum(gap_vars))
    else:
        model.Add(total_gap == 0)

    # Preferred-slot hits: for every chunk, count the preferred slots it covers.
    pref_terms = []
    for tr in task_records:
        team = teams[tr["team_idx"]]
        if not team.preferred_slots:
            continue
        for cr in tr["chunks"]:
            d = tr["chunk_dur"]
            for v in team.preferred_slots:
                # cov  iff  start <= v < start + d
                cov = model.NewBoolVar("cov")
                model.Add(cr["start"] <= v).OnlyEnforceIf(cov)
                model.Add(cr["end"] > v).OnlyEnforceIf(cov)
                # if not cov, at least one of the two must fail
                lo_bad = model.NewBoolVar("lo_bad")  # start > v
                hi_bad = model.NewBoolVar("hi_bad")  # end <= v
                model.Add(cr["start"] > v).OnlyEnforceIf(lo_bad)
                model.Add(cr["start"] <= v).OnlyEnforceIf(lo_bad.Not())
                model.Add(cr["end"] <= v).OnlyEnforceIf(hi_bad)
                model.Add(cr["end"] > v).OnlyEnforceIf(hi_bad.Not())
                model.AddBoolOr([lo_bad, hi_bad]).OnlyEnforceIf(cov.Not())
                pref_terms.append(cov)

    if pref_terms:
        total_pref = model.NewIntVar(0, len(pref_terms), "total_pref")
        model.Add(total_pref == sum(pref_terms))
    else:
        total_pref = model.NewConstant(0)

    return makespan, total_gap, total_pref


def _infeasibility_hint(teams: list[Team], resources: list[Resource]) -> str:
    """Cheap heuristics that often explain INFEASIBLE."""
    res_units = {r.name: r.units for r in resources}
    hints: list[str] = []
    for team in teams:
        free = HORIZON - len(team.unavailable_slots)
        for ti, task in enumerate(team.tasks):
            if task.hours > free:
                hints.append(
                    f"Team {team.name!r} task #{ti} needs {task.hours}h on "
                    f"{task.resource} but the team has only {free}h available."
                )
            n = res_units.get(task.resource, 0)
            if n == 0:
                hints.append(f"Team {team.name!r} task #{ti} requests "
                             f"{task.resource} which is not in the pool.")
    if not hints:
        # Aggregate demand vs aggregate capacity per resource type.
        demand: dict[str, int] = {}
        for team in teams:
            for task in team.tasks:
                demand[task.resource] = demand.get(task.resource, 0) + task.hours
        for name, hours in demand.items():
            cap = HORIZON * res_units.get(name, 0)
            if hours > cap:
                hints.append(
                    f"Total demand for {name} ({hours}h) exceeds weekly "
                    f"capacity ({cap}h on {res_units.get(name, 0)} units)."
                )
    if not hints:
        return "Constraints conflict in a non-obvious way; try relaxing unavailable slots or splitting long tasks."
    return " | ".join(hints)
