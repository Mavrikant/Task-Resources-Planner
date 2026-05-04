"""Main application window with Resources / Teams / Schedule tabs."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from ..models import DEFAULT_RESOURCES, Resource, ScheduleResult, Team
from ..persistence import load_project, save_project
from ..solver import build_and_solve
from .gantt_view import GanttFrame
from .team_editor import TeamEditorFrame


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


# --- Teams tab -------------------------------------------------------------

class TeamsFrame(tk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app

        # left: team list
        left = tk.Frame(self)
        left.pack(side="left", fill="y", padx=8, pady=8)
        tk.Label(left, text="Teams", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.team_list = tk.Listbox(left, exportselection=False, width=22, height=20)
        self.team_list.pack(fill="y", expand=True)
        self.team_list.bind("<<ListboxSelect>>", self._on_select)

        btn_row = tk.Frame(left)
        btn_row.pack(fill="x", pady=4)
        tk.Button(btn_row, text="Add team", command=self._add_team).pack(side="left")
        tk.Button(btn_row, text="Delete", command=self._delete_team).pack(side="left", padx=4)

        # right: editor + solve button
        right = tk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        self.editor = TeamEditorFrame(
            right,
            get_resources=lambda: self.app.resources,
            on_dirty=self.app.mark_dirty,
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
        self.team_list.delete(0, "end")
        for t in self.app.teams:
            self.team_list.insert("end", t.name)
        # Re-show currently selected team (or clear)
        sel_idx = self._current_index()
        if sel_idx is None:
            self.editor.show_team(None)
        else:
            self.editor.show_team(self.app.teams[sel_idx])

    def select(self, idx: int):
        self.team_list.selection_clear(0, "end")
        if 0 <= idx < len(self.app.teams):
            self.team_list.selection_set(idx)
            self.team_list.see(idx)
            self.editor.show_team(self.app.teams[idx])

    # --- events ---

    def _on_select(self, _event):
        idx = self._current_index()
        if idx is None:
            self.editor.show_team(None)
        else:
            self.editor.show_team(self.app.teams[idx])

    def _add_team(self):
        name = simpledialog.askstring("Add team", "Team name:", parent=self)
        if not name:
            return
        try:
            team = Team(name=name.strip())
        except ValueError as e:
            messagebox.showerror("Invalid name", str(e))
            return
        self.app.teams.append(team)
        self.app.mark_dirty()
        self.refresh()
        self.select(len(self.app.teams) - 1)

    def _delete_team(self):
        idx = self._current_index()
        if idx is None:
            return
        team = self.app.teams[idx]
        if not messagebox.askyesno("Delete team",
                                    f"Delete team {team.name!r}?"):
            return
        del self.app.teams[idx]
        self.app.mark_dirty()
        self.refresh()

    def _current_index(self) -> Optional[int]:
        sel = self.team_list.curselection()
        if not sel:
            return None
        return int(sel[0])


# --- Schedule tab ----------------------------------------------------------

class ScheduleFrame(tk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app
        self.gantt = GanttFrame(self)
        self.gantt.pack(fill="both", expand=True, padx=4, pady=4)

    def show(self, result: ScheduleResult):
        if result.feasible:
            self.gantt.show(result, self.app.teams, self.app.resources)
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

        self.teams: list[Team] = []
        self.resources: list[Resource] = list(DEFAULT_RESOURCES)
        self.current_file: Optional[Path] = None
        self.last_result: Optional[ScheduleResult] = None
        self._dirty = False

        self._build_menu()
        self._build_tabs()
        self._update_title()

    # --- menu / tabs ---

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
        self.teams_tab = TeamsFrame(nb, self)
        self.schedule_tab = ScheduleFrame(nb, self)

        nb.add(self.resources_tab, text="Resources")
        nb.add(self.teams_tab,     text="Teams")
        nb.add(self.schedule_tab,  text="Schedule")
        nb.select(self.teams_tab)

    # --- file ops ---

    def new_project(self):
        if not self._confirm_discard():
            return
        self.teams = []
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
            teams, resources = load_project(path)
        except Exception as e:
            messagebox.showerror("Could not open", str(e))
            return
        self.teams = teams
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
            save_project(self.current_file, self.teams, self.resources)
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
        if not self.teams:
            messagebox.showwarning("Nothing to solve",
                                    "Add at least one team with tasks first.")
            return
        if not any(t.tasks for t in self.teams):
            messagebox.showwarning("Nothing to solve",
                                    "No team has any tasks defined.")
            return

        self.teams_tab.status_var.set("Solving…")
        self.teams_tab.solve_btn.config(state="disabled")
        self.update_idletasks()

        result_holder: dict = {}

        def worker():
            result_holder["result"] = build_and_solve(
                self.teams, self.resources, time_limit_s=20,
            )

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def poll():
            if thread.is_alive():
                self.after(100, poll)
                return
            self.teams_tab.solve_btn.config(state="normal")
            result: ScheduleResult = result_holder["result"]
            self.last_result = result
            if result.feasible:
                self.teams_tab.status_var.set(
                    f"OK — makespan {result.makespan} h "
                    f"({result.solve_time_s:.2f} s)"
                )
                self.schedule_tab.show(result)
                self.notebook.select(self.schedule_tab)
            else:
                self.teams_tab.status_var.set(
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
        self.teams_tab.refresh()
        self._update_title()

    def _update_title(self):
        name = self.current_file.name if self.current_file else "(unsaved)"
        mark = "*" if self._dirty else ""
        self.title(f"Lab Equipment Weekly Scheduler — {name}{mark}")
