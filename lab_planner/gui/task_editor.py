"""Task editor frame: name, hours, requirements table, and a 7×24 slot grid."""
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
    is_weekend,
    is_work_hour,
)


# --- 7x24 slot grid ---------------------------------------------------------

class SlotGridWidget(tk.Frame):
    """A 7x24 click-to-cycle grid showing preferred / unavailable slots."""

    NEUTRAL, PREFERRED, UNAVAILABLE = 0, 1, 2
    NEUTRAL_WORK = "#ffffff"
    NEUTRAL_OFF_HOURS = "#ececec"   # light grey for off-hours weekday
    NEUTRAL_WEEKEND = "#dcdcdc"     # darker grey for weekend
    COLOURS_STATEFUL = {
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

        # Press-and-drag painting: left = unavailable, right = preferred,
        # middle = clear. Same handler for press and motion events.
        self.canvas.bind("<Button-1>",   self._paint_unavailable)
        self.canvas.bind("<B1-Motion>",  self._paint_unavailable)
        self.canvas.bind("<Button-3>",   self._paint_preferred)
        self.canvas.bind("<B3-Motion>",  self._paint_preferred)
        self.canvas.bind("<Button-2>",   self._paint_neutral)
        self.canvas.bind("<B2-Motion>",  self._paint_neutral)

        legend = tk.Frame(self)
        legend.pack(anchor="w", pady=(4, 0))
        for label, colour in [("Work hours", self.NEUTRAL_WORK),
                              ("Off-hours",  self.NEUTRAL_OFF_HOURS),
                              ("Weekend",    self.NEUTRAL_WEEKEND),
                              ("Preferred",  self.COLOURS_STATEFUL[self.PREFERRED]),
                              ("Unavailable", self.COLOURS_STATEFUL[self.UNAVAILABLE])]:
            sw = tk.Frame(legend, width=14, height=14, bg=colour,
                          highlightthickness=1, highlightbackground="#888")
            sw.pack(side="left", padx=(8, 2))
            tk.Label(legend, text=label).pack(side="left")
        tk.Label(legend,
                 text="   (drag with: left=unavailable  right=preferred  middle=clear)",
                 fg="#666").pack(side="left", padx=(20, 0))

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
                    fill=self._neutral_colour(slot), outline="#dddddd",
                )
                self._rid_by_slot[slot] = rid

    def _neutral_colour(self, slot: int) -> str:
        if is_weekend(slot):
            return self.NEUTRAL_WEEKEND
        if is_work_hour(slot):
            return self.NEUTRAL_WORK
        return self.NEUTRAL_OFF_HOURS

    def _colour_for(self, slot: int, state: int) -> str:
        if state in self.COLOURS_STATEFUL:
            return self.COLOURS_STATEFUL[state]
        return self._neutral_colour(slot)

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

    def _paint_unavailable(self, event):
        self._paint(event, self.UNAVAILABLE)

    def _paint_preferred(self, event):
        self._paint(event, self.PREFERRED)

    def _paint_neutral(self, event):
        self._paint(event, self.NEUTRAL)

    def _paint(self, event, state: int):
        slot = self._slot_at(event)
        if slot is None:
            return
        self._set(slot, state)

    def _set(self, slot: int, state: int):
        if self._states[slot] == state:
            return
        self._states[slot] = state
        self.canvas.itemconfig(self._rid_by_slot[slot],
                               fill=self._colour_for(slot, state))
        if self.on_change:
            self.on_change(slot, state)

    def load_from_task(self, task: Task):
        self._states = [self.NEUTRAL] * HORIZON
        for s in task.preferred_slots:
            self._states[s] = self.PREFERRED
        for s in task.unavailable_slots:
            self._states[s] = self.UNAVAILABLE
        for slot, rid in self._rid_by_slot.items():
            self.canvas.itemconfig(
                rid, fill=self._colour_for(slot, self._states[slot])
            )


# --- requirement edit dialog ------------------------------------------------

