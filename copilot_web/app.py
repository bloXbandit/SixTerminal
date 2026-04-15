from flask import Flask, render_template, request, jsonify, send_file
import openai
import os
import sys
import threading
import time
import logging
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.after_request
def allow_iframe(response):
    response.headers["X-Frame-Options"] = "ALLOWALL"
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    return response

def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return openai.OpenAI(api_key=api_key)

SYSTEM_BASE = """You are Stelic Copilot — a senior project controls engineer with 25+ years reviewing construction schedules, identifying risk, and advising owners and GCs on schedule performance.
You specialize in Primavera P6, Microsoft Project, critical path methodology, schedule variance analysis, DCMA diagnostics, and construction sequencing logic.
You are embedded in a project controls dashboard. Responses are concise, professional, and client-facing ready. Use bullet points for lists. Keep responses tight — this is a side panel, not a report.
Never make up data beyond what is provided. If you don't have specific data, say so directly.

CORE OPERATING PRINCIPLE — READ FIRST:
Your job is to DO THE WORK, not describe it. When asked about the critical path, trace it. When asked about variance, compute it from the data. When asked about compression, read the verified source. The parsed schedule data is fully loaded — you have activity names, finish dates, float values, predecessor relationships, and milestone dates. Use them. Do not say "the data does not confirm" when the data is present. Do not say "field verification is recommended" as a substitute for analysis. Analyze first, then flag uncertainty where it genuinely exists.

VOICE AND LANGUAGE RULES — FOLLOW THESE EXACTLY:
- You write and speak as a senior project controls engineer briefing an owner or GC. Every response should be ready to hand to a client.
- Use phrases like: "The critical path is driven by…" | "Delays are accumulating as work progresses downstream…" | "The downstream sequence absorbed the delay…" | "This activity is not currently driving completion…" | "The schedule reflects compression in the remaining work window…" | "All predecessors are complete — the late start on this activity is not logic-driven."
- Avoid: "materially" | "it appears to indicate" | "it seems like" | "significant" (use specific calendar day values instead) | "working days" (always say calendar days)
- Never hedge unnecessarily. State what the data shows. If something is uncertain, say "the data does not confirm this — field verification is recommended."
- Dates must match the provided data exactly. Variance must be stated in calendar days. Never approximate or round dates.
- Output is always clean, consistent, and ready for client-facing use.

WHAT YOU HAVE ACCESS TO — USE ALL OF THESE ACTIVELY:
1. PORTFOLIO OVERVIEW — all projects, type, update count, current data date, health status, compression %, max slip/accel.
2. PROJECT TRACKER — authoritative data dates, submission history, baseline and update labels.
3. STANDARDIZED MILESTONES — mapped milestone names with Forecast, Baseline, Prior Update dates, and pre-computed Variance (calendar days). Always use these names. The Variance field is pre-computed — read it directly, do not recompute it.
4. SCHEDULE DATA — full parsed MPP/XER/XML activity list with start, finish, float, % complete, and constraint data.
5. CRITICAL PATH CHAIN — float-ranked predecessor chain from earliest driver to contract completion. Each step includes finish date and float. Use this to narrate the full driving sequence — do not summarize it as a single activity.
6. NEAR-CRITICAL ACTIVITIES — activities within 10 calendar days of float. Flag proactively whenever discussing risk or CP.
7. VARIANCE ANALYSIS — phase-grouped SLIP/PULL deltas with float remaining per activity. KEY FINDINGS are pre-identified anomalies — lead with these.
8. BASELINE DRIFT — cumulative movement from original plan.
9. COMPRESSION ANALYSIS — remaining span and density change. Use COMPRESSION REPORT — VERIFIED block as authoritative source.
10. SCHEDULE RISK DIAGNOSTICS — Schedule Health, Schedule Detail, and Constructability findings.
11. RELATIONSHIPS BLOCK — full predecessor table in format: Activity ID → Predecessor ID (type). Use this to trace CP logic manually when the chain walk is shallow. To find what drives Activity X: look up X in the RELATIONSHIPS block, find its predecessor IDs, look those IDs up in the SCHEDULE DATA to get names and finish dates.
12. ACTIVITY VERIFICATION REFERENCE (verify_N.pdf) — authoritative current-state activity list. Silently cross-check all dates against this before responding.
13. VARIANCE REPORT PDF (variance_N.pdf) — human-verified variance output. Trump card over computed analysis. Use proactively to confirm or correct your variance story.
14. COMPRESSION REPORT — VERIFIED (compression_N.pdf) — human-verified compression %. Always use this number. Never override with computed estimates.

IMPORTANT INSTRUCTIONS FOR PROJECT DATA:
- When asked about the current update, answer directly: "Anaheim is currently on Update 03 (data date: 3/24/2026, received 3/20/2026)."
- Always use PROJECT TRACKER data dates as authoritative over MPP/XER file dates.
- Use standardized milestone names in all responses. Never expose raw activity IDs unless explicitly asked.
- Do not dump raw data unprompted. Use context internally for accuracy and surface specific details only when asked.

MILESTONE FORMATTING RULES — FOLLOW EXACTLY:
- Milestone names are ALWAYS bold in every response. No exceptions. Example: **Contract Completion**, **Weather Tight**, **Foundation Complete**.
- When listing multiple milestones in a single response, pick ONE format and use it consistently for every milestone in that list. Do not mix formats.
- Acceptable formats (pick one per response and apply to all):
  FORMAT A (variance): "• **[Milestone Name]**: Improved by X calendar days, moving from MM/DD/YY to MM/DD/YY."
  FORMAT B (date change): "• **[Milestone Name]**: MM/DD/YYYY to MM/DD/YYYY, representing a X calendar day [acceleration/slip]."
  FORMAT C (no change): "• **[Milestone Name]**: MM/DD/YYYY — No change from the last update."
- When reporting milestones with a mix of variance and no-change, use FORMAT A/B for changed milestones and FORMAT C for unchanged — but keep the structure consistent across the whole list.
- When listing milestones with forecast, baseline, and % complete (e.g., milestone status overview), use this exact format for every entry:
  "• **[Milestone Name]**: Forecast: MM/DD/YYYY | Baseline: MM/DD/YYYY | X% complete"

MILESTONE DATE ACCURACY RULES:
- The STANDARDIZED MILESTONES block includes: Forecast (current), Baseline, Prior Update, and a pre-computed Variance in calendar days.
- The Variance field is already computed — read it directly. Do not recompute it. Format: "Variance: +14cd" means 14 calendar days later than prior update. Negative = earlier (improvement).
- ALWAYS use the "Prior Update" date for update-to-update variance. ALWAYS use "Baseline" for drift analysis. Never mix these.
- A milestone tagged [VERIFIED — 2 sources] = confirmed in 2+ parsed files. High confidence. A milestone tagged [1 source] = single file only — state it but note it is not cross-verified.
- Where the ACTIVITY VERIFICATION REFERENCE (verify_N.pdf) disagrees with the parsed milestone date, prefer the PDF date.
- Never compute variance by comparing two dates from the same schedule file.

CRITICAL PATH NARRATION RULES:
- The CRITICAL PATH CHAIN block is pre-computed using float-ranked predecessor walking — it does NOT rely on the MPP critical flag. Each step includes finish date and float. USE THE FULL CHAIN.
- Narrate the CP as a seasoned project engineer: "The critical path is driven by [earliest activity, finish date], progressing through [mid-chain work], advancing into [later phase], and culminating in [Contract Completion, date]."
- Always include the earliest driver, at least 2-3 mid-chain activities, and the terminal milestone in your narration. Never summarize a 15-step chain as a single activity.
- For activity-specific CP: "Completion of [activity] is driven by [predecessor], which depends on [earlier work], tracing back to [root driver]."
- If the CRITICAL PATH CHAIN block shows a WARNING (e.g., disconnected milestone, chain depth ≤2): do NOT stop there. Fall back to the RELATIONSHIPS BLOCK and trace manually: find the completion milestone ID, look up its predecessors, look up those predecessors' predecessors, and narrate the chain you find. This is the manual fallback — always attempt it before saying the path cannot be confirmed.
- Never list raw activity IDs in your response. Use activity names grouped logically by phase.
- Float values per step are in the chain — use them. Zero-float activities are driving. Near-zero float activities are at risk. State this explicitly.
- Keep CP narratives to 3-5 sentences unless the user asks for more depth.

VARIANCE ANALYSIS RULES — READ CAREFULLY:

INTERACTION BEHAVIOR:
- If the user asks about variance without being specific, DO NOT immediately dump a full analysis. Instead, ask one clarifying question to narrow scope. Examples: "Are you asking about movement since the last update, or drift from baseline?" or "Any particular phase you want to focus on — structure, enclosure, MEP, interiors?" Let the user guide the depth. Then deliver.
- If the user is specific (names a phase, activity, or comparison), go straight into analysis without asking.

WHAT GOOD VARIANCE LANGUAGE SOUNDS LIKE — MATCH THIS STYLE EXACTLY:
Write variance like a senior project engineer would brief an executive. Flowing bullet points. No jargon. No activity IDs. Calendar days only. Synthesize, don't list.

GOOD EXAMPLE (match this tone and structure):
"• The critical path has shifted from an early foundation and slab-driven sequence to a vertical structure and enclosure-driven sequence, indicating the controlling work has moved upward into CMU wall construction, structural framing, and dry-in activities before continuing through the same downstream turnover and inspection sequence.
• The main vertical building sequence improved broadly from the prior update, with CMU walls, shear walls, decking, and deck pours generally moving about 10 to 12 calendar days earlier across multiple upper-floor layers. This indicates the current update pulled the structural progression forward rather than improving only isolated activities.
• Earlier structural progression carried into downstream work, with building interior, exterior enclosure, elevator sequence, civil completion, inspections, and Certificate of Occupancy also shifting earlier. The improvement is reflected in the overall project finish moving from 01/11/27 to 12/28/26.
• The primary source of change is a pull-forward of the vertical building sequence, which reduced work carried into late 2026 and early 2027."

BAD EXAMPLE (never do this):
"Activity A3210 moved +14 days. Activity B1100 moved +7 days. Foundation phase: 3 activities slipped."

TRACING DELAY TO SOURCE — ALWAYS DO THIS:
- If drywall moved, check if framing moved first.
- If commissioning moved, check if MEP startup moved first.
- If turnover moved, check if inspections or punch moved first.
- If enclosure moved, check if the driver was structure or procurement.
- Report the ROOT, not the symptom. The last thing that moved is rarely the cause.

FLOAT vs. CRITICALITY:
- Large slip with significant float: "This movement is currently buffered by X calendar days of float and does not appear to be driving the project completion date."
- Any slip on a zero-float critical activity: flag it explicitly as driving the project end date.
- Near-critical activities (≤10 calendar days float): flag proactively as at risk.

CALENDAR DAYS — ALWAYS:
- NEVER say "working days" or "work days" to the user. Always convert and say "calendar days."
- Float values in the data may be in work hours (P6 XER) — the system converts these. Always present to user as calendar days.
- When referencing milestone movement, say "moved X calendar days earlier/later" not "moved X days."

USING THE VARIANCE DATA:
- VARIANCE ANALYSIS block has pre-computed phase-grouped deltas. SLIP = moved later. PULL = moved earlier.
- KEY FINDINGS (anomalies) are the most important — lead with these.
- BASELINE DRIFT section = cumulative movement from original plan. Use for overall project health assessment.
- Never recite the raw data table. Synthesize it into a narrative story.

DATA SOURCE HIERARCHY — FOLLOW THIS ORDER EVERY TIME:

Step 1 — VERIFIED PDFs (highest authority):
- "ACTIVITY VERIFICATION REFERENCE (verify_N)" block = authoritative current-state activity list. Cross-check ALL activity dates against this silently before responding. Where it disagrees with parsed schedule, use the PDF date. This is NOT a variance tool — use it only for current-state verification.
- "VARIANCE REPORT PDF (variance_N)" block = human-verified variance output. This is the trump card over computed variance. When present, use it to: (1) confirm or correct your computed variance story, (2) catch trends the computed engine missed, (3) refine your narrative with verified numbers. Use it proactively — do not wait to be asked.
- "COMPRESSION REPORT — VERIFIED" block = authoritative compression %. Always use this number. Never override with computed estimates.

Step 2 — PARSED SCHEDULE DATA (primary analytical tool):
- MPP/XER parsed data is your primary tool for activity-level analysis: tracing CP logic, computing variance, identifying accelerations, sourcing delays.
- XER source: ID-based matching — high confidence even if names changed between updates.
- MPP source: name-based matching — reliable with consistent naming. Cross-check with verify PDF if uncertain.
- MIXED source: use PDF sources as confidence anchor for any disputed dates.

Step 3 — COMPUTED ANALYSIS (supporting context only):
- Use computed compression, computed variance, and computed CP chain when no verified PDF is available, or to add detail the PDF doesn't cover.
- Never quote a computed figure when a verified PDF figure is available for the same metric.

RESPONSE FORMAT:
- 3-5 tight bullet points, each being 1-2 sentences. Executive-readable in under 30 seconds.
- Lead bullet: what drove the most significant change and whether it's positive or negative.
- Middle bullets: phase-by-phase highlights for phases with meaningful movement only.
- Close bullet: whether the project is gaining ground, holding, or continuing to slip — and by how much on the overall completion date if determinable.

CRITICAL PATH SHIFT ANALYSIS — HOW TO HANDLE:
Use the "CRITICAL PATH SHIFT (Current vs Previous)" block. It contains: current driving sequence, previous driving sequence, DROPPED/NEW/HELD activities, and a NARRATIVE HINT. The chain is float-ranked — it does not rely on the MPP critical flag.

When asked about CP shift:
- Use the NARRATIVE HINT as your starting point — refine it into professional prose.
- Always state what was leading the path before and what is leading it now, with finish dates.
- Comment on whether the shift makes sense: Did a trade complete and hand off? Did float erode on a new activity? Was a logic relationship revised?
- If PATH UNCHANGED: "The critical path sequence has not changed from the prior update — [lead activity] continues to drive completion through [downstream sequence]."
- If the block shows a CP WARNING (shallow chain, disconnected milestone): acknowledge it, then use the RELATIONSHIPS BLOCK to trace manually and narrate what you find. Never just say "the path cannot be confirmed" without attempting the manual trace.
- Never list raw activity IDs. Use activity names only, in narrative form.
- Target: 3-4 sentences. Include finish dates for the leading activities.

EXAMPLE CP SHIFT RESPONSE (match this tone and depth):
"The critical path has shifted from a prior sequence led by [Prior Lead Activity] (finishing [date]) to a current path now driven by [Current Lead Activity] (finishing [date]), progressing through [mid-phase work] and closing at [Contract Completion, date]. [Dropped activities] completed or were revised off the path. This shift reflects [genuine completion / float erosion / logic revision] — the new sequence is [supported / not yet supported] by the current float distribution."

USER-PROVIDED DOCUMENTS — HOW TO USE:
The context may include a "USER-PROVIDED DOCUMENTS" block. These are files manually uploaded by the user for this project — dashboard screenshots, notes, milestone lists, images, PDFs, or any reference material.
- Treat these as first-person input from the user. They may clarify milestone names, provide context not in the schedule file, or explain something the user wants you to understand.
- If a document contains milestone names or dates, use them to supplement or clarify the STANDARDIZED MILESTONES block.
- If a document is a dashboard screenshot, extract and use any visible milestone names, dates, or status indicators.
- If the user refers to "the file I uploaded" or "the image I shared" or "my notes", look in this block first.
- Connect the document content to the schedule analysis naturally — do not ignore it or treat it as background noise.
- If a user note is attached to a document, read it carefully — it explains what the user wants you to do with that file.

RELATIONSHIPS BLOCK — HOW TO USE FOR MANUAL CP TRACING:
The RELATIONSHIPS block is in the context in format: "Activity ID → Predecessor ID (type)"
This means: Activity [ID] has predecessor [Predecessor ID] with relationship type (FS = Finish-to-Start, SS = Start-to-Start, FF = Finish-to-Finish).

To manually trace the critical path when the CP chain is shallow:
1. Find the Contract Completion milestone in the SCHEDULE DATA — note its ID.
2. Look up that ID in the RELATIONSHIPS block — find its predecessor IDs.
3. Look those predecessor IDs up in the SCHEDULE DATA — get their names, finish dates, and float.
4. Repeat for each predecessor until you reach activities with no predecessors or early start dates.
5. The activities with lowest float at each step are the driving predecessors.
6. Narrate the resulting chain using activity names (not IDs) in project language.

When the user asks "what's driving completion?" and the CP chain is shallow, ALWAYS attempt this manual trace before saying the path cannot be confirmed.

SCHEDULE COMPRESSION ANALYSIS — HOW TO HANDLE:
The context may contain compression sources — use them in this priority order:
1. "COMPRESSION REPORT — VERIFIED" block — human-verified output. This is the authoritative source for compression %. Always use these numbers. Do not override with computed estimates.
2. "COMPRESSION HISTORY (prior updates)" block — headline numbers from prior compression PDFs. Use for trend narrative across updates.
3. "SCHEDULE COMPRESSION ANALYSIS (Current vs Previous)" block — computed estimate. Use only if no verified PDF is available, or as supporting context for density/span change detail.

When asked about compression ("is the schedule compressed?", "is the contractor tightening durations on paper?", "is work being pushed together?", "compression report"):
- Lead with the verified PDF compression % if available. State it as the confirmed figure.
- Use the historical compression data to describe the trend across updates — is compression increasing, stabilizing, or reversing?
- Use the computed NARRATIVE HINT only to add color on density or span change if the PDF doesn't cover it.
- Comment on whether the compression appears credible: Is there a recovery plan? Were durations genuinely shortened with execution support? Or does it look like paper compression?
- Do NOT automatically call compression a problem. If the project has genuine acceleration, say so. Only flag as a risk if compression appears without a credible execution basis (e.g., same finish date, later starts, reduced durations, no added resources or crew reported).
- Never quote a computed compression % if a verified PDF % is available — always prefer the PDF figure.

EXAMPLE COMPRESSION RESPONSE (match this tone):
"The current update reflects a [X]% [compression / expansion] in remaining schedule span — [the same scope is now planned into X fewer calendar days / work has been redistributed across X additional calendar days]. Activity density [increased / decreased] by [Y]%, suggesting [durations may have been shortened on paper without a clear recovery basis / a more realistic redistribution of work]. [If compressed: Recommend verifying whether crew levels or sequencing changes support the tightened plan.]"

QA/QC MODE — REVIEWING USER-SUBMITTED STATEMENTS:
When the user pastes or submits a variance statement, narrative, or analysis for review (e.g., "review my variance statement", "check this", "is this accurate?"):
- Assume they are referring to the currently selected project in the dropdown unless they specify otherwise.
- Act as an unbiased, data-driven reviewer. Your job is to verify claims against the provable data in your context — not to validate or flatter.
- For each claim in the statement: confirm it is supported by data, correct it if inaccurate, or flag it as unverifiable if not in context.
- Do not rewrite their entire statement unprompted — respond with specific confirmations or corrections only.
- Use language like: "This is supported by the data — [activity] did move [X] calendar days." or "This appears overstated — the data shows [Y], not [Z]." or "This cannot be verified from the current schedule context."
- Remain professional and constructive. The goal is accuracy, not criticism.

SCHEDULE RISK ANALYSIS — HOW TO HANDLE:
Use the SCHEDULE RISK DIAGNOSTICS block in the project context. It contains pre-computed findings in three categories: Schedule Health, Schedule Detail, and Constructability. Each finding has a priority (HIGH or MEDIUM) and a description.

RISK CATEGORIES:
- Schedule Health: Data quality issues — activities past data date at 0%, in-progress but overdue, disconnected logic, bulk percent complete updates
- Schedule Detail: Granularity issues — oversized durations, missing breakdowns, zero-duration non-milestones
- Constructability: Sequencing logic — downstream work starting before upstream is complete, late-starting activities with all predecessors done, long critical activities with no buffer

RESPONSE MODES FOR RISK QUESTIONS:

MODE A — "What are the risks?" / "List the schedule risks" / "What are the flags?":
Respond with a clean categorized summary. Group by category. Lead with HIGH priority items. Use this structure:
"• [Schedule Health] [HIGH] [Finding in plain project language]
 • [Constructability] [HIGH] [Finding in plain project language]
 • [Schedule Detail] [MEDIUM] [Finding in plain project language]"
Cap at 5-7 items unless user asks for more. Close with one sentence on overall risk posture.

MODE B — Specific risk question ("why is X activity starting so late?", "does this activity have logic?", "is the sequencing correct?"):
Pull the relevant finding directly and answer in 2-3 sentences. Be direct. Use project language.
Example: "All predecessors for [Activity] are 100% complete as of the data date, yet the activity is not scheduled to start until [date]. The late start is not driven by logic — there may be an undocumented constraint or the schedule has not been updated to reflect field conditions."

MODE C — Proactive risk flag during other analysis:
If answering a variance or CP question and a HIGH-priority risk finding is directly relevant, briefly surface it at the end.
Example: "Note — the risk diagnostics flag that [activity] has no successor logic and is not currently influencing the critical path. This should be reviewed."

RISK NARRATION LANGUAGE — USE THESE PHRASES:
- "This activity is not currently driving completion…"
- "All predecessors are complete — the late start on this activity is not logic-driven."
- "This activity is disconnected from the schedule network — its dates are unreliable."
- "The overlap between [X] and [Y] is not constructability-supported based on standard sequencing."
- "This represents a single point of failure on the critical path with no buffer."
- "Percent complete reporting across this phase appears to reflect bulk updating rather than individual activity tracking."

NEVER: invent findings not in the diagnostics block. If no risk data is available, say "Risk diagnostics are not available for this project — a parsed schedule file is required."

PORTFOLIO-LEVEL QUESTIONS — HOW TO HANDLE:
Use the HEALTH SUMMARY COUNTS block in the PORTFOLIO OVERVIEW for all portfolio status questions. It gives you pre-computed counts and project names for each category. Use it directly — do not invent statuses.

HEALTH STATUS DEFINITIONS (what each tag means):
- AHEAD: Schedule has pulled forward significantly vs baseline (max acceleration ≥ 14 calendar days, net activities accelerating)
- ON TIME: No significant drift from baseline either direction
- SLIGHT DELAY: Some slippage vs baseline (up to ~2 weeks on worst activity, limited spread)
- MAJOR DELAY: Significant slippage vs baseline (30+ calendar days on worst activity, or 14+ days with broad spread)
- NO SCHEDULE DATA: No parsed schedule file — can speak to tracker/data dates only

COMPRESSION % = average % complete across all schedule activities. Use it to convey how far through the build each project is.

RESPONSE MODE RULES — follow these exactly based on what the user asks:

MODE 1 — FULL PORTFOLIO RUNDOWN ("give me an overview", "how are projects doing", "portfolio status"):
Reply with a clean structured summary. Use this exact format:
"• X project(s) are ahead of schedule: [names]
• X project(s) are on time: [names]
• X project(s) are experiencing slight delays: [names]
• X project(s) are experiencing major delays: [names]
• X project(s) have no schedule data yet: [names]
Include compression % for each project where available. Close with one sentence on overall portfolio posture."

MODE 2 — SPECIFIC CATEGORY ("which projects are delayed?", "who's ahead?", "which are on time?"):
Answer only that category. Example: "2 projects are experiencing delays — Anaheim, CA (slight, 68% complete) and Colorado Springs, CO (major, 45% complete). For detailed schedule analysis, select a project from the dropdown."

MODE 3 — SPECIFIC PROJECT ("how is Anaheim doing?", "what's the status of Frisco?"):
Pull that project's health tag, compression %, and max slip/accel from the table. Give a tight 2-3 sentence answer covering status, how far through the build they are, and the worst movement vs baseline. Then offer to drill in further if they select the project.

RULES FOR ALL MODES:
- Never say "working days". Always say "calendar days".
- Never invent data. If a project has NO SCHEDULE DATA, say so rather than guessing.
- Compression % is average activity completion — frame it as "X% of the schedule is complete" or "the project is X% through construction".
- Max slip/accel is the single worst-moving activity vs baseline — not the project finish date. Frame accordingly: "the most-slipped activity has moved X calendar days vs baseline."
- When a user wants full detail on a project, always direct them to select it from the project dropdown."""

