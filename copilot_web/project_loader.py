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
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Limits concurrent MPP/XER parses to 3 — prevents CPU starvation on single-core Render instances
_mpp_semaphore = threading.Semaphore(3)

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")

_project_cache: Dict[str, str] = {}
_project_meta: Dict[str, dict] = {}
_project_health: Dict[str, dict] = {}  # {slug: {status, compression_pct, max_slip_days, max_accel_days}}
_project_tasks: Dict[str, list] = {}          # {slug: [task_dicts]} — current schedule tasks for milestone lookup
_project_tasks_previous: Dict[str, list] = {}  # {slug: [task_dicts]} — previous update tasks
_project_tasks_baseline: Dict[str, list] = {}  # {slug: [task_dicts]} — baseline tasks


def _get_mpp_parser():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from mpp_parser import MPPParser
    return MPPParser


def _get_xer_parser():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from parser import P6Parser
    return P6Parser


SCHEDULE_EXTS = (".mpp", ".xml", ".xer")


def _load_metadata_only(slug: str, project_path: str):
    """Load only metadata at startup — fast, no schedule parsing."""
    meta_path = os.path.join(project_path, "meta.json")
    if not os.path.exists(meta_path):
        return
    try:
        with open(meta_path, "r") as f:
            meta = json.load(f)
        _project_meta[slug] = meta
        logger.info(f"[{slug}] Metadata loaded")
    except Exception as e:
        logger.warning(f"[{slug}] Failed to load metadata: {e}")


def _load_schedule_data(slug: str, project_path: str):
    """Parse schedule files on demand — slower, called when project is first queried."""
    logger.info(f"[{slug}] Parsing schedule data on demand...")
    try:
        context = _build_versioned_context(slug, project_path)
        _project_cache[slug] = context
        status = "with schedule data" if context else "no schedule data found"
        logger.info(f"[{slug}] Schedule parsing complete — {status}")
        return context
    except Exception as e:
        logger.error(f"[{slug}] Schedule parsing failed: {e}")
        _project_cache[slug] = ""
        return ""


def _load_single_project(slug: str, project_path: str):
    """Load one project — metadata only at startup. Kept for compatibility."""
    _load_metadata_only(slug, project_path)


def load_all_projects():
    """Scans projects/ folder, loads metadata only (fast).
    Schedule data is parsed on-demand when project is first queried.
    """
    import threading as _thr
    if not os.path.exists(PROJECTS_DIR):
        logger.warning(f"Projects directory not found: {PROJECTS_DIR}")
        return

    slugs = [
        s for s in sorted(os.listdir(PROJECTS_DIR))
        if os.path.isdir(os.path.join(PROJECTS_DIR, s))
        and os.path.exists(os.path.join(PROJECTS_DIR, s, "meta.json"))
    ]

    # Pre-warm JVM in the main thread before any parsing happens
    try:
        from mpp_parser import _get_mpxj
        _get_mpxj()
        logger.info("JVM pre-warmed — ready for on-demand MPP parsing.")
    except Exception as _jvm_e:
        logger.warning(f"JVM pre-warm failed (MPP parsing may be unavailable): {_jvm_e}")

    # Start all metadata threads simultaneously — fast, no heavy parsing
    threads = []
    for slug in slugs:
        project_path = os.path.join(PROJECTS_DIR, slug)
        t = _thr.Thread(target=_load_metadata_only, args=(slug, project_path), daemon=True)
        t.start()
        threads.append((slug, t))
        logger.info(f"[{slug}] Metadata load started.")

    # Wait for all metadata — should complete quickly
    for slug, t in threads:
        t.join(timeout=30)  # 30s is plenty for metadata only
        if t.is_alive():
            logger.warning(f"[{slug}] Metadata load timed out after 30s")

    logger.info(f"Project loader: {len(_project_meta)} projects metadata loaded. Schedule data loads on-demand.")


def _find_versioned_files(project_path: str) -> dict:
    """
    Scans a project folder and returns:
      baseline: filepath or None
      updates:  list of (label, filepath) sorted ascending by label
      verify_pdf: filepath or None
      variance_pdfs: dict of {update_num: filepath} for variance_N.pdf files
    """
    import re as _re
    baseline = None
    updates = []
    verify_pdf = None
    variance_pdfs = {}  # {int: filepath}

    verify_pdfs = {}  # {int: filepath} for versioned verify_N.pdf
    verify_bl_pdf = None  # baseline All Activities PDF (prior for Update 1 projects)

    for fname in os.listdir(project_path):
        lower = fname.lower()
        fpath = os.path.join(project_path, fname)

        if lower == "verify.pdf":
            verify_pdf = fpath
            continue

        # verify_BL.pdf — baseline All Activities, used as prior for Update 1 projects
        if lower == "verify_bl.pdf":
            verify_bl_pdf = fpath
            continue

        # verify_N.pdf — versioned activity list per update
        vfm = _re.match(r'^verify[_\-](\d+)\.pdf$', lower)
        if vfm:
            verify_pdfs[int(vfm.group(1))] = fpath
            continue

        # variance_N.pdf — e.g. variance_1.pdf, variance_2.pdf
        vm = _re.match(r'^variance[_\-](\d+)\.pdf$', lower)
        if vm:
            variance_pdfs[int(vm.group(1))] = fpath
            continue

        name_no_ext = os.path.splitext(lower)[0]
        ext = os.path.splitext(lower)[1]

        if ext not in SCHEDULE_EXTS:
            continue

        if name_no_ext == "baseline":
            baseline = fpath
        elif name_no_ext.startswith("update_"):
            updates.append((name_no_ext, fpath))

    updates.sort(key=lambda x: int(x[0].split("_", 1)[1]) if x[0].split("_", 1)[1].isdigit() else 0)
    return {"baseline": baseline, "updates": updates, "verify_pdf": verify_pdf, "variance_pdfs": variance_pdfs, "verify_pdfs": verify_pdfs, "verify_bl_pdf": verify_bl_pdf}


