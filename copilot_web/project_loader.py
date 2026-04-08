"""
project_loader.py - Loads pre-fed MPP/XER project files from the projects/ folder.
Parses on startup and caches context per project in memory.
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


def load_all_projects():
    """
    Scans projects/ folder, parses any MPP/XER files found, caches context.
    Called once on app startup.
    """
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

        schedule_file = _find_schedule_file(project_path)
        if not schedule_file:
            logger.info(f"[{slug}] No schedule file found — metadata only.")
            _project_cache[slug] = ""
            continue

        try:
            context = _parse_schedule(schedule_file)
            _project_cache[slug] = context
            logger.info(f"[{slug}] Loaded: {os.path.basename(schedule_file)}")
        except Exception as e:
            logger.error(f"[{slug}] Parse failed: {e}")
            _project_cache[slug] = f"[Schedule file present but could not be parsed: {e}]"

    logger.info(f"Project loader: {len(_project_meta)} projects loaded, {sum(1 for v in _project_cache.values() if v)} with schedule data.")


def _find_schedule_file(project_path: str) -> Optional[str]:
    """Find the first .mpp or .xer file in the project folder."""
    for fname in os.listdir(project_path):
        if fname.lower().endswith((".mpp", ".xer", ".xml")):
            return os.path.join(project_path, fname)
    return None


def _parse_schedule(filepath: str) -> str:
    """Parse a schedule file and return LLM context string."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".mpp" or ext == ".xml":
        MPPParser = _get_mpp_parser()
        p = MPPParser(filepath)
        return p.get_llm_context()

    elif ext == ".xer":
        P6Parser = _get_xer_parser()
        p = P6Parser(filepath)
        ctx = p.get_llm_context()
        lines = [
            f"=== PROJECT SCHEDULE DATA ===",
            f"Project: {ctx.get('project_info', {}).get('name', 'Unknown')}",
            f"Data Date: {ctx.get('project_info', {}).get('data_date', 'N/A')}",
            f"",
            f"SCHEDULE SUMMARY:",
            f"  Total Activities: {ctx.get('project_metrics', {}).get('total_activities', 0)}",
            f"  Completed: {ctx.get('project_metrics', {}).get('completed', 0)}",
            f"  In Progress: {ctx.get('project_metrics', {}).get('in_progress', 0)}",
            f"  Not Started: {ctx.get('project_metrics', {}).get('not_started', 0)}",
            f"  % Complete: {ctx.get('project_metrics', {}).get('percent_complete', '0%')}",
            f"",
            f"WBS PHASES: {', '.join(ctx.get('wbs_phases', []))}",
            f"",
            f"DCMA METRICS: {json.dumps(ctx.get('dcma_metrics', {}))}",
        ]
        return "\n".join(lines)

    return f"[Unsupported format: {ext}]"


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

    schedule_ctx = _project_cache.get(slug, "")
    if schedule_ctx:
        parts.append("")
        parts.append(schedule_ctx)
    else:
        parts.append("[No schedule file loaded for this project yet. User can attach an MPP/XER file to provide schedule data.]")

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
