"""Round-trip tests for JSON save/load."""
from pathlib import Path

import pytest

from lab_planner.models import DEFAULT_RESOURCES, Task
from lab_planner.persistence import load_project, save_project


def test_roundtrip_preserves_everything(tmp_path: Path):
    tasks = [
        Task("Build A",
             requirements={"VSG": 2, "OBB": 1},
             hours=4,
             preferred_slots={10, 11, 12},
             unavailable_slots={0, 1, 2}),
        Task("Bake",
             requirements={"Fırın": 2},  # non-ASCII test
             hours=8,
             preferred_slots=set(),
             unavailable_slots={50, 51}),
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