def _parse_schedule(filepath: str) -> Optional[dict]:
    """
    Parse any schedule file (mpp/xml/xer) and return a normalized dict:
    { raw_context: str, source: str, tasks: List[Dict] }
    tasks is used by the variance engine for delta computation.
    """
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext in (".mpp", ".xml"):
            MPPParser = _get_mpp_parser()
            p = MPPParser(filepath)
            raw = p.get_llm_context()
            return {
                "raw_context": raw,
                "source": os.path.basename(filepath),
                "tasks": p.tasks,
            }

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
                f"  Critical Activities: {ctx.get('critical_stats', {}).get('critical_count', 0)}",
                "",
                f"WBS PHASES: {', '.join(ctx.get('wbs_phases', []))}",
                "",
                f"DCMA METRICS: {json.dumps(ctx.get('dcma_metrics', {}), default=lambda x: int(x) if hasattr(x, 'item') else str(x))}",
            ]
            cp_ctx = ctx.get("cp_chain_context", "")
            if cp_ctx:
                lines += ["", cp_ctx]
            nc_ctx = ctx.get("near_critical_context", "")
            if nc_ctx:
                lines += ["", nc_ctx]
            # Normalize XER rows into task dicts for variance engine
            xer_tasks = []
            if p.df_activities is not None and not p.df_activities.empty:
                for _, row in p.df_activities.iterrows():
                    xer_tasks.append(p._normalize_task_row(row))
            return {
                "raw_context": "\n".join(lines),
                "source": os.path.basename(filepath),
                "tasks": xer_tasks,
            }

    except Exception as e:
        logger.error(f"Parse failed for {filepath}: {e}")
        return None

    return None


def _ocr_pdf_lines(pdf_path: str, max_pages: int = 30) -> list:
    """
    Extract text lines from a PDF using OCR (pytesseract + pdf2image).
    Used as fallback when pdfplumber returns no text (image-based PDFs).
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
        lines = []
        images = convert_from_path(pdf_path, first_page=1, last_page=max_pages, dpi=200)
        for img in images:
            text = pytesseract.image_to_string(img)
            for line in text.splitlines():
                line = line.strip()
                if len(line) > 5:
                    lines.append(line)
        return lines
    except Exception as e:
        logger.warning(f"OCR fallback failed for {os.path.basename(pdf_path)}: {e}")
        return []


def _is_image_based_pdf(pdf_path: str) -> bool:
    """Check first 3 pages — returns True only if none have extractable text."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return True
            for page in pdf.pages[:3]:
                text = page.extract_text()
                if text and len(text.strip()) >= 50:
                    return False
            return True
    except Exception:
        return True


def _extract_text_or_ocr(pdf_path: str, max_pages: int = 30) -> list:
    """
    Try pdfplumber text extraction first. If no text found (image-based PDF),
    fall back to OCR via pytesseract.
    Fast pre-check avoids hanging on image PDFs during full extraction.
    """
    # Fast pre-check on page 1 only — avoids hanging on image-only PDFs
    if _is_image_based_pdf(pdf_path):
        logger.info(f"  Image-based PDF detected, using OCR: {os.path.basename(pdf_path)}")
        return _ocr_pdf_lines(pdf_path, max_pages)
    try:
        import pdfplumber
        lines = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:max_pages]:
                text = page.extract_text()
                if text:
                    for line in text.splitlines():
                        line = line.strip()
                        if len(line) > 5:
                            lines.append(line)
        if lines:
            return lines
    except Exception:
        pass
    logger.info(f"  No text layer found in full read, trying OCR: {os.path.basename(pdf_path)}")
    return _ocr_pdf_lines(pdf_path, max_pages)


def _extract_pdf_milestones(pdf_path: str, max_pages: int = 30) -> list:
    """
    Extract meaningful lines from verify.pdf for schedule crosscheck.
    Text-layer only with 30s timeout — image-based PDFs skipped instantly.
    """
    import threading as _thr
    if _is_image_based_pdf(pdf_path):
        logger.info(f"  Verify PDF is image-based, skipping: {os.path.basename(pdf_path)}")
        return []
    result = []
    def _read():
        try:
            import pdfplumber
            logger.info(f"  PDF open: {os.path.basename(pdf_path)}")
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:max_pages]:
                    text = page.extract_text()
                    if text:
                        for line in text.splitlines():
                            line = line.strip()
                            if len(line) > 5:
                                result.append(line)
        except Exception as e:
            logger.warning(f"PDF crosscheck failed: {e}")
    t = _thr.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=20)
    if t.is_alive():
        logger.warning(f"PDF read timed out (20s), skipping: {os.path.basename(pdf_path)}")
        return []
    return result


