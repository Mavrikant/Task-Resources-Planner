"""Gantt-chart visualization of a `ScheduleResult` embedded in tkinter."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.figure import Figure
from matplotlib.patches import Patch

from ..models import (
    DAY_NAMES,
    HORIZON,
    HOURS_PER_DAY,
    Resource,
    ScheduleResult,
    Task,
    expand_units,
    is_weekend,
    is_work_hour,
    unit_label,
)


class GanttFrame(tk.Frame):
    """Embeds a matplotlib Gantt chart and a status line."""

    def __init__(self, master):
        super().__init__(master)
        self.fig: Figure = Figure(figsize=(12, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._draw_empty("Run Solve to produce a schedule.")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas, self)
        toolbar.update()

        self.status_var = tk.StringVar(value="No schedule yet.")
        ttk.Label(self, textvariable=self.status_var,
                  anchor="w").pack(fill="x", padx=8, pady=(0, 4))

    # --- public ---

    def show(self, result: ScheduleResult,
             tasks: list[Task], resources: list[Resource]):
        self.ax.clear()

        units = expand_units(resources)
        n_units = len(units)
        labels = [unit_label(units, uid) for uid, _, _ in units]

        # Background shading: weekends (darker) and weekday off-hours (lighter).
        for s, e in _consecutive_runs(lambda s: is_weekend(s)):
            self.ax.axvspan(s, e, facecolor="#bdbdbd", alpha=0.35, zorder=0)
        for s, e in _consecutive_runs(
            lambda s: not is_work_hour(s) and not is_weekend(s)
        ):
            self.ax.axvspan(s, e, facecolor="#d9d9d9", alpha=0.35, zorder=0)

        task_names = [t.name for t in tasks]
        # Use a 40-colour palette cycling tab20 + tab20b for many tasks.
        cmap_a = plt.get_cmap("tab20")
        cmap_b = plt.get_cmap("tab20b")
        n = max(len(task_names), 1)
        def _colour(i):
            return cmap_a(i % 20) if (i // 20) % 2 == 0 else cmap_b(i % 20)
        colour = {name: _colour(i) for i, name in enumerate(task_names)}

        for a in result.assignments:
            self.ax.broken_barh(
                [(a.start_slot, a.duration)],
                (a.unit_id - 0.4, 0.8),
                facecolors=colour.get(a.task_name, "#888888"),
                edgecolors="black", linewidth=0.5,
                zorder=2,
            )
            if a.duration >= 2:
                self.ax.text(
                    a.start_slot + a.duration / 2, a.unit_id,
                    a.task_name, ha="center", va="center",
                    fontsize=7, color="black",
                )

        self.ax.set_yticks(range(n_units))
        self.ax.set_yticklabels(labels, fontsize=8)
        self.ax.set_ylim(-0.6, n_units - 0.4)
        self.ax.invert_yaxis()

        self.ax.set_xlim(0, HORIZON)

        # Major ticks every 6 hours; bold day-name where hour-of-day == 0.
        major_step = 6
        major_ticks = list(range(0, HORIZON + 1, major_step))
        major_labels = []
        for t in major_ticks:
            if t == HORIZON:
                major_labels.append("+1w")
                continue
            day, hour_of_day = divmod(t, HOURS_PER_DAY)
            if hour_of_day == 0:
                major_labels.append(f"{DAY_NAMES[day]}\n{hour_of_day:02d}:00")
            else:
                major_labels.append(f"{hour_of_day:02d}:00")
        self.ax.set_xticks(major_ticks)
        self.ax.set_xticklabels(major_labels, fontsize=7)

        # Minor ticks every hour for fine grid + readability.
        self.ax.set_xticks(range(HORIZON + 1), minor=True)
        self.ax.grid(axis="x", which="major", linestyle="-",
                     color="#888", alpha=0.45)
        self.ax.grid(axis="x", which="minor", linestyle=":",
                     color="#cccccc", alpha=0.5)

        # Bold vertical separators at day boundaries on top of the grid.
        for d in range(1, 7):
            self.ax.axvline(d * HOURS_PER_DAY, color="#555",
                             linewidth=0.9, alpha=0.7, zorder=1)

        self.ax.set_xlabel("Hour of day  (Mon-Sun, 0-23)")
        self.ax.set_title("Lab equipment weekly schedule")

        # Legend: tasks plus the two background categories.
        handles = []
        if task_names:
            handles.extend(
                Patch(facecolor=colour[n], edgecolor="black", label=n)
                for n in task_names
            )
        handles.append(Patch(facecolor="#d9d9d9", alpha=0.35,
                             edgecolor="#888", label="Off-hours"))
        handles.append(Patch(facecolor="#bdbdbd", alpha=0.35,
                             edgecolor="#888", label="Weekend"))
        self.ax.legend(handles=handles, loc="upper right",
                       fontsize=7, ncol=min(4, len(handles)))

        self.fig.tight_layout()
        self.canvas.draw()

        self.status_var.set(
            f"Status: {result.status_name}   "
            f"Makespan: {result.makespan} h   "
            f"Solve time: {result.solve_time_s:.2f} s   "
            f"Reservations: {len(result.assignments)}"
        )

    def show_message(self, msg: str):
        self._draw_empty(msg)
        self.canvas.draw()
        self.status_var.set(msg)

    def _draw_empty(self, msg: str):
        self.ax.clear()
        self.ax.text(0.5, 0.5, msg, ha="center", va="center",
                     transform=self.ax.transAxes, fontsize=12, color="#666")
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for s in self.ax.spines.values():
            s.set_visible(False)


def _consecutive_runs(predicate):
    """Yield (start, end) pairs of contiguous slots where `predicate(slot)` is True."""
    start = None
    for s in range(HORIZON):
        if predicate(s):
            if start is None:
                start = s
        elif start is not None:
            yield start, s
            start = None
    if start is not None:
        yield start, HORIZON
