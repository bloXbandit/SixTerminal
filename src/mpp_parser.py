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
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _get_mpxj():
    """Lazy import mpxj and return the module. Raises ImportError with helpful message if missing."""
    try:
        import mpxj
        return mpxj
    except ImportError:
        raise ImportError(
            "mpxj is not installed. Run: pip install mpxj\n"
            "Note: mpxj requires Java 11+ to be installed on the system."
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
        self.project_metadata: Dict[str, Any] = {}
        self._llm_context_cache: Optional[str] = None

        self._load()

    def _load(self):
        """Parse the file using mpxj's UniversalProjectReader."""
        mpxj = _get_mpxj()
        from mpxj import UniversalProjectReader

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
            logger.info(f"Parsed {len(self.tasks)} tasks from {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to parse file: {e}")
            raise

    def _extract_metadata(self):
        """Pull project-level properties."""
        p = self.project.project_properties
        self.project_metadata = {
            "project_name": str(p.name) if p.name else os.path.splitext(os.path.basename(self.file_path))[0],
            "author": str(p.author) if p.author else "",
            "company": str(p.company) if p.company else "",
            "start_date": self._fmt_date(p.start_date),
            "finish_date": self._fmt_date(p.finish_date),
            "status_date": self._fmt_date(p.status_date),
            "currency_symbol": str(p.currency_symbol) if p.currency_symbol else "$",
        }
        logger.info(f"Project: {self.project_metadata['project_name']}")

    def _extract_tasks(self):
        """Extract all tasks/milestones into a list of dicts."""
        self.tasks = []
        for task in self.project.tasks:
            if task is None or task.id is None:
                continue
            if str(task.name or "").strip() == "" and int(task.id) == 0:
                continue

            t = {
                "id": str(task.id),
                "name": str(task.name) if task.name else "",
                "wbs": str(task.wbs) if task.wbs else "",
                "outline_level": int(task.outline_level) if task.outline_level else 0,
                "milestone": bool(task.milestone),
                "summary": bool(task.summary),
                "percent_complete": float(task.percent_complete) if task.percent_complete else 0.0,
                "baseline_start": self._fmt_date(task.baseline_start),
                "baseline_finish": self._fmt_date(task.baseline_finish),
                "start": self._fmt_date(task.start),
                "finish": self._fmt_date(task.finish),
                "actual_start": self._fmt_date(task.actual_start),
                "actual_finish": self._fmt_date(task.actual_finish),
                "duration": str(task.duration) if task.duration else "",
                "baseline_duration": str(task.baseline_duration) if task.baseline_duration else "",
                "total_slack": str(task.total_slack) if task.total_slack else "",
                "free_slack": str(task.free_slack) if task.free_slack else "",
                "critical": bool(task.critical),
                "notes": str(task.notes).strip() if task.notes else "",
                "constraint_type": str(task.constraint_type) if task.constraint_type else "",
                "constraint_date": self._fmt_date(task.constraint_date),
                "priority": int(task.priority.value) if task.priority else 500,
            }

            self.tasks.append(t)

    def _extract_resources(self):
        """Extract resource assignments."""
        self.resources = []
        for res in self.project.resources:
            if res is None or res.id is None:
                continue
            self.resources.append({
                "id": str(res.id),
                "name": str(res.name) if res.name else "",
                "type": str(res.type) if res.type else "",
                "email": str(res.email_address) if res.email_address else "",
            })

    def _fmt_date(self, dt) -> str:
        """Format a Java/mpxj date object to string."""
        if dt is None:
            return ""
        try:
            return str(dt)[:10]
        except Exception:
            return ""

    def get_milestones(self) -> List[Dict[str, Any]]:
        """Return only milestone tasks."""
        return [t for t in self.tasks if t["milestone"]]

    def get_critical_path(self) -> List[Dict[str, Any]]:
        """Return only critical path tasks."""
        return [t for t in self.tasks if t["critical"]]

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

        if critical:
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
            "milestones": self.get_milestones(),
            "critical_path": self.get_critical_path(),
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
