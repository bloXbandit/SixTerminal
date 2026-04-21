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
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Limits concurrent MPP/XER parses to 3 — prevents CPU starvation on single-core Render instances
_mpp_semaphore = threading.Semaphore(3)

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")

# Encryption helpers — graceful no-op if key not set or cryptography not installed
try:
    from crypto import read_encrypted_json, write_encrypted_json
except ImportError:
    def read_encrypted_json(path):
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    def write_encrypted_json(path, obj):
        with open(path, "w", encoding="utf-8") as f: json.dump(obj, f, indent=2, default=str)

_project_cache: Dict[str, str] = {}
_project_meta: Dict[str, dict] = {}
_project_health: Dict[str, dict] = {}  # {slug: {status, compression_pct, max_slip_days, max_accel_days}}
_project_tasks: Dict[str, list] = {}          # {slug: [task_dicts]} — current schedule tasks for milestone lookup
_project_tasks_previous: Dict[str, list] = {}  # {slug: [task_dicts]} — previous update tasks
_project_tasks_baseline: Dict[str, list] = {}  # {slug: [task_dicts]} — baseline tasks
_project_relationships: Dict[str, list] = {}  # {slug: [rel_dicts]} — current relationships for CP analysis
_loading_in_progress: set = set()  # Track which slugs are currently loading in background
_loading_start_times: Dict[str, float] = {}  # {slug: timestamp} — when loading started


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
    If ENCRYPTION_KEY is set the file is decrypted to a temp file before parsing.
    """
    import tempfile
    ext = os.path.splitext(filepath)[1].lower()

    # Decrypt to a temp file if encryption is enabled
    try:
        from crypto import read_encrypted_bytes, is_enabled as _enc_on
        if _enc_on():
            _raw = read_encrypted_bytes(filepath)
            _tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            _tmp.write(_raw)
            _tmp.close()
            _parse_path = _tmp.name
        else:
            _parse_path = filepath
    except ImportError:
        _parse_path = filepath

    try:
        if ext in (".mpp", ".xml"):
            MPPParser = _get_mpp_parser()
            p = MPPParser(_parse_path)
            raw = p.get_llm_context()
            return {
                "raw_context": raw,
                "source": os.path.basename(filepath),
                "tasks": p.tasks,
                "relationships": p.relationships,
            }

        elif ext == ".xer":
            P6Parser = _get_xer_parser()
            p = P6Parser(_parse_path)
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
            # Normalize XER relationships to standard format
            xer_rels = []
            if p.df_relationships is not None and not p.df_relationships.empty:
                for _, row in p.df_relationships.iterrows():
                    xer_rels.append({
                        "successor_id": str(row.get("task_id", "")),
                        "predecessor_id": str(row.get("pred_task_id", "")),
                    })
            return {
                "raw_context": "\n".join(lines),
                "source": os.path.basename(filepath),
                "tasks": xer_tasks,
                "relationships": xer_rels,
            }

    except Exception as e:
        logger.error(f"Parse failed for {filepath}: {e}")
        return None
    finally:
        # Clean up temp decryption file if one was created
        if _parse_path != filepath:
            try:
                os.unlink(_parse_path)
            except Exception:
                pass

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
        images = convert_from_path(pdf_path, first_page=1, last_page=max_pages, dpi=300)
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
    Extract text from PDF. Prefers pre-extracted .txt sidecar from build-time.
    Falls back to pdfplumber/OCR only if no sidecar exists.
    """
    # First: try pre-extracted .txt sidecar (build-time extraction)
    sidecar = _read_txt_sidecar(pdf_path)
    if sidecar:
        return sidecar

    # Fallback: live extraction with OCR for image-based PDFs
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


def _read_txt_sidecar(pdf_path: str) -> list:
    """Read pre-extracted .txt sidecar if it exists. Returns empty list if not found."""
    txt_path = pdf_path.replace('.pdf', '.txt')
    if os.path.exists(txt_path):
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if len(line.strip()) > 3]
                if lines:
                    logger.info(f"  Using pre-extracted .txt: {os.path.basename(txt_path)}")
                    return lines
        except Exception as e:
            logger.warning(f"Failed to read .txt sidecar {txt_path}: {e}")
    return []


def _extract_pdf_milestones(pdf_path: str, max_pages: int = 30) -> list:
    """
    Extract meaningful lines from verify.pdf for schedule crosscheck.
    Prefers pre-extracted .txt sidecar files from build-time extraction.
    Falls back to pdfplumber with 5s timeout only if no sidecar exists.
    """
    # First: try pre-extracted .txt sidecar (build-time extraction)
    sidecar = _read_txt_sidecar(pdf_path)
    if sidecar:
        return sidecar

    # Fallback: live PDF extraction (slow, may timeout)
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
    t.join(timeout=5)
    if t.is_alive():
        logger.warning(f"PDF read timed out (5s), skipping: {os.path.basename(pdf_path)}")
        return []
    return result