def _extract_variance_pdf(pdf_path: str) -> list:
    """
    Extract text lines from a variance_N.pdf report.
    Text-layer only with 30s timeout — image-based PDFs skipped instantly.
    """
    import threading as _thr
    if _is_image_based_pdf(pdf_path):
        logger.info(f"  Variance PDF is image-based, skipping: {os.path.basename(pdf_path)}")
        return []
    result = []
    def _read():
        try:
            import pdfplumber
            logger.info(f"  Variance PDF open: {os.path.basename(pdf_path)}")
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:30]:
                    text = page.extract_text()
                    if text:
                        for line in text.splitlines():
                            line = line.strip()
                            if len(line) > 5:
                                result.append(line)
        except Exception as e:
            logger.warning(f"Variance PDF extraction failed: {e}")
    t = _thr.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=20)
    if t.is_alive():
        logger.warning(f"Variance PDF timed out (20s), skipping: {os.path.basename(pdf_path)}")
        return []
    return result


def _extract_compression_pdf(pdf_path: str) -> Optional[dict]:
    """
    Parse a Schedule Compression PDF (from schedule validator).
    Extracts: compression %, schedule A/B data dates + finish dates,
    and the monthly activity days comparison table.

    Expected layout (from screenshot):
      - "Remaining Work Compression  -5 %"
      - Table: A = Earlier schedule (data date, finish date)
               B = Later schedule (data date, finish date)
      - Monthly table: Month | Activity Days (A) | Activity Days (B)
    """
    import threading as _thr
    import re
    result_holder = [None]
    exc_holder = []

    def _read():
        try:
            result = {
                "compression_pct": None,
                "earlier_data_date": None,
                "later_data_date": None,
                "earlier_finish": None,
                "later_finish": None,
                "monthly": [],
                "raw_lines": [],
            }
            logger.info(f"  Compression PDF open: {os.path.basename(pdf_path)}")
            lines = _extract_text_or_ocr(pdf_path, max_pages=5)
            result["raw_lines"] = lines

            for line in lines:
                m = re.search(r'Remaining Work Compression\s+([-+]?[\dOoIlSsBbZz]+)\s*%', line, re.IGNORECASE)
                if m:
                    raw_val = m.group(1)
                    # Clean common OCR misreads: O->0, o->0, I/l->1, S/s->5, B/b->8, Z/z->2
                    cleaned = raw_val.translate(str.maketrans('OoIlSsBbZz', '0011558822'))
                    try:
                        pct = int(cleaned)
                        if -100 <= pct <= 100:
                            result["compression_pct"] = pct
                        else:
                            logger.warning(f"Compression % out of range ({pct}), ignoring — raw: '{raw_val}'")
                    except ValueError:
                        logger.warning(f"Compression % could not parse after OCR cleanup — raw: '{raw_val}', cleaned: '{cleaned}'")
                m = re.findall(r'Data Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})', line)
                if m:
                    if result["earlier_data_date"] is None:
                        result["earlier_data_date"] = m[0]
                    elif result["later_data_date"] is None and m[0] != result["earlier_data_date"]:
                        result["later_data_date"] = m[0]
                m = re.findall(r'Finish Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})', line)
                if m:
                    if result["earlier_finish"] is None:
                        result["earlier_finish"] = m[0]
                    elif result["later_finish"] is None and m[0] != result["earlier_finish"]:
                        result["later_finish"] = m[0]
                m = re.match(r'^([A-Za-z]{3}\s+\d{2})\s+(\d+)\s+(\d+)$', line)
                if m:
                    result["monthly"].append({
                        "month": m.group(1),
                        "earlier_days": int(m.group(2)),
                        "later_days": int(m.group(3)),
                    })
            result_holder[0] = result if result["compression_pct"] is not None else None
        except Exception as e:
            exc_holder.append(e)

    t = _thr.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=120)
    if t.is_alive():
        logger.warning(f"Compression PDF timed out (120s), skipping: {os.path.basename(pdf_path)}")
        return None
    if exc_holder:
        logger.warning(f"Compression PDF extraction failed ({pdf_path}): {exc_holder[0]}")
        return None
    return result_holder[0]


