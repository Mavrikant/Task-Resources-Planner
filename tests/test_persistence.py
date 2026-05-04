"""Round-trip tests for JSON save/load."""
from pathlib import Path

from lab_planner.models import DEFAULT_RESOURCES, Task, Team
from lab_planner.persistence import load_project, save_project


def test_roundtrip_preserves_everything(tmp_path: Path):
    teams = [
        Team("A",
             tasks=[Task("VSG", 3, allow_split=False),
                    Task("OBB", 2, allow_split=True)],
             preferred_slots={10, 11, 12},
             unavailable_slots={0, 1, 2}),
        Team("B",
             tasks=[Task("Fırın", 5, allow_split=True)],  # non-ASCII test
             preferred_slots=set(),
             unavailable_slots={50, 51}),
    ]
    file = tmp_path / "proj.json"
    save_project(file, teams, DEFAULT_RESOURCES)

    teams2, resources2 = load_project(file)
    assert resources2 == DEFAULT_RESOURCES
    assert teams2 == teams


def test_file_is_utf8_with_unicode(tmp_path: Path):
    teams = [Team("Türk takım",
                  tasks=[Task("Fırın", 1, allow_split=False)])]
    file = tmp_path / "tr.json"
    save_project(file, teams, DEFAULT_RESOURCES)
    text = file.read_text(encoding="utf-8")
    assert "Fırın" in text
    assert "Türk takım" in text


def test_load_rejects_unknown_version(tmp_path: Path):
    file = tmp_path / "bad.json"
    file.write_text('{"version": 99, "teams": [], "resources": []}',
                    encoding="utf-8")
    try:
        load_project(file)
    except ValueError as e:
        assert "schema version" in str(e)
    else:
        raise AssertionError("expected ValueError")