def _extract_variance_pdf(pdf_path: str) -> list:
    """
    Extract text lines from a variance_N.pdf report.
    Prefers pre-extracted .txt sidecar files from build-time extraction.
    Falls back to pdfplumber with 5s timeout only if no sidecar exists.
    """
    # First: try pre-extracted .txt sidecar (build-time extraction)
    sidecar = _read_txt_sidecar(pdf_path)
    if sidecar:
        return sidecar

    # Fallback: live PDF extraction (slow, may timeout)
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
    t.join(timeout=5)
    if t.is_alive():
        logger.warning(f"Variance PDF timed out (5s), skipping: {os.path.basename(pdf_path)}")
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

            # Second-pass: crop the bottom 40% of page 1 to capture the monthly table
            # (the bar chart graphic obscures the table in full-page OCR)
            try:
                from pdf2image import convert_from_path as _cfp
                import pytesseract as _tess
                _pages = _cfp(pdf_path, first_page=1, last_page=1, dpi=300)
                if _pages:
                    _pg = _pages[0]
                    _w, _h = _pg.size
                    _crop = _pg.crop((0, int(_h * 0.60), _w, _h))
                    _crop_text = _tess.image_to_string(_crop)
                    _crop_lines = [l.strip() for l in _crop_text.splitlines() if l.strip()]
                    # Append only lines not already in the main scan
                    existing_set = set(lines)
                    for _cl in _crop_lines:
                        if _cl not in existing_set:
                            lines.append(_cl)
                    logger.info(f"  Compression PDF crop-OCR added {len(_crop_lines)} lines from bottom 40%")
            except Exception as _ce:
                logger.warning(f"  Compression PDF crop-OCR failed: {_ce}")

            def _parse_pct_val(raw_val):
                """Parse a raw OCR string into an integer %, returning None on failure."""
                cleaned = raw_val.strip().lstrip('{[(').rstrip('}])')
                cleaned = cleaned.translate(str.maketrans('OoIlSsBbZz', '0011558822'))
                try:
                    pct = int(cleaned)
                    return pct if -100 <= pct <= 100 else None
                except ValueError:
                    return None

            for i, line in enumerate(lines):
                # Primary match: number on same line as header (handles OCR noise chars before/after number)
                # e.g. "Remaining Work Compression {35 %" or "Remaining Work Compression { 35 |%"
                # The |, I, or l between number and % is OCR noise from the box border
                m = re.search(r'Remaining Work Compression\s*[{\[(]?\s*([-+]?[\dOoIlSsBbZz]+)\s*[|Il]?\s*%', line, re.IGNORECASE)
                if m:
                    pct = _parse_pct_val(m.group(1))
                    if pct is not None:
                        result["compression_pct"] = pct
                        logger.info(f"  Compression % found on same line: {pct}%")
                    else:
                        logger.warning(f"Compression % out of range or unparseable — raw: '{m.group(1)}'")
                elif re.search(r'Remaining Work Compression', line, re.IGNORECASE):
                    # Fallback: number is on the next line (PDF layout splits them)
                    # e.g. line N: "Remaining Work Compression"
                    #      line N+1: "35 %" or "{35 %" or "35%"
                    for j in range(i + 1, min(i + 4, len(lines))):
                        next_line = lines[j].strip()
                        nm = re.match(r'^[{\[(]?\s*([-+]?[\dOoIlSsBbZz]+)\s*%', next_line)
                        if nm:
                            pct = _parse_pct_val(nm.group(1))
                            if pct is not None:
                                result["compression_pct"] = pct
                                logger.info(f"  Compression % found on next line ({j}): {pct}%")
                            break
                        if next_line:  # non-empty line that didn't match — stop looking
                            break
                # Handle both dates on same line: "Data Date: 01/09/2026 Data Date: 03/24/2026"
                m = re.findall(r'Data Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})', line)
                if m:
                    if result["earlier_data_date"] is None:
                        result["earlier_data_date"] = m[0]
                    if len(m) >= 2 and result["later_data_date"] is None:
                        result["later_data_date"] = m[1]
                    elif len(m) == 1 and result["later_data_date"] is None and m[0] != result["earlier_data_date"]:
                        result["later_data_date"] = m[0]
                # Handle both finish dates on same line: "Finish Date: 01/11/2027 Finish Date: 12/28/2026"
                m = re.findall(r'Finish Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})', line)
                if m:
                    if result["earlier_finish"] is None:
                        result["earlier_finish"] = m[0]
                    if len(m) >= 2 and result["later_finish"] is None:
                        result["later_finish"] = m[1]
                    elif len(m) == 1 and result["later_finish"] is None and m[0] != result["earlier_finish"]:
                        result["later_finish"] = m[0]
                # Format A: "Mar 26  39  56" — single line (200 DPI OCR)
                m = re.match(r'^([A-Za-z]{3}\s+\d{2})\s+(\d+)\s+(\d+)$', line)
                if m:
                    result["monthly"].append({
                        "month": m.group(1),
                        "earlier_days": int(m.group(2)),
                        "later_days": int(m.group(3)),
                    })

            # Format B (300 DPI column-split): month names in one column, then two number columns
            # Pattern: months appear as "Mar 26", "Apr 26" etc. followed later by two numeric columns
            # Detect this layout when monthly is still empty after the line scan
            if not result["monthly"]:
                month_pat = re.compile(r'^([A-Za-z]{3}\s+\d{2})$')
                num_pat   = re.compile(r'^(\d+)$')
                month_names = []
                earlier_nums = []
                later_nums   = []
                # Collect all month-name lines and all standalone number lines
                for line in lines:
                    if month_pat.match(line.strip()):
                        month_names.append(line.strip())
                    elif num_pat.match(line.strip()):
                        earlier_nums.append(int(line.strip()))  # accumulate all numbers first
                # Deduplicate month names (OCR sometimes repeats them from chart axis + table)
                seen = []
                for mn in month_names:
                    if mn not in seen:
                        seen.append(mn)
                month_names = seen
                # The numbers appear as two consecutive groups of len(month_names) each
                n = len(month_names)
                if n > 0 and len(earlier_nums) >= 2 * n:
                    # Take the last 2*n numbers (table is at the bottom; chart axis numbers may precede)
                    tail = earlier_nums[-2 * n:]
                    e_col = tail[:n]
                    l_col = tail[n:]
                    for mn, ed, ld in zip(month_names, e_col, l_col):
                        result["monthly"].append({
                            "month": mn,
                            "earlier_days": ed,
                            "later_days": ld,
                        })
                    logger.info(f"  Monthly table parsed via column-split layout: {n} rows")
                elif n > 0 and len(earlier_nums) == n:
                    # Only one column of numbers found — can't split, skip
                    logger.warning(f"  Monthly table: found {n} months but only {len(earlier_nums)} numbers — skipping")

            # If no explicit % found in text, compute from monthly table
            if result["compression_pct"] is None and result["monthly"]:
                earlier_total = sum(m["earlier_days"] for m in result["monthly"])
                later_total = sum(m["later_days"] for m in result["monthly"])
                if earlier_total > 0:
                    computed_pct = round((later_total - earlier_total) / earlier_total * 100, 1)
                    if -100 <= computed_pct <= 100:
                        result["compression_pct"] = computed_pct
                        logger.info(f"  Compression % computed from monthly table: {computed_pct}% "
                                    f"(earlier={earlier_total} days, later={later_total} days)")

            # --- Compute all derived metrics ---
            from datetime import datetime as _cdt
            def _parse_date(s):
                if not s: return None
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
                    try: return _cdt.strptime(str(s).strip()[:10], fmt)
                    except ValueError: pass
                return None

            monthly = result["monthly"]
            if monthly:
                earlier_total = sum(r["earlier_days"] for r in monthly)
                later_total   = sum(r["later_days"]   for r in monthly)
                delta_total   = later_total - earlier_total
                result["total_earlier_activity_days"] = earlier_total
                result["total_later_activity_days"]   = later_total
                result["total_activity_day_delta"]    = delta_total
                # Peak compression month (largest positive delta = most added work)
                peak = max(monthly, key=lambda r: r["later_days"] - r["earlier_days"])
                result["peak_compression_month"] = peak["month"]
                result["peak_compression_delta"] = peak["later_days"] - peak["earlier_days"]

            # Finish date slip (calendar days): later_finish - earlier_finish
            d_ef = _parse_date(result.get("earlier_finish"))
            d_lf = _parse_date(result.get("later_finish"))
            if d_ef and d_lf:
                result["finish_slip_days"] = (d_lf - d_ef).days

            # Remaining work span (calendar days): finish - data_date for each schedule
            d_edd = _parse_date(result.get("earlier_data_date"))
            d_ldd = _parse_date(result.get("later_data_date"))
            if d_ef and d_edd:
                result["earlier_remaining_span_days"] = (d_ef - d_edd).days
            if d_lf and d_ldd:
                result["later_remaining_span_days"] = (d_lf - d_ldd).days

            # Comparison window (calendar days between the two data dates)
            if d_edd and d_ldd:
                result["comparison_window_days"] = (d_ldd - d_edd).days

            # Return result if we have monthly data OR an explicit pct — not just when pct is set
            has_data = (result["compression_pct"] is not None or
                        result["monthly"] or
                        result["earlier_data_date"] or
                        result["later_data_date"])
            result_holder[0] = result if has_data else None
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


