"""
critical_path.py - Critical path chain builder for MPP/XML and XER schedules.

Builds ordered predecessor chains from any target activity backwards through
the schedule network. Used to generate narrative critical path descriptions
for the LLM Copilot.

Two modes:
  - Full project CP: walks back from the contract completion / last milestone
  - Per-activity runoff: walks back from any named/matched activity

Chain walk strategy (Option 2 — float-ranked, no critical flag dependency):
  At each step, all predecessors are considered. The one with the LOWEST total
  float (most constrained) is selected as the driving predecessor. If float is
  unavailable, the latest-finishing predecessor is used as a proxy. This means
  the chain walk works correctly even when the MPP critical flag is unreliable
  or missing, which is common in contractor-submitted schedules.

  The critical flag is used ONLY as a tiebreaker when two predecessors have
  identical float — it is never the primary selection criterion.

Output is a structured chain dict the LLM can narrate naturally.
"""

from typing import List, Dict, Optional, Tuple, Set
import logging

logger = logging.getLogger(__name__)

CONTRACT_KEYWORDS = [
    "certificate of occupancy",
    "substantial completion",
    "turnover",
    "contract complete",
    "project complete",
    "final completion",
    "beneficial occupancy",
    "punch list complete",
    "final inspection",
    "owner acceptance",
    "project closeout",
    "contract completion",
]


def _is_contract_completion(name: str) -> bool:
    low = name.lower()
    return any(kw in low for kw in CONTRACT_KEYWORDS)


def _find_target_task(tasks: List[Dict], target_name: Optional[str] = None) -> Optional[Dict]:
    """
    Find the target task to trace back from.
    If target_name provided: fuzzy match by substring (case-insensitive).
    If not provided: find contract completion milestone.
    Falls back to the latest-finishing incomplete task.
    """
    if target_name:
        low = target_name.lower()
        # Exact substring match first
        for t in tasks:
            if low in t.get("name", "").lower():
                return t
        # Token match fallback
        tokens = low.split()
        best, best_score = None, 0
        for t in tasks:
            name_low = t.get("name", "").lower()
            score = sum(1 for tok in tokens if tok in name_low)
            if score > best_score:
                best, best_score = t, score
        return best if best_score > 0 else None

    # No target — find contract completion milestone
    for t in tasks:
        if _is_contract_completion(t.get("name", "")) and t.get("milestone", False):
            return t
    # Fallback: any activity matching contract keywords
    for t in tasks:
        if _is_contract_completion(t.get("name", "")):
            return t
    # Last fallback: latest finish date among incomplete tasks
    incomplete = [t for t in tasks if t.get("percent_complete", 0) < 100]
    if incomplete:
        def sort_key(t):
            return t.get("finish") or t.get("target_end_date") or ""
        return max(incomplete, key=sort_key)
    return None


def _build_predecessor_map(relationships: List[Dict]) -> Dict[str, List[str]]:
    """
    Build {task_id: [predecessor_task_ids]} map from relationship list.
    Accepts both MPP-style and XER-style field names.
    """
    pred_map: Dict[str, List[str]] = {}
    for rel in relationships:
        # Normalized: successor_id / predecessor_id
        # Legacy fallbacks: task_id / predecessor_task_id / pred_task_id
        succ = str(rel.get("successor_id") or rel.get("task_id") or rel.get("succ_task_id") or "").strip()
        pred = str(rel.get("predecessor_id") or rel.get("predecessor_task_id") or rel.get("pred_task_id") or "").strip()
        if succ and pred and succ != "None" and pred != "None":
            pred_map.setdefault(succ, []).append(pred)
    return pred_map


def _get_float_days(task: Dict) -> Optional[float]:
    """
    Extract total float as a float (days). Handles MPP duration strings ('5.0d', '40.0h')
    and XER float hours. Returns None if unavailable.
    """
    import re
    raw = task.get("total_slack") or task.get("total_float_hrs")
    if raw is None or raw == "":
        return None
    try:
        s = str(raw).lower().strip()
        m = re.match(r'(-?[\d.]+)\s*([dh]?)', s)
        if m:
            val = float(m.group(1))
            unit = m.group(2)
            if unit == 'h':
                return round(val / 8.0, 1)
            return round(val, 1)
    except Exception:
        pass
    return None


