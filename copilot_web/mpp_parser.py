"""
mpp_parser.py - Read and write MS Project (.mpp) and P6 XML (.xml) files using mpxj.

Supports:
- Reading .mpp (MS Project binary)
- Reading .xml (MS Project XML / P6 XML)
- Writing .xml (MS Project XML)
- Writing .mpp (MS Project binary via mpxj)
- Extracting structured context for the AI Copilot
"""

import os
import logging
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_jvm_lock = threading.Lock()


def _get_mpxj():
    """Start JVM and import mpxj per official docs: https://pypi.org/project/mpxj/
    Thread-safe: uses double-checked locking so only one thread ever calls startJVM().
    """
    try:
        import jpype
        import mpxj  # noqa: F401 - triggers mpxj jar loading
        if not jpype.isJVMStarted():
            with _jvm_lock:
                if not jpype.isJVMStarted():
                    jpype.startJVM()
        if not jpype.isThreadAttachedToJVM():
            jpype.attachThreadToJVM()
        return mpxj
    except ImportError as _e:
        raise ImportError(
            f"mpxj is not installed. Run: pip install mpxj\n"
            f"Note: mpxj requires Java 11+ to be installed on the system.\n"
            f"Underlying error: {_e}"
        )


class MPPParser:
    """
    Read and write MS Project (.mpp) and XML schedule files using mpxj.
    Extracts activities, milestones, WBS, and project metadata.
    Provides LLM-ready context for the AI Copilot.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.project = None
        self.tasks: List[Dict[str, Any]] = []
        self.resources: List[Dict[str, Any]] = []
        self.relationships: List[Dict[str, Any]] = []
        self.project_metadata: Dict[str, Any] = {}
        self._llm_context_cache: Optional[str] = None
        self._cp_chain: Optional[Dict] = None

        self._load()

    def _load(self):
        """Parse the file using mpxj's UniversalProjectReader."""
        _get_mpxj()
        from org.mpxj.reader import UniversalProjectReader

        logger.info(f"Parsing file: {self.file_path}")

        try:
            reader = UniversalProjectReader()
            try:
                self.project = reader.read(self.file_path)
            except Exception as e:
                if "password" in str(e).lower() or "encrypted" in str(e).lower():
                    raise ValueError(f"MPP file is password protected and cannot be read: {self.file_path}")
                raise
            self._extract_metadata()
            self._extract_tasks()
            self._extract_resources()
            self._extract_relationships()
            self._build_cp_chain()
            logger.info(f"Parsed {len(self.tasks)} tasks from {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to parse file: {e}")
            raise

    def _extract_metadata(self):
        """Pull project-level properties."""
        p = self.project.getProjectProperties()
        name = p.getName()
        author = p.getAuthor()
        company = p.getCompany()
        currency = p.getCurrencySymbol()
        self.project_metadata = {
            "project_name": str(name) if name else os.path.splitext(os.path.basename(self.file_path))[0],
            "author": str(author) if author else "",
            "company": str(company) if company else "",
            "start_date": self._fmt_date(p.getStartDate()),
            "finish_date": self._fmt_date(p.getFinishDate()),
            "status_date": self._fmt_date(p.getStatusDate()),
            "currency_symbol": str(currency) if currency else "$",
        }
        logger.info(f"Project: {self.project_metadata['project_name']}")

    def _extract_tasks(self):
        """Extract all tasks/milestones into a list of dicts."""
        self.tasks = []
        for task in self.project.getTasks():
            if task is None:
                continue
            task_id = task.getID()
            if task_id is None:
                continue
            task_name = task.getName()
            if str(task_name or "").strip() == "" and int(task_id) == 0:
                continue
            pct = task.getPercentageComplete()
            priority = task.getPriority()
            t = {
                "id": str(task_id),
                "name": str(task_name) if task_name else "",
                "wbs": str(task.getWBS()) if task.getWBS() else "",
                "outline_level": int(task.getOutlineLevel()) if task.getOutlineLevel() else 0,
                "milestone": bool(task.getMilestone()),
                "summary": bool(task.getSummary()),
                "percent_complete": float(str(pct)) if pct is not None else 0.0,
                "baseline_start": self._fmt_date(task.getBaselineStart()),
                "baseline_finish": self._fmt_date(task.getBaselineFinish()),
                "start": self._fmt_date(task.getStart()),
                "finish": self._fmt_date(task.getFinish()),
                "actual_start": self._fmt_date(task.getActualStart()),
                "actual_finish": self._fmt_date(task.getActualFinish()),
                "duration": str(task.getDuration()) if task.getDuration() else "",
                "baseline_duration": str(task.getBaselineDuration()) if task.getBaselineDuration() else "",
                "total_slack": str(task.getTotalSlack()) if task.getTotalSlack() else "",
                "free_slack": str(task.getFreeSlack()) if task.getFreeSlack() else "",
                "critical": bool(task.getCritical()),
                "notes": str(task.getNotes()).strip() if task.getNotes() else "",
                "constraint_type": str(task.getConstraintType()) if task.getConstraintType() else "",
                "constraint_date": self._fmt_date(task.getConstraintDate()),
                "priority": int(str(priority.getValue())) if priority else 500,
            }
            self.tasks.append(t)

    def _extract_resources(self):
        """Extract resource assignments."""
        self.resources = []
        for res in self.project.getResources():
            if res is None or res.getID() is None:
                continue
            self.resources.append({
                "id": str(res.getID()),
                "name": str(res.getName()) if res.getName() else "",
                "type": str(res.getType()) if res.getType() else "",
                "email": str(res.getEmailAddress()) if res.getEmailAddress() else "",
            })

    def _extract_relationships(self):
        """Extract task predecessor relationships using project.getRelations().
        
        Uses the RelationContainer API instead of task.getPredecessors() because
        getPredecessors() returns an empty list on many MPP files even when
        relationships exist. project.getRelations() reliably returns all links.
        """
        self.relationships = []
        try:
            relations = self.project.getRelations()
            if not relations:
                return
            # Build a task ID lookup for name resolution
            task_id_to_name = {}
            for task in self.project.getTasks():
                if task is not None and task.getID() is not None:
                    task_id_to_name[str(task.getID())] = str(task.getName() or "")
            for rel in relations:
                try:
                    pred_task = rel.getPredecessorTask()
                    succ_task = rel.getSuccessorTask()
                    if pred_task is None or succ_task is None:
                        continue
                    pred_id = pred_task.getID()
                    succ_id = succ_task.getID()
                    if pred_id is None or succ_id is None:
                        continue
                    lag = rel.getLag()
                    self.relationships.append({
                        "successor_id": str(succ_id),
                        "predecessor_id": str(pred_id),
                        "successor_name": str(succ_task.getName() or ""),
                        "predecessor_name": str(pred_task.getName() or ""),
                        "type": str(rel.getType()) if rel.getType() else "FS",
                        "lag": str(lag) if lag else "0",
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not extract relationships: {e}")

    def _build_cp_chain(self):
        """Build the critical path chain from contract completion backwards."""
        # Fix import path for Render environment
        import sys, os
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        try:
            from critical_path import build_critical_chain
            critical_ids = {str(t["id"]) for t in self.tasks if t.get("critical")}
            self._cp_chain = build_critical_chain(
                tasks=self.tasks,
                relationships=self.relationships,
                target_name=None,
                critical_ids=critical_ids,
            )
        except Exception as e:
            logger.warning(f"CP chain build failed: {e}")
            self._cp_chain = None

    def _fmt_date(self, dt) -> str:
        """Format a Java/mpxj date object to string."""
        if dt is None:
            return ""
        try:
            return str(dt)[:10]
        except Exception:
            return ""

    def _slack_days(self, slack_str: str) -> Optional[float]:
        """Parse mpxj duration string to days. Returns None if unparseable."""
        if not slack_str:
            return None
        try:
            s = str(slack_str).lower().strip()
            # mpxj formats: '5.0d', '40.0h', '5 days', '0.0d'
            import re
            m = re.match(r'([\d.]+)\s*([dh]?)', s)
            if m:
                val = float(m.group(1))
                unit = m.group(2)
                if unit == 'h':
                    return round(val / 8.0, 1)
                return round(val, 1)
        except Exception:
            pass
        return None

    def get_milestones(self) -> List[Dict[str, Any]]:
        """Return only milestone tasks."""
        return [t for t in self.tasks if t["milestone"]]

    def get_critical_path(self) -> List[Dict[str, Any]]:
        """Return only critical path tasks."""
        return [t for t in self.tasks if t["critical"]]

    def get_critical_chain(self, target_name: Optional[str] = None) -> Dict:
        """Build and return CP chain for any target activity (or full project CP)."""
        # Fix import path for Render environment
        import sys, os
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        try:
            from critical_path import build_critical_chain
            critical_ids = {str(t["id"]) for t in self.tasks if t.get("critical")}
            return build_critical_chain(
                tasks=self.tasks,
                relationships=self.relationships,
                target_name=target_name,
                critical_ids=critical_ids,
            )
        except Exception as e:
            return {"error": str(e)}

    def get_summary_tasks(self) -> List[Dict[str, Any]]:
        """Return only WBS summary tasks."""
        return [t for t in self.tasks if t["summary"]]

    def get_llm_context(self, force_refresh=False) -> str:
        """
        Build a rich, token-efficient string context for the AI Copilot.
        Includes project metadata, milestones, critical path, and schedule health.
        Cached after first call.
        """
        if self._llm_context_cache and not force_refresh:
            return self._llm_context_cache

        meta = self.project_metadata
        total = len(self.tasks)
        completed = len([t for t in self.tasks if t["percent_complete"] >= 100])
        in_progress = len([t for t in self.tasks if 0 < t["percent_complete"] < 100])
        not_started = len([t for t in self.tasks if t["percent_complete"] == 0 and not t["summary"]])
        milestones = self.get_milestones()
        critical = self.get_critical_path()

        lines = [
            f"=== PROJECT SCHEDULE DATA ===",
            f"Project: {meta['project_name']}",
            f"Start: {meta['start_date']}  |  Finish: {meta['finish_date']}  |  Status Date: {meta['status_date']}",
            f"",
            f"SCHEDULE SUMMARY:",
            f"  Total Activities: {total}",
            f"  Completed: {completed}",
            f"  In Progress: {in_progress}",
            f"  Not Started: {not_started}",
            f"  Critical Path Tasks: {len(critical)}",
            f"  Milestones: {len(milestones)}",
            f"",
        ]

        if milestones:
            lines.append("MILESTONES:")
            for m in milestones:
                status = "Complete" if m["percent_complete"] >= 100 else ("In Progress" if m["actual_start"] else "Not Started")
                baseline = m["baseline_finish"] or m["baseline_start"] or "—"
                forecast = m["finish"] or m["start"] or "—"
                lines.append(f"  - {m['name']}")
                lines.append(f"    Baseline: {baseline} | Forecast: {forecast} | Status: {status}")
            lines.append("")

        # Near-critical: total_slack > 0 but <= 10 working days, not summary, not complete
        near_critical = [
            t for t in self.tasks
            if not t["critical"]
            and not t["summary"]
            and t["percent_complete"] < 100
            and t["total_slack"] not in ("", None)
            and self._slack_days(t["total_slack"]) is not None
            and 0 < self._slack_days(t["total_slack"]) <= 10
        ]
        if near_critical:
            near_critical.sort(key=lambda t: self._slack_days(t["total_slack"]) or 99)
            lines.append(f"NEAR-CRITICAL ACTIVITIES (0 < float ≤ 10 days, {len(near_critical)} total):")
            for t in near_critical[:15]:
                days = self._slack_days(t["total_slack"])
                lines.append(f"  - {t['name']} | Float: {days} cal days | Finish: {t['finish']}")
            if len(near_critical) > 15:
                lines.append(f"  ... +{len(near_critical) - 15} more near-critical")
            lines.append("")

        if self._cp_chain and not self._cp_chain.get("error"):
            try:
                # Fix import path for Render environment
                import sys, os
                here = os.path.dirname(os.path.abspath(__file__))
                if here not in sys.path:
                    sys.path.insert(0, here)
                from critical_path import format_chain_for_context
                lines.append(format_chain_for_context(self._cp_chain))
                lines.append("")
            except Exception:
                pass
        elif critical:
            lines.append(f"CRITICAL PATH ({len(critical)} tasks):")
            for t in critical[:20]:
                if not t["summary"]:
                    lines.append(f"  - {t['name']} | Start: {t['start']} | Finish: {t['finish']} | {t['percent_complete']:.0f}%")
            if len(critical) > 20:
                lines.append(f"  ... and {len(critical) - 20} more critical tasks")
            lines.append("")

        delayed_milestones = []
        for m in milestones:
            if m["baseline_finish"] and m["finish"] and m["finish"] > m["baseline_finish"]:
                delayed_milestones.append(m)

        if delayed_milestones:
            lines.append(f"DELAYED MILESTONES ({len(delayed_milestones)}):")
            for m in delayed_milestones:
                lines.append(f"  - {m['name']} | Baseline: {m['baseline_finish']} | Forecast: {m['finish']}")
            lines.append("")

        # --- Constraint context block (conversation mode only — not for narrative) ---
        constrained = [
            t for t in self.tasks
            if t.get("constraint_type") and t["constraint_type"] not in ("", "AS_SOON_AS_POSSIBLE", "ASAP")
            and not t["summary"]
            and t["percent_complete"] < 100
        ]
        if constrained:
            # Threshold flag: >5% of incomplete activities have hard constraints
            incomplete_total = len([t for t in self.tasks if not t["summary"] and t["percent_complete"] < 100])
            hard_constrained = [
                t for t in constrained
                if t["constraint_type"] in ("MUST_FINISH_ON", "MUST_START_ON",
                                             "MANDATORY_FINISH", "MANDATORY_START")
            ]
            hard_pct = (len(hard_constrained) / incomplete_total * 100) if incomplete_total > 0 else 0
            lines.append("CONSTRAINT DETAILS (conversation mode only — not for narrative unless asked):")
            for t in constrained[:30]:
                cdate = t.get("constraint_date") or ""
                cdate_str = f" on {cdate}" if cdate else ""
                lines.append(f"  - {t['name']} | {t['constraint_type']}{cdate_str} | Finish: {t['finish']}")
            if len(constrained) > 30:
                lines.append(f"  ... +{len(constrained) - 30} more constrained activities")
            if hard_pct > 5:
                lines.append(
                    f"SCHEDULE QUALITY FLAG: {len(hard_constrained)} of {incomplete_total} incomplete activities "
                    f"({hard_pct:.1f}%) have hard constraints (Mandatory Finish/Start). "
                    f"Hard constraints override schedule logic and can mask float — this is a schedule quality risk."
                )
            lines.append("")

        self._llm_context_cache = "\n".join(lines)
        return self._llm_context_cache

    def write_xml(self, output_path: str):
        """Write the project to MS Project XML format."""
        mpxj = _get_mpxj()
        from mpxj.writer import MSPDIWriter

        writer = MSPDIWriter()
        writer.write(self.project, output_path)
        logger.info(f"Written to XML: {output_path}")

    def to_dict(self) -> Dict[str, Any]:
        """Return full project data as a serializable dict."""
        return {
            "metadata": self.project_metadata,
            "tasks": self.tasks,
            "resources": self.resources,
            "relationships": self.relationships,
            "milestones": self.get_milestones(),
            "critical_path": self.get_critical_path(),
            "cp_chain": self._cp_chain,
        }


def read_project(file_path: str) -> MPPParser:
    """Convenience function — read any supported schedule file."""
    return MPPParser(file_path)


def convert(input_path: str, output_path: str):
    """
    Convert between any supported formats.
    Supported outputs: .xml (MS Project XML), .xer (Primavera)
    Note: Writing .mpp is NOT supported by mpxj.
    e.g. convert('schedule.mpp', 'schedule.xml')
         convert('schedule.xer', 'schedule.xml')
    """
    parser = MPPParser(input_path)
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".xml":
        parser.write_xml(output_path)
    elif ext == ".mpp":
        raise ValueError(
            "Writing .mpp files is not supported by mpxj. "
            "Export to .xml instead: convert(input, 'output.xml')"
        )
    else:
        raise ValueError(f"Unsupported output format: {ext}")
    logger.info(f"Converted {input_path} → {output_path}")
    return parser


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python mpp_parser.py <file.mpp|file.xml> [output.xml|output.mpp]")
        sys.exit(1)

    input_file = sys.argv[1]
    p = MPPParser(input_file)
    print(p.get_llm_context())

    if len(sys.argv) == 3:
        convert(input_file, sys.argv[2])
        print(f"Converted to: {sys.argv[2]}")
