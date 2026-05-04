"""Team editor frame: name, tasks list, and a clickable 7×24 slot grid."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from ..models import (
    DAY_NAMES,
    HORIZON,
    HOURS_PER_DAY,
    Resource,
    Task,
    Team,
)


# --- 7x24 slot grid ---------------------------------------------------------

class SlotGridWidget(tk.Frame):
    """A 7x24 click-to-cycle grid showing preferred / unavailable slots."""

    NEUTRAL, PREFERRED, UNAVAILABLE = 0, 1, 2
    COLOURS = {
        NEUTRAL: "#ffffff",
        PREFERRED: "#a8e6a3",
        UNAVAILABLE: "#ff9b9b",
    }
    CELL_W = 28
    CELL_H = 22
    LABEL_W = 42
    LABEL_H = 18

    def __init__(self, master,
                 on_change: Optional[Callable[[int, int], None]] = None):
        super().__init__(master)
        self.on_change = on_change
        self._states = [self.NEUTRAL] * HORIZON
        self._rid_by_slot: dict[int, int] = {}

        w = self.LABEL_W + HOURS_PER_DAY * self.CELL_W + 1
        h = self.LABEL_H + 7 * self.CELL_H + 1
        self.canvas = tk.Canvas(self, width=w, height=h,
                                bg="white", highlightthickness=0)
        self.canvas.pack()
        self._draw_chrome()
        self._draw_cells()

        self.canvas.bind("<Button-1>", self._on_left_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

        legend = tk.Frame(self)
        legend.pack(anchor="w", pady=(4, 0))
        for label, colour in [("Neutral", self.COLOURS[self.NEUTRAL]),
                              ("Preferred", self.COLOURS[self.PREFERRED]),
                              ("Unavailable", self.COLOURS[self.UNAVAILABLE])]:
            sw = tk.Frame(legend, width=14, height=14, bg=colour,
                          highlightthickness=1, highlightbackground="#888")
            sw.pack(side="left", padx=(8, 2))
            tk.Label(legend, text=label).pack(side="left")
        tk.Label(legend, text="   (left-click cycles, right-click clears)",
                 fg="#666").pack(side="left", padx=(20, 0))

    # --- drawing ---

    def _draw_chrome(self):
        for d, name in enumerate(DAY_NAMES):
            y = self.LABEL_H + d * self.CELL_H + self.CELL_H / 2
            self.canvas.create_text(self.LABEL_W / 2, y, text=name, anchor="center",
                                    font=("TkDefaultFont", 9, "bold"))
        for h in range(HOURS_PER_DAY):
            x = self.LABEL_W + h * self.CELL_W + self.CELL_W / 2
            self.canvas.create_text(x, self.LABEL_H / 2, text=str(h),
                                    anchor="center", font=("TkDefaultFont", 8))

    def _draw_cells(self):
        for d in range(7):
            for h in range(HOURS_PER_DAY):
                slot = d * HOURS_PER_DAY + h
                x0 = self.LABEL_W + h * self.CELL_W
                y0 = self.LABEL_H + d * self.CELL_H
                rid = self.canvas.create_rectangle(
                    x0, y0, x0 + self.CELL_W, y0 + self.CELL_H,
                    fill=self.COLOURS[self.NEUTRAL], outline="#dddddd",
                )
                self._rid_by_slot[slot] = rid

    # --- interaction ---

    def _slot_at(self, event) -> Optional[int]:
        x = event.x - self.LABEL_W
        y = event.y - self.LABEL_H
        if x < 0 or y < 0:
            return None
        h = int(x // self.CELL_W)
        d = int(y // self.CELL_H)
        if 0 <= h < HOURS_PER_DAY and 0 <= d < 7:
            return d * HOURS_PER_DAY + h
        return None

    def _on_left_click(self, event):
        slot = self._slot_at(event)
        if slot is None:
            return
        self._set(slot, (self._states[slot] + 1) % 3)

    def _on_right_click(self, event):
        slot = self._slot_at(event)
        if slot is None:
            return
        self._set(slot, self.NEUTRAL)

    def _set(self, slot: int, state: int):
        if self._states[slot] == state:
            return
        self._states[slot] = state
        self.canvas.itemconfig(self._rid_by_slot[slot],
                               fill=self.COLOURS[state])
        if self.on_change:
            self.on_change(slot, state)

    # --- public API ---

    def load_from_team(self, team: Team):
        self._states = [self.NEUTRAL] * HORIZON
        for s in team.preferred_slots:
            self._states[s] = self.PREFERRED
        for s in team.unavailable_slots:
            self._states[s] = self.UNAVAILABLE
        for slot, rid in self._rid_by_slot.items():
            self.canvas.itemconfig(rid, fill=self.COLOURS[self._states[slot]])

    def write_to_team(self, team: Team):
        team.preferred_slots = {s for s, st in enumerate(self._states)
                                if st == self.PREFERRED}
        team.unavailable_slots = {s for s, st in enumerate(self._states)
                                  if st == self.UNAVAILABLE}


# --- task editor dialog -----------------------------------------------------

class TaskDialog(simpledialog.Dialog):
    """Modal dialog for creating or editing a Task."""

    def __init__(self, parent, resources: list[Resource],
                 task: Optional[Task] = None, title: str = "Task"):
        self.resources = resources
        self.task = task
        self.result: Optional[Task] = None
        super().__init__(parent, title=title)

    def body(self, master):
        tk.Label(master, text="Resource:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.resource_var = tk.StringVar(value=self.task.resource if self.task
                                         else self.resources[0].name)
        self.resource_box = ttk.Combobox(
            master, textvariable=self.resource_var,
            values=[r.name for r in self.resources], state="readonly", width=14,
        )
        self.resource_box.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        tk.Label(master, text="Hours:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self.hours_var = tk.IntVar(value=self.task.hours if self.task else 1)
        tk.Spinbox(master, from_=1, to=HORIZON, textvariable=self.hours_var,
                   width=6).grid(row=1, column=1, sticky="w", padx=4, pady=4)

        self.split_var = tk.BooleanVar(value=self.task.allow_split if self.task else True)
        tk.Checkbutton(master, text="Allow split into 1-hour chunks",
                       variable=self.split_var).grid(row=2, column=0, columnspan=2,
                                                     sticky="w", padx=4, pady=4)
        return self.resource_box

    def apply(self):
        try:
            self.result = Task(
                resource=self.resource_var.get(),
                hours=int(self.hours_var.get()),
                allow_split=bool(self.split_var.get()),
            )
        except ValueError as e:
            messagebox.showerror("Invalid task", str(e))
            self.result = None


# --- team editor frame ------------------------------------------------------

class TeamEditorFrame(tk.Frame):
    """Right-hand pane for editing the currently selected team."""

    def __init__(self, master, get_resources: Callable[[], list[Resource]],
                 on_dirty: Callable[[], None]):
        super().__init__(master)
        self._get_resources = get_resources
        self._on_dirty = on_dirty
        self._team: Optional[Team] = None
        self._building = False

        # name row
        name_row = tk.Frame(self)
        name_row.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(name_row, text="Team name:").pack(side="left")
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(name_row, textvariable=self.name_var, width=30)
        self.name_entry.pack(side="left", padx=(6, 0))
        self.name_var.trace_add("write", self._on_name_changed)

        # tasks list
        tasks_frame = tk.LabelFrame(self, text="Tasks")
        tasks_frame.pack(fill="x", padx=8, pady=4)
        cols = ("resource", "hours", "split")
        self.tree = ttk.Treeview(tasks_frame, columns=cols, show="headings", height=6)
        self.tree.heading("resource", text="Resource")
        self.tree.heading("hours", text="Hours")
        self.tree.heading("split", text="Split?")
        self.tree.column("resource", width=140, anchor="w")
        self.tree.column("hours", width=70, anchor="center")
        self.tree.column("split", width=70, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)

        btn_col = tk.Frame(tasks_frame)
        btn_col.pack(side="left", fill="y", padx=4, pady=4)
        tk.Button(btn_col, text="Add",  width=10, command=self._add_task).pack(pady=2)
        tk.Button(btn_col, text="Edit", width=10, command=self._edit_task).pack(pady=2)
        tk.Button(btn_col, text="Delete", width=10, command=self._delete_task).pack(pady=2)
        self.tree.bind("<Double-1>", lambda e: self._edit_task())

        # slot grid
        grid_frame = tk.LabelFrame(self, text="Preferred / Unavailable slots")
        grid_frame.pack(fill="x", padx=8, pady=(4, 8))
        self.slot_grid = SlotGridWidget(grid_frame, on_change=self._on_grid_change)
        self.slot_grid.pack(padx=6, pady=6)

        self._set_enabled(False)

    # --- public ---

    def show_team(self, team: Optional[Team]):
        self._team = team
        if team is None:
            self._set_enabled(False)
            self._building = True
            self.name_var.set("")
            self.tree.delete(*self.tree.get_children())
            self._building = False
            return
        self._set_enabled(True)
        self._building = True
        self.name_var.set(team.name)
        self._refresh_tasks()
        self.slot_grid.load_from_team(team)
        self._building = False

    # --- events ---

    def _on_name_changed(self, *args):
        if self._building or self._team is None:
            return
        self._team.name = self.name_var.get()
        self._on_dirty()

    def _on_grid_change(self, slot: int, state: int):
        if self._team is None:
            return
        self._team.preferred_slots.discard(slot)
        self._team.unavailable_slots.discard(slot)
        if state == SlotGridWidget.PREFERRED:
            self._team.preferred_slots.add(slot)
        elif state == SlotGridWidget.UNAVAILABLE:
            self._team.unavailable_slots.add(slot)
        self._on_dirty()

    def _add_task(self):
        if self._team is None:
            return
        dlg = TaskDialog(self, self._get_resources(), title="Add task")
        if dlg.result is not None:
            self._team.tasks.append(dlg.result)
            self._refresh_tasks()
            self._on_dirty()

    def _edit_task(self):
        if self._team is None:
            return
        idx = self._selected_index()
        if idx is None:
            return
        dlg = TaskDialog(self, self._get_resources(),
                         task=self._team.tasks[idx], title="Edit task")
        if dlg.result is not None:
            self._team.tasks[idx] = dlg.result
            self._refresh_tasks()
            self._on_dirty()

    def _delete_task(self):
        if self._team is None:
            return
        idx = self._selected_index()
        if idx is None:
            return
        del self._team.tasks[idx]
        self._refresh_tasks()
        self._on_dirty()

    # --- helpers ---

    def _selected_index(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.index(sel[0])

    def _refresh_tasks(self):
        self.tree.delete(*self.tree.get_children())
        if self._team is None:
            return
        for t in self._team.tasks:
            self.tree.insert("", "end",
                             values=(t.resource, t.hours,
                                     "yes" if t.allow_split else "no"))

    def _set_enabled(self, enabled: bool):
        self.name_entry.config(state="normal" if enabled else "disabled")