class RequirementDialog(simpledialog.Dialog):
    """Modal dialog to add/edit one (resource, quantity) requirement."""

    def __init__(self, parent, resources: list[Resource],
                 current: Optional[tuple[str, int]] = None,
                 forbidden: Optional[set[str]] = None,
                 title: str = "Requirement"):
        self.resources = resources
        self.current = current
        self.forbidden = forbidden or set()
        self.result: Optional[tuple[str, int]] = None
        super().__init__(parent, title=title)

    def body(self, master):
        choices = [r.name for r in self.resources
                   if r.name not in self.forbidden
                   or (self.current and self.current[0] == r.name)]
        tk.Label(master, text="Resource:").grid(row=0, column=0, sticky="e",
                                                 padx=4, pady=4)
        self.res_var = tk.StringVar(
            value=self.current[0] if self.current else (choices[0] if choices else "")
        )
        self.res_box = ttk.Combobox(master, textvariable=self.res_var,
                                     values=choices, state="readonly", width=14)
        self.res_box.grid(row=0, column=1, sticky="w", padx=4, pady=4)
        self.res_box.bind("<<ComboboxSelected>>", self._update_qty_max)

        tk.Label(master, text="Quantity:").grid(row=1, column=0, sticky="e",
                                                 padx=4, pady=4)
        self.qty_var = tk.IntVar(value=self.current[1] if self.current else 1)
        self.qty_spin = tk.Spinbox(master, from_=1, to=99,
                                    textvariable=self.qty_var, width=6)
        self.qty_spin.grid(row=1, column=1, sticky="w", padx=4, pady=4)
        self._update_qty_max()
        return self.res_box

    def _update_qty_max(self, *_args):
        name = self.res_var.get()
        for r in self.resources:
            if r.name == name:
                self.qty_spin.config(to=r.units)
                if self.qty_var.get() > r.units:
                    self.qty_var.set(r.units)
                break

    def apply(self):
        try:
            self.result = (self.res_var.get(), int(self.qty_var.get()))
        except ValueError as e:
            messagebox.showerror("Invalid quantity", str(e))
            self.result = None


# --- task editor frame ------------------------------------------------------

