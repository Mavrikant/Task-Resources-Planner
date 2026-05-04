"""Tests for the data model layer."""
import pytest

from lab_planner.models import (
    DEFAULT_RESOURCES,
    HORIZON,
    Assignment,
    Resource,
    Task,
    day_hour_to_slot,
    duplicate_task,
    expand_units,
    format_requirements,
    is_weekend,
    is_work_hour,
    next_copy_name,
    non_work_slots,
    slot_to_day_hour,
    unit_label,
)


def test_default_pool_totals_19_units():
    assert sum(r.units for r in DEFAULT_RESOURCES) == 19


def test_default_pool_has_expected_types():
    names = {r.name for r in DEFAULT_RESOURCES}
    assert names == {"VSG", "VSGRS", "OBB", "IFF", "IFR", "1553", "RFCU",
                     "ADF Tester", "Temperature Test Chamber", "A429",
                     "Oscilloscope", "AA"}


def test_horizon_is_one_week():
    assert HORIZON == 7 * 24


def test_resource_validation():
    with pytest.raises(ValueError):
        Resource("", 1)
    with pytest.raises(ValueError):
        Resource("VSG", 0)


def test_task_must_have_requirements():
    with pytest.raises(ValueError):
        Task("X", requirements={}, hours=1)


def test_task_hours_validation():
    with pytest.raises(ValueError):
        Task("X", requirements={"VSG": 1}, hours=0)
    with pytest.raises(ValueError):
        Task("X", requirements={"VSG": 1}, hours=HORIZON + 1)


def test_task_requirement_qty_validation():
    with pytest.raises(ValueError):
        Task("X", requirements={"VSG": 0}, hours=1)
    with pytest.raises(ValueError):
        Task("X", requirements={"": 1}, hours=1)


def test_task_slot_validation():
    Task("X", requirements={"VSG": 1}, hours=2,
         preferred_slots={0, 167})
    with pytest.raises(ValueError):
        Task("X", requirements={"VSG": 1}, hours=2,
             preferred_slots={168})
    with pytest.raises(ValueError):
        Task("X", requirements={"VSG": 1}, hours=2,
             preferred_slots={5}, unavailable_slots={5})


def test_slot_conversions_roundtrip():
    for s in [0, 1, 23, 24, 100, 167]:
        d, h = slot_to_day_hour(s)
        assert day_hour_to_slot(d, h) == s


def test_expand_units_assigns_unique_ids():
    units = expand_units(DEFAULT_RESOURCES)
    assert len(units) == 19
    assert [u[0] for u in units] == list(range(19))


def test_unit_label_singletons_have_no_index():
    units = expand_units(DEFAULT_RESOURCES)
    obb_id = next(u[0] for u in units if u[1] == "OBB")
    assert unit_label(units, obb_id) == "OBB"
    vsg_ids = [u[0] for u in units if u[1] == "VSG"]
    labels = [unit_label(units, uid) for uid in vsg_ids]
    assert labels == ["VSG #1", "VSG #2", "VSG #3"]


def test_format_requirements():
    assert format_requirements({"VSG": 2, "OBB": 1}) == "VSG×2 + OBB"
    assert format_requirements({"VSG": 1}) == "VSG"
    assert format_requirements({}) == "(none)"


def test_assignment_duration():
    a = Assignment("X", 0, "VSG", 0, 5, 9)
    assert a.duration == 4


def test_work_hour_classification():
    # Mon 08:00 is a work hour; Mon 07:59 (slot 7) and Mon 18:00 (slot 18) are not.
    assert is_work_hour(8) is True
    assert is_work_hour(17) is True
    assert is_work_hour(7) is False
    assert is_work_hour(18) is False
    # Sat/Sun never count even at 10:00.
    assert is_work_hour(5 * 24 + 10) is False
    assert is_work_hour(6 * 24 + 10) is False
    assert is_weekend(5 * 24 + 0) is True
    assert is_weekend(0) is False


def test_non_work_slots_count():
    # 5 weekdays × 10 work hours = 50; rest of the week = 168 - 50 = 118.
    assert len(non_work_slots()) == HORIZON - 5 * 10
    # Spot-check: Tue 14:00 is work hour, NOT in non_work_slots
    tue_2pm = 1 * 24 + 14
    assert tue_2pm not in non_work_slots()


def test_task_work_hours_only_default_false():
    t = Task("X", requirements={"VSG": 1}, hours=2)
    assert t.work_hours_only is False


def test_task_deadline_default_none():
    t = Task("X", requirements={"VSG": 1}, hours=2)
    assert t.deadline is None


def test_task_deadline_validation():
    Task("X", requirements={"VSG": 1}, hours=4, deadline=10)
    with pytest.raises(ValueError, match="deadline"):
        Task("X", requirements={"VSG": 1}, hours=4, deadline=3)
    with pytest.raises(ValueError, match="deadline"):
        Task("X", requirements={"VSG": 1}, hours=4, deadline=0)
    with pytest.raises(ValueError, match="deadline"):
        Task("X", requirements={"VSG": 1}, hours=4, deadline=HORIZON + 1)


def test_format_deadline():
    from lab_planner.models import format_deadline
    assert format_deadline(None) == "-"
    assert format_deadline(168) == "end of week"
    assert format_deadline(42) == "Tue 18:00"
    assert format_deadline(24) == "end of Mon"
    assert format_deadline(1) == "Mon 01:00"


def test_next_copy_name_progression():
    assert next_copy_name("Foo") == "Foo (copy)"
    assert next_copy_name("Foo (copy)") == "Foo (copy 2)"
    assert next_copy_name("Foo (copy 2)") == "Foo (copy 3)"
    assert next_copy_name("Foo (copy 7)") == "Foo (copy 8)"
    # Names that look similar but are not the suffix pattern stay intact.
    assert next_copy_name("Foo (final)") == "Foo (final) (copy)"


def test_duplicate_task_is_deep_copy():
    src = Task("Build",
               requirements={"VSG": 2, "OBB": 1},
               hours=4,
               preferred_slots={10, 11, 12},
               unavailable_slots={0},
               work_hours_only=True)
    dup = duplicate_task(src)
    assert dup.name == "Build (copy)"
    assert dup.requirements == src.requirements
    assert dup.preferred_slots == src.preferred_slots
    assert dup.unavailable_slots == src.unavailable_slots
    assert dup.hours == src.hours
    assert dup.work_hours_only == src.work_hours_only
    # Mutating the source must not bleed into the copy.
    src.preferred_slots.add(99)
    src.requirements["AA"] = 1
    assert 99 not in dup.preferred_slots
    assert "AA" not in dup.requirements
