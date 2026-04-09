"""
variance_engine.py - Schedule variance analysis engine for Stelic Copilot.

Compares two schedule snapshots (current vs. previous or vs. baseline) and
produces a structured, phase-grouped variance report for LLM narration.

The LLM is expected to NARRATE this data in project language, not dump it.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

# Phase keyword groups — activities are bucketed into these by name matching.
# Order matters: first match wins.
PHASE_GROUPS = [
    ("Site / Civil",          ["site", "civil", "grading", "earthwork", "clearing", "erosion", "utility", "utilities", "underground", "storm", "sewer", "water main", "paving", "parking lot", "curb", "sidewalk"]),
    ("Foundations",           ["foundation", "footing", "footer", "caisson", "pile", "grade beam", "slab on grade", "sog", "underslab", "underpinning"]),
    ("Structure / Frame",     ["structural", "structure", "steel", "column", "beam", "frame", "framing", "deck", "decking", "shear wall", "cmu", "masonry", "concrete", "tilt", "precast", "post-tension"]),
    ("Dry-in / Enclosure",    ["roof", "roofing", "dry-in", "dryin", "enclosure", "exterior", "facade", "curtain wall", "storefront", "glazing", "window", "waterproof", "building envelope", "cladding", "skin"]),
    ("MEP Rough-in",          ["mechanical", "electrical", "plumbing", "hvac", "ductwork", "conduit", "rough-in", "roughin", "piping", "fire protection", "sprinkler", "low voltage", "data", "telecom"]),
    ("Elevator / Vertical",   ["elevator", "escalator", "lift", "hoistway"]),
    ("Interiors",             ["drywall", "framing interior", "insulation", "finishes", "flooring", "ceiling", "painting", "paint", "millwork", "casework", "tile", "carpet", "doors", "hardware", "interior"]),
    ("MEP Finish / Trim",     ["trim out", "trim-out", "device", "fixtures", "switchgear", "startup", "start-up", "balancing", "commissioning", "controls", "bms", "fire alarm", "test and balance"]),
    ("Site Improvements",     ["site improvement", "landscaping", "irrigation", "hardscape", "fencing", "signage", "striping", "monument"]),
    ("Inspections / Closeout",["inspection", "punch", "certificate of occupancy", "substantial completion", "turnover", "closeout", "final completion", "final inspection", "beneficial occupancy", "owner acceptance", "project closeout"]),
]

DEFAULT_PHASE = "General / Other"


def _phase_for(name: str) -> str:
    """Assign an activity to a phase group based on its name."""
    low = name.lower()
    for phase, keywords in PHASE_GROUPS:
        if any(kw in low for kw in keywords):
            return phase
    return DEFAULT_PHASE


def _parse_date(val) -> Optional[date]:
    """Parse any date string or object to a date. Returns None on failure."""
    if val is None:
        return None
    # datetime is a subclass of date — must check datetime first
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
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


def _day_delta(new_date: Optional[date], old_date: Optional[date]) -> Optional[int]:
    """Positive = slipped, Negative = accelerated."""
    if new_date is None or old_date is None:
        return None
    return (new_date - old_date).days


def _extract_activity_map(tasks: List[Dict]) -> Dict[str, Dict]:
    """
    Build {normalized_name: task_dict} from a task list.
    Filters out summaries and blank names.
    Where duplicate names exist, append a counter suffix to keep both.
    """
    result = {}
    name_count: Dict[str, int] = {}
    for t in tasks:
        name = (t.get("name") or t.get("task_name") or "").strip()
        if not name:
            continue
        if t.get("summary", False):
            continue
        key = name.lower()
        if key in result:
            # First collision — rename the existing entry with suffix :1
            if name_count.get(key, 0) == 0:
                result[key + ":1"] = result.pop(key)
                name_count[key] = 1
            name_count[key] += 1
            result[key + f":{name_count[key]}"] = t
        else:
            result[key] = t
    return result


def compute_variance(
    current_tasks: List[Dict],
    previous_tasks: List[Dict],
    label_current: str = "Current",
    label_previous: str = "Previous",
) -> Dict:
    """
    Compare current vs. previous task lists and produce phase-grouped variance.

    Returns:
        {
          "label_current": str,
          "label_previous": str,
          "phases": {
              phase_name: {
                  "slipped": [variance_items],
                  "accelerated": [variance_items],
                  "unchanged": int,
                  "new_activities": [names],
                  "removed_activities": [names],
              }
          },
          "summary": {
              "total_compared": int,
              "total_slipped": int,
              "total_accelerated": int,
              "max_slip_days": int,
              "max_slip_activity": str,
              "max_accel_days": int,
              "max_accel_activity": str,
              "phases_with_movement": [str],
          },
          "anomalies": [str],   # Notable findings for LLM to highlight
        }
    """
    curr_map = _extract_activity_map(current_tasks)
    prev_map = _extract_activity_map(previous_tasks)

    phases: Dict[str, Dict] = {}

    def _get_phase(name_key: str) -> str:
        return _phase_for(name_key)

    def _ensure_phase(phase: str):
        if phase not in phases:
            phases[phase] = {
                "slipped": [],
                "accelerated": [],
                "unchanged": 0,
                "new_activities": [],
                "removed_activities": [],
            }

    total_slipped = 0
    total_accelerated = 0
    max_slip_days = 0
    max_slip_activity = ""
    max_accel_days = 0
    max_accel_activity = ""

    # Match activities by name
    all_names = set(curr_map.keys()) | set(prev_map.keys())

    for name_key in all_names:
        curr = curr_map.get(name_key)
        prev = prev_map.get(name_key)
        phase = _get_phase(name_key)
        _ensure_phase(phase)

        display_name = (curr or prev).get("name") or (curr or prev).get("task_name") or name_key

        if curr and not prev:
            phases[phase]["new_activities"].append(display_name)
            continue

        if prev and not curr:
            phases[phase]["removed_activities"].append(display_name)
            continue

        # Both exist — compute finish delta
        curr_finish = _parse_date(curr.get("finish") or curr.get("target_end_date"))
        prev_finish = _parse_date(prev.get("finish") or prev.get("target_end_date"))
        curr_start  = _parse_date(curr.get("start") or curr.get("target_start_date"))
        prev_start  = _parse_date(prev.get("start") or prev.get("target_start_date"))

        finish_delta = _day_delta(curr_finish, prev_finish)
        start_delta  = _day_delta(curr_start, prev_start)

        if finish_delta is None:
            phases[phase]["unchanged"] += 1
            continue

        # Ignore trivial movement (1-2 day noise)
        if abs(finish_delta) <= 2:
            phases[phase]["unchanged"] += 1
            continue

        # Float info for context — handle both MPP string format and XER hours float
        float_days = None
        raw_float = curr.get("total_slack") or curr.get("total_float_hrs")
        if raw_float is not None and raw_float != "":
            try:
                import re as _re
                s_f = str(raw_float).strip().lower()
                m_f = _re.match(r'([\d.]+)\s*([dh]?)', s_f)
                if m_f:
                    fval = float(m_f.group(1))
                    unit = m_f.group(2)
                    if unit == 'h':
                        float_days = round(fval / 8.0, 1)  # hours → days
                    elif unit == 'd':
                        float_days = round(fval, 1)         # already days
                    else:
                        # No unit — if value looks like hours (>60), convert
                        float_days = round(fval / 8.0, 1) if fval > 60 else round(fval, 1)
            except Exception:
                pass

        item = {
            "name": display_name,
            "phase": phase,
            "finish_delta": finish_delta,
            "start_delta": start_delta,
            "curr_finish": str(curr_finish) if curr_finish else None,
            "prev_finish": str(prev_finish) if prev_finish else None,
            "curr_start": str(curr_start) if curr_start else None,
            "prev_start": str(prev_start) if prev_start else None,
            "float_days": float_days,
            "critical": curr.get("critical", False),
            "percent_complete": curr.get("percent_complete", 0),
        }

        if finish_delta > 0:
            phases[phase]["slipped"].append(item)
            total_slipped += 1
            if finish_delta > max_slip_days:
                max_slip_days = finish_delta
                max_slip_activity = display_name
        else:
            phases[phase]["accelerated"].append(item)
            total_accelerated += 1
            if abs(finish_delta) > max_accel_days:
                max_accel_days = abs(finish_delta)
                max_accel_activity = display_name

    # Sort slipped by magnitude descending
    for phase_data in phases.values():
        phase_data["slipped"].sort(key=lambda x: x["finish_delta"], reverse=True)
        phase_data["accelerated"].sort(key=lambda x: abs(x["finish_delta"]), reverse=True)

    phases_with_movement = [
        p for p, d in phases.items()
        if d["slipped"] or d["accelerated"]
    ]

    # Build anomaly flags for LLM attention
    anomalies = _detect_anomalies(phases, max_slip_days, max_slip_activity)

    return {
        "label_current": label_current,
        "label_previous": label_previous,
        "phases": phases,
        "summary": {
            "total_compared": len(all_names),
            "total_slipped": total_slipped,
            "total_accelerated": total_accelerated,
            "max_slip_days": max_slip_days,
            "max_slip_activity": max_slip_activity,
            "max_accel_days": max_accel_days,
            "max_accel_activity": max_accel_activity,
            "phases_with_movement": phases_with_movement,
        },
        "anomalies": anomalies,
    }


def _detect_anomalies(phases: Dict, max_slip: int, max_slip_act: str) -> List[str]:
    """
    Flag notable conditions the LLM should call out specifically.
    """
    flags = []

    for phase, data in phases.items():
        slipped = data["slipped"]
        if not slipped:
            continue

        # Large slip on a critical activity with no float buffer
        critical_slips = [s for s in slipped if s["critical"] and (s["float_days"] or 0) < 5]
        for s in critical_slips[:3]:
            flags.append(
                f"CRITICAL SLIP: '{s['name']}' ({phase}) slipped {s['finish_delta']} calendar days with near-zero float \u2014 likely driving project completion."
            )

        # Large slip offset by float — recoverable
        buffered_slips = [s for s in slipped if (s["float_days"] or 0) >= s["finish_delta"] and s["finish_delta"] > 5]
        for s in buffered_slips[:2]:
            flags.append(
                f"FLOAT-BUFFERED: '{s['name']}' ({phase}) slipped {s['finish_delta']} calendar days but has {s['float_days']} calendar days float \u2014 may not affect completion."
            )

        # Systemic movement — 3+ activities in same phase all moved same direction
        if len(slipped) >= 3:
            avg_slip = sum(s["finish_delta"] for s in slipped) / len(slipped)
            if avg_slip >= 7:
                flags.append(
                    f"SYSTEMIC SLIP: {len(slipped)} activities in '{phase}' averaged {avg_slip:.0f} calendar days slip \u2014 likely a phase-level driver, not isolated."
                )

        # Early-phase slip propagating forward
        early_phases = ["Site / Civil", "Foundations", "Structure / Frame"]
        late_phases = ["MEP Finish / Trim", "Interiors", "Inspections / Closeout"]
        if phase in early_phases and slipped:
            for lp in late_phases:
                if phases.get(lp, {}).get("slipped"):
                    flags.append(
                        f"PROPAGATION: Slip in '{phase}' may be driving downstream movement in '{lp}' \u2014 trace source before reporting."
                    )
                    break

    # Compression flag — late phases slipped while early phases accelerated
    late_slipped = any(
        phases.get(p, {}).get("slipped")
        for p in ["MEP Finish / Trim", "Inspections / Closeout", "Interiors"]
    )
    early_accel = any(
        phases.get(p, {}).get("accelerated")
        for p in ["Site / Civil", "Foundations", "Structure / Frame"]
    )
    if late_slipped and early_accel:
        flags.append(
            "SCHEDULE COMPRESSION: Early phases accelerated while late phases slipped — downstream work may be overlapping more aggressively than prior update."
        )

    return flags


def compute_compression(current_tasks: List[Dict], previous_tasks: List[Dict]) -> Dict:
    """
    Quantifies schedule compression between two snapshots.
    Compression = same/similar scope packed into less remaining time.

    Returns:
        {
          "current_remaining_span_days": int,   # calendar days from data date to last finish
          "previous_remaining_span_days": int,
          "span_delta_days": int,               # negative = compressed, positive = expanded
          "current_activity_density": float,    # activities per remaining week
          "previous_activity_density": float,
          "density_delta_pct": float,           # % change in density (positive = more compressed)
          "current_incomplete_count": int,
          "previous_incomplete_count": int,
          "compression_signal": str,            # "COMPRESSED" | "EXPANDED" | "NEUTRAL"
          "compression_pct": float,             # % the remaining span changed
          "narrative_hint": str,
        }
    """
    def _remaining(tasks):
        incomplete = [t for t in tasks if float(t.get("percent_complete") or 0) < 100]
        dates = []
        for t in incomplete:
            d = _parse_date(t.get("finish") or t.get("target_end_date") or t.get("early_end_date"))
            if d:
                dates.append(d)
        if not dates:
            return None, None, len(incomplete)
        return min(dates), max(dates), len(incomplete)

    curr_start, curr_end, curr_count = _remaining(current_tasks)
    prev_start, prev_end, prev_count = _remaining(previous_tasks)

    curr_span = (curr_end - curr_start).days if curr_start and curr_end else None
    prev_span = (prev_end - prev_start).days if prev_start and prev_end else None

    if curr_span is None or prev_span is None or prev_span == 0:
        return {
            "compression_signal": "UNKNOWN",
            "narrative_hint": "Insufficient date data to assess compression."
        }

    span_delta = curr_span - prev_span
    compression_pct = round((span_delta / prev_span) * 100, 1)

    # Density = incomplete activities per week of remaining span
    curr_density = round((curr_count / (curr_span / 7)) if curr_span > 0 else 0, 2)
    prev_density = round((prev_count / (prev_span / 7)) if prev_span > 0 else 0, 2)
    density_delta_pct = round(((curr_density - prev_density) / prev_density * 100) if prev_density > 0 else 0, 1)

    # Signal thresholds
    if compression_pct <= -5 and density_delta_pct >= 5:
        signal = "COMPRESSED"
    elif compression_pct >= 5 and density_delta_pct <= -5:
        signal = "EXPANDED"
    else:
        signal = "NEUTRAL"

    # Narrative hint
    if signal == "COMPRESSED":
        hint = (
            f"The remaining schedule has compressed by {abs(compression_pct)}% — "
            f"the same scope is now planned into {abs(span_delta)} fewer calendar days. "
            f"Activity density increased by {density_delta_pct}%. "
            f"Assess whether durations were shortened on paper or genuine acceleration is supported."
        )
    elif signal == "EXPANDED":
        hint = (
            f"The remaining schedule has expanded by {abs(compression_pct)}% — "
            f"work has been redistributed across {abs(span_delta)} additional calendar days. "
            f"Activity density decreased by {abs(density_delta_pct)}%. "
            f"This may reflect a more realistic plan or a pushed-out completion."
        )
    else:
        hint = (
            f"No significant compression or expansion detected. "
            f"Remaining span changed by {span_delta:+d} calendar days ({compression_pct:+.1f}%) "
            f"with a {density_delta_pct:+.1f}% change in activity density."
        )

    return {
        "current_remaining_span_days": curr_span,
        "previous_remaining_span_days": prev_span,
        "span_delta_days": span_delta,
        "current_activity_density": curr_density,
        "previous_activity_density": prev_density,
        "density_delta_pct": density_delta_pct,
        "current_incomplete_count": curr_count,
        "previous_incomplete_count": prev_count,
        "compression_signal": signal,
        "compression_pct": compression_pct,
        "narrative_hint": hint,
    }


def format_variance_for_context(variance: Dict, max_items_per_phase: int = 5) -> str:
    """
    Formats the variance result into a compact LLM context block.
    The LLM narrates from this — it does NOT dump this raw to the user.
    """
    if not variance:
        return ""

    s = variance.get("summary", {})
    label_curr = variance.get("label_current", "Current")
    label_prev = variance.get("label_previous", "Previous")

    lines = [
        f"=== VARIANCE ANALYSIS: {label_curr} vs. {label_prev} ===",
        f"Activities compared: {s.get('total_compared', 0)} | "
        f"Slipped: {s.get('total_slipped', 0)} | "
        f"Accelerated (pulled earlier): {s.get('total_accelerated', 0)}",
        "(All day values are CALENDAR DAYS)",
    ]

    if s.get("max_slip_days", 0) > 0:
        lines.append(f"Largest slip: {s['max_slip_days']} calendar days — {s['max_slip_activity']}")
    if s.get("max_accel_days", 0) > 0:
        lines.append(f"Largest pull-forward: {s['max_accel_days']} calendar days — {s['max_accel_activity']}")

    lines.append("")

    # Anomalies first — most important for LLM focus
    anomalies = variance.get("anomalies", [])
    if anomalies:
        lines.append("KEY FINDINGS (address these specifically):")
        for a in anomalies:
            lines.append(f"  ! {a}")
        lines.append("")

    # Phase-by-phase breakdown
    phases = variance.get("phases", {})
    phase_order = [p for p, _ in PHASE_GROUPS] + [DEFAULT_PHASE]

    for phase in phase_order:
        data = phases.get(phase)
        if not data:
            continue
        slipped = data["slipped"]
        accel = data["accelerated"]
        if not slipped and not accel:
            continue

        lines.append(f"[ {phase} ]")

        for item in slipped[:max_items_per_phase]:
            crit_tag = " [CRITICAL]" if item["critical"] else ""
            float_tag = f" | Float: {item['float_days']} cal days" if item["float_days"] is not None else ""
            lines.append(
                f"  SLIP  {item['finish_delta']:+d} cal days  {item['name']}{crit_tag}{float_tag}"
                + (f"  ({item['prev_finish']} \u2192 {item['curr_finish']})" if item["prev_finish"] and item["curr_finish"] else "")
            )
        if len(slipped) > max_items_per_phase:
            lines.append(f"  ... +{len(slipped) - max_items_per_phase} more slipped in this phase")

        for item in accel[:max_items_per_phase]:
            crit_tag = " [CRITICAL]" if item["critical"] else ""
            float_tag = f" | Float: {item['float_days']} cal days" if item["float_days"] is not None else ""
            lines.append(
                f"  PULL  {item['finish_delta']:+d} cal days  {item['name']}{crit_tag}{float_tag}"
                + (f"  ({item['prev_finish']} \u2192 {item['curr_finish']})" if item["prev_finish"] and item["curr_finish"] else "")
            )
        if len(accel) > max_items_per_phase:
            lines.append(f"  ... +{len(accel) - max_items_per_phase} more pulled earlier in this phase")

        new_acts = data.get("new_activities", [])
        removed = data.get("removed_activities", [])
        if new_acts:
            lines.append(f"  NEW   {len(new_acts)} activities added in this phase")
        if removed:
            lines.append(f"  REMOV {len(removed)} activities removed in this phase")
        lines.append("")

    return "\n".join(lines)