def _walk_predecessors(
    start_id: str,
    pred_map: Dict[str, List[str]],
    task_lookup: Dict[str, Dict],
    max_depth: int = 60,
    critical_ids: Optional[Set[str]] = None,
) -> List[Dict]:
    """
    Walk backwards through predecessor chain from start_id.

    Selection strategy — float-ranked (Option 2):
      1. Among all unvisited predecessors, pick the one with the LOWEST total float.
         Lowest float = most constrained = most likely driving predecessor.
      2. If float is unavailable for all candidates, fall back to latest finish date
         (latest finish = most likely to be on the driving path).
      3. The critical flag is used ONLY as a tiebreaker when float values are equal.

    This approach works correctly even when the MPP critical flag is unreliable,
    absent, or set incorrectly by the contractor's scheduler.

    Returns ordered list [start → ... → earliest driver], most recent first.
    """
    visited: Set[str] = set()
    chain: List[Dict] = []
    current_id = start_id

    for _ in range(max_depth):
        if current_id in visited:
            break
        visited.add(current_id)

        task = task_lookup.get(current_id)
        if task:
            chain.append(task)

        preds = pred_map.get(current_id, [])
        candidates = [p for p in preds if p not in visited]

        if not candidates:
            break

        def pred_sort_key(pid):
            t = task_lookup.get(pid, {})
            float_days = _get_float_days(t)
            finish = t.get("finish") or t.get("target_end_date") or ""
            is_critical = 1 if (critical_ids and pid in critical_ids) else 0

            # Sort key: (float ascending — None treated as large positive, finish descending, critical descending)
            # We want: lowest float first, then latest finish, then critical as tiebreaker
            float_sort = float_days if float_days is not None else 9999.0
            # Invert finish string for descending sort: '~' sorts after all ISO date chars
            finish_desc = tuple(~ord(c) for c in finish) if finish else (0,)
            return (float_sort, -is_critical, finish_desc)

        # Pick the predecessor with lowest float (most constrained)
        # Among ties: prefer critical, then latest finish
        best = min(candidates, key=lambda pid: pred_sort_key(pid))
        current_id = best

    return chain


def build_critical_chain(
    tasks: List[Dict],
    relationships: List[Dict],
    target_name: Optional[str] = None,
    critical_ids: Optional[Set[str]] = None,
) -> Dict:
    """
    Main entry point. Builds a critical path chain for LLM narration.

    Args:
        tasks: normalized task list (from MPPParser or P6Parser)
        relationships: list of {task_id, pred_task_id/predecessor_task_id} dicts
        target_name: optional activity name to trace back from (per-activity runoff)
        critical_ids: optional set of task IDs already flagged critical (used as tiebreaker only)

    Returns dict:
        {
          "mode": "full_project" | "activity_runoff",
          "target": {task dict},
          "chain": [ordered task dicts, most recent -> earliest driver],
          "chain_names": [list of activity names in order],
          "narrative_hint": "string for LLM to use as narration base",
          "depth": int,
          "warning": optional string
        }
    """
    if not tasks:
        return {"error": "No tasks available"}

    if not relationships:
        return {
            "error": "No relationships available — cannot build predecessor chain. "
                     "Check that the schedule file contains logic ties and that the "
                     "relationships list was passed through correctly."
        }

    # Build lookup and predecessor map
    task_lookup: Dict[str, Dict] = {}
    for t in tasks:
        tid = str(t.get("id") or t.get("task_id") or "").strip()
        if tid and tid != "None":
            task_lookup[tid] = t

    pred_map = _build_predecessor_map(relationships)

    if not pred_map:
        return {
            "error": "Predecessor map is empty — relationships parsed but no valid predecessor links found. "
                     "Check field name alignment (task_id / predecessor_task_id for MPP, task_id / pred_task_id for XER)."
        }

    # Find target
    target = _find_target_task(tasks, target_name)
    if not target:
        return {"error": f"Could not find target activity{': ' + target_name if target_name else ' (contract completion)'}"}

    target_id = str(target.get("id") or target.get("task_id") or "").strip()
    mode = "activity_runoff" if target_name else "full_project"

    # Check if target has any predecessors at all
    if target_id not in pred_map:
        # Target has no predecessors in the map — this is the disconnected milestone problem
        return {
            "mode": mode,
            "target": target,
            "chain": [target],
            "chain_names": [target.get("name") or target.get("task_name") or ""],
            "narrative_hint": "",
            "depth": 1,
            "warning": (
                f"'{target.get('name', 'Target activity')}' has no predecessor logic in the schedule network. "
                "This milestone is disconnected — the critical path cannot be traced. "
                "A logic review is required before this schedule can support path-based analysis."
            )
        }

    # Build the chain
    chain = _walk_predecessors(target_id, pred_map, task_lookup, critical_ids=critical_ids)

    if not chain:
        return {
            "mode": mode,
            "target": target,
            "chain": [],
            "chain_names": [],
            "narrative_hint": "",
            "depth": 0,
            "warning": "No predecessor chain found — activity may have no logic ties."
        }

    # Extract names, filtering out summaries/blank
    chain_names = [
        t.get("name") or t.get("task_name") or ""
        for t in chain
        if not t.get("summary", False) and (t.get("name") or t.get("task_name") or "").strip()
    ]

    # Build narrative hint for LLM
    narrative_hint = _build_narrative_hint(chain_names, target, mode)

    # Warn if chain is suspiciously short (likely still disconnected)
    warning = None
    if len(chain_names) <= 2:
        warning = (
            f"Critical path chain is very short ({len(chain_names)} activities). "
            "This may indicate the schedule has incomplete predecessor logic near the completion milestone. "
            "Verify that the completion milestone has upstream logic ties."
        )

    result = {
        "mode": mode,
        "target": target,
        "chain": chain,
        "chain_names": chain_names,
        "narrative_hint": narrative_hint,
        "depth": len(chain),
    }
    if warning:
        result["warning"] = warning
    return result