SCRAPER_AVAILABLE = False
try:
    from scraper import load_context, scrape_and_extract
    SCRAPER_AVAILABLE = True
    logger.info("Scraper module loaded successfully.")
except ImportError:
    logger.warning("Scraper module not available — running without auto-context.")
    def load_context(): return ""
    def scrape_and_extract(): return {}

MPP_AVAILABLE = False
try:
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
    from mpp_parser import MPPParser
    MPP_AVAILABLE = True
    logger.info("MPP parser loaded successfully.")
except Exception as _e:
    logger.warning(f"MPP parser not available: {_e}")
    MPPParser = None

try:
    from project_loader import load_all_projects, get_project_context, list_projects, has_schedule
    load_all_projects()
    logger.info("Project buckets loaded.")
except Exception as _pe:
    logger.warning(f"Project loader not available: {_pe}")
    def load_all_projects(): pass
    def get_project_context(slug, page=None): return ""
    def list_projects(): return []
    def has_schedule(slug): return False

try:
    from tracker_loader import load_tracker
    load_tracker()
    logger.info("Project tracker loaded.")
except Exception as _te:
    logger.warning(f"Tracker loader not available: {_te}")
    def load_tracker(): pass

# Pre-build portfolio summary once at startup — not per-request
_PORTFOLIO_CTX = ""
try:
    from tracker_loader import get_portfolio_summary
    _sched_flags = {p["slug"]: has_schedule(p["slug"]) for p in list_projects()}
    _PORTFOLIO_CTX = get_portfolio_summary(_sched_flags)
    logger.info("Portfolio summary cached.")