def _format_compression_pdf_context(data: dict, label: str = "") -> str:
    """Format extracted compression PDF data as an LLM context block."""
    if not data:
        return ""
    lines = [f"=== COMPRESSION REPORT — VERIFIED (Schedule Validator){' — ' + label if label else ''} ==="]
    pct = data.get("compression_pct")
    if pct is not None:
        direction = "compressed" if pct < 0 else "expanded" if pct > 0 else "unchanged"
        lines.append(f"Remaining Work Compression: {pct:+d}% ({direction})")
    if data.get("earlier_data_date") and data.get("later_data_date"):
        lines.append(f"Compared: {data['earlier_data_date']} (earlier) → {data['later_data_date']} (later)")
    if data.get("earlier_finish") and data.get("later_finish"):
        finish_note = " [finish unchanged]" if data["earlier_finish"] == data["later_finish"] else " [finish changed]"
        lines.append(f"Finish Date: {data['earlier_finish']} → {data['later_finish']}{finish_note}")
    monthly = data.get("monthly", [])
    if monthly:
        lines.append("Monthly Activity Days (Earlier vs Later):")
        for row in monthly:
            delta = row["later_days"] - row["earlier_days"]
            sign = "+" if delta >= 0 else ""
            lines.append(f"  {row['month']:8s}  Earlier: {row['earlier_days']:>4}  Later: {row['later_days']:>4}  Δ {sign}{delta}")
    lines.append("NOTE: Use this as ground truth for compression statements. Prefer these values over computed estimates.")
    return "\n".join(lines)


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
    variance_pdfs = files.get("variance_pdfs", {})
    verify_pdfs = files.get("verify_pdfs", {})

    if not baseline_path and not updates:
        return ""

    parts = []

    # --- Determine current and previous ---
    if updates:
        current_label, current_path = updates[-1]
        if len(updates) >= 2:
            _, previous_path = updates[-2]
        elif baseline_path:
            previous_path = baseline_path
        else:
            previous_path = None
    else:
        current_label, current_path = "baseline", baseline_path
        previous_path = None

    # --- Format label ---
    total_updates = len(updates)
    parts.append(f"SCHEDULE VERSIONS: {'baseline' if baseline_path else 'no baseline'} + {total_updates} update(s)")
    parts.append(f"CURRENT SUBMISSION: {current_label} ({os.path.basename(current_path)})")

    # --- Locate compression PDF for current update (versioned: compression_updateN.pdf) ---
    _compression_pdf_path = None
    try:
        import re as _re
        # Scan folder for all compression_updateN.pdf files
        _comp_pdfs = {}
        for _fn in os.listdir(project_path):
            _cm = _re.match(r'^compression[_\-]update[_\-]?(\d+)\.pdf$', _fn.lower())
            if _cm:
                _comp_pdfs[int(_cm.group(1))] = os.path.join(project_path, _fn)
        if _comp_pdfs:
            m = _re.search(r'update[_\s]*(\d+)', current_label, _re.IGNORECASE)
            if m:
                cur_num = int(m.group(1))
                if cur_num in _comp_pdfs:
                    _compression_pdf_path = _comp_pdfs[cur_num]
                else:
                    _cands = [n for n in _comp_pdfs if n <= cur_num]
                    if _cands:
                        _compression_pdf_path = _comp_pdfs[max(_cands)]
    except Exception:
        pass

    # --- Parse current (with 90s timeout to avoid JVM hangs) ---
    logger.info(f"[{slug}] Parsing current: {os.path.basename(current_path)}")
    import threading as _thr2
    _parse_result = [None]
    def _do_parse_current():
        with _mpp_semaphore:
            _parse_result[0] = _parse_schedule(current_path)
    _pt = _thr2.Thread(target=_do_parse_current, daemon=True)
    _pt.start()
    _pt.join(timeout=60)
    if _pt.is_alive():
        logger.warning(f"[{slug}] Current MPP parse timed out after 60s — skipping")
        parts.append("[Current schedule parse timed out]")
        return "\n".join(parts)
    current_data = _parse_result[0]
    logger.info(f"[{slug}] Current parse done: {'ok' if current_data else 'failed'}")
    if not current_data:
        parts.append("[Current schedule could not be parsed]")
        return "\n".join(parts)

    # --- Store tasks for milestone date cross-referencing ---
    _project_tasks[slug] = current_data.get("tasks", [])
    # Clear previous/baseline caches so stale data doesn't bleed across reloads
    _project_tasks_previous.pop(slug, None)
    _project_tasks_baseline.pop(slug, None)

    # --- Compression % from current tasks ---
    _compression_pct = None
    try:
        tasks = current_data.get("tasks", [])
        non_summary = [t for t in tasks if not t.get("summary", False)]
        if non_summary:
            pcts = [float(t.get("percent_complete") or 0) for t in non_summary]
            _compression_pct = round(sum(pcts) / len(pcts), 1)
    except Exception:
        pass

    parts.append("")
    parts.append("=== CURRENT SCHEDULE ===")
    parts.append(current_data["raw_context"])

    # --- Parse previous for delta context + variance (with 90s timeout) ---
    previous_data = None
    if previous_path:
        logger.info(f"[{slug}] Parsing previous: {os.path.basename(previous_path)}")
        _prev_result = [None]
        def _do_parse_previous():
            with _mpp_semaphore:
                _prev_result[0] = _parse_schedule(previous_path)
        _pp = _thr2.Thread(target=_do_parse_previous, daemon=True)
        _pp.start()
        _pp.join(timeout=45)
        if _pp.is_alive():
            logger.warning(f"[{slug}] Previous MPP parse timed out after 45s — skipping variance")
        else:
            previous_data = _prev_result[0]
        logger.info(f"[{slug}] Previous parse done: {'ok' if previous_data else 'failed/timeout'}")
        if previous_data:
            _project_tasks_previous[slug] = previous_data.get("tasks", [])
            parts.append("")
            parts.append(f"=== PREVIOUS SCHEDULE ({os.path.basename(previous_path)}) ===")
            parts.append(previous_data["raw_context"])

    # --- Compute variance between current and previous ---
    if previous_data and current_data.get("tasks") and previous_data.get("tasks"):
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            from variance_engine import compute_variance, format_variance_for_context, compute_compression
            variance = compute_variance(
                current_tasks=current_data["tasks"],
                previous_tasks=previous_data["tasks"],
                label_current=current_label.replace("_", " ").title(),
                label_previous=os.path.splitext(os.path.basename(previous_path))[0].replace("_", " ").title(),
            )
            variance_ctx = format_variance_for_context(variance)
            if variance_ctx:
                parts.append("")
                parts.append(variance_ctx)

            # --- Compression analysis (current vs previous) ---
            try:
                compression = compute_compression(
                    current_tasks=current_data["tasks"],
                    previous_tasks=previous_data["tasks"],
                )
                if compression.get("compression_signal") != "UNKNOWN":
                    sig = compression["compression_signal"]
                    pct = compression.get("compression_pct", 0)
                    span_delta = compression.get("span_delta_days", 0)
                    density_delta = compression.get("density_delta_pct", 0)
                    hint = compression.get("narrative_hint", "")
                    parts.append("")
                    parts.append(
                        f"=== SCHEDULE COMPRESSION ANALYSIS (Current vs Previous) ===\n"
                        f"Signal: {sig} | Remaining span change: {span_delta:+d} calendar days ({pct:+.1f}%) | "
                        f"Activity density change: {density_delta:+.1f}%\n"
                        f"Incomplete activities: {compression.get('current_incomplete_count','N/A')} now vs "
                        f"{compression.get('previous_incomplete_count','N/A')} prior\n"
                        f"NARRATIVE HINT: {hint}"
                    )
            except Exception as _ce:
                logger.warning(f"[{slug}] Compression computation failed: {_ce}")

            # --- User-uploaded compression PDF cache (manual upload via chat) ---
            try:
                from compression_cache import get_compression_for_update, get_all_compression_for_project
                # Try to get cached compression for current update number
                _update_num = int(current_label.replace("update_", "")) if current_label.startswith("update_") else None
                if _update_num:
                    cached_comp = get_compression_for_update(slug, _update_num)
                    if cached_comp:
                        parts.append("")
                        parts.append(f"=== USER-UPLOADED COMPRESSION REPORT (Update {_update_num}) ===")
                        parts.append(f"Compression %: {cached_comp.get('compression_pct', 'N/A')}%")
                        parts.append(f"Earlier finish: {cached_comp.get('earlier_finish', 'N/A')} | Later finish: {cached_comp.get('later_finish', 'N/A')}")
                        parts.append(f"Earlier data date: {cached_comp.get('earlier_data_date', 'N/A')} | Later data date: {cached_comp.get('later_data_date', 'N/A')}")
                        if cached_comp.get('monthly'):
                            parts.append("Monthly activity days: " + str(cached_comp['monthly']))
                        if cached_comp.get('raw_lines'):
                            parts.append("Extracted text lines:")
                            for line in cached_comp['raw_lines'][:20]:
                                parts.append(f"  {line}")
                    
                    # Also show historical compression data
                    all_comp = get_all_compression_for_project(slug)
                    if all_comp and len(all_comp) > 1:
                        parts.append("")
                        parts.append("=== COMPRESSION HISTORY (user-uploaded reports) ===")
                        for update_num in sorted(all_comp.keys()):
                            comp = all_comp[update_num]
                            parts.append(f"  Update {update_num}: {comp.get('compression_pct', 'N/A')}%")
            except Exception as _ccache:
                logger.debug(f"[{slug}] Compression cache lookup failed: {_ccache}")

            # --- Critical path shift (current vs previous) ---
            try:
                from critical_path import build_critical_chain, compare_critical_chains
                curr_rels = current_data.get("relationships", [])
                prev_rels = previous_data.get("relationships", [])
                curr_chain = build_critical_chain(current_data["tasks"], curr_rels)
                prev_chain = build_critical_chain(previous_data["tasks"], prev_rels)
                cp_shift_ctx = compare_critical_chains(curr_chain, prev_chain)
                if cp_shift_ctx:
                    parts.append("")
                    parts.append(cp_shift_ctx)
            except Exception as _cpe:
                logger.warning(f"[{slug}] CP shift computation failed: {_cpe}")

        except Exception as _ve:
            logger.warning(f"[{slug}] Variance computation failed: {_ve}")

    # --- Parse baseline once for both context display and drift variance (60s timeout) ---
    if baseline_path and baseline_path != current_path:
        _bl_result = [None]
        def _do_parse_baseline():
            with _mpp_semaphore:
                _bl_result[0] = _parse_schedule(baseline_path)
        _pb = _thr2.Thread(target=_do_parse_baseline, daemon=True)
        _pb.start()
        _pb.join(timeout=30)
        if _pb.is_alive():
            logger.warning(f"[{slug}] Baseline MPP parse timed out after 30s — skipping")
        baseline_data = _bl_result[0]
        if baseline_data:
            _project_tasks_baseline[slug] = baseline_data.get("tasks", [])
            parts.append("")
            parts.append(f"=== BASELINE SCHEDULE ({os.path.basename(baseline_path)}) ===")
            parts.append(baseline_data["raw_context"])

            # Compute drift variance using the already-parsed baseline tasks
            if current_data.get("tasks") and baseline_data.get("tasks"):
                try:
                    from variance_engine import compute_variance, format_variance_for_context
                    drift = compute_variance(
                        current_tasks=current_data["tasks"],
                        previous_tasks=baseline_data["tasks"],
                        label_current=current_label.replace("_", " ").title(),
                        label_previous="Baseline",
                    )
                    drift_ctx = format_variance_for_context(drift)
                    if drift_ctx:
                        parts.append("")
                        parts.append("=== BASELINE DRIFT ===")
                        parts.append(drift_ctx)
                    # --- Populate project health from baseline drift ---
                    s = drift.get("summary", {})
                    _project_health[slug] = {
                        "status": _health_tag(
                            s.get("max_slip_days", 0),
                            s.get("max_accel_days", 0),
                            s.get("total_slipped", 0),
                            s.get("total_accelerated", 0),
                        ),
                        "compression_pct": _compression_pct,
                        "max_slip_days": s.get("max_slip_days", 0),
                        "max_accel_days": s.get("max_accel_days", 0),
                        "total_slipped": s.get("total_slipped", 0),
                        "total_accelerated": s.get("total_accelerated", 0),
                    }
                except Exception as _de:
                    logger.warning(f"[{slug}] Baseline drift computation failed: {_de}")

    # --- Schedule risk diagnostics ---
    try:
        from risk_engine import run_risk_diagnostics, format_risk_for_context
        _data_date = None
        try:
            from tracker_loader import get_tracker_context
            _tc = get_tracker_context(slug)
            if _tc:
                import re as _re2
                _ddm = _re2.search(r'Data Date[:\s]+(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})', _tc)
                if _ddm:
                    from datetime import datetime as _dt
                    for _fmt in ("%Y-%m-%d", "%m/%d/%Y"):
                        try:
                            _data_date = _dt.strptime(_ddm.group(1), _fmt).date()
                            break
                        except Exception:
                            pass
        except Exception:
            pass
        risk = run_risk_diagnostics(
            tasks=current_data.get("tasks", []),
            relationships=current_data.get("relationships", []),
            data_date=_data_date,
        )
        risk_ctx = format_risk_for_context(risk)
        if risk_ctx:
            parts.append("")
            parts.append(risk_ctx)
    except Exception as _re:
        logger.warning(f"[{slug}] Risk diagnostics failed: {_re}")

    # --- Variance PDF — trump-card reference for current update variance ---
    if variance_pdfs:
        # Find the variance PDF matching the current update number
        import re as _re2
        current_update_num = None
        m2 = _re2.search(r'update[_\s]*(\d+)', current_label, _re2.IGNORECASE)
        if m2:
            current_update_num = int(m2.group(1))
        # Use exact match first, then fall back to highest available <= current
        variance_pdf_path = None
        if current_update_num is not None:
            if current_update_num in variance_pdfs:
                variance_pdf_path = variance_pdfs[current_update_num]
            else:
                candidates = [n for n in variance_pdfs if n <= current_update_num]
                if candidates:
                    variance_pdf_path = variance_pdfs[max(candidates)]
        if variance_pdf_path:
            try:
                var_lines = _extract_variance_pdf(variance_pdf_path)
                if var_lines:
                    vnum = os.path.splitext(os.path.basename(variance_pdf_path))[0]
                    parts.append("")
                    parts.append(
                        f"=== VARIANCE REPORT PDF ({vnum}) — VERIFIED HUMAN OUTPUT ===\n"
                        f"Use this as the authoritative reference for variance between the two schedule versions it covers.\n"
                        f"Cross-check your computed variance analysis against this. Where they differ, trust this PDF.\n"
                        f"Use it to confirm trends, identify patterns not visible in activity-level deltas, and refine your narrative."
                    )
                    parts.append("\n".join(var_lines[:300]))
            except Exception as _vpdf:
                logger.warning(f"[{slug}] Variance PDF inject failed: {_vpdf}")

    # --- Versioned verify PDF — activity list for current update, highest confidence date source ---
    import re as _re3
    current_update_num_v = None
    m3 = _re3.search(r'update[_\s]*(\d+)', current_label, _re3.IGNORECASE)
    if m3:
        current_update_num_v = int(m3.group(1))

    active_verify_pdf = None
    if verify_pdfs and current_update_num_v is not None:
        if current_update_num_v in verify_pdfs:
            active_verify_pdf = verify_pdfs[current_update_num_v]
        else:
            vcandidates = [n for n in verify_pdfs if n <= current_update_num_v]
            if vcandidates:
                active_verify_pdf = verify_pdfs[max(vcandidates)]
    elif verify_pdf:
        active_verify_pdf = verify_pdf  # fall back to unversioned verify.pdf

    if active_verify_pdf:
        pdf_lines = _extract_pdf_milestones(active_verify_pdf)
        if pdf_lines:
            vlabel = os.path.splitext(os.path.basename(active_verify_pdf))[0]
            parts.append("")
            parts.append(
                f"=== ACTIVITY VERIFICATION REFERENCE ({vlabel}) — use to verify current update activity dates/names ===\n"
                f"This is the authoritative activity list for the current update. Use it to:\n"
                f"  1. Confirm or correct parsed activity dates — where this PDF and the parsed schedule disagree, prefer this PDF.\n"
                f"  2. Increase confidence in your understanding of the current schedule state.\n"
                f"  3. Identify activities that may have been missed or misparsed.\n"
                f"Do not expose this raw data to the user. Use it internally for accuracy."
            )
            parts.append("\n".join(pdf_lines[:300]))

    # --- Prior verify PDF — baseline All Activities for Update 1 projects, or verify_{N-1} for others ---
    prior_verify_pdf = None
    verify_bl_pdf = files.get("verify_bl_pdf")
    if verify_bl_pdf and current_update_num_v == 1:
        # Update 1 — baseline is the prior
        prior_verify_pdf = verify_bl_pdf
        prior_verify_label = "BASELINE (verify_BL)"
        prior_verify_role = "This is the All Activities export from the Baseline schedule — use it as the prior-state reference when computing variance against Update 1."
    elif verify_pdfs and current_update_num_v is not None and current_update_num_v >= 2:
        prior_num = current_update_num_v - 1
        if prior_num in verify_pdfs:
            prior_verify_pdf = verify_pdfs[prior_num]
            prior_verify_label = f"PRIOR UPDATE verify_{prior_num}"
            prior_verify_role = f"This is the All Activities export from Update {prior_num} — use it as the authoritative prior-state reference for activity dates when computing variance against the current update."

    if prior_verify_pdf:
        try:
            prior_lines = _extract_pdf_milestones(prior_verify_pdf)
            if prior_lines:
                parts.append("")
                parts.append(
                    f"=== PRIOR ACTIVITY REFERENCE ({prior_verify_label}) — verified prior schedule state ===\n"
                    f"{prior_verify_role}\n"
                    f"Where parsed prior schedule dates conflict with dates in this PDF, prefer this PDF.\n"
                    f"Do not expose this raw data to the user. Use it internally to anchor variance math and narrative."
                )
                parts.append("\n".join(prior_lines[:300]))
        except Exception as _pv:
            logger.warning(f"[{slug}] Prior verify PDF inject failed: {_pv}")

    return "\n".join(parts)


