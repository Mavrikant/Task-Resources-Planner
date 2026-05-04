"""Tests for the data model layer."""
import pytest

from lab_planner.models import (
    DEFAULT_RESOURCES,
    HORIZON,
    Assignment,
    Resource,
    Task,
    Team,
    day_hour_to_slot,
    expand_units,
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


def test_task_validation():
    with pytest.raises(ValueError):
        Task("VSG", 0)
    with pytest.raises(ValueError):
        Task("VSG", HORIZON + 1)


def test_team_slot_validation():
    Team("A", preferred_slots={0, 5, 167})
    with pytest.raises(ValueError):
        Team("A", preferred_slots={168})
    with pytest.raises(ValueError):
        Team("A", preferred_slots={0}, unavailable_slots={0})


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
    # OBB has only 1 unit -> label is just "OBB"
    obb_id = next(u[0] for u in units if u[1] == "OBB")
    assert unit_label(units, obb_id) == "OBB"
    # VSG has 3 -> labels are "VSG #1", "VSG #2", "VSG #3"
    vsg_ids = [u[0] for u in units if u[1] == "VSG"]
    labels = [unit_label(units, uid) for uid in vsg_ids]
    assert labels == ["VSG #1", "VSG #2", "VSG #3"]


def test_assignment_duration():
    a = Assignment("A", 0, "VSG", 0, 5, 9)
    assert a.duration == 4
