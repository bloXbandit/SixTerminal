"""
Screenshot cache module — stores structured data extracted from user-uploaded
dashboard screenshots and critical-path breakdown images.

Each project gets a single cache file:  cache/{slug}_screenshots.json

Schema per entry:
{
    "filename": "dashboard_up06.png",
    "label": "Frisco Dashboard UP06",
    "user_note": "Use these milestone names",
    "uploaded_at": "2026-04-20 14:32 UTC",
    "source_type": "milestone_dashboard" | "cp_breakdown" | "other",
    "ignored": false,
    "milestones": [
        {"name": "Contract Completion", "current_date": "09/11/26", "prior_date": "09/21/26"}
    ],
    "critical_path": ["Activity A", "Activity B", ...],
    "raw_text": "Full vision description..."
}

Priority rules (injected into context by build_screenshot_context):
  - milestone_dashboard entries with ignored=False → highest priority for milestone dates
  - cp_breakdown entries with ignored=False → supplementary CP override block
  - other entries → standard supplementary docs block
"""
import os
import logging
import datetime
import re
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")


def _ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def _get_cache_path(project_slug: str) -> str:
    _ensure_cache_dir()
    return os.path.join(CACHE_DIR, f"{project_slug}_screenshots.json")


def _read_cache(project_slug: str) -> list:
    """Read screenshot cache for a project. Returns [] on any error."""
    try:
        from crypto import read_encrypted_json
        path = _get_cache_path(project_slug)
        if not os.path.exists(path):
            return []
        data = read_encrypted_json(path)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.warning(f"[{project_slug}] screenshot_cache read error: {e}")
        return []


def _write_cache(project_slug: str, entries: list):
    """Write screenshot cache for a project."""
    try:
        from crypto import write_encrypted_json
        path = _get_cache_path(project_slug)
        write_encrypted_json(path, entries)
    except Exception as e:
        logger.warning(f"[{project_slug}] screenshot_cache write error: {e}")


# ─────────────────────────────────────────────
# Structured extraction from vision description
# ─────────────────────────────────────────────

_DATE_PAT = r'\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b'

# Standardized milestone name keywords — must match the project's milestone_map names
_MILESTONE_KEYWORDS = [
    "contract completion", "substantial completion", "final completion",
    "foundation complete", "structure top out", "weather tight",
    "permanent power", "finishes complete", "elevator complete",
    "mechanical complete", "electrical complete", "plumbing complete",
    "certificate of occupancy", "co", "punch list complete",
    "roof complete", "framing complete", "drywall complete",
    "exterior complete", "sitework complete", "paving complete",
]

_CP_KEYWORDS = [
    "critical path", "driving activities", "critical activities",
    "longest path", "float = 0", "total float: 0",
]


def _classify_source_type(raw_text: str) -> str:
    """Classify screenshot as milestone_dashboard, cp_breakdown, or other."""
    lower = raw_text.lower()
    cp_score = sum(1 for kw in _CP_KEYWORDS if kw in lower)
    milestone_score = sum(1 for kw in _MILESTONE_KEYWORDS if kw in lower)
    if cp_score >= 2 or (cp_score >= 1 and "activities" in lower):
        return "cp_breakdown"
    if milestone_score >= 2 or ("milestone" in lower and re.search(_DATE_PAT, raw_text)):
        return "milestone_dashboard"
    if milestone_score >= 1 and re.search(_DATE_PAT, raw_text):
        return "milestone_dashboard"
    return "other"


def _extract_milestones(raw_text: str) -> list:
    """
    Extract milestone name + current_date (+ prior_date if visible) from vision text.
    Returns list of dicts: {name, current_date, prior_date}
    """
    milestones = []
    lines = raw_text.split("\n")
    for line in lines:
        line_lower = line.lower()
        # Check if any milestone keyword appears in this line
        matched_name = None
        for kw in _MILESTONE_KEYWORDS:
            if kw in line_lower:
                # Capitalize properly
                matched_name = kw.title()
                break
        if not matched_name:
            continue
        dates = re.findall(_DATE_PAT, line)
        if not dates:
            continue
        entry = {
            "name": matched_name,
            "current_date": dates[0] if len(dates) >= 1 else "",
            "prior_date": dates[1] if len(dates) >= 2 else "",
        }
        # Avoid duplicates
        if not any(m["name"].lower() == entry["name"].lower() for m in milestones):
            milestones.append(entry)
    return milestones


