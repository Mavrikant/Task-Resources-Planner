"""Round-trip tests for JSON save/load."""
from pathlib import Path

import pytest

from lab_planner.models import DEFAULT_RESOURCES, Resource, Task
from lab_planner.persistence import (
    load_default_pool,
    load_pool,
    load_project,
    save_pool,
    save_project,
)


def test_roundtrip_preserves_everything(tmp_path: Path):
    tasks = [
        Task("Build A",
             requirements={"VSG": 2, "OBB": 1},
             hours=4,
             preferred_slots={10, 11, 12},
             unavailable_slots={0, 1, 2},
             work_hours_only=True,
             deadline=42),
        Task("Bake",
             requirements={"Fırın": 2},  # non-ASCII test
             hours=8,
             preferred_slots=set(),
             unavailable_slots={50, 51},
             deadline=None),
    ]
    file = tmp_path / "proj.json"
    save_project(file, tasks, DEFAULT_RESOURCES)

    tasks2, resources2 = load_project(file)
    assert resources2 == DEFAULT_RESOURCES
    assert tasks2 == tasks


def test_file_is_utf8_with_unicode(tmp_path: Path):
    tasks = [Task("Pişirme",
                  requirements={"Fırın": 1},
                  hours=2)]
    file = tmp_path / "tr.json"
    save_project(file, tasks, DEFAULT_RESOURCES)
    text = file.read_text(encoding="utf-8")
    assert "Fırın" in text
    assert "Pişirme" in text


def test_load_rejects_old_team_schema(tmp_path: Path):
    file = tmp_path / "old.json"
    file.write_text('{"version": 1, "teams": [], "resources": []}',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="schema version"):
        load_project(file)


# --- equipment pool persistence ---------------------------------------------


def test_pool_roundtrip(tmp_path: Path):
    pool = [
        Resource("Spectrum analyzer", 2),
        Resource("Fırın", 1),
        Resource("CT-94", 1),
    ]
    file = tmp_path / "pool.json"
    save_pool(file, pool)
    loaded = load_pool(file)
    assert loaded == pool


def test_load_pool_rejects_wrong_schema(tmp_path: Path):
    file = tmp_path / "bad.json"
    file.write_text('{"version": 2, "tasks": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="equipment-pool"):
        load_pool(file)


def test_load_pool_rejects_wrong_version(tmp_path: Path):
    file = tmp_path / "future.json"
    file.write_text('{"schema": "equipment-pool", "version": 99, "resources": []}',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        load_pool(file)


def test_load_default_pool_falls_back_when_missing(monkeypatch, tmp_path: Path):
    # Point DEFAULT_POOL_PATH at a non-existent file → fallback kicks in.
    import lab_planner.persistence as persistence
    monkeypatch.setattr(persistence, "DEFAULT_POOL_PATH", tmp_path / "nope.json")
    pool = load_default_pool()
    assert pool == DEFAULT_RESOURCES


def test_load_default_pool_reads_bundled_file():
    """The shipped equipment_pool.json should match DEFAULT_RESOURCES exactly."""
    pool = load_default_pool()
    # We don't assume order, but contents should match.
    assert {r.name: r.units for r in pool} == {r.name: r.units for r in DEFAULT_RESOURCES}