def _health_tag(max_slip: int, max_accel: int, total_slipped: int, total_accelerated: int) -> str:
    """Derive a simple health label from variance summary numbers."""
    net = total_slipped - total_accelerated
    if max_accel >= 14 and net <= 0:
        return "AHEAD"
    if max_slip >= 30 or (max_slip >= 14 and net >= 5):
        return "MAJOR DELAY"
    if max_slip >= 7 or net >= 3:
        return "SLIGHT DELAY"
    return "ON TIME"


def _build_task_lookup(tasks: list) -> tuple:
    """Return (name_lookup, id_lookup) dicts from a task list."""
    by_name: dict = {}
    by_id: dict = {}
    for t in tasks:
        name = (t.get("name") or t.get("task_name") or "").strip().lower()
        tid = str(t.get("id") or t.get("task_id") or t.get("activity_id") or "").strip()
        if name:
            by_name[name] = t
        if tid:
            by_id[tid] = t
    return by_name, by_id


def _resolve_task(act_name: str, act_id: str, by_name: dict, by_id: dict):
    """Find a task by activity name or ID."""
    return by_name.get(act_name.lower()) or by_id.get(act_id) or None


def _extract_finish(task) -> str:
    """Extract finish date string (date portion only) from a task dict."""
    if task is None:
        return ""
    v = (task.get("finish") or task.get("target_end_date") or
         task.get("early_end_date") or "")
    return str(v)[:10] if v else ""