def _extract_cp_activities(raw_text: str) -> list:
    """
    Extract critical path activity names from a CP breakdown screenshot.
    Returns a list of activity name strings.
    """
    activities = []
    lines = raw_text.split("\n")
    in_cp_section = False
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        lower = line_stripped.lower()
        # Detect start of CP section
        if any(kw in lower for kw in _CP_KEYWORDS):
            in_cp_section = True
            continue
        if in_cp_section:
            # Stop at blank sections or new section headers
            if lower.startswith("===") or lower.startswith("---"):
                break
            # Skip lines that are just dates or numbers
            if re.match(r'^[\d/\-\s]+$', line_stripped):
                continue
            if len(line_stripped) > 5:
                activities.append(line_stripped)
    # Fallback: if no CP section found, look for lines with "float" or "critical"
    if not activities:
        for line in lines:
            if "float" in line.lower() or "critical" in line.lower():
                clean = re.sub(r'\s+', ' ', line.strip())
                if len(clean) > 5:
                    activities.append(clean)
    return activities[:50]  # cap at 50 activities


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def save_screenshot(project_slug: str, filename: str, label: str,
                    user_note: str, raw_text: str) -> dict:
    """
    Parse raw vision text, classify the screenshot, extract structured data,
    and save to the project's screenshot cache.
    Returns a summary dict with keys: source_type, has_milestones, has_cp, milestone_count, cp_count.
    """
    source_type = _classify_source_type(raw_text)
    milestones = _extract_milestones(raw_text) if source_type in ("milestone_dashboard", "other") else []
    cp_activities = _extract_cp_activities(raw_text) if source_type in ("cp_breakdown", "other") else []

    entry = {
        "filename": filename,
        "label": label or filename,
        "user_note": user_note,
        "uploaded_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "source_type": source_type,
        "ignored": False,
        "milestones": milestones,
        "critical_path": cp_activities,
        "raw_text": raw_text[:6000],  # cap storage
    }

    entries = _read_cache(project_slug)
    # Replace existing entry with same filename
    entries = [e for e in entries if e.get("filename") != filename]
    entries.append(entry)
    _write_cache(project_slug, entries)

    logger.info(f"[{project_slug}] Screenshot cached: {filename} | type={source_type} | "
                f"milestones={len(milestones)} | cp={len(cp_activities)}")

    return {
        "source_type": source_type,
        "has_milestones": len(milestones) > 0,
        "has_cp": len(cp_activities) > 0,
        "milestone_count": len(milestones),
        "cp_count": len(cp_activities),
    }


def set_ignored(project_slug: str, filename: str, ignored: bool = True) -> bool:
    """Mark a screenshot as ignored (suppresses it from context injection)."""
    entries = _read_cache(project_slug)
    changed = False
    for e in entries:
        if e.get("filename") == filename:
            e["ignored"] = ignored
            changed = True
    if changed:
        _write_cache(project_slug, entries)
    return changed


def get_active_screenshots(project_slug: str) -> list:
    """Return all non-ignored screenshot entries for a project."""
    return [e for e in _read_cache(project_slug) if not e.get("ignored", False)]


def build_screenshot_context(project_slug: str) -> str:
    """
    Build context blocks for injection into the system prompt.
    Returns a string with one or more === ... === blocks.
    """
    entries = get_active_screenshots(project_slug)
    if not entries:
        return ""

    blocks = []

    # ── Milestone dashboard screenshots ──
    milestone_entries = [e for e in entries if e["source_type"] == "milestone_dashboard" and e.get("milestones")]
    if milestone_entries:
        lines = [
            "=== USER DASHBOARD — VERIFIED MILESTONE DATES ===",
            "These milestone dates were extracted from user-uploaded dashboard screenshots.",
            "PRIORITY: Use these dates as the CONTROLLING source for milestone current and prior dates.",
            "They override parsed schedule dates when present. Do NOT contradict these dates.",
            "",
        ]
        for e in milestone_entries:
            lines.append(f"Source: {e['label']} (uploaded: {e['uploaded_at']})")
            if e.get("user_note"):
                lines.append(f"User note: {e['user_note']}")
            for m in e["milestones"]:
                prior_str = f" | Prior: {m['prior_date']}" if m.get("prior_date") else ""
                lines.append(f"  {m['name']}: Current={m['current_date']}{prior_str}")
            lines.append("")
        blocks.append("\n".join(lines))

    # ── CP breakdown screenshots ──
    cp_entries = [e for e in entries if e["source_type"] == "cp_breakdown" and e.get("critical_path")]
    if cp_entries:
        lines = [
            "=== USER-PROVIDED CRITICAL PATH BREAKDOWN ===",
            "These critical path activities were extracted from a user-uploaded CP breakdown screenshot.",
            "Use this to cross-check your internal CP analysis. If your analysis differs, note the discrepancy.",
            "The user can say 'ignore CP upload' to suppress this block.",
            "",
        ]
        for e in cp_entries:
            lines.append(f"Source: {e['label']} (uploaded: {e['uploaded_at']})")
            if e.get("user_note"):
                lines.append(f"User note: {e['user_note']}")
            for act in e["critical_path"]:
                lines.append(f"  - {act}")
            lines.append("")
        blocks.append("\n".join(lines))

    # ── Other screenshots (general reference) ──
    other_entries = [e for e in entries if e["source_type"] == "other"]
    if other_entries:
        lines = [
            "=== USER-UPLOADED SCREENSHOTS (General Reference) ===",
            "",
        ]
        for e in other_entries:
            lines.append(f"--- {e['label']} (uploaded: {e['uploaded_at']}) ---")
            if e.get("user_note"):
                lines.append(f"User note: {e['user_note']}")
            lines.append(e.get("raw_text", "[No content extracted]")[:2000])
            lines.append("")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