class TaskEditorFrame(tk.Frame):
    """Right-hand pane for editing the currently selected task."""

    def __init__(self, master, get_resources: Callable[[], list[Resource]],
                 on_dirty: Callable[[], None],
                 on_changed: Callable[[], None]):
        super().__init__(master)
        self._get_resources = get_resources
        self._on_dirty = on_dirty
        self._on_changed = on_changed  # called when name/hours/req changes (for list refresh)
        self._task: Optional[Task] = None
        self._building = False

        # name + hours row
        top = tk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(top, text="Task name:").pack(side="left")
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(top, textvariable=self.name_var, width=28)
        self.name_entry.pack(side="left", padx=(6, 16))
        self.name_var.trace_add("write", self._on_name_changed)

        tk.Label(top, text="Hours:").pack(side="left")
        self.hours_var = tk.IntVar(value=1)
        self.hours_spin = tk.Spinbox(top, from_=1, to=HORIZON, width=5,
                                       textvariable=self.hours_var,
                                       command=self._on_hours_changed)
        self.hours_spin.pack(side="left", padx=(6, 16))
        self.hours_var.trace_add("write", lambda *a: self._on_hours_changed())

        self.work_only_var = tk.BooleanVar(value=False)
        self.work_only_chk = tk.Checkbutton(
            top, text="Work hours only (Mon-Fri 08-18)",
            variable=self.work_only_var,
            command=self._on_work_only_changed,
        )
        self.work_only_chk.pack(side="left")

        # requirements table
        req_frame = tk.LabelFrame(self, text="Required resources")
        req_frame.pack(fill="x", padx=8, pady=4)
        cols = ("resource", "qty")
        self.req_tree = ttk.Treeview(req_frame, columns=cols,
                                       show="headings", height=5)
        self.req_tree.heading("resource", text="Resource")
        self.req_tree.heading("qty", text="Quantity")
        self.req_tree.column("resource", width=140, anchor="w")
        self.req_tree.column("qty", width=80, anchor="center")
        self.req_tree.pack(side="left", fill="both", expand=True,
                            padx=(4, 0), pady=4)

        btn_col = tk.Frame(req_frame)
        btn_col.pack(side="left", fill="y", padx=4, pady=4)
        tk.Button(btn_col, text="Add",  width=10,
                  command=self._add_requirement).pack(pady=2)
        tk.Button(btn_col, text="Edit", width=10,
                  command=self._edit_requirement).pack(pady=2)
        tk.Button(btn_col, text="Delete", width=10,
                  command=self._delete_requirement).pack(pady=2)
        self.req_tree.bind("<Double-1>", lambda e: self._edit_requirement())

        # slot grid
        grid_frame = tk.LabelFrame(self, text="Preferred / Unavailable slots")
        grid_frame.pack(fill="x", padx=8, pady=(4, 8))
        self.slot_grid = SlotGridWidget(grid_frame, on_change=self._on_grid_change)
        self.slot_grid.pack(padx=6, pady=6)

        self._set_enabled(False)

    # --- public ---

    def show_task(self, task: Optional[Task]):
        self._task = task
        if task is None:
            self._set_enabled(False)
            self._building = True
            self.name_var.set("")
            self.hours_var.set(1)
            self.work_only_var.set(False)
            self.req_tree.delete(*self.req_tree.get_children())
            self._building = False
            return
        self._set_enabled(True)
        self._building = True
        self.name_var.set(task.name)
        self.hours_var.set(task.hours)
        self.work_only_var.set(task.work_hours_only)
        self._refresh_requirements()
        self.slot_grid.load_from_task(task)
        self._building = False

    # --- events ---

    def _on_name_changed(self, *args):
        if self._building or self._task is None:
            return
        self._task.name = self.name_var.get()
        self._on_dirty()
        self._on_changed()

    def _on_hours_changed(self, *_a):
        if self._building or self._task is None:
            return
        try:
            h = int(self.hours_var.get())
        except (tk.TclError, ValueError):
            return
        if h < 1 or h > HORIZON:
            return
        self._task.hours = h
        self._on_dirty()
        self._on_changed()

    def _on_work_only_changed(self):
        if self._building or self._task is None:
            return
        self._task.work_hours_only = bool(self.work_only_var.get())
        self._on_dirty()

    def _on_grid_change(self, slot: int, state: int):
        if self._task is None:
            return
        self._task.preferred_slots.discard(slot)
        self._task.unavailable_slots.discard(slot)
        if state == SlotGridWidget.PREFERRED:
            self._task.preferred_slots.add(slot)
        elif state == SlotGridWidget.UNAVAILABLE:
            self._task.unavailable_slots.add(slot)
        self._on_dirty()

    def _add_requirement(self):
        if self._task is None:
            return
        forbidden = set(self._task.requirements.keys())
        dlg = RequirementDialog(self, self._get_resources(),
                                 forbidden=forbidden, title="Add requirement")
        if dlg.result is not None:
            res, qty = dlg.result
            self._task.requirements[res] = qty
            self._refresh_requirements()
            self._on_dirty()
            self._on_changed()

    def _edit_requirement(self):
        if self._task is None:
            return
        sel = self.req_tree.selection()
        if not sel:
            return
        idx = self.req_tree.index(sel[0])
        existing = list(self._task.requirements.items())
        res, qty = existing[idx]
        forbidden = set(self._task.requirements.keys()) - {res}
        dlg = RequirementDialog(self, self._get_resources(),
                                 current=(res, qty),
                                 forbidden=forbidden, title="Edit requirement")
        if dlg.result is not None:
            new_res, new_qty = dlg.result
            new = {}
            for r, q in existing:
                if r == res:
                    new[new_res] = new_qty
                else:
                    new[r] = q
            self._task.requirements = new
            self._refresh_requirements()
            self._on_dirty()
            self._on_changed()

    def _delete_requirement(self):
        if self._task is None:
            return
        sel = self.req_tree.selection()
        if not sel:
            return
        idx = self.req_tree.index(sel[0])
        keys = list(self._task.requirements.keys())
        if 0 <= idx < len(keys):
            del self._task.requirements[keys[idx]]
            self._refresh_requirements()
            self._on_dirty()
            self._on_changed()

    # --- helpers ---

    def _refresh_requirements(self):
        self.req_tree.delete(*self.req_tree.get_children())
        if self._task is None:
            return
        for res, qty in self._task.requirements.items():
            self.req_tree.insert("", "end", values=(res, qty))

    def _set_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.name_entry.config(state=state)
        self.hours_spin.config(state=state)
        self.work_only_chk.config(state=state)
