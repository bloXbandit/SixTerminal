"""
critical_path.py - Critical path chain builder for MPP/XML and XER schedules.

Builds ordered predecessor chains from any target activity backwards through
the schedule network. Used to generate narrative critical path descriptions
for the LLM Copilot.

Two modes:
  - Full project CP: walks back from the contract completion / last milestone
  - Per-activity runoff: walks back from any named/matched activity

Output is a structured chain dict the LLM can narrate naturally.
"""

from typing import List, Dict, Optional, Tuple, Set
import logging

logger = logging.getLogger(__name__)

CONTRACT_KEYWORDS = [
    "certificate of occupancy", "co ", " co", "substantial completion",
    "turnover", "contract complete", "project complete", "final completion",
    "beneficial occupancy", "punch list complete", "final inspection",
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
            return t.get("finish") or t.get("early_end") or ""
        return max(incomplete, key=sort_key)
    return None


def _build_predecessor_map(relationships: List[Dict]) -> Dict[str, List[str]]:
    """
    Build {task_id: [predecessor_task_ids]} map from relationship list.
    Accepts both MPP-style and XER-style field names.
    """
    pred_map: Dict[str, List[str]] = {}
    for rel in relationships:
        # MPP style: task_id / predecessor_task_id
        # XER style: task_id / pred_task_id
        succ = str(rel.get("task_id") or rel.get("succ_task_id") or "").strip()
        pred = str(rel.get("predecessor_task_id") or rel.get("pred_task_id") or "").strip()
        if succ and pred and succ != "None" and pred != "None":
            pred_map.setdefault(succ, []).append(pred)
    return pred_map


def _walk_predecessors(
    start_id: str,
    pred_map: Dict[str, List[str]],
    task_lookup: Dict[str, Dict],
    max_depth: int = 60,
    critical_ids: Optional[Set[str]] = None,
) -> List[Dict]:
    """
    Walk backwards through predecessor chain from start_id.
    If critical_ids provided, prefer critical predecessors at each step.
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
        if not preds:
            break

        # Prefer critical predecessors; among those pick latest finish (most driving)
        if critical_ids:
            crit_preds = [p for p in preds if p in critical_ids and p not in visited]
            candidates = crit_preds if crit_preds else [p for p in preds if p not in visited]
        else:
            candidates = [p for p in preds if p not in visited]

        if not candidates:
            break

        def pred_sort_key(pid):
            t = task_lookup.get(pid, {})
            return t.get("finish") or t.get("early_end") or t.get("target_end_date") or ""

        current_id = max(candidates, key=pred_sort_key)

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
        critical_ids: optional set of task IDs already flagged critical

    Returns dict:
        {
          "mode": "full_project" | "activity_runoff",
          "target": {task dict},
          "chain": [ordered task dicts, most recent → earliest driver],
          "chain_names": [list of activity names in order],
          "narrative_hint": "string for LLM to use as narration base",
          "depth": int,
          "warning": optional string
        }
    """
    if not tasks:
        return {"error": "No tasks available"}

    # Build lookup and predecessor map
    task_lookup: Dict[str, Dict] = {}
    for t in tasks:
        tid = str(t.get("id") or t.get("task_id") or "").strip()
        if tid and tid != "None":
            task_lookup[tid] = t

    pred_map = _build_predecessor_map(relationships)

    # Find target
    target = _find_target_task(tasks, target_name)
    if not target:
        return {"error": f"Could not find target activity{': ' + target_name if target_name else ' (contract completion)'}"}

    target_id = str(target.get("id") or target.get("task_id") or "").strip()
    mode = "activity_runoff" if target_name else "full_project"

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

    return {
        "mode": mode,
        "target": target,
        "chain": chain,
        "chain_names": chain_names,
        "narrative_hint": narrative_hint,
        "depth": len(chain),
    }


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
    # Group consecutive names into logical phases where possible
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


def format_chain_for_context(chain_result: Dict, max_activities: int = 25) -> str:
    """
    Formats chain result into a compact LLM context block.
    Injected into the system prompt when schedule data is loaded.
    """
    if "error" in chain_result:
        return f"[Critical Path: {chain_result['error']}]"

    mode = chain_result.get("mode", "")
    target = chain_result.get("target", {})
    target_name = target.get("name") or target.get("task_name") or "N/A"
    chain_names = chain_result.get("chain_names", [])
    depth = chain_result.get("depth", 0)
    hint = chain_result.get("narrative_hint", "")
    warning = chain_result.get("warning", "")

    label = "FULL PROJECT CRITICAL PATH" if mode == "full_project" else f"CRITICAL PATH TO: {target_name}"

    lines = [
        f"=== {label} ===",
        f"Driving activities ({depth} steps):",
    ]

    display = chain_names[:max_activities]
    for i, name in enumerate(display, 1):
        lines.append(f"  {i:>2}. {name}")
    if len(chain_names) > max_activities:
        lines.append(f"  ... +{len(chain_names) - max_activities} more")

    if hint:
        lines.append("")
        lines.append(f"NARRATIVE BASE: {hint}")

    if warning:
        lines.append(f"[Note: {warning}]")

    return "\n".join(lines)
