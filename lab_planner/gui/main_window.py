"""Main application window with Resources / Tasks / Schedule tabs."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from ..models import (
    DEFAULT_RESOURCES,
    Resource,
    ScheduleResult,
    Task,
    format_requirements,
)
from ..persistence import load_project, save_project
from ..solver import build_and_solve
from .gantt_view import GanttFrame
from .task_editor import TaskEditorFrame


# --- Resources tab ---------------------------------------------------------

class ResourcesFrame(tk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app

        toolbar = tk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=8)
        tk.Label(toolbar, text="Equipment pool",
                 font=("TkDefaultFont", 11, "bold")).pack(side="left")
        tk.Button(toolbar, text="Edit unit count…",
                  command=self._edit).pack(side="right")

        cols = ("name", "units")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=15)
        self.tree.heading("name", text="Resource")
        self.tree.heading("units", text="Units")
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("units", width=100, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree.bind("<Double-1>", lambda e: self._edit())

        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.app.resources:
            self.tree.insert("", "end", values=(r.name, r.units))

    def _edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        r = self.app.resources[idx]
        new_count = simpledialog.askinteger(
            "Edit unit count", f"Number of units for {r.name!r}:",
            initialvalue=r.units, minvalue=1, maxvalue=99, parent=self,
        )
        if new_count is None:
            return
        try:
            self.app.resources[idx] = Resource(r.name, new_count)
        except ValueError as e:
            messagebox.showerror("Invalid value", str(e))
            return
        self.refresh()
        self.app.mark_dirty()


# --- Tasks tab -------------------------------------------------------------

class TasksFrame(tk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app

        # left: task list
        left = tk.Frame(self)
        left.pack(side="left", fill="y", padx=8, pady=8)
        tk.Label(left, text="Tasks", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        cols = ("name", "summary", "hours")
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                  height=20, selectmode="browse")
        self.tree.heading("name", text="Name")
        self.tree.heading("summary", text="Resources")
        self.tree.heading("hours", text="h")
        self.tree.column("name", width=160, anchor="w")
        self.tree.column("summary", width=240, anchor="w")
        self.tree.column("hours", width=42, anchor="center")
        self.tree.pack(fill="y", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        btn_row = tk.Frame(left)
        btn_row.pack(fill="x", pady=4)
        tk.Button(btn_row, text="Add task", command=self._add_task).pack(side="left")
        tk.Button(btn_row, text="Delete", command=self._delete_task).pack(side="left", padx=4)

        # right: editor + solve button
        right = tk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        self.editor = TaskEditorFrame(
            right,
            get_resources=lambda: self.app.resources,
            on_dirty=self.app.mark_dirty,
            on_changed=self._refresh_selected_row,
        )
        self.editor.pack(fill="both", expand=True)

        solve_row = tk.Frame(right)
        solve_row.pack(fill="x", pady=(8, 0))
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(solve_row, textvariable=self.status_var,
                 fg="#666").pack(side="left")
        self.solve_btn = tk.Button(solve_row, text="Solve schedule",
                                    command=self.app.run_solver,
                                    font=("TkDefaultFont", 10, "bold"))
        self.solve_btn.pack(side="right")

        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for t in self.app.tasks:
            self.tree.insert("", "end",
                              values=(t.name,
                                      format_requirements(t.requirements),
                                      t.hours))
        sel_idx = self._current_index()
        if sel_idx is None:
            self.editor.show_task(None)
        else:
            self.editor.show_task(self.app.tasks[sel_idx])

    def select(self, idx: int):
        children = self.tree.get_children()
        self.tree.selection_remove(self.tree.selection())
        if 0 <= idx < len(children):
            iid = children[idx]
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)

    # --- events ---

    def _on_select(self, _event):
        idx = self._current_index()
        if idx is None:
            self.editor.show_task(None)
        else:
            self.editor.show_task(self.app.tasks[idx])

    def _refresh_selected_row(self):
        """Rewrite just the selected task's row when the editor changes name/hours/req."""
        idx = self._current_index()
        if idx is None:
            return
        children = self.tree.get_children()
        if 0 <= idx < len(children):
            t = self.app.tasks[idx]
            self.tree.item(children[idx],
                            values=(t.name,
                                    format_requirements(t.requirements),
                                    t.hours))

    def _add_task(self):
        if not self.app.resources:
            messagebox.showerror("No resources",
                                  "Add at least one resource first.")
            return
        name = simpledialog.askstring("Add task", "Task name:", parent=self)
        if not name:
            return
        first_res = self.app.resources[0].name
        try:
            task = Task(name=name.strip(),
                         requirements={first_res: 1}, hours=1)
        except ValueError as e:
            messagebox.showerror("Invalid task", str(e))
            return
        self.app.tasks.append(task)
        self.app.mark_dirty()
        self.refresh()
        self.select(len(self.app.tasks) - 1)

    def _delete_task(self):
        idx = self._current_index()
        if idx is None:
            return
        task = self.app.tasks[idx]
        if not messagebox.askyesno("Delete task",
                                    f"Delete task {task.name!r}?"):
            return
        del self.app.tasks[idx]
        self.app.mark_dirty()
        self.refresh()

    def _current_index(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.index(sel[0])


# --- Schedule tab ----------------------------------------------------------

class ScheduleFrame(tk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app
        self.gantt = GanttFrame(self)
        self.gantt.pack(fill="both", expand=True, padx=4, pady=4)

    def show(self, result: ScheduleResult):
        if result.feasible:
            self.gantt.show(result, self.app.tasks, self.app.resources)
        else:
            self.gantt.show_message(
                f"Infeasible: {result.status_name}\n{result.diagnostic}"
            )


# --- Main app --------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lab Equipment Weekly Scheduler")
        self.geometry("1280x820")
        self.minsize(1100, 720)

        self.tasks: list[Task] = []
        self.resources: list[Resource] = list(DEFAULT_RESOURCES)
        self.current_file: Optional[Path] = None
        self.last_result: Optional[ScheduleResult] = None
        self._dirty = False

        self._build_menu()
        self._build_tabs()
        self._update_title()

    def _build_menu(self):
        menu = tk.Menu(self)
        self.config(menu=menu)
        filemenu = tk.Menu(menu, tearoff=0)
        filemenu.add_command(label="New project",  command=self.new_project)
        filemenu.add_command(label="Open…",         command=self.open_project)
        filemenu.add_command(label="Save",          command=self.save_project)
        filemenu.add_command(label="Save as…",      command=self.save_as_project)
        filemenu.add_separator()
        filemenu.add_command(label="Quit",          command=self._on_quit)
        menu.add_cascade(label="File", menu=filemenu)
        self.protocol("WM_DELETE_WINDOW", self._on_quit)

    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.notebook = nb

        self.resources_tab = ResourcesFrame(nb, self)
        self.tasks_tab = TasksFrame(nb, self)
        self.schedule_tab = ScheduleFrame(nb, self)

        nb.add(self.resources_tab, text="Resources")
        nb.add(self.tasks_tab,     text="Tasks")
        nb.add(self.schedule_tab,  text="Schedule")
        nb.select(self.tasks_tab)

    # --- file ops ---

    def new_project(self):
        if not self._confirm_discard():
            return
        self.tasks = []
        self.resources = list(DEFAULT_RESOURCES)
        self.current_file = None
        self.last_result = None
        self._dirty = False
        self._refresh_all()
        self.schedule_tab.gantt.show_message("Run Solve to produce a schedule.")

    def open_project(self):
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="Open project",
            filetypes=[("Lab plan JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            tasks, resources = load_project(path)
        except Exception as e:
            messagebox.showerror("Could not open", str(e))
            return
        self.tasks = tasks
        self.resources = resources
        self.current_file = Path(path)
        self.last_result = None
        self._dirty = False
        self._refresh_all()

    def save_project(self):
        if self.current_file is None:
            self.save_as_project()
            return
        try:
            save_project(self.current_file, self.tasks, self.resources)
        except Exception as e:
            messagebox.showerror("Could not save", str(e))
            return
        self._dirty = False
        self._update_title()

    def save_as_project(self):
        path = filedialog.asksaveasfilename(
            title="Save project as",
            defaultextension=".json",
            filetypes=[("Lab plan JSON", "*.json")],
        )
        if not path:
            return
        self.current_file = Path(path)
        self.save_project()

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        choice = messagebox.askyesnocancel(
            "Unsaved changes",
            "Save changes to current project before continuing?",
        )
        if choice is None:
            return False
        if choice:
            self.save_project()
            return not self._dirty
        return True

    def _on_quit(self):
        if self._confirm_discard():
            self.destroy()

    # --- solver ---

    def run_solver(self):
        if not self.tasks:
            messagebox.showwarning("Nothing to solve",
                                    "Add at least one task first.")
            return

        self.tasks_tab.status_var.set("Solving…")
        self.tasks_tab.solve_btn.config(state="disabled")
        self.update_idletasks()

        result_holder: dict = {}

        def worker():
            result_holder["result"] = build_and_solve(
                self.tasks, self.resources, time_limit_s=20,
            )

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def poll():
            if thread.is_alive():
                self.after(100, poll)
                return
            self.tasks_tab.solve_btn.config(state="normal")
            result: ScheduleResult = result_holder["result"]
            self.last_result = result
            if result.feasible:
                self.tasks_tab.status_var.set(
                    f"OK — makespan {result.makespan} h "
                    f"({result.solve_time_s:.2f} s)"
                )
                self.schedule_tab.show(result)
                self.notebook.select(self.schedule_tab)
            else:
                self.tasks_tab.status_var.set(
                    f"{result.status_name}: {result.diagnostic}"
                )
                messagebox.showerror(
                    "Schedule infeasible",
                    f"Status: {result.status_name}\n\n{result.diagnostic}",
                )

        self.after(100, poll)

    # --- helpers ---

    def mark_dirty(self):
        self._dirty = True
        self._update_title()

    def _refresh_all(self):
        self.resources_tab.refresh()
        self.tasks_tab.refresh()
        self._update_title()

    def _update_title(self):
        name = self.current_file.name if self.current_file else "(unsaved)"
        mark = "*" if self._dirty else ""
        self.title(f"Lab Equipment Weekly Scheduler — {name}{mark}")
