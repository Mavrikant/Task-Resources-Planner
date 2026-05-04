"""Tests for the data model layer."""
import pytest

from lab_planner.models import (
    DEFAULT_RESOURCES,
    HORIZON,
    Assignment,
    Resource,
    Task,
    day_hour_to_slot,
    expand_units,
    format_requirements,
    is_weekend,
    is_work_hour,
    non_work_slots,
    slot_to_day_hour,
    unit_label,
)


def test_default_pool_totals_19_units():
    assert sum(r.units for r in DEFAULT_RESOURCES) == 19


def test_default_pool_has_expected_types():
    names = {r.name for r in DEFAULT_RESOURCES}
    assert names == {"VSG", "VSGRS", "OBB", "IFF", "IFR", "1553",
                     "RFCU", "ADF T", "Fırın", "CT94", "OSC", "AA"}


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