def _build_narrative_hint(chain_names: List[str], target: Dict, mode: str) -> str:
    """
    Builds a structured narrative hint the LLM uses as a base to describe the CP.
    Not the final output — the LLM will refine this into professional prose.
    """
    if not chain_names:
        return ""

    target_name = target.get("name") or target.get("task_name") or "project completion"
    target_date = (
        target.get("finish") or target.get("early_end") or
        target.get("target_end_date") or ""
    )

    if mode == "full_project":
        prefix = f"The critical path to {target_name}"
    else:
        prefix = f"The completion of {target_name} is driven by"

    if len(chain_names) == 1:
        return f"{prefix} {chain_names[0]}."

    # Build a condensed chain description
    if len(chain_names) <= 6:
        mid = ", ".join(chain_names[1:-1])
        if mid:
            hint = f"{prefix} {chain_names[0]}, progressing through {mid}, culminating in {chain_names[-1]}"
        else:
            hint = f"{prefix} {chain_names[0]}, leading into {chain_names[-1]}"
    else:
        early = ", ".join(chain_names[:3])
        mid = ", ".join(chain_names[3:6])
        late = ", ".join(chain_names[6:9]) if len(chain_names) > 6 else ""
        hint = f"{prefix} {early}, advancing through {mid}"
        if late:
            hint += f", then into {late}"
        if len(chain_names) > 9:
            hint += f", and {len(chain_names) - 9} additional driving activities"

    if target_date:
        hint += f", targeting {target_date}."
    else:
        hint += "."

    return hint


