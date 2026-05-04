"""Task-Resources Planner — data models, solver, GUI."""
from pathlib import Path

__version__ = "0.1.0"
APP_NAME = "Task-Resources Planner"

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON_PNG_PATH = _ASSETS / "icon_64.png"
ICON_ICO_PATH = _ASSETS / "icon.ico"