def _extract_compression_image(img_path: str) -> Optional[dict]:
    """
    Extract compression data from a screenshot image (JPG/PNG) using GPT-4o vision.
    Returns the same dict shape as _extract_compression_pdf so _format_compression_pdf_context
    can render it identically.
    Naming convention: compression_updateN.jpg / compression_updateN.png
    """
    import base64
    import re as _re
    from datetime import datetime as _dt

    ext = os.path.splitext(img_path)[1].lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/png")

    try:
        with open(img_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("utf-8")
    except Exception as e:
        logger.warning(f"Compression image read failed ({img_path}): {e}")
        return None

    VISION_PROMPT = (
        "This is a Schedule Validator Remaining Work Compression report screenshot. "
        "Extract EXACTLY the following fields and return them as a JSON object with these keys:\n"
        "  compression_pct: the integer shown next to 'Remaining Work Compression' "
        "(positive if expanded/arrow right, negative if compressed/arrow left). Example: 35 or -12.\n"
        "  earlier_data_date: Data Date in the Earlier/A schedule box (MM/DD/YYYY).\n"
        "  later_data_date: Data Date in the Later/B schedule box (MM/DD/YYYY).\n"
        "  earlier_finish_date: Finish Date in the Earlier/A schedule box (MM/DD/YYYY).\n"
        "  later_finish_date: Finish Date in the Later/B schedule box (MM/DD/YYYY).\n"
        "  monthly: array of objects, one per row in the bottom table, each with: "
        "month (string e.g. 'Mar 26'), earlier_days (integer), later_days (integer).\n"
        "Return ONLY valid JSON. No markdown fences, no explanation."
    )

    try:
        import openai as _oai
        _api_key = os.environ.get("OPENAI_API_KEY", "")
        if not _api_key:
            logger.warning("Compression image extraction: OPENAI_API_KEY not set")
            return None
        _client = _oai.OpenAI(api_key=_api_key)
        resp = _client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}}
                ]
            }],
            max_tokens=800,
            timeout=30
        )
        raw_json = resp.choices[0].message.content.strip()
        # Strip markdown fences if model adds them despite instructions
        raw_json = _re.sub(r'^```(?:json)?\s*', '', raw_json, flags=_re.IGNORECASE)
        raw_json = _re.sub(r'\s*```$', '', raw_json)
        import json as _json
        parsed = _json.loads(raw_json)
    except Exception as e:
        logger.warning(f"Compression image vision extraction failed ({img_path}): {e}")
        return None

    # Normalise dates
    def _parse_date(s):
        if not s: return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try: return _dt.strptime(str(s).strip(), fmt)
            except ValueError: pass
        return None

    earlier_data = _parse_date(parsed.get("earlier_data_date"))
    later_data   = _parse_date(parsed.get("later_data_date"))
    earlier_fin  = _parse_date(parsed.get("earlier_finish_date"))
    later_fin    = _parse_date(parsed.get("later_finish_date"))

    monthly = []
    for row in parsed.get("monthly", []):
        try:
            monthly.append({
                "month": str(row.get("month", "")).strip(),
                "earlier_days": int(row.get("earlier_days", 0)),
                "later_days": int(row.get("later_days", 0)),
            })
        except (TypeError, ValueError):
            continue

    try:
        compression_pct = float(parsed["compression_pct"]) if parsed.get("compression_pct") is not None else None
    except (TypeError, ValueError):
        compression_pct = None

    # Derived metrics — same logic as PDF extractor
    earlier_span   = int((earlier_fin  - earlier_data).days) if earlier_fin  and earlier_data else None
    later_span     = int((later_fin    - later_data).days)   if later_fin    and later_data   else None
    finish_slip    = int((later_fin    - earlier_fin).days)  if later_fin    and earlier_fin  else None
    compare_window = int((later_data   - earlier_data).days) if later_data   and earlier_data else None
    earlier_total  = sum(r["earlier_days"] for r in monthly) if monthly else None
    later_total    = sum(r["later_days"]   for r in monthly) if monthly else None
    activity_delta = (later_total - earlier_total) if (earlier_total is not None and later_total is not None) else None
    peak = max(monthly, key=lambda r: abs(r["later_days"] - r["earlier_days"])) if monthly else None

    result = {
        "compression_pct":               compression_pct,
        "earlier_data_date":             earlier_data.strftime("%m/%d/%Y") if earlier_data else parsed.get("earlier_data_date"),
        "later_data_date":               later_data.strftime("%m/%d/%Y")   if later_data   else parsed.get("later_data_date"),
        "earlier_finish":                earlier_fin.strftime("%m/%d/%Y")  if earlier_fin  else parsed.get("earlier_finish_date"),
        "later_finish":                  later_fin.strftime("%m/%d/%Y")    if later_fin    else parsed.get("later_finish_date"),
        "monthly":                       monthly,
        "earlier_remaining_span_days":   earlier_span,
        "later_remaining_span_days":     later_span,
        "finish_slip_days":              finish_slip,
        "comparison_window_days":        compare_window,
        "total_earlier_activity_days":   earlier_total,
        "total_later_activity_days":     later_total,
        "total_activity_day_delta":      activity_delta,
        "peak_compression_month":        peak["month"] if peak else None,
        "peak_compression_delta":        (peak["later_days"] - peak["earlier_days"]) if peak else None,
        "source":                        "image_vision",
    }
    logger.info(f"[compression_image] {os.path.basename(img_path)}: "
                f"pct={compression_pct}, earlier={result['earlier_data_date']}, "
                f"later={result['later_data_date']}, monthly_rows={len(monthly)}")
    return result


