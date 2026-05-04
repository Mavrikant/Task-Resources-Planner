# Lab Equipment Weekly Scheduler

A desktop tool that builds a tight weekly schedule for shared lab equipment
using constraint programming (Google OR-Tools CP-SAT) and a tkinter GUI.

## Status

Work in progress — see `lab_planner/` for source.

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

## Resources modelled by default

VSG×3, VSGRS×1, OBB×1, IFF×2, IFR×1, 1553×2, RFCU×2, ADF T×1, Fırın×2, CT94×1, OSC×1, AA×2.

## Run tests

```bash
pytest -q
```