def _load_milestone_map(slug: str) -> str:
    """
    Load milestone_map.json and cross-reference against parsed tasks to inject
    actual forecast dates, baseline dates, and % complete into the milestone context.
    Uses 2-source confidence verification: current + previous OR current + baseline.
    Emits a VERIFIED tag when at least 2 sources agree on a date.
    """
    mm_path = os.path.join(PROJECTS_DIR, slug, "milestone_map.json")
    if not os.path.exists(mm_path):
        return ""
    try:
        with open(mm_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        milestones = data.get("milestones", [])
        if not milestones:
            return ""

        # Build lookups for all three schedule versions
        curr_by_name, curr_by_id = _build_task_lookup(_project_tasks.get(slug, []))
        prev_by_name, prev_by_id = _build_task_lookup(_project_tasks_previous.get(slug, []))
        base_by_name, base_by_id = _build_task_lookup(_project_tasks_baseline.get(slug, []))

        lines = [
            "STANDARDIZED MILESTONES (dates cross-referenced across schedule versions — VERIFIED = 2+ sources agree):"
        ]
        for m in sorted(milestones, key=lambda x: x.get("sort", 99)):
            std = m["standardized_name"]
            act_name = (m.get("activity_name") or "").strip()
            act_id = str(m.get("activity_id") or "")

            curr_task = _resolve_task(act_name, act_id, curr_by_name, curr_by_id)
            prev_task = _resolve_task(act_name, act_id, prev_by_name, prev_by_id)
            base_task = _resolve_task(act_name, act_id, base_by_name, base_by_id)

            if curr_task:
                curr_finish = _extract_finish(curr_task)
                pct = curr_task.get("percent_complete", 0)

                # Baseline finish — prefer embedded field, fall back to baseline task
                baseline_finish = (curr_task.get("baseline_finish") or
                                   curr_task.get("bl_finish") or
                                   _extract_finish(base_task) or "")
                if baseline_finish:
                    baseline_finish = str(baseline_finish)[:10]

                # Previous forecast — from prior update task
                prev_finish = _extract_finish(prev_task)

                # --- 2-source confidence check ---
                # Source A: current schedule file
                # Source B: previous update (if finish matches or is close) OR baseline embedded field
                sources_agree = 0
                if curr_finish:
                    sources_agree += 1  # current is always source 1
                if prev_task and prev_finish:
                    sources_agree += 1  # previous update is source 2
                elif base_task and baseline_finish:
                    sources_agree += 1  # baseline is source 2

                confidence = "[VERIFIED — 2 sources]" if sources_agree >= 2 else "[1 source]"

                date_str = f"Forecast: {curr_finish}" if curr_finish else "Forecast: N/A"
                bl_str = f" | Baseline: {baseline_finish}" if baseline_finish else ""
                prev_str = f" | Prior Update: {prev_finish}" if prev_finish else ""
                pct_str = f" | {pct:.0f}% complete" if pct is not None else ""
                lines.append(f"  - {std}: {date_str}{bl_str}{prev_str}{pct_str}  {confidence}")
            else:
                # No current task match — still emit the name
                if act_name and act_name != std:
                    lines.append(f"  - {std}  (activity: '{act_name}' — date not resolved)")
                else:
                    lines.append(f"  - {std}  (date not resolved)")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[{slug}] Could not load milestone map: {e}")
        return ""


def ensure_project_loaded(slug: str) -> bool:
    """On-demand loading: parse schedule data if not already loaded. Returns True if loaded."""
    # Already loaded?
    if slug in _project_cache:
        return True

    # Need metadata first
    if slug not in _project_meta:
        project_path = os.path.join(PROJECTS_DIR, slug)
        if not os.path.exists(project_path):
            return False
        _load_metadata_only(slug, project_path)
        if slug not in _project_meta:
            return False

    # Load schedule data on demand
    project_path = os.path.join(PROJECTS_DIR, slug)
    _load_schedule_data(slug, project_path)
    return slug in _project_cache and _project_cache[slug]


def get_project_context(slug: str, page: Optional[str] = None) -> str:
    """
    Returns the full context string for a project slug.
    Optionally adds a page hint so the LLM knows what view the user is on.
    On-demand: triggers schedule parsing if not already loaded.
    """
    # Trigger on-demand loading
    _ = ensure_project_loaded(slug)

    meta = _project_meta.get(slug)
    if not meta:
        return ""

    parts = [f"PROJECT: {meta['display_name']}"]

    if page:
        parts.append(f"CURRENT PAGE VIEW: {page}")
        parts.append(_page_hint(page))

    # Authoritative tracker data (data dates, update history) — injected first
    try:
        from tracker_loader import get_tracker_context
        tracker_ctx = get_tracker_context(slug)
        if tracker_ctx:
            parts.append("")
            parts.append(tracker_ctx)
    except Exception:
        pass

    milestone_ctx = _load_milestone_map(slug)
    if milestone_ctx:
        parts.append("")
        parts.append(milestone_ctx)

    schedule_ctx = _project_cache.get(slug, "")
    if schedule_ctx:
        parts.append("")
        parts.append(schedule_ctx)
    else:
        # Schedule not loaded yet (on-demand parsing in progress or no data)
        parts.append("")
        parts.append("[Schedule data is loaded on-demand for this project. If this is the first query, parsing may take 30-60 seconds. Try your question again in a moment.]")

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
    """Returns list of all projects with slug, display name, type, and pages.
    Reads meta.json directly from disk so the full list is always available
    immediately, even before the background load_all_projects() thread finishes.
    """
    results = []
    if not os.path.exists(PROJECTS_DIR):
        return results
    for slug in sorted(os.listdir(PROJECTS_DIR)):
        project_path = os.path.join(PROJECTS_DIR, slug)
        if not os.path.isdir(project_path):
            continue
        # Prefer in-memory cache (fully loaded), fall back to direct disk read
        meta = _project_meta.get(slug)
        if meta is None:
            meta_path = os.path.join(project_path, "meta.json")
            if not os.path.exists(meta_path):
                continue
            try:
                with open(meta_path, "r") as f:
                    meta = json.load(f)
            except Exception:
                continue
        results.append({
            "slug": slug,
            "display_name": meta["display_name"],
            "type": meta.get("type", "Construction"),
            "pages": meta["pages"]
        })
    results.sort(key=lambda x: x["display_name"])
    return results


def has_schedule(slug: str) -> bool:
    """Returns True if this project has a parsed schedule file."""
    return bool(_project_cache.get(slug))


def get_project_health(slug: str) -> Optional[dict]:
    """Returns health dict for a slug: {status, compression_pct, max_slip_days, max_accel_days}."""
    return _project_health.get(slug)


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
