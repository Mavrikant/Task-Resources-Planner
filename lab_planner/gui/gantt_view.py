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
    Team,
    expand_units,
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
             teams: list[Team], resources: list[Resource]):
        self.ax.clear()

        units = expand_units(resources)
        n_units = len(units)
        labels = [unit_label(units, uid) for uid, _, _ in units]

        team_names = [t.name for t in teams]
        cmap = plt.get_cmap("tab20", max(len(team_names), 1))
        colour = {name: cmap(i % cmap.N) for i, name in enumerate(team_names)}

        for a in result.assignments:
            self.ax.broken_barh(
                [(a.start_slot, a.duration)],
                (a.unit_id - 0.4, 0.8),
                facecolors=colour.get(a.team_name, "#888888"),
                edgecolors="black", linewidth=0.5,
            )
            if a.duration >= 2:
                self.ax.text(
                    a.start_slot + a.duration / 2, a.unit_id,
                    a.team_name, ha="center", va="center",
                    fontsize=7, color="black",
                )

        # axes
        self.ax.set_yticks(range(n_units))
        self.ax.set_yticklabels(labels, fontsize=8)
        self.ax.set_ylim(-0.6, n_units - 0.4)
        self.ax.invert_yaxis()

        self.ax.set_xlim(0, HORIZON)
        self.ax.set_xticks(range(0, HORIZON + 1, HOURS_PER_DAY))
        self.ax.set_xticklabels(
            [f"{name}\n{d*HOURS_PER_DAY}h" for d, name in enumerate(DAY_NAMES)] + ["+1w"],
            fontsize=8,
        )
        self.ax.set_xticks(range(HORIZON + 1), minor=True)
        self.ax.grid(axis="x", which="major", linestyle="-",
                     color="#888", alpha=0.6)
        self.ax.grid(axis="x", which="minor", linestyle=":",
                     color="#cccccc", alpha=0.6)
        self.ax.set_xlabel("Hour of week")
        self.ax.set_title("Lab equipment weekly schedule")

        if team_names:
            handles = [Patch(facecolor=colour[n], edgecolor="black", label=n)
                       for n in team_names]
            self.ax.legend(handles=handles, loc="upper right",
                           fontsize=8, ncol=min(4, len(team_names)))

        self.fig.tight_layout()
        self.canvas.draw()

        self.status_var.set(
            f"Status: {result.status_name}   "
            f"Makespan: {result.makespan} h   "
            f"Solve time: {result.solve_time_s:.2f} s   "
            f"Tasks: {len(result.assignments)}"
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
