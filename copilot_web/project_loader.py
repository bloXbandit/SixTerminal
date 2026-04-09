"""
project_loader.py - Loads pre-fed MPP/XER project files from the projects/ folder.
Parses on startup and caches context per project in memory.

Run directly to rebuild milestone_map.json files from Milestone Map.xlsx:
    python copilot_web/project_loader.py
"""
import os
import json
import logging
import sys
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")

_project_cache: Dict[str, str] = {}
_project_meta: Dict[str, dict] = {}


def _get_mpp_parser():
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    from mpp_parser import MPPParser
    return MPPParser


def _get_xer_parser():
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    from parser import P6Parser
    return P6Parser


SCHEDULE_EXTS = (".mpp", ".xml", ".xer")


def load_all_projects():
    """Scans projects/ folder, builds versioned schedule context per project."""
    if not os.path.exists(PROJECTS_DIR):
        logger.warning(f"Projects directory not found: {PROJECTS_DIR}")
        return

    for slug in sorted(os.listdir(PROJECTS_DIR)):
        project_path = os.path.join(PROJECTS_DIR, slug)
        if not os.path.isdir(project_path):
            continue

        meta_path = os.path.join(project_path, "meta.json")
        if not os.path.exists(meta_path):
            continue

        with open(meta_path, "r") as f:
            meta = json.load(f)
        _project_meta[slug] = meta

        try:
            context = _build_versioned_context(slug, project_path)
            _project_cache[slug] = context
            status = "with schedule data" if context else "metadata only"
            logger.info(f"[{slug}] Loaded — {status}")
        except Exception as e:
            logger.error(f"[{slug}] Load failed: {e}")
            _project_cache[slug] = ""

    loaded = sum(1 for v in _project_cache.values() if v)
    logger.info(f"Project loader: {len(_project_meta)} projects, {loaded} with schedule data.")


def _find_versioned_files(project_path: str) -> dict:
    """
    Scans a project folder and returns:
      baseline: filepath or None
      updates:  list of (label, filepath) sorted ascending by label
      verify_pdf: filepath or None
    """
    baseline = None
    updates = []
    verify_pdf = None

    for fname in os.listdir(project_path):
        lower = fname.lower()
        fpath = os.path.join(project_path, fname)

        if lower == "verify.pdf":
            verify_pdf = fpath
            continue

        name_no_ext = os.path.splitext(lower)[0]
        ext = os.path.splitext(lower)[1]

        if ext not in SCHEDULE_EXTS:
            continue

        if name_no_ext == "baseline":
            baseline = fpath
        elif name_no_ext.startswith("update_"):
            updates.append((name_no_ext, fpath))

    updates.sort(key=lambda x: x[0])
    return {"baseline": baseline, "updates": updates, "verify_pdf": verify_pdf}


def _parse_schedule(filepath: str) -> Optional[dict]:
    """
    Parse any schedule file (mpp/xml/xer) and return a normalized dict:
    { name, data_date, total, completed, in_progress, not_started, pct_complete,
      milestones: [{name, finish}], raw_context }
    """
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext in (".mpp", ".xml"):
            MPPParser = _get_mpp_parser()
            p = MPPParser(filepath)
            raw = p.get_llm_context()
            return {"raw_context": raw, "source": os.path.basename(filepath)}

        elif ext == ".xer":
            P6Parser = _get_xer_parser()
            p = P6Parser(filepath)
            ctx = p.get_llm_context()
            info = ctx.get("project_info", {})
            metrics = ctx.get("project_metrics", {})
            lines = [
                "=== PROJECT SCHEDULE DATA ===",
                f"Project: {info.get('name', 'Unknown')}",
                f"Data Date: {info.get('data_date', 'N/A')}",
                "",
                "SCHEDULE SUMMARY:",
                f"  Total Activities: {metrics.get('total_activities', 0)}",
                f"  Completed: {metrics.get('completed', 0)}",
                f"  In Progress: {metrics.get('in_progress', 0)}",
                f"  Not Started: {metrics.get('not_started', 0)}",
                f"  % Complete: {metrics.get('percent_complete', '0%')}",
                "",
                f"WBS PHASES: {', '.join(ctx.get('wbs_phases', []))}",
                "",
                f"DCMA METRICS: {json.dumps(ctx.get('dcma_metrics', {}))}",
            ]
            return {"raw_context": "\n".join(lines), "source": os.path.basename(filepath)}

    except Exception as e:
        logger.error(f"Parse failed for {filepath}: {e}")
        return None

    return None