def _format_compression_pdf_context(data: dict, label: str = "") -> str:
    """Format extracted compression PDF data as an LLM context block."""
    if not data:
        return ""
    lines = [f"=== COMPRESSION REPORT — VERIFIED (Schedule Validator){' — ' + label if label else ''} ==="]
    pct = data.get("compression_pct")
    if pct is not None:
        direction = "compressed" if pct < 0 else "expanded" if pct > 0 else "unchanged"
        lines.append(f"Remaining Work Compression: {pct:+.1f}% ({direction})")

    # --- Comparison window ---
    if data.get("earlier_data_date") and data.get("later_data_date"):
        win = data.get("comparison_window_days")
        win_str = f" ({win} calendar days apart)" if win is not None else ""
        lines.append(f"Compared: {data['earlier_data_date']} (earlier) → {data['later_data_date']} (later){win_str}")

    # --- Finish date slip ---
    if data.get("earlier_finish") and data.get("later_finish"):
        slip = data.get("finish_slip_days")
        if slip is not None:
            slip_sign = "+" if slip >= 0 else ""
            slip_desc = f"slipped {slip} calendar days" if slip > 0 else (f"improved {abs(slip)} calendar days" if slip < 0 else "unchanged")
            lines.append(f"Finish Date: {data['earlier_finish']} → {data['later_finish']} ({slip_desc})")
        else:
            finish_note = " [finish unchanged]" if data["earlier_finish"] == data["later_finish"] else " [finish changed]"
            lines.append(f"Finish Date: {data['earlier_finish']} → {data['later_finish']}{finish_note}")

    # --- Remaining work span ---
    e_span = data.get("earlier_remaining_span_days")
    l_span = data.get("later_remaining_span_days")
    if e_span is not None and l_span is not None:
        span_delta = l_span - e_span
        span_sign = "+" if span_delta >= 0 else ""
        lines.append(f"Remaining Work Span: {e_span}cd (earlier) → {l_span}cd (later)  Δ {span_sign}{span_delta}cd")

    # --- Total activity days ---
    e_tot = data.get("total_earlier_activity_days")
    l_tot = data.get("total_later_activity_days")
    d_tot = data.get("total_activity_day_delta")
    if e_tot is not None and l_tot is not None:
        sign = "+" if d_tot >= 0 else ""
        lines.append(f"Total Activity Days: {e_tot} (earlier) → {l_tot} (later)  Δ {sign}{d_tot}")

    # --- Peak compression month ---
    peak_month = data.get("peak_compression_month")
    peak_delta = data.get("peak_compression_delta")
    if peak_month and peak_delta is not None:
        sign = "+" if peak_delta >= 0 else ""
        lines.append(f"Peak Compression Month: {peak_month} ({sign}{peak_delta} activity days added)")

    # --- Monthly table ---
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

    # --- Locate compression file for current update ---
    # Priority: compression_updateN.jpg / .png (vision, most reliable) > compression_updateN.pdf (OCR)
    # Naming: compression_update1.jpg, compression_update2.png, compression_update1.pdf, etc.
    # Always uses the file matching the CURRENT update number.
    # Falls back to the highest available prior update if no exact match exists.
    _compression_file_path = None
    _compression_is_image  = False
    try:
        import re as _re
        _comp_imgs = {}   # {update_num: filepath} for .jpg/.jpeg/.png
        _comp_pdfs = {}   # {update_num: filepath} for .pdf
        for _fn in os.listdir(project_path):
            _lower_fn = _fn.lower()
            # Match compression_updateN.ext or compression_N.ext
            _cm = _re.match(r'^compression[_\-](?:update[_\-]?)?(\d+)\.(jpg|jpeg|png|pdf)$', _lower_fn)
            if _cm:
                _num = int(_cm.group(1))
                _ext = _cm.group(2)
                if _ext in ("jpg", "jpeg", "png"):
                    _comp_imgs[_num] = os.path.join(project_path, _fn)
                elif _ext == "pdf":
                    _comp_pdfs[_num] = os.path.join(project_path, _fn)

        # Determine current update number from label (e.g. "update_4" -> 4)
        _cur_num = None
        _m = _re.search(r'update[_\s]*(\d+)', current_label, _re.IGNORECASE)
        if _m:
            _cur_num = int(_m.group(1))

        def _best_match(source_dict, cur):
            """Return filepath for exact cur match, or highest available <= cur."""
            if not source_dict:
                return None
            if cur is not None and cur in source_dict:
                return source_dict[cur]
            if cur is not None:
                _cands = [n for n in source_dict if n <= cur]
                if _cands:
                    return source_dict[max(_cands)]
            # No update number in label — return highest available
            return source_dict[max(source_dict)]

        # Image preferred over PDF for same update
        _img_path = _best_match(_comp_imgs, _cur_num)
        _pdf_path = _best_match(_comp_pdfs, _cur_num)
        if _img_path:
            _compression_file_path = _img_path
            _compression_is_image  = True
            logger.info(f"[{slug}] Compression image found (preferred over PDF): {os.path.basename(_img_path)}")
        elif _pdf_path:
            _compression_file_path = _pdf_path
            _compression_is_image  = False
            logger.info(f"[{slug}] Compression PDF found: {os.path.basename(_pdf_path)}")
    except Exception as _comp_scan_e:
        logger.warning(f"[{slug}] Compression file scan failed: {_comp_scan_e}")

    # --- Extract compression data ---
    if _compression_file_path:
        try:
            if _compression_is_image:
                logger.info(f"[{slug}] Extracting compression via vision: {os.path.basename(_compression_file_path)}")
                comp_data = _extract_compression_image(_compression_file_path)
            else:
                logger.info(f"[{slug}] Extracting compression via OCR/PDF: {os.path.basename(_compression_file_path)}")
                comp_data = _extract_compression_pdf(_compression_file_path)
            if comp_data:
                comp_ctx = _format_compression_pdf_context(comp_data, label=os.path.basename(_compression_file_path))
                if comp_ctx:
                    parts.append("")
                    parts.append(comp_ctx)
                    if comp_data.get("compression_pct") is not None:
                        _compression_pct = comp_data["compression_pct"]
        except Exception as _ce:
            logger.warning(f"[{slug}] Compression extraction failed: {_ce}")

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

    # --- Store tasks and relationships for milestone date cross-referencing ---
    _project_tasks[slug] = current_data.get("tasks", [])
    _project_relationships[slug] = current_data.get("relationships", [])
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
            variance_ctx = format_variance_for_context(variance, max_items_per_phase=12)
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
                    drift_ctx = format_variance_for_context(drift, max_items_per_phase=12)
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

                # --- SPI computation (status view only) ---
                try:
                    import re as _spi_re
                    _spi_dd_str = None
                    # Extract data date from current schedule context string
                    _spi_dd_m = _spi_re.search(
                        r'(?:Data Date|Status Date)[:\s]+([\d]{4}-[\d]{2}-[\d]{2}|[\d]{1,2}/[\d]{1,2}/[\d]{4})',
                        current_data["raw_context"]
                    )
                    if _spi_dd_m:
                        _spi_dd_str = _spi_dd_m.group(1)
                    # Also try project metadata from current tasks (MPP has status_date)
                    if not _spi_dd_str:
                        for _t in current_data.get("tasks", [])[:1]:
                            _spi_dd_str = _t.get("status_date") or _t.get("data_date") or ""
                    if _spi_dd_str:
                        _spi_result = _compute_spi(
                            current_tasks=current_data.get("tasks", []),
                            baseline_tasks=baseline_data.get("tasks", []),
                            data_date_str=_spi_dd_str,
                        )
                        if _spi_result:
                            _spi_val = _spi_result["spi"]
                            _spi_planned = _spi_result["planned_count"]
                            _spi_actual = _spi_result["actual_count"]
                            _spi_interp = _spi_result["interpretation"]
                            _spi_loaded = _spi_result["is_resource_loaded"]
                            _spi_note = (
                                "Cost-based SPI/CPI available (resource-loaded schedule)."
                                if _spi_loaded else
                                "Cost-based SPI/CPI not available \u2014 schedule is not resource-loaded."
                            )
                            _spi_block = [
                                "=== SCHEDULE PERFORMANCE INDEX (SPI) ===  [STATUS VIEW ONLY — do not include in narrative unless user asks]",
                                f"Schedule Performance Index (SPI): {_spi_val:.3f} (activity-count proxy)",
                                f"  {_spi_actual} of {_spi_planned} activities planned complete by data date are actually complete",
                                f"  Interpretation: {_spi_interp}",
                                f"  Note: {_spi_note}",
                            ]
                            if _spi_result.get("behind_list"):
                                _spi_block.append("  Top behind-schedule activities (baseline due, not done):")
                                for _ba in _spi_result["behind_list"][:5]:
                                    _spi_block.append(
                                        f"    {_ba['code']} {_ba['name']} | {_ba['pct']:.0f}% | BL finish: {_ba['bl_finish']}"
                                    )
                            # Store SPI in project health for status endpoint
                            if slug in _project_health:
                                _project_health[slug]["spi"] = _spi_val
                                _project_health[slug]["spi_planned"] = _spi_planned
                                _project_health[slug]["spi_actual"] = _spi_actual
                                _project_health[slug]["spi_interpretation"] = _spi_interp
                                _project_health[slug]["spi_resource_loaded"] = _spi_loaded
                            parts.append("")
                            parts.append("\n".join(_spi_block))
                            logger.info(f"[{slug}] SPI computed: {_spi_val:.3f} ({_spi_actual}/{_spi_planned})")
                except Exception as _spi_e:
                    logger.debug(f"[{slug}] SPI computation failed: {_spi_e}")

                # --- Contract completion date for portfolio view ---
                try:
                    _mm_path = os.path.join(PROJECTS_DIR, slug, "milestone_map.json")
                    if os.path.exists(_mm_path):
                        _mm_data = read_encrypted_json(_mm_path)
                        _cc_date = ""
                        _cc_act_id = ""
                        _cc_act_name = ""
                        for _mm in _mm_data.get("milestones", []):
                            _std = (_mm.get("standardized_name") or "").lower()
                            if "contract completion" in _std or "substantial completion" in _std:
                                _cc_date = _mm.get("current_date") or ""
                                _cc_act_id = str(_mm.get("activity_id") or "")
                                _cc_act_name = (_mm.get("activity_name") or "").strip()
                                break
                        # If no stored current_date, resolve from current tasks
                        if not _cc_date and (_cc_act_id or _cc_act_name):
                            _cc_by_name, _cc_by_id, _cc_by_code = _build_task_lookup(
                                _project_tasks.get(slug, [])
                            )
                            _cc_task = _resolve_task(
                                _cc_act_name, _cc_act_id,
                                _cc_by_name, _cc_by_id, _cc_by_code
                            )
                            _cc_date = _extract_finish(_cc_task)
                        if _cc_date:
                            _cc_date = str(_cc_date)[:10]
                            if slug in _project_health:
                                _project_health[slug]["contract_completion_date"] = _cc_date
                            logger.debug(f"[{slug}] Contract completion date: {_cc_date}")
                except Exception as _cc_e:
                    logger.debug(f"[{slug}] Contract completion date lookup failed: {_cc_e}")

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

    # --- Constraint list (XER only — conversation mode, not narrative unless asked) ---
    try:
        curr_tasks = current_data.get("tasks", [])
        constrained = [
            t for t in curr_tasks
            if t.get("cstr_type") and not t.get("summary", False)
            and float(t.get("percent_complete") or 0) < 100
        ]
        if constrained:
            incomplete_total = len([t for t in curr_tasks
                                    if not t.get("summary", False)
                                    and float(t.get("percent_complete") or 0) < 100])
            hard_types = {"Mandatory Finish", "Mandatory Start"}
            hard_constrained = [t for t in constrained if t.get("cstr_type") in hard_types]
            hard_pct = (len(hard_constrained) / incomplete_total * 100) if incomplete_total > 0 else 0
            cstr_lines = [
                "=== CONSTRAINT DETAILS (conversation mode only — do not include in narrative unless user asks) ===",
                f"Constrained incomplete activities: {len(constrained)} of {incomplete_total} ({len(constrained)/incomplete_total*100:.1f}%)",
            ]
            for t in constrained[:40]:
                code = t.get("task_code") or t.get("id") or ""
                cdate = t.get("cstr_date") or ""
                cdate_str = f" on {cdate}" if cdate else ""
                ctype2 = t.get("cstr_type2")
                c2_str = f" | Secondary: {ctype2}" if ctype2 else ""
                cstr_lines.append(
                    f"  {code} {t['name']} | {t['cstr_type']}{cdate_str}{c2_str} | Finish: {t['finish']}"
                )
            if len(constrained) > 40:
                cstr_lines.append(f"  ... +{len(constrained) - 40} more constrained activities")
            if hard_pct > 5:
                cstr_lines.append(
                    f"SCHEDULE QUALITY RISK: {len(hard_constrained)} of {incomplete_total} incomplete activities "
                    f"({hard_pct:.1f}%) have hard constraints (Mandatory Finish/Start). "
                    f"Hard constraints override schedule logic and can mask float. "
                    f"Surface this only if user asks about constraints or risks."
                )
            parts.append("")
            parts.append("\n".join(cstr_lines))
    except Exception as _cstr_e:
        logger.debug(f"[{slug}] Constraint list injection failed: {_cstr_e}")

    # --- Float path chains (XER only — conversation mode, not narrative unless asked) ---
    try:
        curr_tasks = current_data.get("tasks", [])
        # Group by float_path number (0 = not assigned, skip)
        from collections import defaultdict
        fp_groups = defaultdict(list)
        for t in curr_tasks:
            fp = t.get("float_path", 0)
            if fp and int(fp) > 0 and not t.get("summary", False):
                fp_groups[int(fp)].append(t)
        if fp_groups:
            fp_lines = [
                "=== FLOAT PATH CHAINS (conversation mode only — do not include in narrative unless user asks) ===",
                "Path 1 = critical chain (P6 native). Path 2+ = near-critical chains in ascending float order.",
            ]
            for path_num in sorted(fp_groups.keys())[:4]:  # show Path 1-4 max
                chain = sorted(fp_groups[path_num], key=lambda t: t.get("float_path_order", 0))
                # Controlling finish = last activity in path by float_path_order
                ctrl = chain[-1] if chain else None
                ctrl_finish = ctrl["finish"] if ctrl else "N/A"
                ctrl_float_days = round(float(ctrl.get("total_float_hrs") or 0) / 8.0, 1) if ctrl else 0
                path_label = "Critical Chain" if path_num == 1 else f"Near-Critical Path {path_num}"
                fp_lines.append(
                    f"  Path {path_num} ({path_label}): {len(chain)} activities | "
                    f"Controlling finish: {ctrl_finish} | Float: {ctrl_float_days} days"
                )
                # Show first 5 activities in chain
                for act in chain[:5]:
                    code = act.get("task_code") or act.get("id") or ""
                    float_d = round(float(act.get("total_float_hrs") or 0) / 8.0, 1)
                    fp_lines.append(
                        f"    {code} {act['name']} | Finish: {act['finish']} | Float: {float_d}d"
                    )
                if len(chain) > 5:
                    fp_lines.append(f"    ... +{len(chain) - 5} more in path {path_num}")
            parts.append("")
            parts.append("\n".join(fp_lines))
    except Exception as _fp_e:
        logger.debug(f"[{slug}] Float path chains injection failed: {_fp_e}")

    # --- Cross-update activity diff (conversation mode only — not narrative unless asked) ---
    try:
        curr_tasks = current_data.get("tasks", [])
        prev_tasks = previous_data.get("tasks", []) if previous_data else []
        if curr_tasks and prev_tasks:
            # Build task_code sets (fall back to id if no code)
            def _code(t):
                c = str(t.get("task_code") or "").strip()
                return c if c else str(t.get("id") or "").strip()
            curr_codes = {_code(t): t for t in curr_tasks if _code(t)}
            prev_codes = {_code(t): t for t in prev_tasks if _code(t)}
            added   = [c for c in curr_codes if c not in prev_codes]
            removed = [c for c in prev_codes if c not in curr_codes]
            renamed = [
                (c, prev_codes[c]["name"], curr_codes[c]["name"])
                for c in curr_codes
                if c in prev_codes
                and curr_codes[c]["name"].strip() != prev_codes[c]["name"].strip()
            ]
            if added or removed or renamed:
                diff_lines = [
                    f"=== SCHEDULE CHANGES ({current_label.replace('_',' ').title()} vs Previous) "
                    f"(conversation mode only — include in narrative only if user asks) ===",
                ]
                if added:
                    diff_lines.append(f"  ADDED ({len(added)} activities):")
                    for c in added[:20]:
                        diff_lines.append(f"    + {c} {curr_codes[c]['name']}")
                    if len(added) > 20:
                        diff_lines.append(f"    ... +{len(added)-20} more added")
                if removed:
                    diff_lines.append(f"  REMOVED ({len(removed)} activities):")
                    for c in removed[:20]:
                        diff_lines.append(f"    - {c} {prev_codes[c]['name']}")
                    if len(removed) > 20:
                        diff_lines.append(f"    ... +{len(removed)-20} more removed")
                if renamed:
                    diff_lines.append(f"  RENAMED ({len(renamed)} activities):")
                    for c, old_n, new_n in renamed[:15]:
                        diff_lines.append(f"    ~ {c}: '{old_n}' → '{new_n}'")
                    if len(renamed) > 15:
                        diff_lines.append(f"    ... +{len(renamed)-15} more renamed")
                parts.append("")
                parts.append("\n".join(diff_lines))
    except Exception as _diff_e:
        logger.debug(f"[{slug}] Cross-update diff injection failed: {_diff_e}")

    # --- Relationships for activity critical path tracing ---
    try:
        rels = current_data.get("relationships", [])
        if rels:
            # Build a compact predecessor table for the agent
            rel_lines = ["RELATIONSHIPS (for activity critical path tracing):"]
            rel_lines.append("Format: Activity ID → Predecessor ID (relationship type)")
            # Show first 50 relationships (should be enough for CP tracing)
            for r in rels[:50]:
                succ = r.get("successor_id", "")
                pred = r.get("predecessor_id", "")
                rel_type = r.get("type", "FS")
                if succ and pred:
                    rel_lines.append(f"  {succ} → {pred} ({rel_type})")
            if len(rels) > 50:
                rel_lines.append(f"  ... +{len(rels) - 50} more relationships")
            parts.append("")
            parts.append("\n".join(rel_lines))
    except Exception as _rel:
        logger.debug(f"[{slug}] Relationships section failed: {_rel}")

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

    # --- RELATIONSHIPS block — raw predecessor table for agent manual CP tracing and delay sourcing ---
    # Injected as text so the agent can walk any activity's upstream chain when the pre-computed
    # chain is shallow or the user asks about a specific activity not in the chain.
    try:
        curr_rels = current_data.get("relationships", [])
        curr_tasks = current_data.get("tasks", [])
        if curr_rels:
            # Build ID → name lookup for readable output
            id_to_name: dict = {}
            for _t in curr_tasks:
                _tid = str(_t.get("id") or _t.get("task_id") or _t.get("activity_id") or "").strip()
                _tname = (_t.get("name") or _t.get("task_name") or "").strip()
                if _tid and _tname:
                    id_to_name[_tid] = _tname
            rel_lines = []
            for _r in curr_rels[:600]:  # cap at 600 to stay token-efficient
                succ_id = str(_r.get("task_id") or _r.get("succ_task_id") or "").strip()
                pred_id = str(_r.get("predecessor_task_id") or _r.get("pred_task_id") or "").strip()
                rel_type = str(_r.get("type") or _r.get("pred_type") or "FS").strip()
                if succ_id and pred_id:
                    succ_name = id_to_name.get(succ_id, "")
                    pred_name = id_to_name.get(pred_id, "")
                    succ_str = f"{succ_id} \"{succ_name}\"" if succ_name else succ_id
                    pred_str = f"{pred_id} \"{pred_name}\"" if pred_name else pred_id
                    rel_lines.append(f"  {succ_str} → {pred_str} ({rel_type})")
            if rel_lines:
                parts.append("")
                parts.append(
                    f"=== RELATIONSHIPS ({len(rel_lines)} links) ===\n"
                    f"Format: Activity ID \"Name\" → Predecessor ID \"Name\" (type)\n"
                    f"Use this table to trace any activity's upstream chain manually.\n"
                    f"To source a delay: find the slipped activity, look up its predecessor IDs here,\n"
                    f"then look those IDs up in SCHEDULE DATA for their finish dates and float.\n"
                    f"Walk back until you reach the root driver (earliest activity with no predecessors or earliest start)."
                )
                parts.extend(rel_lines)
    except Exception as _rele:
        logger.warning(f"[{slug}] Relationships injection failed: {_rele}")

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


