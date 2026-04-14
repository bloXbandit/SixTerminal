"""
risk_engine.py - Schedule risk diagnostic engine for Stelic Copilot.

Runs intensive, unbiased checks across three categories:
  - Schedule Health:     Data quality, percent complete alignment, logic gaps
  - Schedule Detail:     Activity granularity, missing breakdowns, duration outliers
  - Constructability:    Sequence logic, trade overlap, duration realism vs project type

Each check produces a structured finding the LLM narrates — not dumps — to the user.
Priority: HIGH = driving risk, affects completion | MEDIUM = quality concern, may mask risk
"""

from typing import List, Dict, Optional
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)

# Max reasonable single-activity duration by type (calendar days)
DURATION_THRESHOLDS = {
    "default":         90,
    "summary":        365,
    "concrete":        60,
    "framing":         45,
    "drywall":         45,
    "roofing":         30,
    "mep":             60,
    "elevator":        90,
    "inspection":      30,
    "closeout":        60,
    "sitework":        90,
}

# Activities that should always have both predecessors and successors
CRITICAL_ACTIVITY_KEYWORDS = [
    "foundation", "structure", "framing", "drywall", "roof", "mechanical",
    "electrical", "plumbing", "elevator", "inspection", "commissioning",
    "punch", "turnover", "certificate", "occupancy", "completion",
]

# Activities that should logically follow others — if they start before expected, flag
SEQUENCE_RULES = [
    ("drywall", ["framing", "mep rough"]),
    ("paint", ["drywall"]),
    ("flooring", ["drywall", "paint"]),
    ("commissioning", ["mechanical", "electrical", "hvac"]),
    ("inspection", ["drywall", "mep"]),
    ("certificate of occupancy", ["inspection", "punch"]),
    ("substantial completion", ["inspection", "punch"]),
    ("turnover", ["punch", "inspection"]),
]


def _parse_date(val):
    if val is None:
        return None
    from datetime import datetime, date as dt
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, dt):
        return val
    s = str(val).strip()[:10]
    if not s or s in ("nan", "None", "NaT", ""):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _duration_days(task: Dict) -> Optional[int]:
    start = _parse_date(task.get("start") or task.get("target_start_date") or task.get("early_start_date"))
    finish = _parse_date(task.get("finish") or task.get("target_end_date") or task.get("early_end_date"))
    if start and finish and finish >= start:
        return (finish - start).days
    return None


def _get_name(task: Dict) -> str:
    return (task.get("name") or task.get("task_name") or "").strip()


def _get_id(task: Dict) -> str:
    return str(task.get("id") or task.get("task_id") or task.get("activity_id") or "").strip()


def _is_summary(task: Dict) -> bool:
    return bool(task.get("summary", False))


def _pct(task: Dict) -> float:
    try:
        return float(task.get("percent_complete") or 0)
    except Exception:
        return 0.0