def compare_critical_chains(current_chain: Dict, previous_chain: Dict) -> str:
    """
    Compares two critical path chains (current vs previous) and returns a
    structured context block describing what shifted, what dropped off, and
    what's new — for LLM narration.
    """
    curr_names = current_chain.get("chain_names", [])
    prev_names = previous_chain.get("chain_names", [])

    if not curr_names and not prev_names:
        return ""

    curr_set = set(n.lower() for n in curr_names)
    prev_set = set(n.lower() for n in prev_names)

    held = [n for n in curr_names if n.lower() in prev_set]
    dropped = [n for n in prev_names if n.lower() not in curr_set]
    added = [n for n in curr_names if n.lower() not in prev_set]

    curr_top = curr_names[:3] if curr_names else []
    prev_top = prev_names[:3] if prev_names else []

    lines = ["=== CRITICAL PATH SHIFT (Current vs Previous) ==="]

    # Surface any warnings from the chain builds
    curr_warn = current_chain.get("warning", "")
    prev_warn = previous_chain.get("warning", "")
    if curr_warn:
        lines.append(f"[CURRENT CP WARNING]: {curr_warn}")
    if prev_warn:
        lines.append(f"[PREVIOUS CP WARNING]: {prev_warn}")

    if curr_top:
        lines.append(f"Current driving sequence (top): {' → '.join(curr_top)}")
    if prev_top:
        lines.append(f"Previous driving sequence (top): {' → '.join(prev_top)}")

    lines.append("")

    if not dropped and not added:
        lines.append("PATH UNCHANGED: The driving sequence has not materially changed from the previous update.")
    else:
        if dropped:
            lines.append(f"DROPPED FROM PATH ({len(dropped)}): {', '.join(dropped[:6])}")
        if added:
            lines.append(f"NEW ON PATH ({len(added)}): {', '.join(added[:6])}")
        if held:
            lines.append(f"HELD ON PATH ({len(held)}): {', '.join(held[:6])}")

        # Characterize the shift
        if dropped and added:
            lines.append("")
            lines.append(
                f"SHIFT SUMMARY: The critical path has moved away from "
                f"'{dropped[0]}'-led sequence toward a path now driven by '{added[0]}'. "
                f"Assess whether the logic change reflects genuine resequencing or revised relationships."
            )
        elif added and not dropped:
            lines.append("")
            lines.append(
                f"PATH EXTENDED: {len(added)} new activities joined the critical path — "
                f"these were previously off-path and may indicate float erosion or logic additions."
            )
        elif dropped and not added:
            lines.append("")
            lines.append(
                f"PATH SHORTENED: {len(dropped)} activities dropped off the critical path — "
                f"these may have completed or had their logic revised."
            )

    # Narrative hint for LLM
    if curr_names and prev_names and (dropped or added):
        prev_lead = prev_names[0] if prev_names else "prior sequence"
        curr_lead = curr_names[0] if curr_names else "current sequence"
        curr_tail = curr_names[-1] if len(curr_names) > 1 else ""
        hint = (
            f"The critical path has shifted from a path previously led by '{prev_lead}' "
            f"to a current path now led by '{curr_lead}'"
        )
        if curr_tail and curr_tail != curr_lead:
            hint += f", continuing through to '{curr_tail}'"
        hint += ". "
        hint += "Review whether this reflects a legitimate resequencing or a paper revision."
        lines.append("")
        lines.append(f"NARRATIVE HINT: {hint}")

    return "\n".join(lines)


def format_chain_for_context(chain_result: Dict, max_activities: int = 25) -> str:
    """
    Formats chain result into a compact LLM context block.
    Injected into the system prompt when schedule data is loaded.
    Includes finish date and float per step so the LLM can narrate timing precisely.
    """
    if "error" in chain_result:
        return f"[Critical Path: {chain_result['error']}]"

    mode = chain_result.get("mode", "")
    target = chain_result.get("target", {})
    target_name = target.get("name") or target.get("task_name") or "N/A"
    chain = chain_result.get("chain", [])
    chain_names = chain_result.get("chain_names", [])
    depth = chain_result.get("depth", 0)
    hint = chain_result.get("narrative_hint", "")
    warning = chain_result.get("warning", "")

    label = "FULL PROJECT CRITICAL PATH" if mode == "full_project" else f"CRITICAL PATH TO: {target_name}"

    lines = [
        f"=== {label} ===",
        f"Driving activities ({depth} steps, float-ranked — lowest float = most driving):",
    ]

    # Build a name→task lookup from the chain for per-step metadata
    chain_task_lookup = {}
    for t in chain:
        name = t.get("name") or t.get("task_name") or ""
        if name:
            chain_task_lookup[name] = t

    display_names = chain_names[:max_activities]
    for i, name in enumerate(display_names, 1):
        t = chain_task_lookup.get(name, {})
        finish = t.get("finish") or t.get("target_end_date") or ""
        float_days = _get_float_days(t)
        float_str = f" | Float: {float_days}d" if float_days is not None else ""
        finish_str = f" | Finish: {finish}" if finish else ""
        pct = t.get("percent_complete", None)
        pct_str = f" | {pct:.0f}%" if pct is not None else ""
        lines.append(f"  {i:>2}. {name}{finish_str}{float_str}{pct_str}")

    if len(chain_names) > max_activities:
        lines.append(f"  ... +{len(chain_names) - max_activities} more")

    if hint:
        lines.append("")
        lines.append(f"NARRATIVE BASE: {hint}")

    if warning:
        lines.append(f"[CP WARNING: {warning}]")

    return "\n".join(lines)
