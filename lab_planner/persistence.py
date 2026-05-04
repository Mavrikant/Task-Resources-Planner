"""JSON save/load for projects and equipment pools."""
from __future__ import annotations

import json
from pathlib import Path

from .models import DEFAULT_RESOURCES, Resource, Task


SCHEMA_VERSION = 2
POOL_SCHEMA_VERSION = 1
POOL_SCHEMA_NAME = "equipment-pool"

# Where the bundled default pool lives (project-root / equipment_pool.json).
DEFAULT_POOL_PATH = Path(__file__).resolve().parent.parent / "equipment_pool.json"


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
                "work_hours_only": t.work_hours_only,
                "deadline": t.deadline,
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
        deadline = t.get("deadline")
        tasks.append(Task(
            name=t["name"],
            requirements={k: int(v) for k, v in t.get("requirements", {}).items()},
            hours=int(t.get("hours", 1)),
            preferred_slots=set(t.get("preferred_slots", [])),
            unavailable_slots=set(t.get("unavailable_slots", [])),
            work_hours_only=bool(t.get("work_hours_only", False)),
            deadline=int(deadline) if deadline is not None else None,
        ))
    return tasks, resources


# --- Equipment pool save / load --------------------------------------------

def save_pool(path: str | Path, resources: list[Resource]) -> None:
    """Write a list of resources to a standalone equipment-pool JSON file."""
    payload = {
        "schema": POOL_SCHEMA_NAME,
        "version": POOL_SCHEMA_VERSION,
        "resources": [{"name": r.name, "units": r.units} for r in resources],
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def load_pool(path: str | Path) -> list[Resource]:
    """Read a standalone equipment-pool JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != POOL_SCHEMA_NAME:
        raise ValueError(
            f"Not an equipment-pool file: schema={data.get('schema')!r}"
        )
    if data.get("version") != POOL_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported equipment-pool schema version "
            f"{data.get('version')!r}; expected {POOL_SCHEMA_VERSION}."
        )
    return [Resource(name=r["name"], units=int(r["units"]))
            for r in data.get("resources", [])]


def load_default_pool() -> list[Resource]:
    """Return the pool from `DEFAULT_POOL_PATH` if present, else the hardcoded fallback."""
    if DEFAULT_POOL_PATH.exists():
        try:
            return load_pool(DEFAULT_POOL_PATH)
        except (ValueError, json.JSONDecodeError, OSError):
            pass
    return list(DEFAULT_RESOURCES)
