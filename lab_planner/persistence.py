"""JSON save/load for projects (teams + resources)."""
from __future__ import annotations

import json
from pathlib import Path

from .models import Resource, Task, Team


SCHEMA_VERSION = 1


def save_project(path: str | Path,
                 teams: list[Team],
                 resources: list[Resource]) -> None:
    """Serialize teams and resources to a UTF-8 JSON file."""
    payload = {
        "version": SCHEMA_VERSION,
        "resources": [{"name": r.name, "units": r.units} for r in resources],
        "teams": [
            {
                "name": team.name,
                "tasks": [
                    {"resource": t.resource, "hours": t.hours,
                     "allow_split": t.allow_split}
                    for t in team.tasks
                ],
                "preferred_slots": sorted(team.preferred_slots),
                "unavailable_slots": sorted(team.unavailable_slots),
            }
            for team in teams
        ],
    }
    p = Path(path)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def load_project(path: str | Path) -> tuple[list[Team], list[Resource]]:
    """Read a project file and return (teams, resources)."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("version") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version: {data.get('version')!r}"
        )
    resources = [Resource(name=r["name"], units=int(r["units"]))
                 for r in data.get("resources", [])]
    teams: list[Team] = []
    for t in data.get("teams", []):
        tasks = [Task(resource=tt["resource"],
                      hours=int(tt["hours"]),
                      allow_split=bool(tt.get("allow_split", True)))
                 for tt in t.get("tasks", [])]
        teams.append(Team(
            name=t["name"],
            tasks=tasks,
            preferred_slots=set(t.get("preferred_slots", [])),
            unavailable_slots=set(t.get("unavailable_slots", [])),
        ))
    return teams, resources