def _compute_spi(current_tasks: list, baseline_tasks: list, data_date_str: str) -> Optional[dict]:
    """
    Compute activity-count SPI proxy.
    For XER: uses task_code to match current vs baseline; baseline_finish <= data_date = planned done.
    For MPP: uses activity name/id match; baseline_finish field.
    Returns dict with planned_count, actual_count, spi, interpretation, is_resource_loaded.
    Returns None if insufficient data.
    """
    if not current_tasks or not baseline_tasks or not data_date_str:
        return None
    try:
        from datetime import datetime as _dt
        # Parse data date
        _data_date = None
        for _fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                _data_date = _dt.strptime(str(data_date_str).strip()[:10], _fmt).date()
                break
            except ValueError:
                pass
        if _data_date is None:
            return None

        # Build baseline finish lookup by task_code (XER) or name (MPP)
        bl_finish: dict = {}  # code/name -> date
        for t in baseline_tasks:
            if t.get("summary", False):
                continue
            task_type = str(t.get("task_type") or "").lower()
            if "loe" in task_type or "wbs" in task_type:
                continue
            # Prefer task_code (XER), fall back to name
            key = str(t.get("task_code") or "").strip()
            if not key:
                key = str(t.get("name") or t.get("task_name") or "").strip().lower()
            if not key:
                continue
            bl_fin_raw = (t.get("baseline_finish") or t.get("finish") or "")[:10]
            if not bl_fin_raw:
                continue
            for _fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                try:
                    bl_finish[key] = _dt.strptime(bl_fin_raw, _fmt).date()
                    break
                except ValueError:
                    pass

        if not bl_finish:
            return None

        # Auto-detect percent scale: XER uses 0.0-1.0, MPP uses 0-100
        # If max pct across non-summary tasks is <= 1.0, treat as fraction scale
        _all_pcts = [
            float(t.get("percent_complete") or 0)
            for t in current_tasks
            if not t.get("summary", False)
        ]
        _pct_scale = 1.0 if (max(_all_pcts) <= 1.0 if _all_pcts else True) else 100.0
        _done_threshold = _pct_scale  # 1.0 for XER, 100.0 for MPP

        # Count planned-complete and actually-complete
        planned_count = 0
        actual_count = 0
        behind_list = []

        for t in current_tasks:
            if t.get("summary", False):
                continue
            task_type = str(t.get("task_type") or "").lower()
            if "loe" in task_type or "wbs" in task_type:
                continue
            key = str(t.get("task_code") or "").strip()
            if not key:
                key = str(t.get("name") or t.get("task_name") or "").strip().lower()
            if not key:
                continue
            bl_fin = bl_finish.get(key)
            if bl_fin is None:
                continue
            if bl_fin <= _data_date:
                planned_count += 1
                pct = float(t.get("percent_complete") or 0)
                if pct >= _done_threshold:
                    actual_count += 1
                else:
                    # Normalize pct to 0-100 for display
                    pct_display = pct * 100 if _pct_scale == 1.0 else pct
                    behind_list.append({
                        "code": str(t.get("task_code") or t.get("id") or ""),
                        "name": str(t.get("name") or ""),
                        "pct": round(pct_display, 1),
                        "bl_finish": str(bl_fin),
                    })

        if planned_count == 0:
            return None

        spi = round(actual_count / planned_count, 3)
        # Note: actual_count was computed with pct_done threshold above — already correct

        if spi >= 1.0:
            interpretation = "On or ahead of schedule"
        elif spi >= 0.90:
            interpretation = "Slightly behind schedule"
        elif spi >= 0.75:
            interpretation = "Moderately behind schedule"
        else:
            interpretation = "Significantly behind schedule"

        # Check if schedule is resource-loaded (any task has cost data)
        is_resource_loaded = any(
            t.get("bcwp") or t.get("bcws") or t.get("acwp") or t.get("baseline_cost")
            for t in current_tasks
        )

        return {
            "spi": spi,
            "planned_count": planned_count,
            "actual_count": actual_count,
            "behind_count": planned_count - actual_count,
            "data_date": str(_data_date),
            "interpretation": interpretation,
            "is_resource_loaded": is_resource_loaded,
            "behind_list": behind_list[:10],  # top 10 for context
        }
    except Exception as _spi_e:
        logger.debug(f"SPI computation failed: {_spi_e}")
        return None


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
    """Return (name_lookup, id_lookup, code_lookup) dicts from a task list.
    code_lookup indexes P6 activity codes (task_code field, e.g. PS-CMIL-1170).
    """
    by_name: dict = {}
    by_id: dict = {}
    by_code: dict = {}  # P6 activity code -> task
    for t in tasks:
        name = (t.get("name") or t.get("task_name") or "").strip().lower()
        tid = str(t.get("id") or t.get("task_id") or t.get("activity_id") or "").strip()
        code = str(t.get("task_code") or "").strip()
        if name:
            by_name[name] = t
        if tid:
            by_id[tid] = t
        if code:
            by_code[code] = t
    return by_name, by_id, by_code


