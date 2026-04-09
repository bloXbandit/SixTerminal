"""
tracker_loader.py - Parses Project tracker1.csv on startup.
Provides authoritative data dates, update numbers, file names, and project history
for LLM context injection. Used as a crosscheck against MPP/XER/XML data dates.
"""
import os
import csv
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

def _find_tracker() -> str:
    """Locate Project tracker1.csv — works locally (../root) and on Render (/app root)."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "Project tracker1.csv"),          # co-located in copilot_web/
        os.path.join(here, "..", "Project tracker1.csv"),    # repo root (local dev)
        os.path.join("/app", "Project tracker1.csv"),        # Render /app root
    ]
    for p in candidates:
        if os.path.exists(os.path.normpath(p)):
            return os.path.normpath(p)
    return candidates[0]  # fallback — will warn on load

TRACKER_PATH = _find_tracker()

_tracker_cache: Dict[str, dict] = {}

NAME_TO_SLUG = {
    "anaheim":          "anaheim_ca",
    "anna":             "anna_tx",
    "aventura":         "aventura_fl",
    "colorado springs": "colorado_springs_co",
    "davenport":        "davenport_fl",
    "delray bch":       "delray_fl",
    "delray":           "delray_fl",
    "fairfax":          "fairfax_va",
    "frisco":           "frisco_tx",
    "meridian":         "meridian_id",
    "mesa":             "mesa_az",
    "mt.juliet":        "mt_juliet_tn",
    "mt. juliet":       "mt_juliet_tn",
    "mt juliet":        "mt_juliet_tn",
    "san diego":        "san_diego_ca",
    "selma":            "selma_nc",
    "willis":           "willis_tx",
}


def _normalize_name(raw: str) -> str:
    return raw.strip().lower().rstrip(",")


def _name_to_slug(raw: str) -> Optional[str]:
    key = _normalize_name(raw)
    return NAME_TO_SLUG.get(key)


def load_tracker():
    """Parse Project tracker1.csv and build per-project submission history."""
    global _tracker_cache
    _tracker_cache = {}

    path = os.path.abspath(TRACKER_PATH)
    if not os.path.exists(path):
        logger.warning(f"Project tracker not found: {path}")
        return

    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        logger.error(f"Failed to read tracker CSV: {e}")
        return

    by_slug: Dict[str, dict] = {}

    for row in rows:
        proj_name  = (row.get("Project Name") or row.get("Project Name ") or "").strip()
        code       = (row.get("Code") or "").strip()
        file_name  = (row.get("File Name") or row.get("File Name ") or "").strip()
        data_date  = (row.get("Data Date") or row.get("Data Date ") or "").strip()
        proj_type  = (row.get("Project Type ( Development / Construction)") or "").strip()
        file_type  = (row.get("File Type (Baseline/ Update )") or row.get("File Type (Baseline/ Update)") or "").strip()
        date_recv  = (row.get("Date Received") or "").strip()

        if not proj_name or not file_name:
            continue

        slug = _name_to_slug(proj_name)
        if not slug:
            continue

        if slug not in by_slug:
            by_slug[slug] = {
                "project_name": proj_name,
                "code": code,
                "type": proj_type,
                "submissions": [],
            }
        elif code and not by_slug[slug]["code"]:
            by_slug[slug]["code"] = code

        by_slug[slug]["submissions"].append({
            "file_name": file_name,
            "data_date": data_date,
            "file_type": file_type.strip(),
            "date_received": date_recv,
        })

    for slug, data in by_slug.items():
        subs = data["submissions"]

        baseline = next((s for s in subs if "baseline" in s["file_type"].lower()), None)

        updates = [s for s in subs if "update" in s["file_type"].lower()]

        def update_num(s):
            parts = s["file_type"].lower().replace("update", "").strip().split()
            for p in parts:
                if p.isdigit():
                    return int(p)
            return 0

        updates.sort(key=update_num)
        current = updates[-1] if updates else baseline

        _tracker_cache[slug] = {
            "project_name": data["project_name"],
            "code": data["code"],
            "type": data["type"],
            "baseline": baseline,
            "current": current,
            "previous": updates[-2] if len(updates) >= 2 else baseline,
            "total_updates": len(updates),
            "all_submissions": subs,
        }

    logger.info(f"Tracker loaded: {len(_tracker_cache)} projects.")


def get_tracker_context(slug: str) -> str:
    """
    Returns a formatted tracker context block for LLM injection.
    Provides authoritative data dates, update counts, and history.
    Only surfaces to user if requested — used internally for accuracy.
    """
    data = _tracker_cache.get(slug)
    if not data:
        return ""

    current = data.get("current") or {}
    previous = data.get("previous") or {}
    baseline = data.get("baseline") or {}
    total = data.get("total_updates", 0)
    code = data.get("code", "")
    proj_type = data.get("type", "")

    lines = [
        "=== PROJECT TRACKER (authoritative — use these dates, do not expose raw unless asked) ===",
        f"Project Code: {code}" if code else "",
        f"Type: {proj_type}" if proj_type else "",
        f"Total Updates Submitted: {total}",
        "",
        f"CURRENT SUBMISSION:",
        f"  Label: {current.get('file_type', 'N/A')}",
        f"  File:  {current.get('file_name', 'N/A')}",
        f"  Data Date: {current.get('data_date', 'N/A')}",
        f"  Received: {current.get('date_received', 'N/A')}",
    ]

    if previous and previous != current:
        lines += [
            "",
            f"PREVIOUS SUBMISSION:",
            f"  Label: {previous.get('file_type', 'N/A')}",
            f"  File:  {previous.get('file_name', 'N/A')}",
            f"  Data Date: {previous.get('data_date', 'N/A')}",
        ]

    if baseline and baseline != current:
        lines += [
            "",
            f"BASELINE:",
            f"  File:  {baseline.get('file_name', 'N/A')}",
            f"  Data Date: {baseline.get('data_date', 'N/A')}",
        ]

    lines += [
        "",
        "SUBMISSION HISTORY:",
    ]
    for s in data.get("all_submissions", []):
        lines.append(f"  [{s['file_type']}]  Data Date: {s['data_date']}  |  Received: {s['date_received']}  |  {s['file_name']}")

    return "\n".join(l for l in lines if l is not None)


def get_tracker_data(slug: str) -> Optional[dict]:
    """Returns raw tracker dict for a slug. None if not tracked."""
    return _tracker_cache.get(slug)


def get_portfolio_summary(schedule_flags: Optional[Dict[str, bool]] = None) -> str:
    """
    Returns a compact portfolio-level health summary across all tracked projects.
    schedule_flags: optional {slug: bool} — True if schedule file is loaded for that project.
    Used for cross-project awareness: "which projects are behind?" / "portfolio overview".
    """
    if not _tracker_cache:
        return ""

    lines = [
        "=== PORTFOLIO OVERVIEW (all projects — use for cross-project questions) ===",
        "Format: Project | Type | Updates | Current Data Date | Schedule Loaded",
        "",
    ]

    # Sort: Construction first, then Development; alphabetical within each group
    construction = sorted(
        [(slug, d) for slug, d in _tracker_cache.items() if "construction" in (d.get("type") or "").lower()],
        key=lambda x: x[1]["project_name"]
    )
    development = sorted(
        [(slug, d) for slug, d in _tracker_cache.items() if "development" in (d.get("type") or "").lower()],
        key=lambda x: x[1]["project_name"]
    )
    other = sorted(
        [(slug, d) for slug, d in _tracker_cache.items()
         if slug not in {s for s, _ in construction} and slug not in {s for s, _ in development}],
        key=lambda x: x[1]["project_name"]
    )

    def _project_row(slug: str, data: dict) -> str:
        name = data.get("project_name", slug)
        total = data.get("total_updates", 0)
        current = data.get("current") or {}
        data_date = current.get("data_date", "N/A")
        file_type = current.get("file_type", "N/A")
        has_sched = schedule_flags.get(slug, False) if schedule_flags else False
        sched_tag = "Yes" if has_sched else "No file"
        return f"  {name:<22} | {data.get('type', 'N/A'):<14} | {total} update(s) | {file_type} | Data: {data_date} | Schedule: {sched_tag}"

    if construction:
        lines.append("CONSTRUCTION PROJECTS:")
        for slug, data in construction:
            lines.append(_project_row(slug, data))
        lines.append("")

    if development:
        lines.append("DEVELOPMENT PROJECTS:")
        for slug, data in development:
            lines.append(_project_row(slug, data))
        lines.append("")

    if other:
        lines.append("OTHER PROJECTS:")
        for slug, data in other:
            lines.append(_project_row(slug, data))
        lines.append("")

    lines.append(
        "NOTE: Schedule health detail (variance, CP, float) is only available for projects with schedule files loaded. "
        "For detailed project analysis, the user must select a specific project from the dropdown."
    )

    return "\n".join(lines)