def run_risk_diagnostics(
    tasks: List[Dict],
    relationships: List[Dict],
    data_date: Optional[date] = None,
) -> Dict:
    """
    Run all risk diagnostic checks. Returns structured findings by category.

    Returns:
        {
          "schedule_health": [finding, ...],
          "schedule_detail": [finding, ...],
          "constructability": [finding, ...],
          "summary": {high_count, medium_count, total}
        }
    Each finding: {category, priority, description, activity_name, activity_id}
    """
    findings = {
        "schedule_health": [],
        "schedule_detail": [],
        "constructability": [],
    }

    non_summary = [t for t in tasks if not _is_summary(t)]
    summary_tasks = [t for t in tasks if _is_summary(t)]

    # Build relationship maps
    has_predecessor: set = set()
    has_successor: set = set()
    for rel in relationships:
        succ = str(rel.get("successor_id") or rel.get("task_id") or rel.get("succ_task_id") or "").strip()
        pred = str(rel.get("predecessor_id") or rel.get("predecessor_task_id") or rel.get("pred_task_id") or "").strip()
        if succ and succ != "None":
            has_predecessor.add(succ)
        if pred and pred != "None":
            has_successor.add(pred)

    task_lookup: Dict[str, Dict] = {}
    for t in tasks:
        tid = _get_id(t)
        if tid:
            task_lookup[tid] = t

    # -------------------------------------------------------------------------
    # SCHEDULE HEALTH CHECKS
    # -------------------------------------------------------------------------

    # H1: Activities past data date with 0% complete (should have started or be complete)
    if data_date:
        for t in non_summary:
            start = _parse_date(t.get("start") or t.get("target_start_date") or t.get("early_start_date"))
            if start and start < data_date and _pct(t) == 0:
                name = _get_name(t)
                tid = _get_id(t)
                findings["schedule_health"].append({
                    "priority": "HIGH",
                    "description": (
                        f"Activity '{name}' (ID: {tid}) has a planned start of {start} — "
                        f"before the data date of {data_date} — but shows 0% complete. "
                        f"Either the activity has not started as planned or percent complete has not been updated."
                    ),
                    "activity_name": name,
                    "activity_id": tid,
                })

    # H2: Activities in progress (0 < pct < 100) with finish date before data date
    if data_date:
        for t in non_summary:
            finish = _parse_date(t.get("finish") or t.get("target_end_date") or t.get("early_end_date"))
            pct_val = _pct(t)
            if finish and finish < data_date and 0 < pct_val < 100:
                name = _get_name(t)
                tid = _get_id(t)
                findings["schedule_health"].append({
                    "priority": "HIGH",
                    "description": (
                        f"Activity '{name}' (ID: {tid}) was scheduled to finish by {finish} "
                        f"but remains at {pct_val:.0f}% complete as of data date {data_date}. "
                        f"This activity is overdue and its incomplete status may be masking a delay."
                    ),
                    "activity_name": name,
                    "activity_id": tid,
                })

    # H3: Missing logic — critical-type activities with no predecessor or no successor
    for t in non_summary:
        name = _get_name(t).lower()
        tid = _get_id(t)
        display = _get_name(t)
        is_critical_type = any(kw in name for kw in CRITICAL_ACTIVITY_KEYWORDS)
        if not is_critical_type:
            continue
        no_pred = tid not in has_predecessor
        no_succ = tid not in has_successor
        if no_pred and no_succ:
            findings["schedule_health"].append({
                "priority": "HIGH",
                "description": (
                    f"Activity '{display}' (ID: {tid}) has no predecessor and no successor. "
                    f"This activity is completely disconnected from the schedule network — "
                    f"it cannot drive or be driven by any other work, and its dates are unreliable."
                ),
                "activity_name": display,
                "activity_id": tid,
            })
        elif no_pred and _pct(t) < 100:
            findings["schedule_health"].append({
                "priority": "MEDIUM",
                "description": (
                    f"Activity '{display}' (ID: {tid}) has no predecessor logic. "
                    f"Its start date is unconstrained — it may be showing an earlier opening "
                    f"date than reality supports. A predecessor tie should be assigned."
                ),
                "activity_name": display,
                "activity_id": tid,
            })
        elif no_succ and _pct(t) < 100:
            findings["schedule_health"].append({
                "priority": "MEDIUM",
                "description": (
                    f"Activity '{display}' (ID: {tid}) has no successor logic. "
                    f"No downstream work depends on its completion — it is an open end "
                    f"and may not be influencing the critical path."
                ),
                "activity_name": display,
                "activity_id": tid,
            })

    # H4: Large blocks of activities all at exactly the same percent complete
    from collections import Counter
    pct_counts = Counter(round(_pct(t)) for t in non_summary if 0 < _pct(t) < 100)
    for pct_val, count in pct_counts.items():
        if count >= 8:
            findings["schedule_health"].append({
                "priority": "MEDIUM",
                "description": (
                    f"{count} activities are all reporting exactly {pct_val:.0f}% complete. "
                    f"Uniform percent complete across many activities suggests bulk-updating rather than "
                    f"individual activity tracking — progress reporting may not reflect actual field conditions."
                ),
                "activity_name": "",
                "activity_id": "",
            })

    # -------------------------------------------------------------------------
    # SCHEDULE DETAIL CHECKS
    # -------------------------------------------------------------------------

    # D1: High-duration activities that should be decomposed
    for t in non_summary:
        dur = _duration_days(t)
        name = _get_name(t)
        tid = _get_id(t)
        if dur is None:
            continue
        # Determine threshold
        name_low = name.lower()
        threshold = DURATION_THRESHOLDS["default"]
        for kw, val in {
            "concrete": DURATION_THRESHOLDS["concrete"],
            "framing": DURATION_THRESHOLDS["framing"],
            "drywall": DURATION_THRESHOLDS["drywall"],
            "roof": DURATION_THRESHOLDS["roofing"],
            "elevator": DURATION_THRESHOLDS["elevator"],
            "inspection": DURATION_THRESHOLDS["inspection"],
            "punch": DURATION_THRESHOLDS["closeout"],
            "site": DURATION_THRESHOLDS["sitework"],
        }.items():
            if kw in name_low:
                threshold = val
                break
        if dur > threshold:
            findings["schedule_detail"].append({
                "priority": "MEDIUM",
                "description": (
                    f"Activity '{name}' (ID: {tid}) has a duration of {dur} calendar days — "
                    f"above the expected threshold of {threshold} days for this type of work. "
                    f"Consider decomposing into smaller, trackable activities to improve schedule fidelity."
                ),
                "activity_name": name,
                "activity_id": tid,
            })

    # D2: Summary tasks that encompass an entire phase with no breakdown
    for t in summary_tasks:
        name = _get_name(t)
        tid = _get_id(t)
        dur = _duration_days(t)
        if dur and dur > 120:
            findings["schedule_detail"].append({
                "priority": "MEDIUM",
                "description": (
                    f"Summary task '{name}' (ID: {tid}) spans {dur} calendar days with no visible "
                    f"sub-activity breakdown in the schedule. Breaking this down by floor, zone, or trade "
                    f"would improve visibility into progress and enable earlier risk identification."
                ),
                "activity_name": name,
                "activity_id": tid,
            })

    # D3: Activities with identical start and finish dates (zero duration non-milestones)
    for t in non_summary:
        start = _parse_date(t.get("start") or t.get("target_start_date"))
        finish = _parse_date(t.get("finish") or t.get("target_end_date"))
        name = _get_name(t)
        tid = _get_id(t)
        is_milestone = bool(t.get("milestone", False))
        if start and finish and start == finish and not is_milestone and name:
            findings["schedule_detail"].append({
                "priority": "MEDIUM",
                "description": (
                    f"Activity '{name}' (ID: {tid}) has a zero-duration that is not flagged as a milestone. "
                    f"If this represents real work, a duration should be assigned. "
                    f"If it is a milestone, it should be flagged accordingly."
                ),
                "activity_name": name,
                "activity_id": tid,
            })

    # -------------------------------------------------------------------------
    # CONSTRUCTABILITY CHECKS
    # -------------------------------------------------------------------------

    # C1: Sequence logic — downstream work starting before upstream logic suggests
    task_by_name: Dict[str, Dict] = {}
    for t in non_summary:
        task_by_name[_get_name(t).lower()] = t

    for downstream_kw, upstream_kws in SEQUENCE_RULES:
        # Find downstream activities
        downstream = [t for t in non_summary if downstream_kw in _get_name(t).lower()]
        for dt_task in downstream[:3]:  # Cap at 3 per rule
            dt_start = _parse_date(dt_task.get("start") or dt_task.get("target_start_date"))
            dt_name = _get_name(dt_task)
            dt_id = _get_id(dt_task)
            if not dt_start:
                continue
            for up_kw in upstream_kws:
                upstream = [t for t in non_summary if up_kw in _get_name(t).lower()]
                for up_task in upstream[:2]:
                    up_finish = _parse_date(up_task.get("finish") or up_task.get("target_end_date"))
                    up_name = _get_name(up_task)
                    up_pct = _pct(up_task)
                    if not up_finish:
                        continue
                    # Flag if downstream starts before upstream finishes by more than 7 days
                    # AND upstream is not complete
                    if dt_start < up_finish and (up_finish - dt_start).days > 7 and up_pct < 100:
                        findings["constructability"].append({
                            "priority": "HIGH",
                            "description": (
                                f"'{dt_name}' (ID: {dt_id}) is scheduled to start {dt_start} — "
                                f"before '{up_name}' finishes on {up_finish}. "
                                f"Based on standard construction sequencing, {downstream_kw} work "
                                f"cannot productively proceed until {up_kw} is complete. "
                                f"Verify whether this overlap is intentional and field-supported."
                            ),
                            "activity_name": dt_name,
                            "activity_id": dt_id,
                        })

    # C2: Late-starting activities where all named predecessors are complete
    if data_date:
        for t in non_summary:
            start = _parse_date(t.get("start") or t.get("target_start_date") or t.get("early_start_date"))
            tid = _get_id(t)
            name = _get_name(t)
            pct_val = _pct(t)
            if not start or pct_val > 0:
                continue
            # Activity hasn't started, starts significantly after data date
            if start > data_date + timedelta(days=30):
                # Check if it has predecessors — if all complete, flag as late start
                pred_ids = [
                    str(rel.get("predecessor_id") or rel.get("predecessor_task_id") or rel.get("pred_task_id") or "").strip()
                    for rel in relationships
                    if str(rel.get("successor_id") or rel.get("task_id") or rel.get("succ_task_id") or "").strip() == tid
                ]
                if pred_ids:
                    preds_all_complete = all(
                        _pct(task_lookup.get(pid, {})) >= 100
                        for pid in pred_ids if pid in task_lookup
                    )
                    if preds_all_complete and pred_ids:
                        findings["constructability"].append({
                            "priority": "HIGH",
                            "description": (
                                f"Activity '{name}' (ID: {tid}) is not scheduled to start until {start}, "
                                f"yet all of its predecessors are 100% complete as of data date {data_date}. "
                                f"This activity is starting later than its logic allows — "
                                f"the delay may be artificial or there may be an undocumented constraint driving the late start."
                            ),
                            "activity_name": name,
                            "activity_id": tid,
                        })

    # C3: Activities with float = 0 (critical) that have very long durations — single point of failure
    for t in non_summary:
        float_val = t.get("total_float") or t.get("float_days") or t.get("total_float_hr_cnt")
        if float_val is None:
            continue
        try:
            float_days = float(float_val)
            # P6 stores float in hours — normalize
            if float_days > 500:
                float_days = float_days / 8
        except Exception:
            continue
        dur = _duration_days(t)
        name = _get_name(t)
        tid = _get_id(t)
        if float_days <= 0 and dur and dur > 45:
            findings["constructability"].append({
                "priority": "HIGH",
                "description": (
                    f"Activity '{name}' (ID: {tid}) is on the critical path (zero float) "
                    f"with a duration of {dur} calendar days. This single activity represents a significant "
                    f"window of risk with no schedule buffer. Consider whether this can be broken into phases "
                    f"or whether contingency has been allocated around it."
                ),
                "activity_name": name,
                "activity_id": tid,
            })

    # Cap findings per category to avoid token overload
    for cat in findings:
        high = [f for f in findings[cat] if f["priority"] == "HIGH"]
        med = [f for f in findings[cat] if f["priority"] == "MEDIUM"]
        findings[cat] = high[:8] + med[:5]

    high_total = sum(1 for cat in findings for f in findings[cat] if f["priority"] == "HIGH")
    med_total = sum(1 for cat in findings for f in findings[cat] if f["priority"] == "MEDIUM")

    findings["summary"] = {
        "high_count": high_total,
        "medium_count": med_total,
        "total": high_total + med_total,
    }

    return findings


def format_risk_for_context(risk: Dict) -> str:
    """
    Format risk findings into a compact LLM context block.
    The LLM narrates these — it does NOT dump the raw list.
    """
    if not risk:
        return ""

    s = risk.get("summary", {})
    if s.get("total", 0) == 0:
        return "=== SCHEDULE RISK DIAGNOSTICS ===\nNo significant risk findings detected."

    lines = [
        f"=== SCHEDULE RISK DIAGNOSTICS ===",
        f"Findings: {s.get('high_count', 0)} HIGH priority | {s.get('medium_count', 0)} MEDIUM priority",
        f"(Use these to narrate project risks when asked — do not dump this list verbatim)",
        "",
    ]

    categories = [
        ("schedule_health",   "SCHEDULE HEALTH"),
        ("schedule_detail",   "SCHEDULE DETAIL"),
        ("constructability",  "CONSTRUCTABILITY"),
    ]

    for key, label in categories:
        items = risk.get(key, [])
        if not items:
            continue
        lines.append(f"[ {label} ]")
        for f in items:
            pri = f["priority"]
            desc = f["description"]
            lines.append(f"  [{pri}] {desc}")
        lines.append("")

    return "\n".join(lines)
