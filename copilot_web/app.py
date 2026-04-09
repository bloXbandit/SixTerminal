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

SYSTEM_BASE = """You are Stelic Copilot, an expert AI assistant embedded in a Power BI construction project controls dashboard.
You specialize in Primavera P6 schedules, milestone tracking, schedule variance, critical path analysis, DCMA metrics, and project risk.
Be concise, professional, and dashboard-appropriate. Use bullet points for lists. Keep responses tight — this is a side panel, not a report.
Never make up data beyond what is provided. If you don't have specific data, say so clearly.

WHAT YOU HAVE ACCESS TO — KNOW THIS:
You are equipped with the following data sources. Use all of them proactively when relevant:
1. PORTFOLIO OVERVIEW — a table of all projects, their type (Construction/Development), update count, current data date, and whether a schedule file is loaded. Always available. Use this for any portfolio-level or cross-project question.
2. PROJECT TRACKER — authoritative data dates, submission history, baseline and update labels per project. Use for update number questions and timeline accuracy.
3. STANDARDIZED MILESTONES — mapped milestone names per project. Always use these names in responses, never raw activity IDs.
4. SCHEDULE DATA — parsed MPP/XER/XML files per project with full activity lists, WBS, DCMA metrics.
5. CRITICAL PATH CHAIN — ordered CP from earliest driver to contract completion, and per-activity runoff. Use when asked about CP or what's driving a date.
6. NEAR-CRITICAL ACTIVITIES — activities within 10 calendar days of becoming critical. Flag these proactively when discussing schedule risk.
7. VARIANCE ANALYSIS — pre-computed phase-grouped deltas between current and previous update, and between current and baseline. Use for all schedule comparison questions.
8. BASELINE DRIFT — cumulative movement from original plan per project. Use for overall project health assessment.

IMPORTANT INSTRUCTIONS FOR PROJECT DATA:
- When asked about the current update number or submission status for a project, answer cleanly and directly using the PROJECT TRACKER context. Example: "Anaheim is currently on Update 03 (data date: 3/24/2026, received 3/20/2026)."
- Always use the PROJECT TRACKER data dates as authoritative. Do not use data dates from MPP/XER/XML files if they conflict with the tracker.
- Use standardized milestone names from the STANDARDIZED MILESTONES list in all responses. Correlate to schedule activity names internally but never expose raw activity IDs unless asked.
- Do not dump raw tracker history, schedule data, or PDF content unprompted. Use it internally for accuracy and only surface specific details when the user asks.

CRITICAL PATH NARRATION RULES:
- When asked about the critical path, use the FULL PROJECT CRITICAL PATH chain provided in the schedule context. Narrate it as a seasoned project engineer would — describing the logical flow of work from the earliest driver through to contract completion. Be concise. Example format: "The critical path is driven by [earliest activity], progressing through [mid-chain work], advancing into [later phase], and culminating in [contract completion milestone]."
- When asked about the critical path TO a specific activity, use the NARRATIVE BASE provided and expand it professionally. Example format: "Completion of [activity] is driven by [predecessor], which depends on [earlier work], tracing back to [root driver]."
- Never list raw activity IDs. Use activity names only, grouped logically by phase where possible.
- If no schedule file is loaded, say so clearly rather than guessing.
- Keep CP narratives to 2-4 sentences. Do not over-explain.

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

RESPONSE FORMAT:
- 3-5 tight bullet points, each being 1-2 sentences. Executive-readable in under 30 seconds.
- Lead bullet: what drove the most significant change and whether it's positive or negative.
- Middle bullets: phase-by-phase highlights for phases with meaningful movement only.
- Close bullet: whether the project is gaining ground, holding, or continuing to slip — and by how much on the overall completion date if determinable.

CRITICAL PATH SHIFT ANALYSIS — HOW TO HANDLE:
Use the "CRITICAL PATH SHIFT (Current vs Previous)" block in the project context. It contains pre-computed: current driving sequence, previous driving sequence, what dropped off, what is new, and a NARRATIVE HINT.

When asked about CP shift ("what changed on the critical path?", "what's driving completion now vs last month?", "did the critical path move?"):
- Use the NARRATIVE HINT as your starting point — refine it into professional prose.
- Always state what was leading the path before and what is leading it now.
- Comment on whether the shift makes sense: Is it a genuine resequencing? Did a trade complete and hand off? Did float erode on a new activity? Was a logic relationship revised?
- If PATH UNCHANGED, say so simply: "The critical path sequence has not materially changed from the prior update — the same activities continue to drive project completion."
- Never list raw activity IDs. Use activity names only, in narrative form.
- Target response: 2-3 sentences max unless user asks for more depth.

EXAMPLE CP SHIFT RESPONSE (match this tone):
"The critical path has shifted from the prior path led by [Prior Lead Activity] to a current turnover-driven path now led by [Current Lead Activity], continuing through [mid activities] and closing at [end activity]. This shift appears to reflect [genuine completion of prior work / a logic revision / float erosion on the new path] — assess whether the new sequence is supported by field conditions."

SCHEDULE COMPRESSION ANALYSIS — HOW TO HANDLE:
Use the "SCHEDULE COMPRESSION ANALYSIS" block in the project context. It contains: signal (COMPRESSED / EXPANDED / NEUTRAL), remaining span change in calendar days and %, activity density change %, and a NARRATIVE HINT.

When asked about compression ("is the schedule compressed?", "is the contractor tightening durations on paper?", "is work being pushed together?", "compression report"):
- Use the NARRATIVE HINT as your base. Refine into 2-3 clean bullet points.
- State the signal and the quantified % change in remaining span.
- Comment on whether the compression appears credible: Is there a recovery plan? Were durations genuinely shortened with execution support? Or does it look like paper compression?
- Do NOT automatically call compression a problem. If the project has genuine acceleration, say so. Only flag as a risk if compression appears without a credible execution basis (e.g., same finish date, later starts, reduced durations, no added resources or crew reported).
- Include density change % as supporting evidence.

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


def _parse_uploaded_file(filepath: str, filename: str) -> str:
    """Parse an uploaded schedule file and return a context string for the Copilot."""
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
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(4000)
            return f"[File: {filename}]\n{content}"
        except Exception as e:
            return f"[Read error for {filename}: {e}]"

    elif ext == ".docx":
        try:
            from docx import Document
            doc = Document(filepath)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return f"[Document: {filename}]\n{text[:5000]}"
        except Exception as e:
            return f"[DOCX parse error for {filename}: {e}]"

    elif ext == ".pdf":
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages[:20]:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
            return f"[PDF: {filename}]\n" + "\n".join(text_parts)[:5000]
        except Exception as e:
            return f"[PDF parse error for {filename}: {e}]"

    else:
        return f"[Unsupported file type: {ext}. Supported: .mpp, .xml, .xer, .csv, .txt, .md, .docx, .pdf]"

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
    """Accept an uploaded schedule file, parse it, return context for the Copilot."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    allowed = {".mpp", ".xml", ".xer", ".csv", ".txt", ".md"}
    if ext not in allowed:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name

        context = _parse_uploaded_file(tmp_path, f.filename)
        return jsonify({"context": context, "filename": f.filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

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