def _extract_pdf_milestones(pdf_path: str) -> list:
    """
    Extract activity names and finish dates from a verify.pdf for crosscheck.
    Returns list of dicts: [{activity, finish}]
    """
    try:
        import pdfplumber
        entries = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:30]:
                text = page.extract_text()
                if text:
                    for line in text.splitlines():
                        entries.append(line.strip())
        return entries
    except Exception as e:
        logger.warning(f"PDF crosscheck failed: {e}")
        return []


def _build_versioned_context(slug: str, project_path: str) -> str:
    """
    Build the full LLM context for a project using versioned files.
    Handles any mix of mpp/xml/xer across baseline and updates.
    Uses verify.pdf as a silent crosscheck if present.
    """
    files = _find_versioned_files(project_path)
    baseline_path = files["baseline"]
    updates = files["updates"]
    verify_pdf = files["verify_pdf"]

    if not baseline_path and not updates:
        return ""

    parts = []

    # --- Determine current and previous ---
    current_label, current_path = updates[-1] if updates else ("baseline", baseline_path)
    previous_path = None
    if len(updates) >= 2:
        previous_label, previous_path = updates[-2]
    elif len(updates) == 1 and baseline_path:
        previous_label, previous_path = "baseline", baseline_path

    # --- Format label ---
    total_updates = len(updates)
    parts.append(f"SCHEDULE VERSIONS: {'baseline' if baseline_path else 'no baseline'} + {total_updates} update(s)")
    parts.append(f"CURRENT SUBMISSION: {current_label} ({os.path.basename(current_path)})")

    # --- Parse current ---
    current_data = _parse_schedule(current_path)
    if not current_data:
        parts.append("[Current schedule could not be parsed]")
        return "\n".join(parts)

    parts.append("")
    parts.append("=== CURRENT SCHEDULE ===")
    parts.append(current_data["raw_context"])

    # --- Parse previous for delta context ---
    if previous_path:
        previous_data = _parse_schedule(previous_path)
        if previous_data:
            parts.append("")
            parts.append(f"=== PREVIOUS SCHEDULE ({os.path.basename(previous_path)}) ===")
            parts.append(previous_data["raw_context"])

    # --- Parse baseline for drift context ---
    if baseline_path and baseline_path != current_path:
        baseline_data = _parse_schedule(baseline_path)
        if baseline_data:
            parts.append("")
            parts.append(f"=== BASELINE SCHEDULE ({os.path.basename(baseline_path)}) ===")
            parts.append(baseline_data["raw_context"])

    # --- PDF crosscheck (silent, for LLM verification only) ---
    if verify_pdf:
        pdf_lines = _extract_pdf_milestones(verify_pdf)
        if pdf_lines:
            parts.append("")
            parts.append("=== PDF VERIFICATION REFERENCE (use to crosscheck activity dates/names — do not expose raw) ===")
            parts.append("\n".join(pdf_lines[:200]))

    return "\n".join(parts)


