"""Tests for the CP-SAT scheduling model (tasks-first, multi-resource)."""
from lab_planner.models import (
    DEFAULT_RESOURCES,
    HORIZON,
    Resource,
    Task,
    is_work_hour,
)
from lab_planner.solver import build_and_solve


def test_single_task_smoke():
    tasks = [Task("Build", requirements={"VSG": 1, "OBB": 1}, hours=3)]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=5)
    assert res.feasible
    assert res.makespan == 3
    # Should have one assignment per required unit
    assert len(res.assignments) == 2
    by_resource = {a.resource_name for a in res.assignments}
    assert by_resource == {"VSG", "OBB"}
    # All assignments span the same window
    starts = {a.start_slot for a in res.assignments}
    ends = {a.end_slot for a in res.assignments}
    assert starts == {0} and ends == {3}


def test_multi_unit_per_type():
    """Task asking for 2× VSG must reserve two distinct VSG units."""
    tasks = [Task("Wide", requirements={"VSG": 2}, hours=2)]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=5)
    assert res.feasible
    assert len(res.assignments) == 2
    assert all(a.resource_name == "VSG" for a in res.assignments)
    # The two reserved units are distinct
    assert len({a.unit_id for a in res.assignments}) == 2


def test_unit_no_overlap_serializes_two_tasks():
    """Two tasks both needing OBB (only 1 unit) must run back-to-back."""
    tasks = [
        Task("A", requirements={"OBB": 1}, hours=3),
        Task("B", requirements={"OBB": 1}, hours=2),
    ]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=5)
    assert res.feasible
    assert res.makespan == 5
    obb = sorted([(a.start_slot, a.end_slot, a.task_name)
                  for a in res.assignments if a.resource_name == "OBB"])
    # No overlap on the single OBB unit
    assert obb[0][1] <= obb[1][0]


def test_unavailable_blocks_window():
    tasks = [
        Task("A", requirements={"VSG": 1}, hours=4,
             unavailable_slots=set(range(0, 10))),
    ]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=5)
    assert res.feasible
    a = res.assignments[0]
    assert a.start_slot >= 10
    # No assignment overlaps any unavailable slot
    for s in range(a.start_slot, a.end_slot):
        assert s not in set(range(0, 10))


def test_preferred_pulls_into_window():
    """When makespan is fixed by another task, the small task drifts to its green window."""
    tasks = [
        Task("Small", requirements={"VSG": 1}, hours=3,
             preferred_slots=set(range(40, 50))),
        Task("Huge",  requirements={"OBB": 1}, hours=50),
    ]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=10)
    assert res.feasible
    small = next(a for a in res.assignments if a.task_name == "Small")
    # Should land entirely within the preferred window
    assert 40 <= small.start_slot and small.end_slot <= 50


def test_infeasible_returns_status():
    tasks = [
        Task("Bad", requirements={"VSG": 1}, hours=1,
             unavailable_slots=set(range(HORIZON))),
    ]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=5)
    assert not res.feasible
    assert res.status_name in {"INFEASIBLE", "INVALID"}
    assert res.diagnostic


def test_unknown_resource_caught_early():
    tasks = [Task("Bad", requirements={"NOPE": 1}, hours=1)]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=2)
    assert not res.feasible
    assert "NOPE" in res.diagnostic


def test_quantity_exceeding_pool_caught_early():
    tasks = [Task("Bad", requirements={"OBB": 5}, hours=1)]  # only 1 OBB unit exists
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=2)
    assert not res.feasible
    assert "OBB" in res.diagnostic


def test_work_hours_only_keeps_task_inside_business_hours():
    """A 4h work-hours-only task must run on a weekday between 08-18."""
    tasks = [Task("Office", requirements={"VSG": 1}, hours=4,
                  work_hours_only=True)]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=5)
    assert res.feasible
    a = res.assignments[0]
    for s in range(a.start_slot, a.end_slot):
        assert is_work_hour(s), f"slot {s} is outside work hours"


def test_work_hours_only_infeasible_when_too_long_for_one_workday():
    """11-hour work-hours-only task is infeasible (work day is only 10 h)."""
    tasks = [Task("TooLong", requirements={"VSG": 1}, hours=11,
                  work_hours_only=True)]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=5)
    assert not res.feasible
    assert res.status_name in {"INFEASIBLE", "INVALID"}


def test_three_tasks_share_resources_correctly():
    """Three short tasks each need VSG (3 units) and OBB (1 unit).
    OBB serializes them; VSG can run in parallel."""
    tasks = [
        Task(f"T{i}", requirements={"VSG": 1, "OBB": 1}, hours=2)
        for i in range(3)
    ]
    res = build_and_solve(tasks, DEFAULT_RESOURCES, time_limit_s=5)
    assert res.feasible
    assert res.makespan == 6  # 3 × 2h serialized on OBB

    # On the OBB unit, blocks are non-overlapping
    obb = sorted([(a.start_slot, a.end_slot)
                  for a in res.assignments if a.resource_name == "OBB"])
    for (s1, e1), (s2, e2) in zip(obb, obb[1:]):
        assert e1 <= s2
