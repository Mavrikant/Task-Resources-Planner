"""Main application window with Resources / Tasks / Schedule tabs."""
from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from .. import APP_NAME, ICON_PNG_PATH, __version__
from ..models import (
    Resource,
    ScheduleResult,
    Task,
    duplicate_task,
    format_deadline,
    format_requirements,
)
from ..persistence import (
    load_default_pool,
    load_pool,
    load_project,
    save_pool,
    save_project,
)
from ..solver import build_and_solve
from .gantt_view import GanttFrame
from .task_editor import TaskEditorFrame

# Platform-correct modifier for app-level shortcuts.
# - Tk bind syntax uses "Command" on macOS, "Control" elsewhere.
# - Menu accelerator strings use "Cmd" / "Ctrl".
if sys.platform == "darwin":
    _MOD_KEY = "Command"
    _MOD_LABEL = "Cmd"
else:
    _MOD_KEY = "Control"
    _MOD_LABEL = "Ctrl"


# --- Resources tab ---------------------------------------------------------

class EquipmentDialog(simpledialog.Dialog):
    """Modal dialog to add or edit a resource type (name + units)."""

    def __init__(self, parent,
                 current: Optional[Resource] = None,
                 forbidden_names: Optional[set[str]] = None,
                 title: str = "Equipment"):
        self.current = current
        self.forbidden = forbidden_names or set()
        self.result: Optional[Resource] = None
        super().__init__(parent, title=title)

    def body(self, master):
        tk.Label(master, text="Name:").grid(row=0, column=0, sticky="e",
                                             padx=4, pady=4)
        self.name_var = tk.StringVar(value=self.current.name if self.current else "")
        self.name_entry = tk.Entry(master, textvariable=self.name_var, width=18)
        self.name_entry.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        tk.Label(master, text="Units:").grid(row=1, column=0, sticky="e",
                                              padx=4, pady=4)
        self.units_var = tk.IntVar(value=self.current.units if self.current else 1)
        tk.Spinbox(master, from_=1, to=99, textvariable=self.units_var,
                   width=6).grid(row=1, column=1, sticky="w", padx=4, pady=4)
        return self.name_entry

    def apply(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Invalid name", "Name cannot be empty.")
            self.result = None
            return
        if name in self.forbidden:
            messagebox.showerror("Duplicate name",
                                  f"An equipment named {name!r} already exists.")
            self.result = None
            return
        try:
            self.result = Resource(name, int(self.units_var.get()))
        except ValueError as e:
            messagebox.showerror("Invalid value", str(e))
            self.result = None


class ResourcesFrame(tk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app

        toolbar = tk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=8)
        tk.Label(toolbar, text="Equipment pool",
                 font=("TkDefaultFont", 11, "bold")).pack(side="left")

        right_btns = tk.Frame(toolbar)
        right_btns.pack(side="right")
        tk.Button(right_btns, text="Add…",     command=self._add).pack(side="left", padx=2)
        tk.Button(right_btns, text="Edit…",    command=self._edit).pack(side="left", padx=2)
        tk.Button(right_btns, text="Delete",   command=self._delete).pack(side="left", padx=2)
        tk.Frame(right_btns, width=14).pack(side="left")
        tk.Button(right_btns, text="Import pool…", command=self._import_pool).pack(side="left", padx=2)
        tk.Button(right_btns, text="Export pool…", command=self._export_pool).pack(side="left", padx=2)

        cols = ("name", "units")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=15)
        self.tree.heading("name", text="Resource")
        self.tree.heading("units", text="Units")
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("units", width=100, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree.bind("<Double-1>", lambda e: self._edit())

        hint = tk.Label(self, fg="#666", anchor="w",
                        text=("Equipment pool defines all available equipment types and their "
                              "unit counts. Pools can be loaded/saved separately from projects."))
        hint.pack(fill="x", padx=8, pady=(0, 8))

        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.app.resources:
            self.tree.insert("", "end", values=(r.name, r.units))

    def _selected_index(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.index(sel[0])

    def _add(self):
        forbidden = {r.name for r in self.app.resources}
        dlg = EquipmentDialog(self, forbidden_names=forbidden,
                                title="Add equipment")
        if dlg.result is None:
            return
        self.app.resources.append(dlg.result)
        self.refresh()
        self.app.mark_dirty()

    def _edit(self):
        idx = self._selected_index()
        if idx is None:
            return
        r = self.app.resources[idx]
        forbidden = {x.name for x in self.app.resources} - {r.name}
        dlg = EquipmentDialog(self, current=r, forbidden_names=forbidden,
                                title="Edit equipment")
        if dlg.result is None:
            return
        # If the name changed, update every task that referred to the old name.
        if dlg.result.name != r.name:
            for t in self.app.tasks:
                if r.name in t.requirements:
                    t.requirements[dlg.result.name] = t.requirements.pop(r.name)
        self.app.resources[idx] = dlg.result
        self.refresh()
        self.app.tasks_tab.refresh()
        self.app.mark_dirty()

    def _delete(self):
        idx = self._selected_index()
        if idx is None:
            return
        r = self.app.resources[idx]
        in_use_by = [t.name for t in self.app.tasks if r.name in t.requirements]
        if in_use_by:
            messagebox.showerror(
                "Cannot delete",
                f"{r.name!r} is required by: " + ", ".join(in_use_by[:5])
                + (" …" if len(in_use_by) > 5 else "")
                + "\n\nRemove it from those tasks first.",
            )
            return
        if not messagebox.askyesno("Delete equipment",
                                    f"Delete equipment type {r.name!r}?"):
            return
        del self.app.resources[idx]
        self.refresh()
        self.app.mark_dirty()

    def _import_pool(self):
        path = filedialog.askopenfilename(
            title="Import equipment pool",
            filetypes=[("Equipment-pool JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            pool = load_pool(path)
        except Exception as e:
            messagebox.showerror("Could not import pool", str(e))
            return
        # Warn if any current task would be orphaned.
        new_names = {r.name for r in pool}
        orphans = [(t.name, missing) for t in self.app.tasks
                   for missing in t.requirements
                   if missing not in new_names]
        if orphans:
            lines = [f"  • {tn}: needs {res}" for tn, res in orphans[:8]]
            if not messagebox.askyesno(
                "Tasks reference missing equipment",
                "Some tasks reference equipment not in the imported pool:\n\n"
                + "\n".join(lines)
                + ("\n  …" if len(orphans) > 8 else "")
                + "\n\nImport anyway? (Solver will report INVALID until you fix the tasks.)"):
                return
        self.app.resources = pool
        self.refresh()
        self.app.mark_dirty()

    def _export_pool(self):
        path = filedialog.asksaveasfilename(
            title="Export equipment pool",
            defaultextension=".json",
            filetypes=[("Equipment-pool JSON", "*.json")],
        )
        if not path:
            return
        try:
            save_pool(path, self.app.resources)
        except Exception as e:
            messagebox.showerror("Could not export pool", str(e))


# --- Tasks tab -------------------------------------------------------------

class TasksFrame(tk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app

        # left: task list (drag rows to reorder; first row = highest priority)
        left = tk.Frame(self)
        left.pack(side="left", fill="y", padx=8, pady=8)
        tk.Label(left, text="Tasks (drag to reorder = priority)",
                 font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        cols = ("priority", "name", "summary", "hours", "deadline")
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                  height=20, selectmode="browse")
        self.tree.heading("priority", text="#")
        self.tree.heading("name",     text="Name")
        self.tree.heading("summary",  text="Resources")
        self.tree.heading("hours",    text="h")
        self.tree.heading("deadline", text="Deadline")
        self.tree.column("priority", width=32,  anchor="center")
        self.tree.column("name",     width=160, anchor="w")
        self.tree.column("summary",  width=210, anchor="w")
        self.tree.column("hours",    width=36,  anchor="center")
        self.tree.column("deadline", width=92,  anchor="w")
        self.tree.pack(fill="y", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Drag-to-reorder.
        self._drag_src_iid: Optional[str] = None
        self._drag_started: bool = False
        self.tree.bind("<ButtonPress-1>",   self._on_drag_start, add="+")
        self.tree.bind("<B1-Motion>",       self._on_drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_drag_end,    add="+")

        btn_row = tk.Frame(left)
        btn_row.pack(fill="x", pady=4)
        tk.Button(btn_row, text="Add",       command=self._add_task).pack(side="left")
        tk.Button(btn_row, text="Duplicate", command=self._duplicate_task).pack(side="left", padx=4)
        tk.Button(btn_row, text="Delete",    command=self._delete_task).pack(side="left")

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
        for i, t in enumerate(self.app.tasks):
            self.tree.insert("", "end",
                              values=(i + 1,
                                      t.name,
                                      format_requirements(t.requirements),
                                      t.hours,
                                      format_deadline(t.deadline)))
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
                            values=(idx + 1,
                                    t.name,
                                    format_requirements(t.requirements),
                                    t.hours,
                                    format_deadline(t.deadline)))

    # --- drag-to-reorder handlers ---

    def _on_drag_start(self, event):
        iid = self.tree.identify_row(event.y)
        self._drag_src_iid = iid if iid else None
        self._drag_started = False

    def _on_drag_motion(self, event):
        if self._drag_src_iid is None:
            return
        if not self._drag_started:
            self.tree.config(cursor="hand2")
            self._drag_started = True

    def _on_drag_end(self, event):
        if self._drag_src_iid is None:
            return
        self.tree.config(cursor="")
        if self._drag_started:
            dst_iid = self.tree.identify_row(event.y)
            if dst_iid and dst_iid != self._drag_src_iid:
                src_idx = self.tree.index(self._drag_src_iid)
                dst_idx = self.tree.index(dst_iid)
                task = self.app.tasks.pop(src_idx)
                self.app.tasks.insert(dst_idx, task)
                self.app.mark_dirty()
                self.refresh()
                self.select(dst_idx)
        self._drag_src_iid = None
        self._drag_started = False

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

    def _duplicate_task(self):
        idx = self._current_index()
        if idx is None:
            messagebox.showinfo("Duplicate task",
                                  "Select a task in the list first.")
            return
        new_task = duplicate_task(self.app.tasks[idx])
        self.app.tasks.insert(idx + 1, new_task)
        self.app.mark_dirty()
        self.refresh()
        self.select(idx + 1)

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
        self.title(f"{APP_NAME} v{__version__}")
        self.geometry("1600x800")
        self.minsize(1100, 720)
        self._apply_icon()

        self.tasks: list[Task] = []
        self.resources: list[Resource] = load_default_pool()
        self.current_file: Optional[Path] = None
        self.last_result: Optional[ScheduleResult] = None
        self._dirty = False

        self._build_menu()
        self._build_tabs()
        self._update_title()

    def _apply_icon(self):
        """Set the window icon from assets/icon.png."""
        try:
            if ICON_PNG_PATH.exists():
                self._icon_image = tk.PhotoImage(file=str(ICON_PNG_PATH))
                self.iconphoto(True, self._icon_image)
        except Exception:
            # Missing icon should never crash the app.
            pass

        if sys.platform == "darwin" and ICON_PNG_PATH.exists():
            self._apply_macos_dock_icon()

    def _apply_macos_dock_icon(self):
        # Tk's iconphoto doesn't update the macOS Dock icon for unbundled
        # Python apps; set it directly via AppKit when PyObjC is available.
        try:
            from AppKit import NSApplication, NSImage
        except Exception:
            return
        try:
            image = NSImage.alloc().initWithContentsOfFile_(str(ICON_PNG_PATH))
            if image is not None:
                NSApplication.sharedApplication().setApplicationIconImage_(image)
        except Exception:
            pass

    def _build_menu(self):
        menu = tk.Menu(self)
        self.config(menu=menu)
        filemenu = tk.Menu(menu, tearoff=0)
        filemenu.add_command(label="New project",
                              accelerator=f"{_MOD_LABEL}+N",
                              command=self.new_project)
        filemenu.add_command(label="Open…",
                              accelerator=f"{_MOD_LABEL}+O",
                              command=self.open_project)
        filemenu.add_command(label="Save",
                              accelerator=f"{_MOD_LABEL}+S",
                              command=self.save_project)
        filemenu.add_command(label="Save as…",
                              accelerator=f"{_MOD_LABEL}+Shift+S",
                              command=self.save_as_project)
        filemenu.add_separator()
        filemenu.add_command(label="Solve schedule",
                              accelerator=f"{_MOD_LABEL}+R",
                              command=self.run_solver)
        # On macOS, Tk auto-installs Cmd+Q on the Apple menu; only add an
        # in-menu Quit shortcut on Linux/Windows.
        if sys.platform != "darwin":
            filemenu.add_separator()
            filemenu.add_command(label="Quit",
                                  accelerator="Ctrl+Q",
                                  command=self._on_quit)
        menu.add_cascade(label="File", menu=filemenu)

        helpmenu = tk.Menu(menu, tearoff=0)
        helpmenu.add_command(label="About…", command=self._show_about)
        menu.add_cascade(label="Help", menu=helpmenu)

        # Global keyboard shortcuts. bind_all so they fire regardless of
        # which child widget has focus. The lambda swallows the event arg
        # and returns "break" to stop further propagation.
        def _bind(key, fn):
            self.bind_all(f"<{_MOD_KEY}-{key}>", lambda _e: (fn(), "break")[1])
        _bind("n", self.new_project)
        _bind("o", self.open_project)
        _bind("s", self.save_project)
        _bind("S", self.save_as_project)
        _bind("r", self.run_solver)
        if sys.platform != "darwin":
            _bind("q", self._on_quit)

        self.protocol("WM_DELETE_WINDOW", self._on_quit)

    def _show_about(self):
        import platform
        from ortools import __version__ as ortools_version
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME}\n"
            f"Version {__version__}\n\n"
            "CP-SAT scheduler for shared lab equipment.\n"
            "Built with Google OR-Tools and tkinter.\n\n"
            f"Python {platform.python_version()}  •  "
            f"OR-Tools {ortools_version}",
        )

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
        self.resources = load_default_pool()
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
        self.title(f"{APP_NAME} v{__version__} — {name}{mark}")