def _load_milestone_map(slug: str) -> str:
    """Load milestone_map.json for a project and return a formatted context block."""
    mm_path = os.path.join(PROJECTS_DIR, slug, "milestone_map.json")
    if not os.path.exists(mm_path):
        return ""
    try:
        with open(mm_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        milestones = data.get("milestones", [])
        if not milestones:
            return ""
        lines = ["STANDARDIZED MILESTONES (always use these names in responses):"]
        for m in milestones:
            std = m["standardized_name"]
            act = m["activity_name"]
            act_id = m["activity_id"]
            if act and act != std:
                lines.append(f"  - {std}  (schedule activity: '{act}', ID: {act_id})")
            else:
                lines.append(f"  - {std}  (ID: {act_id})")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[{slug}] Could not load milestone map: {e}")
        return ""


def get_project_context(slug: str, page: Optional[str] = None) -> str:
    """
    Returns the full context string for a project slug.
    Optionally adds a page hint so the LLM knows what view the user is on.
    """
    meta = _project_meta.get(slug)
    if not meta:
        return ""

    parts = [f"PROJECT: {meta['display_name']}"]

    if page:
        parts.append(f"CURRENT PAGE VIEW: {page}")
        parts.append(_page_hint(page))

    milestone_ctx = _load_milestone_map(slug)
    if milestone_ctx:
        parts.append("")
        parts.append(milestone_ctx)

    schedule_ctx = _project_cache.get(slug, "")
    if schedule_ctx:
        parts.append("")
        parts.append(schedule_ctx)
    else:
        parts.append("\n[No schedule file loaded for this project yet. User can attach an MPP/XER file to provide schedule data.]")

    return "\n".join(parts)


def _page_hint(page: str) -> str:
    """Return a brief instruction hint based on the current Power BI page view."""
    hints = {
        "Landing Page": "The user is viewing the main project overview showing key milestones, KPIs, and overall project status.",
        "Risk": "The user is viewing the Risk Report. Focus on risks, issues, mitigation strategies, and risk scores.",
        "Schedule Performance Report": "The user is viewing Schedule Performance. Focus on SPI, schedule variance, earned value metrics.",
        "Calendar View": "The user is viewing the Calendar View showing activity timing and resource loading by date.",
        "Schedule": "The user is viewing the detailed Schedule. Focus on activity sequences, critical path, and float.",
    }
    return hints.get(page, f"The user is viewing the {page} page.")


def list_projects():
    """Returns list of all projects with slug and display name."""
    return [
        {"slug": slug, "display_name": meta["display_name"], "pages": meta["pages"]}
        for slug, meta in sorted(_project_meta.items(), key=lambda x: x[1]["display_name"])
    ]


def has_schedule(slug: str) -> bool:
    """Returns True if this project has a parsed schedule file."""
    return bool(_project_cache.get(slug))


if __name__ == "__main__":
    """
    Run this script directly to parse Milestone Map.xlsx and write
    milestone_map.json into each project bucket folder.
    """
    try:
        import openpyxl
    except ImportError:
        print("Installing openpyxl...")
        import subprocess
        subprocess.check_call(["pip", "install", "openpyxl", "--quiet"])
        import openpyxl

    XLSX_PATH = os.path.join(os.path.dirname(__file__), "..", "Milestone Map.xlsx")
    XLSX_PATH = os.path.abspath(XLSX_PATH)

    SLUG_MAP = {
        "Anaheim, CA": "anaheim_ca", "Anna, TX": "anna_tx",
        "Aventura, FL": "aventura_fl", "Colorado Springs, CO": "colorado_springs_co",
        "Davenport, FL": "davenport_fl", "Delray, FL": "delray_fl",
        "Fairfax, VA": "fairfax_va", "Frisco, TX": "frisco_tx",
        "Meridian, ID": "meridian_id", "Mesa, AZ": "mesa_az",
        "Mt Juliet, TN": "mt_juliet_tn", "San Diego, CA": "san_diego_ca",
        "Selma, NC": "selma_nc", "Willis, TX": "willis_tx",
    }

    def _is_na(v):
        return v is None or str(v).strip().upper() == "N/A"

    print(f"Reading: {XLSX_PATH}")
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb.active
    by_project = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        proj_type  = str(row[0]).strip() if row[0] else ""
        proj_name  = str(row[1]).strip() if row[1] else ""
        std_name   = str(row[2]).strip() if row[2] else ""
        act_id     = row[3]
        sort_ord   = row[4]
        act_name   = str(row[5]).strip() if row[5] else ""

        if not proj_name or not std_name:
            continue
        if _is_na(act_id) and _is_na(act_name):
            continue

        if proj_name not in by_project:
            by_project[proj_name] = {"type": proj_type, "milestones": []}

        by_project[proj_name]["milestones"].append({
            "standardized_name": std_name,
            "activity_id": None if _is_na(act_id) else act_id,
            "activity_name": None if _is_na(act_name) else act_name,
            "sort": sort_ord,
        })

    written = 0
    for proj_name, data in by_project.items():
        slug = SLUG_MAP.get(proj_name)
        if not slug:
            print(f"  SKIPPED (no bucket): {proj_name}")
            continue
        out = os.path.join(PROJECTS_DIR, slug, "milestone_map.json")
        payload = {
            "project": proj_name,
            "type": data["type"],
            "milestones": sorted(data["milestones"], key=lambda x: x["sort"] or 99)
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        count = len(data["milestones"])
        print(f"  OK  {slug}: {count} milestones")
        written += 1

    print(f"\nDone. {written} milestone_map.json files written.")
