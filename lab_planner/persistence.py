"""JSON save/load for projects (tasks + resources)."""
from __future__ import annotations

import json
from pathlib import Path

from .models import Resource, Task


SCHEMA_VERSION = 2


def save_project(path: str | Path,
                 tasks: list[Task],
                 resources: list[Resource]) -> None:
    payload = {
        "version": SCHEMA_VERSION,
        "resources": [{"name": r.name, "units": r.units} for r in resources],
        "tasks": [
            {
                "name": t.name,
                "requirements": dict(t.requirements),
                "hours": t.hours,
                "preferred_slots": sorted(t.preferred_slots),
                "unavailable_slots": sorted(t.unavailable_slots),
            }
            for t in tasks
        ],
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def load_project(path: str | Path) -> tuple[list[Task], list[Resource]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version {version!r}; "
            f"expected {SCHEMA_VERSION}. (Old team-based files are no "
            "longer supported — recreate the project with tasks instead.)"
        )
    resources = [Resource(name=r["name"], units=int(r["units"]))
                 for r in data.get("resources", [])]
    tasks: list[Task] = []
    for t in data.get("tasks", []):
        tasks.append(Task(
            name=t["name"],
            requirements={k: int(v) for k, v in t.get("requirements", {}).items()},
            hours=int(t.get("hours", 1)),
            preferred_slots=set(t.get("preferred_slots", [])),
            unavailable_slots=set(t.get("unavailable_slots", [])),
        ))
    return tasks, resources