def _is_p6_activity_code(s: str) -> bool:
    """Return True if s looks like a P6 activity code (letters-numbers-letters pattern).
    Examples: PS-CMIL-1170, EL-INST-1000, IB-L1IN-1100
    """
    import re
    return bool(re.match(r'^[A-Z]{1,4}-[A-Z0-9]{2,8}-\d{3,6}$', s.strip()))


def _resolve_task(act_name: str, act_id: str, by_name: dict, by_id: dict, by_code: dict = None):
    """Find a task by P6 activity code, numeric ID, or name (in that priority order)."""
    # 1. P6 activity code match (highest priority for XER files)
    if by_code and act_id and _is_p6_activity_code(act_id):
        t = by_code.get(act_id)
        if t:
            return t
    # 2. Numeric ID match
    if act_id:
        t = by_id.get(act_id)
        if t:
            return t
    # 3. Name match (fallback)
    return by_name.get(act_name.lower()) or None


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
        logger.warning(f"[{slug}] milestone_map.json not found — STANDARDIZED MILESTONES block will be empty. "
                       f"Run the milestone map builder or upload a Milestone Map.xlsx to populate it.")
        return ""
    try:
        data = read_encrypted_json(mm_path)
        milestones = data.get("milestones", [])
        if not milestones:
            return ""

        # Build lookups for all three schedule versions (name, numeric id, P6 activity code)
        curr_by_name, curr_by_id, curr_by_code = _build_task_lookup(_project_tasks.get(slug, []))
        prev_by_name, prev_by_id, prev_by_code = _build_task_lookup(_project_tasks_previous.get(slug, []))
        base_by_name, base_by_id, base_by_code = _build_task_lookup(_project_tasks_baseline.get(slug, []))

        lines = [
            "STANDARDIZED MILESTONES (dates cross-referenced across schedule versions — VERIFIED = 2+ sources agree):"
        ]
        # Collect entries as (sort_date, is_contract_completion, line_text) for date-based ordering
        _milestone_entries = []  # list of (datetime_or_None, is_contract_completion: bool, line: str)
        for m in sorted(milestones, key=lambda x: x.get("sort", 99)):
            std = m["standardized_name"]
            act_name = (m.get("activity_name") or "").strip()
            act_id = str(m.get("activity_id") or "")

            curr_task = _resolve_task(act_name, act_id, curr_by_name, curr_by_id, curr_by_code)
            prev_task = _resolve_task(act_name, act_id, prev_by_name, prev_by_id, prev_by_code)
            base_task = _resolve_task(act_name, act_id, base_by_name, base_by_id, base_by_code)

            # Helper: parse a date string in either YYYY-MM-DD or MM/DD/YY or MM/DD/YYYY
            def _parse_date_flex(s):
                from datetime import datetime as _dt2
                if not s:
                    return None
                s = str(s).strip()[:10]
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                    try:
                        return _dt2.strptime(s, fmt)
                    except ValueError:
                        continue
                return None

            # Helper: normalise a date to YYYY-MM-DD string
            def _norm_date(s):
                d = _parse_date_flex(s)
                return d.strftime("%Y-%m-%d") if d else ""

            if curr_task:
                # --- Forecast (current) ---
                # milestone_map current_date is the AUTHORITATIVE override when populated
                # (set from human-verified variance PDF).  Fall back to parsed schedule only
                # when current_date is absent.
                stored_current = m.get("current_date", "")
                if stored_current:
                    curr_finish = _norm_date(stored_current)
                else:
                    curr_finish = _extract_finish(curr_task)

                pct = curr_task.get("percent_complete", 0)

                # Baseline finish — prefer embedded field, fall back to baseline task
                baseline_finish = (curr_task.get("baseline_finish") or
                                   curr_task.get("bl_finish") or
                                   _extract_finish(base_task) or "")
                if baseline_finish:
                    baseline_finish = _norm_date(baseline_finish) or str(baseline_finish)[:10]

                # Previous forecast — prefer stored prior_update_date in milestone_map.json
                # (written by update_milestone_prior_dates helper), fall back to parsed prev task
                stored_prior = m.get("prior_update_date", "")
                if stored_prior:
                    prev_finish = _norm_date(stored_prior) or str(stored_prior)[:10]
                else:
                    prev_finish = _extract_finish(prev_task)

                # --- 2-source confidence check ---
                sources_agree = 0
                if curr_finish:
                    sources_agree += 1  # current is always source 1
                if stored_current or (prev_task and prev_finish):
                    sources_agree += 1  # milestone_map verified date or previous update
                elif base_task and baseline_finish:
                    sources_agree += 1  # baseline is source 2

                confidence = "[VERIFIED — 2 sources]" if sources_agree >= 2 else "[1 source]"

                date_str = f"Forecast: {curr_finish}" if curr_finish else "Forecast: N/A"
                bl_str = f" | Baseline: {baseline_finish}" if baseline_finish else ""
                prev_str = f" | Prior Update: {prev_finish}" if prev_finish else ""
                pct_str = f" | {pct:.0f}% complete" if pct is not None else ""

                # Pre-compute update-to-update variance (calendar days)
                var_str = ""
                if curr_finish and prev_finish:
                    try:
                        d1 = _parse_date_flex(curr_finish)
                        d2 = _parse_date_flex(prev_finish)
                        if d1 and d2:
                            delta = (d1 - d2).days
                            sign = "+" if delta >= 0 else ""
                            var_str = f" | Variance: {sign}{delta}cd"
                    except Exception:
                        pass

                # Pre-compute baseline drift (calendar days)
                drift_str = ""
                if curr_finish and baseline_finish:
                    try:
                        d1 = _parse_date_flex(curr_finish)
                        d2 = _parse_date_flex(baseline_finish)
                        if d1 and d2:
                            drift = (d1 - d2).days
                            sign = "+" if drift >= 0 else ""
                            drift_str = f" | Drift: {sign}{drift}cd vs BL"
                    except Exception:
                        pass

                _is_cc = "contract completion" in std.lower() or "substantial completion" in std.lower()
                _sort_dt = _parse_date_flex(curr_finish) if curr_finish else None
                _milestone_entries.append((_sort_dt, _is_cc, f"  - {std}: {date_str}{bl_str}{prev_str}{var_str}{drift_str}{pct_str}  {confidence}"))
            else:
                # No current task match — use stored current_date from milestone_map if available
                stored_current = m.get("current_date", "")
                stored_prior = m.get("prior_update_date", "")
                if stored_current:
                    curr_finish = _norm_date(stored_current)
                    prev_finish = _norm_date(stored_prior) if stored_prior else ""
                    var_str = ""
                    if curr_finish and prev_finish:
                        try:
                            d1 = _parse_date_flex(curr_finish)
                            d2 = _parse_date_flex(prev_finish)
                            if d1 and d2:
                                delta = (d1 - d2).days
                                sign = "+" if delta >= 0 else ""
                                var_str = f" | Variance: {sign}{delta}cd"
                        except Exception:
                            pass
                    prev_str = f" | Prior Update: {prev_finish}" if prev_finish else ""
                    _is_cc = "contract completion" in std.lower() or "substantial completion" in std.lower()
                    _sort_dt = _parse_date_flex(curr_finish) if curr_finish else None
                    _milestone_entries.append((_sort_dt, _is_cc, f"  - {std}: Forecast: {curr_finish}{prev_str}{var_str}  [VERIFIED — milestone map]"))
                elif act_name and act_name != std:
                    _is_cc = "contract completion" in std.lower() or "substantial completion" in std.lower()
                    _milestone_entries.append((None, _is_cc, f"  - {std}  (activity: '{act_name}' — date not resolved)"))
                else:
                    _is_cc = "contract completion" in std.lower() or "substantial completion" in std.lower()
                    _milestone_entries.append((None, _is_cc, f"  - {std}  (date not resolved)"))

        # Sort: non-CC milestones by finish date ascending (None dates go last within non-CC),
        # Contract Completion always pinned as the final entry.
        from datetime import datetime as _dt_sort
        _non_cc = [(dt, line) for dt, is_cc, line in _milestone_entries if not is_cc]
        _cc     = [(dt, line) for dt, is_cc, line in _milestone_entries if is_cc]
        _non_cc_sorted = sorted(_non_cc, key=lambda x: x[0] if x[0] else _dt_sort(9999, 1, 1))
        _cc_sorted     = sorted(_cc,     key=lambda x: x[0] if x[0] else _dt_sort(9999, 1, 1))
        for _, line in _non_cc_sorted:
            lines.append(line)
        for _, line in _cc_sorted:
            lines.append(line)

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[{slug}] Could not load milestone map: {e}")
        return ""


