# SixTerminal Implementation Plan

**Date:** January 30, 2026
**Status:** In Progress
**Executor:** Ecarg (OpenClaw)

This document outlines the technical implementation steps for the SixTerminal P6 Stairway Tracker, utilizing `PyP6XER` for parsing and `openpyxl` for dashboard generation.

## 1. Project Structure

We will build a modular Python package in `src/`.

```
src/
├── __init__.py
├── parser.py       # Wrapper around PyP6XER to extract clean DataFrames
├── analyzer.py     # Logic for critical path, float analysis, and variance
├── diff_engine.py  # Compares two Schedule objects to find changes (Approach 6)
├── dashboard.py    # Excel generation using openpyxl (Stairway Chart, Executive Summary)
├── monitor.py      # File watcher service for the "Hybrid" approach
└── config.py       # Configuration loader (JSON/Env)
```

## 2. Core Dependencies

- **PyP6XER:** Primary parser for `.xer` files.
- **pandas:** For heavy lifting of schedule data (merging, filtering, calculating variances).
- **openpyxl:** For high-fidelity Excel output (conditional formatting, styling).
- **watchdog:** For the file monitoring service (Phase 2).

## 3. Implementation Phases

### Phase 1: The Engine (Parsing & Analysis)
*Goal: Turn an XER file into a usable Python object.*

- Implement `parser.py` to load XER using `PyP6XER`.
- Extract tables: `TASK` (Activities), `TASKPRED` (Logic), `PROJECT` (Meta), `PROJWBS` (WBS).
- Clean dates and handle nulls using Pandas.
- Implement `analyzer.py` to calculate:
    - `Status`: On Track / At Risk / Critical.
    - `Variance`: Baseline Finish vs. Current Finish.
    - `Critical Path`: Filter by `TotalFloat <= 0`.

### Phase 2: The Dashboard (Visualization)
*Goal: Generate the "Stairway" Excel file.*

- Implement `dashboard.py`.
- **Executive Summary:** High-level metrics.
- **Milestone Tracker:** The "Stairway" visualization.
    - *Tech Note:* We will use Excel Conditional Formatting cells to simulate the stairway steps if true shapes are too complex for `openpyxl`, or use ASCII/Unicode bars for text-based dashboards.
- **Procurement & Punchlist:** Data tables with "Traffic Light" formatting.

### Phase 3: Change Detection (Diff Engine)
*Goal: Compare "Yesterday.xer" vs "Today.xer".*

- Implement `diff_engine.py`.
- Compare activity attributes (Start, Finish, Duration, Name).
- Categorize changes:
    - 🔴 **CRITICAL:** Milestone slip > 10 days.
    - 🟡 **HIGH:** Finish Date slip > 5 days.
    - 🟢 **MEDIUM:** Name/Logic changes.

## 4. Immediate Next Steps

1.  Set up `requirements.txt`.
2.  Create `src/parser.py` and verify `PyP6XER` works on sample data (if available) or mock data.
3.  Build the `DashboardGenerator` class.

---
*Verified against "P6_Stairway_Tracker_Planning_Document.md" and User Requirements.*