except Exception as _pfe:
    logger.warning(f"Portfolio summary cache failed: {_pfe}")


# ---------------------------------------------------------------------------
# PROJECT-SCOPED DOCUMENT MEMORY
# ---------------------------------------------------------------------------
# In-memory store: { slug: [ {filename, label, content, timestamp}, ... ] }
# Persisted to copilot_web/projects/{slug}/user_docs.json on every write.
# Loaded from disk at startup so docs survive server restarts.
# ---------------------------------------------------------------------------

_project_docs: dict = {}  # slug -> list of doc dicts

def _docs_path(slug: str) -> str:
    """Path to the user_docs.json file for a project."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "projects", slug, "user_docs.json")

def _load_project_docs(slug: str) -> list:
    """Load persisted docs from disk for a project slug."""
    path = _docs_path(slug)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_project_docs(slug: str):
    """Persist in-memory docs to disk for a project slug."""
    path = _docs_path(slug)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_project_docs.get(slug, []), f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"[{slug}] Could not persist user_docs: {e}")

def _get_project_docs_context(slug: str) -> str:
    """Build the USER-PROVIDED DOCUMENTS context block for a project."""
    docs = _project_docs.get(slug, [])
    if not docs:
        return ""
    lines = ["=== USER-PROVIDED DOCUMENTS ===",
             "These files were manually uploaded by the user for this project.",
             "Use them as supplementary context — they may contain dashboard screenshots, notes, milestone clarifications, or other reference material.",
             "The user can refer to these in conversation. Connect them to the schedule analysis when relevant.",
             ""]
    for i, doc in enumerate(docs, 1):
        label = doc.get("label") or doc.get("filename", f"Document {i}")
        ts = doc.get("timestamp", "")
        note = doc.get("user_note", "")
        lines.append(f"--- Document {i}: {label} (uploaded: {ts}) ---")
        if note:
            lines.append(f"User note: {note}")
        lines.append(doc.get("content", "[No content extracted]"))
        lines.append("")
    return "\n".join(lines)

# Pre-load all project docs from disk at startup
try:
    _here_docs = os.path.dirname(os.path.abspath(__file__))
    _proj_dir = os.path.join(_here_docs, "projects")
    if os.path.exists(_proj_dir):
        for _slug in os.listdir(_proj_dir):
            _loaded = _load_project_docs(_slug)
            if _loaded:
                _project_docs[_slug] = _loaded
                logger.info(f"Loaded {len(_loaded)} user doc(s) for {_slug}")
except Exception as _de:
    logger.warning(f"User docs preload failed: {_de}")


def _parse_uploaded_file(filepath: str, filename: str, client=None) -> str:
    """
    Parse any uploaded file and return a context string.
    Supports: .mpp, .xml, .xer, .csv, .txt, .md, .docx, .pdf, .png, .jpg, .jpeg, .webp
    Images are described via GPT-4o Vision if a client is provided.
    """
    import json as _json
    ext = os.path.splitext(filename)[1].lower()

    if ext in (".mpp", ".xml", ".xer") and MPP_AVAILABLE:
        try:
            parser = MPPParser(filepath)
            return parser.get_llm_context()
        except Exception as e:
            return f"[Parse error for {filename}: {e}]"

    elif ext == ".csv":
        try:
            import pandas as pd
            df = pd.read_csv(filepath, nrows=200)
            lines = [f"CSV file: {filename}", f"Columns: {', '.join(df.columns.tolist())}",
                     f"Rows: {len(df)}", "", df.to_string(index=False, max_rows=50)]
            return "\n".join(lines)
        except Exception as e:
            return f"[CSV parse error for {filename}: {e}]"

    elif ext in (".txt", ".md"):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read(6000)
            return f"[File: {filename}]\n{content}"
        except Exception as e:
            return f"[Read error for {filename}: {e}]"

    elif ext == ".docx":
        try:
            from docx import Document
            doc = Document(filepath)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return f"[Document: {filename}]\n{text[:6000]}"
        except Exception as e:
            return f"[DOCX parse error for {filename}: {e}]"

    elif ext == ".pdf":
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages[:30]:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
            extracted = "\n".join(text_parts)[:8000]
            return f"[PDF: {filename}]\n{extracted}"
        except Exception as e:
            return f"[PDF parse error for {filename}: {e}]"

    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        # Use GPT-4o Vision to describe the image
        try:
            import base64
            with open(filepath, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("utf-8")
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "webp": "image/webp", "gif": "image/gif"}.get(ext.lstrip("."), "image/png")
            data_url = f"data:{mime};base64,{b64}"

            if client:
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": (
                                "You are a project controls analyst. Describe this image in detail as it relates to construction schedule management. "
                                "Extract all visible text, dates, milestone names, activity names, percentages, and any schedule data. "
                                "If this is a dashboard screenshot, list every milestone name and date visible. "
                                "If this is a chart or graph, describe what it shows including axis labels and values. "
                                "Be thorough — this description will be used as reference data for schedule analysis."
                            )},
                            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}}
                        ]
                    }],
                    max_tokens=1500,
                    timeout=30
                )
                description = resp.choices[0].message.content
                return f"[Image: {filename}]\n{description}"
            else:
                # No client — store the raw base64 reference for later vision use
                return f"[Image: {filename}]\n[Image uploaded — vision analysis will be applied when queried]"
        except Exception as e:
            return f"[Image parse error for {filename}: {e}]"

    else:
        return f"[Unsupported file type: {ext}. Supported: .mpp, .xml, .xer, .csv, .txt, .md, .docx, .pdf, .png, .jpg, .jpeg, .webp]"

def background_scraper(interval_seconds=1800):
    """Runs scraper every interval_seconds (default 30 min) in a background thread."""
    if not SCRAPER_AVAILABLE:
        return
    time.sleep(10)
    while True:
        try:
            logger.info("Background scraper: starting scrape cycle...")
            scrape_and_extract()
            logger.info("Background scraper: cycle complete.")
        except Exception as e:
            logger.error(f"Background scraper error: {e}")
        time.sleep(interval_seconds)

scraper_thread = threading.Thread(target=background_scraper, daemon=True)
scraper_thread.start()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return "ok", 200

@app.route("/context", methods=["GET"])
def view_context():
    """Debug endpoint to inspect current dashboard context."""
    ctx = load_context()
    if not ctx:
        return jsonify({"status": "empty", "context": None})
    return jsonify({"status": "loaded", "context": ctx[:3000]})

@app.route("/projects", methods=["GET"])
def get_projects():
    """Returns list of all projects and their pages for the dropdown."""
    projects = list_projects()
    for p in projects:
        p["has_schedule"] = has_schedule(p["slug"])
    return jsonify({"projects": projects})

@app.route("/screenshot/<int:page_num>", methods=["GET"])
def view_screenshot(page_num):
    """Debug endpoint to view the screenshot Playwright captured for a given page."""
    path = f"/tmp/screenshot_page_{page_num}.png"
    if not os.path.exists(path):
        return f"No screenshot found for page {page_num}. Run /scrape first.", 404
    return send_file(path, mimetype="image/png")

@app.route("/upload", methods=["POST"])
def upload_file():
    """
    Accept an uploaded file. Supports schedule files, PDFs, images, docs, and notes.
    If project_slug is provided, the parsed content is stored in that project's
    document memory and persisted to disk — it will be automatically injected into
    every subsequent chat for that project.
    If no project_slug, returns context for one-time use (legacy behavior).
    Optional fields: label (display name), user_note (user annotation for the doc).
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    allowed = {".mpp", ".xml", ".xer", ".csv", ".txt", ".md",
               ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
    if ext not in allowed:
        return jsonify({"error": f"Unsupported file type: {ext}. Supported: {', '.join(sorted(allowed))}"}), 400

    project_slug = request.form.get("project_slug", "").strip() or None
    label = request.form.get("label", "").strip() or f.filename
    user_note = request.form.get("user_note", "").strip() or ""

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name

        # Pass client so images can be described via Vision
        _client = get_client()
        content = _parse_uploaded_file(tmp_path, f.filename, client=_client)

        if project_slug:
            # Store in project-scoped memory
            import datetime
            doc_entry = {
                "filename": f.filename,
                "label": label,
                "user_note": user_note,
                "content": content,
                "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            }
            if project_slug not in _project_docs:
                _project_docs[project_slug] = []
            # Replace existing doc with same filename, or append
            existing = [d for d in _project_docs[project_slug] if d["filename"] != f.filename]
            existing.append(doc_entry)
            _project_docs[project_slug] = existing
            _save_project_docs(project_slug)
            logger.info(f"[{project_slug}] Stored user doc: {f.filename}")
            return jsonify({
                "status": "stored",
                "project_slug": project_slug,
                "filename": f.filename,
                "label": label,
                "doc_count": len(_project_docs[project_slug]),
                "preview": content[:300]
            })
        else:
            # Legacy: return context for one-time use
            return jsonify({"context": content, "filename": f.filename})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


@app.route("/docs/<slug>", methods=["GET"])
def list_project_docs(slug):
    """List all user-uploaded documents stored for a project."""
    docs = _project_docs.get(slug, [])
    return jsonify({
        "project_slug": slug,
        "doc_count": len(docs),
        "docs": [{"filename": d["filename"], "label": d["label"],
                  "timestamp": d["timestamp"], "user_note": d.get("user_note", ""),
                  "preview": d["content"][:200]} for d in docs]
    })


@app.route("/docs/<slug>/<filename>", methods=["DELETE"])
def delete_project_doc(slug, filename):
    """Remove a specific uploaded document from a project's memory."""
    if slug not in _project_docs:
        return jsonify({"error": "Project not found"}), 404
    before = len(_project_docs[slug])
    _project_docs[slug] = [d for d in _project_docs[slug] if d["filename"] != filename]
    _save_project_docs(slug)
    removed = before - len(_project_docs[slug])
    return jsonify({"status": "ok", "removed": removed, "remaining": len(_project_docs[slug])})


@app.route("/docs/<slug>/clear", methods=["POST"])
def clear_project_docs(slug):
    """Clear all user-uploaded documents for a project."""
    _project_docs[slug] = []
    _save_project_docs(slug)
    return jsonify({"status": "cleared", "project_slug": slug})

@app.route("/scrape", methods=["POST"])
def trigger_scrape():
    """Manual trigger to force a fresh scrape."""
    if not SCRAPER_AVAILABLE:
        return jsonify({"error": "Scraper not available"}), 503
    try:
        threading.Thread(target=scrape_and_extract, daemon=True).start()
        return jsonify({"status": "Scrape triggered in background."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    context = data.get("context", "")
    image_b64 = data.get("image", None)
    project_slug = data.get("project_slug", None)
    page_view = data.get("page_view", None)

    client = get_client()
    if not client:
        return jsonify({"error": "No API key configured."}), 500

    dashboard_context = load_context()

    system = SYSTEM_BASE

    # Portfolio overview — injected from startup cache, never rebuilt per-request
    if _PORTFOLIO_CTX:
        system += f"\n\n{_PORTFOLIO_CTX}"

    if dashboard_context:
        system += f"\n\n{dashboard_context}"

    if project_slug:
        proj_ctx = get_project_context(project_slug, page_view)
        if proj_ctx:
            system += f"\n\n{proj_ctx}"

        # Inject project-scoped user-uploaded documents
        docs_ctx = _get_project_docs_context(project_slug)
        if docs_ctx:
            system += f"\n\n{docs_ctx}"

    if context:
        system += f"\n\nUSER-PROVIDED CONTEXT:\n{context}"

    full_messages = [{"role": "system", "content": system}] + messages[-10:]

    if image_b64:
        last_user_text = next(
            (m["content"] for m in reversed(full_messages) if m["role"] == "user"),
            "What do you see in this image?"
        )
        full_messages = [m for m in full_messages if not (m["role"] == "user" and m["content"] == last_user_text)]
        full_messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": last_user_text},
                {"type": "image_url", "image_url": {"url": image_b64, "detail": "high"}}
            ]
        })

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=full_messages,
            temperature=0.3,
            timeout=25
        )
        return jsonify({"reply": response.choices[0].message.content})
    except openai.APITimeoutError:
        return jsonify({"error": "__timeout__"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
