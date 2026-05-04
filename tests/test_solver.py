"""Tests for the CP-SAT scheduling model."""
import pytest

from lab_planner.models import (
    DEFAULT_RESOURCES,
    HORIZON,
    Resource,
    Task,
    Team,
)
from lab_planner.solver import build_and_solve


def test_two_team_smoke():
    """Two teams, each with VSG 3h + OBB 2h, contiguous, no preferences."""
    teams = [
        Team("A", tasks=[Task("VSG", 3, allow_split=False),
                         Task("OBB", 2, allow_split=False)]),
        Team("B", tasks=[Task("VSG", 3, allow_split=False),
                         Task("OBB", 2, allow_split=False)]),
    ]
    res = build_and_solve(teams, DEFAULT_RESOURCES, time_limit_s=10)
    assert res.feasible, f"unexpected status {res.status_name}: {res.diagnostic}"
    # Optimal makespan is 5 — both teams fit OBB serially while sharing VSGs
    assert res.makespan is not None and res.makespan <= 7
    assert len(res.assignments) == 4

    # No two assignments may share the same physical unit at the same slot
    by_unit: dict[int, list[tuple[int, int]]] = {}
    for a in res.assignments:
        by_unit.setdefault(a.unit_id, []).append((a.start_slot, a.end_slot))
    for uid, blocks in by_unit.items():
        blocks.sort()
        for (s1, e1), (s2, e2) in zip(blocks, blocks[1:]):
            assert e1 <= s2, f"unit {uid} overlap: {(s1,e1)} vs {(s2,e2)}"

    # Same team must never be doing two things at once
    by_team: dict[str, list[tuple[int, int]]] = {}
    for a in res.assignments:
        by_team.setdefault(a.team_name, []).append((a.start_slot, a.end_slot))
    for name, blocks in by_team.items():
        blocks.sort()
        for (s1, e1), (s2, e2) in zip(blocks, blocks[1:]):
            assert e1 <= s2, f"team {name} overlap: {(s1,e1)} vs {(s2,e2)}"


def test_unavailable_blocks_slot():
    """A team's tasks must avoid unavailable slots entirely."""
    unavail = set(range(0, 10))
    teams = [
        Team("A", tasks=[Task("VSG", 3, allow_split=True)],
             unavailable_slots=unavail),
    ]
    res = build_and_solve(teams, DEFAULT_RESOURCES, time_limit_s=10)
    assert res.feasible
    # Every chunk slot must be at or after slot 10
    for a in res.assignments:
        for s in range(a.start_slot, a.end_slot):
            assert s not in unavail, f"chunk landed in unavailable slot {s}"


def test_preferred_bonus_breaks_tie():
    """When makespan is fixed by another job, the team's task should
    drift to its preferred window."""
    # Team B's huge task forces makespan = 50.  Team A's small task can
    # then go anywhere in [0, 45]; preferred slots {45..49} should pull it.
    teams = [
        Team("A",
             tasks=[Task("VSG", 5, allow_split=False)],
             preferred_slots=set(range(45, 50))),
        Team("B",
             tasks=[Task("OBB", 50, allow_split=False)]),
    ]
    res = build_and_solve(teams, DEFAULT_RESOURCES, time_limit_s=15)
    assert res.feasible
    a_blocks = [a for a in res.assignments if a.team_name == "A"]
    assert len(a_blocks) == 1
    assert a_blocks[0].start_slot == 45, (
        f"expected start 45 to maximise preferred-slot hits, got {a_blocks[0].start_slot}"
    )


def test_infeasible_returns_status():
    """When demand exceeds capacity the solver reports INFEASIBLE cleanly."""
    teams = [
        Team("A",
             tasks=[Task("VSG", 1, allow_split=False)],
             unavailable_slots=set(range(HORIZON))),  # all 168 slots blocked
    ]
    res = build_and_solve(teams, DEFAULT_RESOURCES, time_limit_s=5)
    assert not res.feasible
    assert res.status_name in {"INFEASIBLE", "INVALID"}
    assert res.diagnostic  # gave a hint


def test_split_task_distributes_chunks():
    """A 4h splittable task on a single-unit resource shared by two teams
    should still produce a valid plan with 4 chunks."""
    teams = [
        Team("A", tasks=[Task("OBB", 4, allow_split=True)]),
        Team("B", tasks=[Task("OBB", 4, allow_split=True)]),
    ]
    res = build_and_solve(teams, DEFAULT_RESOURCES, time_limit_s=10)
    assert res.feasible
    assert sum(1 for a in res.assignments if a.team_name == "A") == 4
    assert sum(1 for a in res.assignments if a.team_name == "B") == 4
    # Total OBB usage = 8 hours, all on unit 0 since OBB has 1 unit
    obb = [a for a in res.assignments if a.resource_name == "OBB"]
    assert len({a.unit_id for a in obb}) == 1


def test_unknown_resource_is_caught():
    teams = [Team("A", tasks=[Task("DOES_NOT_EXIST", 1)])]
    res = build_and_solve(teams, DEFAULT_RESOURCES, time_limit_s=2)
    assert not res.feasible
    assert "DOES_NOT_EXIST" in res.diagnostic