def _background_load_schedule(slug: str, project_path: str):
    """Background thread worker to load schedule data."""
    global _loading_in_progress, _loading_start_times
    try:
        _load_schedule_data(slug, project_path)
    finally:
        _loading_in_progress.discard(slug)
        _loading_start_times.pop(slug, None)  # Clear start time when done


def ensure_project_loaded(slug: str) -> bool:
    """On-demand loading: parse schedule data if not already loaded.
    Returns True if data is ready, False if loading started in background.
    Non-blocking: always returns immediately.
    """
    global _loading_in_progress, _loading_start_times

    # Already loaded?
    if slug in _project_cache and _project_cache[slug]:
        return True

    # Currently loading in background?
    if slug in _loading_in_progress:
        return False

    # Need metadata first (fast, do synchronously)
    if slug not in _project_meta:
        project_path = os.path.join(PROJECTS_DIR, slug)
        if not os.path.exists(project_path):
            return False
        _load_metadata_only(slug, project_path)
        if slug not in _project_meta:
            return False

    # Start schedule loading in background thread
    project_path = os.path.join(PROJECTS_DIR, slug)
    _loading_in_progress.add(slug)
    _loading_start_times[slug] = time.time()  # Record start time for ETA
    t = threading.Thread(target=_background_load_schedule, args=(slug, project_path), daemon=True)
    t.start()
    logger.info(f"[{slug}] Schedule loading started in background thread")
    return False


