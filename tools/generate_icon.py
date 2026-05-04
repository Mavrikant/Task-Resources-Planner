"""Regenerate the app icon. Run from the project root:

    python tools/generate_icon.py

Produces:
    assets/icon_64.png  — used by tkinter.iconphoto on every platform
    assets/icon.ico     — used by tkinter.iconbitmap on Windows (4 sizes)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)


def _draw(size: int) -> Image.Image:
    """Draw the icon at `size` pixels. The icon is a small calendar grid
    overlaid with a few colored 'task' bars, evoking the Gantt view."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)

    # Outer rounded rectangle (the 'card').
    pad = max(2, size // 16)
    radius = max(4, size // 8)
    d.rounded_rectangle(
        (pad, pad, size - pad - 1, size - pad - 1),
        radius=radius,
        fill=(255, 255, 255, 255),
        outline=(40, 40, 40, 255),
        width=max(1, size // 32),
    )

    # 7-column × 6-row inner grid (visualises week × hours-of-day blocks).
    inner = pad + max(2, size // 16)
    cell_w = (size - 2 * inner) / 7
    cell_h = (size - 2 * inner) / 6
    for c in range(8):
        x = inner + c * cell_w
        d.line([(x, inner), (x, inner + 6 * cell_h)],
               fill=(225, 225, 225, 255), width=1)
    for r in range(7):
        y = inner + r * cell_h
        d.line([(inner, y), (inner + 7 * cell_w, y)],
               fill=(225, 225, 225, 255), width=1)

    # Three coloured 'tasks' arranged like a tiny Gantt chart.
    def task(col: int, row: int, span: int, fill):
        x0 = inner + col * cell_w + 1
        y0 = inner + row * cell_h + 1
        x1 = inner + (col + span) * cell_w - 1
        y1 = inner + (row + 1) * cell_h - 1
        d.rectangle((x0, y0, x1, y1), fill=fill,
                    outline=(20, 20, 20, 255),
                    width=max(1, size // 64))

    task(0, 1, 3, (59, 130, 246, 255))   # blue
    task(2, 3, 2, (16, 185, 129, 255))   # green
    task(4, 2, 3, (245, 158, 11, 255))   # amber

    return img


def main():
    big = _draw(256)
    big.save(ASSETS / "icon_64.png")  # name kept; we save 256px for crisp scaling
    big.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128)],
    )
    print("wrote", (ASSETS / "icon_64.png"))
    print("wrote", (ASSETS / "icon.ico"))


if __name__ == "__main__":
    main()
