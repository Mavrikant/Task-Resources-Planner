"""Data models for the lab equipment scheduler.

Time is measured in 1-hour slots over a 7-day horizon (168 slots total).
A slot index `s` maps to: day = s // 24 (0=Mon..6=Sun), hour = s % 24.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


HORIZON = 168
DAYS = 7
HOURS_PER_DAY = 24
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class Resource:
    """A type of lab equipment with a number of physical units."""
    name: str
    units: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Resource name cannot be empty")
        if self.units < 1:
            raise ValueError(f"Resource {self.name!r} must have at least 1 unit")


@dataclass
class Task:
    """A single piece of work a team needs done on a resource type."""
    resource: str          # name matching a Resource
    hours: int             # required hours (1..24 typical)
    allow_split: bool = True

    def __post_init__(self) -> None:
        if self.hours < 1:
            raise ValueError(f"Task hours must be >= 1 (got {self.hours})")
        if self.hours > HORIZON:
            raise ValueError(f"Task hours {self.hours} exceeds horizon {HORIZON}")


@dataclass
class Team:
    """A team that owns a list of tasks plus per-team slot preferences."""
    name: str
    tasks: list[Task] = field(default_factory=list)
    preferred_slots: set[int] = field(default_factory=set)
    unavailable_slots: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Team name cannot be empty")
        self.preferred_slots = {int(s) for s in self.preferred_slots}
        self.unavailable_slots = {int(s) for s in self.unavailable_slots}
        for s in self.preferred_slots | self.unavailable_slots:
            if not 0 <= s < HORIZON:
                raise ValueError(f"Slot {s} out of range [0, {HORIZON})")
        overlap = self.preferred_slots & self.unavailable_slots
        if overlap:
            raise ValueError(f"Slots cannot be both preferred and unavailable: {sorted(overlap)}")


@dataclass
class Assignment:
    """A single 1-hour-or-longer block of work in the produced schedule."""
    team_name: str
    task_index: int       # index within team.tasks
    resource_name: str
    unit_id: int          # global physical-unit id (0..total_units-1)
    start_slot: int
    end_slot: int         # exclusive

    @property
    def duration(self) -> int:
        return self.end_slot - self.start_slot


@dataclass
class ScheduleResult:
    """Outcome of one solve."""
    status_name: str                       # "OPTIMAL" / "FEASIBLE" / "INFEASIBLE" / ...
    feasible: bool
    makespan: Optional[int]
    solve_time_s: float
    assignments: list[Assignment] = field(default_factory=list)
    diagnostic: str = ""


# --- Default resource pool from the user's brief ----------------------------

DEFAULT_RESOURCES: list[Resource] = [
    Resource("VSG",   3),
    Resource("VSGRS", 1),
    Resource("OBB",   1),
    Resource("IFF",   2),
    Resource("IFR",   1),
    Resource("1553",  2),
    Resource("RFCU",  2),
    Resource("ADF T", 1),
    Resource("Fırın", 2),
    Resource("CT94",  1),
    Resource("OSC",   1),
    Resource("AA",    2),
]


def slot_to_day_hour(slot: int) -> tuple[int, int]:
    return slot // HOURS_PER_DAY, slot % HOURS_PER_DAY


def day_hour_to_slot(day: int, hour: int) -> int:
    if not 0 <= day < DAYS or not 0 <= hour < HOURS_PER_DAY:
        raise ValueError(f"Invalid day/hour: {day}/{hour}")
    return day * HOURS_PER_DAY + hour


def expand_units(resources: list[Resource]) -> list[tuple[int, str, int]]:
    """Return [(unit_id, resource_name, index_within_type), ...] for the pool."""
    units: list[tuple[int, str, int]] = []
    for r in resources:
        for i in range(r.units):
            units.append((len(units), r.name, i))
    return units


def unit_label(units: list[tuple[int, str, int]], unit_id: int) -> str:
    """Human-friendly label for a physical unit, e.g. 'VSG #2'."""
    _, name, idx = units[unit_id]
    same_type = [u for u in units if u[1] == name]
    if len(same_type) == 1:
        return name
    return f"{name} #{idx + 1}"