def get_project_load_status(slug: str) -> dict:
    """Get loading status and estimated time remaining for a project.
    Returns dict with: loaded (bool), loading (bool), elapsed_seconds (float), 
    estimated_remaining_seconds (int), message (str)
    """
    global _loading_in_progress, _loading_start_times, _project_cache
    
    # Typical load times based on file size/complexity (seconds)
    TYPICAL_LOAD_TIME = 45  # Most MPP files load in 30-60s
    
    is_loaded = slug in _project_cache and _project_cache[slug]
    is_loading = slug in _loading_in_progress
    
    if is_loaded:
        return {
            "loaded": True,
            "loading": False,
            "elapsed_seconds": 0,
            "estimated_remaining_seconds": 0,
            "message": "Ready"
        }
    
    if is_loading:
        start_time = _loading_start_times.get(slug, time.time())
        elapsed = time.time() - start_time
        remaining = max(5, int(TYPICAL_LOAD_TIME - elapsed))
        return {
            "loaded": False,
            "loading": True,
            "elapsed_seconds": round(elapsed, 1),
            "estimated_remaining_seconds": remaining,
            "message": f"Loading... approximately {remaining}s remaining"
        }
    
    # Not loaded and not loading - either no schedule or not triggered
    return {
        "loaded": False,
        "loading": False,
        "elapsed_seconds": 0,
        "estimated_remaining_seconds": 0,
        "message": "Not loaded"
    }


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
        # Schedule not loaded yet (background parsing in progress or no data)
        parts.append("")
        is_loading = slug in _loading_in_progress
        if is_loading:
            parts.append("[Schedule data is loading in the background (started ~30 seconds ago). Please wait 20-30 seconds and ask again.]")
        else:
            parts.append("[No schedule data available for this project. User can upload an MPP/XER file to provide schedule data.]")

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


def get_project_relationships(slug: str) -> List[dict]:
    """Returns relationship list for a slug: [{successor_id, predecessor_id, type, lag}, ...]."""
    return _project_relationships.get(slug, [])

def update_milestone_prior_dates(slug: str) -> int:
    """
    Rolls the current forecast dates into prior_update_date for each milestone
    in milestone_map.json. Call this BEFORE loading a new update file so that
    the previous forecast is preserved as the prior update date.

    Returns the number of milestones updated.

    Usage:
        from project_loader import update_milestone_prior_dates
        update_milestone_prior_dates('frisco_tx')  # call before loading UP07
    """
    mm_path = os.path.join(PROJECTS_DIR, slug, "milestone_map.json")
    if not os.path.exists(mm_path):
        logger.warning(f"[{slug}] milestone_map.json not found — cannot update prior dates")
        return 0
    try:
        data = read_encrypted_json(mm_path)
        milestones = data.get("milestones", [])
        if not milestones:
            return 0

        # Build current task lookup from in-memory parsed tasks
        curr_by_name, curr_by_id = _build_task_lookup(_project_tasks.get(slug, []))

        updated = 0
        for m in milestones:
            act_name = (m.get("activity_name") or "").strip()
            act_id = str(m.get("activity_id") or "")
            curr_task = _resolve_task(act_name, act_id, curr_by_name, curr_by_id)
            if curr_task:
                curr_finish = _extract_finish(curr_task)
                if curr_finish:
                    m["prior_update_date"] = curr_finish
                    updated += 1

        write_encrypted_json(mm_path, data)
        logger.info(f"[{slug}] Updated prior_update_date for {updated} milestones")
        return updated
    except Exception as e:
        logger.warning(f"[{slug}] update_milestone_prior_dates failed: {e}")
        return 0


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
        write_encrypted_json(out, payload)
        count = len(data["milestones"])
        print(f"  OK  {slug}: {count} milestones")
        written += 1

    print(f"\nDone. {written} milestone_map.json files written.")
