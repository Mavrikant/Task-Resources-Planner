"""Data models for the lab equipment scheduler.

A schedule covers one week as 168 one-hour slots. A `Task` is the unit of
work scheduled: it consumes a multiset of physical resource units for
`hours` consecutive hours and may declare its own preferred and
unavailable slots.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Optional


HORIZON = 168
DAYS = 7
HOURS_PER_DAY = 24
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Work-hours definition: weekdays Mon..Fri, 08:00..18:00 (so 18:00 itself is off).
WORK_START_HOUR = 8
WORK_END_HOUR = 18           # exclusive: hour 17 is the last work hour
WORKDAYS = frozenset({0, 1, 2, 3, 4})   # Mon..Fri


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
    """A scheduled piece of work that locks one or more units together for `hours`."""
    name: str
    requirements: dict[str, int] = field(default_factory=dict)
    hours: int = 1
    preferred_slots: set[int] = field(default_factory=set)
    unavailable_slots: set[int] = field(default_factory=set)
    work_hours_only: bool = False  # if True, must run inside Mon-Fri 08-18

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Task name cannot be empty")
        if self.hours < 1:
            raise ValueError(f"Task hours must be >= 1 (got {self.hours})")
        if self.hours > HORIZON:
            raise ValueError(f"Task hours {self.hours} exceeds horizon {HORIZON}")
        if not self.requirements:
            raise ValueError(f"Task {self.name!r} has no resource requirements")
        for res, qty in self.requirements.items():
            if not res:
                raise ValueError("Empty resource name in requirements")
            if qty < 1:
                raise ValueError(
                    f"Task {self.name!r}: requirement for {res!r} must be >= 1"
                )
        self.preferred_slots = {int(s) for s in self.preferred_slots}
        self.unavailable_slots = {int(s) for s in self.unavailable_slots}
        for s in self.preferred_slots | self.unavailable_slots:
            if not 0 <= s < HORIZON:
                raise ValueError(f"Slot {s} out of range [0, {HORIZON})")
        overlap = self.preferred_slots & self.unavailable_slots
        if overlap:
            raise ValueError(
                f"Slots cannot be both preferred and unavailable: {sorted(overlap)}"
            )


@dataclass
class Assignment:
    """One physical unit reserved by one task during one continuous span."""
    task_name: str
    task_index: int
    resource_name: str
    unit_id: int
    start_slot: int
    end_slot: int

    @property
    def duration(self) -> int:
        return self.end_slot - self.start_slot


@dataclass
class ScheduleResult:
    status_name: str
    feasible: bool
    makespan: Optional[int]
    solve_time_s: float
    assignments: list[Assignment] = field(default_factory=list)
    diagnostic: str = ""


# --- Default resource pool from the user's brief ---------------------------

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


def is_work_hour(slot: int) -> bool:
    """True if `slot` falls within Mon-Fri 08:00-18:00."""
    day, hour = slot_to_day_hour(slot)
    return day in WORKDAYS and WORK_START_HOUR <= hour < WORK_END_HOUR


def is_weekend(slot: int) -> bool:
    day, _ = slot_to_day_hour(slot)
    return day not in WORKDAYS


def non_work_slots() -> set[int]:
    """All 168 - (5×10) = 118 slots that fall outside work hours."""
    return {s for s in range(HORIZON) if not is_work_hour(s)}


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


def format_requirements(req: dict[str, int]) -> str:
    """Pretty 'VSG×2 + OBB + IFF' style summary."""
    parts = []
    for name, qty in req.items():
        parts.append(f"{name}×{qty}" if qty > 1 else name)
    return " + ".join(parts) if parts else "(none)"


_COPY_RE = re.compile(r"^(?P<stem>.*) \(copy(?: (?P<n>\d+))?\)$")


def next_copy_name(base: str) -> str:
    """Generate the next sensible name for a duplicated task.

    'Foo'           → 'Foo (copy)'
    'Foo (copy)'    → 'Foo (copy 2)'
    'Foo (copy 7)'  → 'Foo (copy 8)'
    """
    m = _COPY_RE.match(base)
    if not m:
        return f"{base} (copy)"
    stem = m.group("stem")
    n = int(m.group("n") or 1) + 1
    return f"{stem} (copy {n})"


def duplicate_task(task: Task) -> Task:
    """Return a deep copy of `task` with an auto-generated copy-name."""
    new = copy.deepcopy(task)
    new.name = next_copy_name(task.name)
    return new
