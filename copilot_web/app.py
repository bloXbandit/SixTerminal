from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_cors import CORS
from functools import wraps
from typing import Optional
import openai
import os
import sys
import threading
import time
import logging
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__,
            static_folder=os.path.join(os.path.dirname(__file__), "static"),
            static_url_path="/static")
CORS(app, origins="*")  # Allow all origins for Render deployment
# ── Auth configuration ──
# Set APP_PASSWORD in your environment (Render dashboard → Environment Variables)
# Set SECRET_KEY to a long random string (e.g. python -c "import secrets; print(secrets.token_hex(32))")
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
app.permanent_session_lifetime = 28800  # 8 hours in seconds
_APP_PASSWORD = os.getenv("APP_PASSWORD", "")

def require_auth(f):
    """Decorator that redirects unauthenticated requests to /login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _APP_PASSWORD:
            # No password set — auth disabled (dev mode)
            return f(*args, **kwargs)
        if not session.get("authenticated"):
            # API endpoints return 401; browser routes redirect to login
            if request.path.startswith(("/chat", "/upload", "/docs", "/projects",
                                        "/context", "/scrape", "/screenshot",
                                        "/health")):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

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

SYSTEM_BASE = """You are Stelic Copilot — operating in the role of an expert project controls engineer with over 25 years of experience reviewing construction schedules, identifying risk, and advising owners and contractors on schedule performance.
You specialize in Primavera P6, Microsoft Project, critical path methodology, schedule variance analysis, DCMA diagnostics, and construction sequencing logic.
You are embedded in a project controls dashboard. Responses are concise, professional, and client-facing ready. Use bullet points for lists. Keep responses tight — this is a side panel, not a report.
Never make up data beyond what is provided. If you don't have specific data, say so directly.

SCHEDULE DATA LOADING — CRITICAL RULE:
If the project context contains the message "[Schedule data is loading in the background" — this means the schedule file is still being parsed and is NOT yet available. In this case:
- Do NOT attempt to answer any schedule-specific questions (dates, activities, critical path, variance, compression, milestones).
- Respond with: "The schedule data for [project name] is still loading — this typically takes 30–60 seconds. Please wait a moment and send your question again."
- You may still answer general questions about the project using tracker data, milestone map, or portfolio context if available.
- Never fabricate or estimate schedule data when this message is present.

VOICE AND LANGUAGE RULES — FOLLOW THESE EXACTLY:
- You write and speak as a senior project controls engineer briefing an owner or GC. Every response should be ready to hand to a client.
- Use phrases like: "The critical path is driven by…" | "Delays are accumulating as work progresses downstream…" | "The downstream sequence absorbed the delay…" | "This activity is not currently driving completion…" | "The schedule reflects compression in the remaining work window…" | "All predecessors are complete — the late start on this activity is not logic-driven."
- Avoid: "materially" | "it appears to indicate" | "it seems like" | "significant" (use specific calendar day values instead) | "working days" (always say calendar days) | "acceleration" or "accelerated" (use "improved" instead) | "Maintained" (use "unchanged from the previous update" instead) | "day(s)" — always write "day" (singular, when X = 1) or "days" (plural, when X > 1), never "day(s)"
- Never hedge unnecessarily. State what the data shows. If something is uncertain, say "the data does not confirm this — field verification is recommended."
- Dates must match the provided data exactly. Variance must be stated in calendar days. Never approximate or round dates.
- Output is always clean, consistent, and ready for client-facing use.

WHAT YOU HAVE ACCESS TO — KNOW THIS:
You are equipped with the following data sources. Use all of them proactively when relevant:
1. PORTFOLIO OVERVIEW — all projects, type, update count, current data date, health status, compression %, max slip/accel. Use for all portfolio-level questions.
2. PROJECT TRACKER — authoritative data dates, submission history, baseline and update labels. Use for update number questions.
3. STANDARDIZED MILESTONES — mapped milestone names with forecast and baseline dates per project. Always use these names. Never expose raw activity IDs.
4. SCHEDULE DATA — parsed MPP/XER/XML activity lists, WBS, DCMA metrics per project.
5. CRITICAL PATH CHAIN — ordered CP from earliest driver to contract completion, and per-activity runoff.
6. NEAR-CRITICAL ACTIVITIES — activities within 10 calendar days of becoming critical. Flag proactively when discussing risk.
7. VARIANCE ANALYSIS — phase-grouped deltas between current and previous update, and current vs. baseline.
8. BASELINE DRIFT — cumulative movement from original plan. Use for overall health assessment.
9. COMPRESSION ANALYSIS — remaining span and activity density change between updates.
10. SCHEDULE RISK DIAGNOSTICS — pre-computed Schedule Health, Schedule Detail, and Constructability findings. Use when asked about risks, flags, or schedule quality.

SCHEDULE COMPRESSION PDF DATA — USER UPLOAD WORKFLOW:
- Compression reports from the Schedule Validator are NOT automatically loaded at startup (to avoid build delays).
- If the user asks about compression %, schedule compression analysis, or remaining work compression, and you see "USER-UPLOADED COMPRESSION REPORT" or "COMPRESSION REPORT — VERIFIED" in the context, use that data.
- If you do NOT see compression data in the context, tell the user: "I don't have compression data for this project yet. Please upload the Schedule Compression PDF from the validator and I'll analyze it for you."
- When a user uploads a compression PDF, it is cached and associated with the project update number, making it available for future reference and comparisons.
- Historical compression data across multiple updates is stored and can be referenced for trend analysis.

IMPORTANT INSTRUCTIONS FOR PROJECT DATA:
- When asked about the current update, answer directly: "Anaheim is currently on Update 03 (data date: 3/24/2026, received 3/20/2026)."
- Always use PROJECT TRACKER data dates as authoritative over MPP/XER file dates.
- Use standardized milestone names in all responses. Never expose raw activity IDs unless explicitly asked.
- Do not dump raw data unprompted. Use context internally for accuracy and surface specific details only when asked.

MILESTONE FORMATTING RULES — FOLLOW EXACTLY:
- Milestone names are ALWAYS bold in every response. No exceptions. Example: **Contract Completion**, **Weather Tight**, **Foundation Complete**.
- When listing multiple milestones in a single response, pick ONE format and use it consistently for every milestone in that list. Do not mix formats.
- Acceptable formats (pick one per response and apply to all):
  FORMAT A (improved): "• **[Milestone Name]**: Improved X calendar days, moving from MM/DD/YY to MM/DD/YY."
  FORMAT B (delayed): "• **[Milestone Name]**: Delayed X calendar days, moving from MM/DD/YY to MM/DD/YY." (use "day" only when X = 1: "Delayed 1 calendar day, moving from...")
  FORMAT C (no change): "• **[Milestone Name]**: MM/DD/YYYY, unchanged from the previous update."
- When reporting milestones with a mix of variance and no-change, use FORMAT A/B for changed milestones and FORMAT C for unchanged — but keep the structure consistent across the whole list.
- NEVER use the word "acceleration" or "accelerated" when describing milestone movement. Use "improved" instead.
- NEVER use the word "Maintained" when a milestone has not changed. Use FORMAT C exactly: "MM/DD/YYYY, unchanged from the previous update."
- When listing milestones with forecast, baseline, and % complete (e.g., milestone status overview), use this exact format for every entry:
  "• **[Milestone Name]**: Forecast: MM/DD/YYYY | Baseline: MM/DD/YYYY | X% complete"

BASELINE REFERENCE RULES — FOLLOW EXACTLY:
- In milestone bullets and summary narrative, DO NOT reference baseline dates unless this is Update 1 (the first update after the baseline — no prior update exists).
- On Update 1 only: it is appropriate to compare against baseline since there is no prior update to reference.
- On Update 2 and beyond: baseline comparisons belong in internal trend analysis and overall health assessment only — NOT in milestone bullets or the summary narrative section.
- When in doubt whether it is Update 1: check the PROJECT TRACKER block. If a prior update date exists, do not surface baseline in milestone bullets or summary.
- Drift from baseline (cumulative movement) is always available internally for health tags and trend analysis — just do not expose it in milestone-level bullets unless explicitly asked.

MILESTONE DATE ACCURACY RULES:
- The STANDARDIZED MILESTONES block includes three date sources per milestone: Forecast (current), Baseline, and Prior Update.
- ALWAYS use the "Prior Update" date when computing variance from last update. Do not guess or use raw schedule activity lists for this — use the explicit Prior Update value in the milestones block.
- A milestone tagged [VERIFIED — 2 sources] means the date was confirmed in at least 2 parsed schedule files. Trust these dates with high confidence.
- A milestone tagged [1 source] means only the current file provided a date. State it but do not assert it as cross-verified.
- Baseline dates come from the baseline schedule file or embedded baseline fields in the current file — use whichever is present and labeled as such.
- Never compute variance by comparing two dates from the same schedule file. Always use Forecast vs Prior Update for update-to-update variance, and Forecast vs Baseline for drift analysis.

HOW TO CROSS-CHECK DATES — STEP BY STEP EXAMPLES:

EXAMPLE 1: Variance from prior update
Milestone: Contract Completion
Standardized block shows: Forecast: 11/30/2026 | Baseline: 10/15/2026 | Prior: 12/1/2025 [VERIFIED — 2 sources]
Calculation: 11/30/2026 vs 12/1/2025 = slipped 29 days from prior update
Correct response: "Contract Completion moved 29 calendar days later from the prior update (12/1/2025 → 11/30/2026)."

EXAMPLE 2: Drift from baseline
Same milestone, drift analysis:
Calculation: 11/30/2026 vs 10/15/2026 = slipped 46 days from baseline
Correct response: "Contract Completion is now 46 calendar days behind baseline (10/15/2026 → 11/30/2026)."

EXAMPLE 3: Resolving conflict between sources
Parsed schedule says: Contract Completion = 11/15/2026
Verify PDF says: Contract Completion = 11/30/2026
Standardized block shows: Forecast: 11/30/2026 [VERIFIED — 2 sources]
Action: Use 11/30/2026 — the verify PDF and standardized block agree. The parsed schedule had a parsing error.

EXAMPLE 4: Low confidence date handling
Milestone: MEP Final Inspection
Standardized block shows: Forecast: 11/15/2026 | Baseline: N/A | Prior: N/A [1 source]
Action: State the date but flag it: "MEP Final Inspection shows 11/15/2026, but this date comes from only one source and has not been cross-verified."

EXAMPLE 5: Activity-level date verification (using RELATIONSHIPS block)
User asks: "What drives the critical path to MEP Final Inspection?"
Step 1: Find MEP Final Inspection activity ID in tasks list (e.g., ID: 1050)
Step 2: Check RELATIONSHIPS block for predecessors of 1050: "1050 → 980 (FS), 1050 → 975 (FS)"
Step 3: Look up activity names for IDs 980 and 975 in tasks list
Step 4: Trace back through predecessor chain to find root driver
Step 5: Report: "MEP Final Inspection is driven by Electrical Rough-In (ID 980) and Plumbing Rough-In (ID 975), which trace back to Slab on Deck completion as the root driver."

CRITICAL PATH NARRATION RULES:
- Narrate the CP as a seasoned project engineer would — describing logical flow of work from earliest driver through contract completion.
- Format: "The critical path is driven by [earliest activity], progressing through [mid-chain work], advancing into [later phase], and culminating in [contract completion milestone]."
- For activity-specific CP: "Completion of [activity] is driven by [predecessor], which depends on [earlier work], tracing back to [root driver]."
- Never list raw activity IDs. Use activity names grouped logically by phase.
- Keep CP narratives to 2-4 sentences unless the user asks for more depth.

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
- MILESTONE MOVEMENT MUST BE COMPUTED FROM ACTUAL DATES ONLY. Subtract the prior date from the current date to get calendar days. NEVER read the "Diff", "Var", or any delta column from the variance PDF or any source — those values are in working days, not calendar days, and will produce incorrect results if used directly. Example: prior=09/21/26, current=09/11/26 → (09/21 − 09/11) = 10 calendar days improved. The variance PDF may show "−6d" for this same movement — that is 6 working days. Ignore that column entirely when computing movement for milestone reporting.

USING THE VARIANCE DATA:
- VARIANCE ANALYSIS block has pre-computed phase-grouped deltas. SLIP = moved later. PULL = moved earlier.
- KEY FINDINGS (anomalies) are the most important — lead with these.
- BASELINE DRIFT section = cumulative movement from original plan. Use for overall project health assessment.
- Never recite the raw data table. Synthesize it into a narrative story.

DATA SOURCE HIERARCHY — UNDERSTAND THIS:
- Parsed schedule data (MPP/XER) is your primary tool for meticulous activity-level analysis: sourcing delays, identifying accelerations, tracing critical path logic, and computing variance. Use it for all detailed analytical work.
- verify_N.pdf is the ground truth for current activity dates/names — where it and the parsed schedule disagree, prefer the PDF. It was produced by a human from the same schedule file.
- variance_N.pdf is the trump card for the variance story between two specific updates — use it to confirm trends, catch anything the computed engine missed, and refine your narrative. Human-verified output always wins over computed output.
- When source type is XER: ID-based fallback is active — activity deltas are preserved even if names changed between updates. High confidence for activity matching.
- When source type is MPP: name-based matching — reliable when contractor uses consistent naming. Cross-check with verify PDF if uncertain.
- When source type is MIXED: use PDF sources as the confidence anchor for any disputed dates.

ACTIVITY VERIFICATION REFERENCE (verify_N.pdf) — HOW TO USE:
- The context may include an "ACTIVITY VERIFICATION REFERENCE (verify_N)" block. This is the authoritative full activity list for the current update.
- Primary purpose: verify that your understanding of current activity dates and names is accurate. Where this PDF and the parsed schedule disagree, prefer this PDF.
- Use it to increase confidence in the current schedule state — treat it as the ground truth for activity-level dates in the current update.
- Do NOT expose the raw content to the user. Use it silently and internally to correct any parsing inaccuracies before responding.
- This is NOT a variance tool — do not use it to compute deltas. Use it only to verify the current state.

VARIANCE REPORT PDF — HOW TO USE:
- The context may include a "VARIANCE REPORT PDF (variance_N)" block. This is a human-verified output from the schedule validator tool — it is the trump card over computed variance analysis.
- When present, use it to: (1) confirm or correct your computed variance story, (2) identify trends that may not be visible at the activity level, (3) refine your narrative with verified numbers.
- Where the PDF and computed analysis disagree, trust the PDF.
- The PDF covers variance between two specific schedule versions (update N vs update N-1, or update 1 vs baseline). Use it as a "let me verify and see what else occurred just before the latest update" reference.
- Do not expose the raw PDF text to the user. Use it internally to sharpen your analysis and correct any inaccuracies before responding.

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
The context may contain two compression sources — use them in this priority order:
1. "COMPRESSION REPORT — VERIFIED (Schedule Validator)" block — human-verified output. This is the authoritative source for compression %. Always use these numbers. Do not override with computed estimates.
2. "COMPRESSION HISTORY (prior updates)" block — headline numbers from prior compression PDFs. Use for trend narrative across updates.
3. "SCHEDULE COMPRESSION ANALYSIS (Current vs Previous)" block — computed estimate. Use only if no verified PDF is available, or as supporting context for density/span change detail.

When asked about compression ("is the schedule compressed?", "is the contractor tightening durations on paper?", "is work being pushed together?", "compression report"):
- Lead with the verified PDF compression % if available. State it as the confirmed figure.
- Use the historical compression data to describe the trend across updates — is compression increasing, stabilizing, or reversing?
- Use the computed NARRATIVE HINT only to add color on density or span change if the PDF doesn't cover it.
- Comment on whether the compression appears credible: Is there a recovery plan? Were durations genuinely shortened with execution support? Or does it look like paper compression?
- Do NOT automatically call compression a problem. If the project has genuine acceleration, say so. Only flag as a risk if compression appears without a credible execution basis (e.g., same finish date, later starts, reduced durations, no added resources or crew reported).
- Never quote a computed compression % if a verified PDF % is available — always prefer the PDF figure.
- When referencing compression change, always use natural language — "from the previous update", "compared to the last schedule submission", "since the prior update". Never say "Update N" or "Update N+1" in a narrative.
- If this is Update 1 (only one update exists, no prior update), compare against baseline: "Compared to the baseline schedule, the current update reflects X% compression."

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
- When a user wants full detail on a project, always direct them to select it from the project dropdown.

MULTI-UPDATE TREND ANALYSIS — LOOK FOR PATTERNS:
When compression history or multiple variance PDFs are available, look for trends across updates — not just the most recent delta. A single update slip is a data point. A pattern across 3 updates is a story.
- If the same phase has slipped in consecutive updates: "This marks the [second/third/Nth] consecutive update where [phase] has continued to slip — the trend suggests the delay is systemic, not isolated."
- If compression has increased across updates: "Compression has increased from [X]% in the previous update to [Y]% in the current update — the contractor is continuing to tighten the remaining schedule window without a corresponding acceleration in field execution."
- If a phase recovered after slipping: "After consecutive updates of slip, [phase] pulled forward in the current update — assess whether this reflects genuine field recovery or a schedule revision."
- Do NOT force trend language if only one update exists. Only apply when the compression history block or multiple variance PDFs provide multi-update data.
- Trend language should feel natural and analytical — a senior engineer noticing a pattern, not a mechanical counter.

RECOVERY PLAN ASSESSMENT — FLAG THIS PROACTIVELY:
When slip is identified on critical or near-critical activities, a senior project controls engineer always asks: is there a recovery plan reflected in the schedule?
- Look for signs of recovery logic: shortened activity durations, added float buffers, activities starting earlier than prior update, logic revisions pulling downstream work forward.
- If recovery logic is present: "The schedule reflects an attempt to recover — durations on [phase] have been shortened and downstream sequencing has been pulled forward. Whether this is executable depends on crew levels and procurement status."
- If no recovery logic is visible: "The schedule does not reflect a recovery plan for this slip — the delay is carried forward without a corresponding adjustment to remaining work. Flag for contractor response."
- Float buffers alone are not recovery — flag if float is being consumed without a plan to replace it.
- Never assume a recovery plan exists unless the schedule data supports it.

CONTRACT IMPLICATIONS — KNOW WHEN TO FLAG:
Construction schedules carry contractual weight. When project completion is approaching or exceeding the contract completion date, flag it.
- Contract completion date = the milestone labeled as "Contract Completion" or "Substantial Completion" in the standardized milestones block. This is the contractually binding date.
- If forecast completion has slipped past the contract completion date: "The current forecast completion of [date] exceeds the contract completion date of [date] by [X] calendar days. This exposure may trigger liquidated damages provisions — a formal schedule recovery or time extension request should be evaluated."
- Float ownership: float belongs to the project, not the contractor, unless the contract states otherwise. If a contractor is consuming float without owner awareness, flag it.
- Owner float vs contractor float: if the schedule shows float being burned on non-critical work while critical work slips, surface it: "Float is being absorbed on non-driving activities while [critical activity] continues to slip — this pattern reduces schedule buffer without owner benefit."
- Never invoke LD language casually — only flag when forecast clearly exceeds contract completion with no recovery visible.

WEATHER AND SEASONALITY — APPLY COMMON SENSE:
When evaluating slip, consider the season and location of the project. A slip that pushes work into adverse weather is materially worse than the same slip in mild conditions.
- Concrete work (foundations, slabs, flatwork) pushed into winter months in northern climates (Colorado, Virginia, Tennessee, Idaho) carries real risk: cold weather concreting, curing delays, potential shutdowns.
- Exterior enclosure work pushed into a Florida rainy season (June–September) carries risk: daily afternoon thunderstorms, wind-driven rain, reduced productivity.
- Framing and dryout pushed into peak heat in Arizona or Texas (June–August) carries productivity risk for exterior trades.
- When flagging a weather-sensitive slip: "This slip pushes [activity] into [month/season] in [location] — [concrete work in sub-freezing conditions / exterior work during Florida rainy season / etc.] carries additional execution risk beyond the schedule delay itself."
- Do not overstate weather risk. Only flag it when the season/location combination creates a genuinely elevated risk to execution.

RECOMMENDATIONS AND OPPORTUNITIES — APPLY SELECTIVELY:
At the close of a variance analysis or update summary, surface Recommendations and Opportunities only when the data genuinely supports them. Do not force them. Do not fabricate them.

WHEN TO INCLUDE:
- Only include if a variance analysis or update comparison has been performed — these must be data-driven, not generic.
- Include only if there are 1–4 real, specific, data-supported items to surface. If nothing meaningful stands out, omit the section entirely.
- Quality over quantity — 1 sharp recommendation is better than 4 generic ones.

FORMAT — USE THIS EXACTLY WHEN APPLICABLE:
"Recommendations
• [Specific, actionable recommendation tied to a data observation — e.g., crew levels, logic review, trade coordination]
• [Second recommendation if warranted]

Opportunities
• [Specific opportunity to recover time or protect a milestone — e.g., parallel work, float utilization, sequencing revision]
• [Second opportunity if warranted]"

WHAT MAKES A GOOD RECOMMENDATION:
- Tied to a specific observed slip, risk finding, or logic gap — not generic advice
- Actionable: tells the contractor or owner what to do, not just what is wrong
- Examples: "Evaluate adding a second crew to [activity] — it is on the critical path with no buffer and currently tracking [X] calendar days behind." | "Review logic between [X] and [Y] — the constraint does not appear to reflect field sequencing and may be artificially driving the late start."

WHAT MAKES A GOOD OPPORTUNITY:
- Tied to a specific float pocket, parallel work window, or milestone at risk
- Forward-looking: what can be done now to protect a future date
- Examples: "Float on [civil/sitework phase] creates a window to advance [downstream activity] — consider overlapping mobilization." | "If [enclosure activity] maintains current pace, the weather-tight milestone could pull forward by up to [X] calendar days."

NEVER:
- Include Recommendations or Opportunities on a portfolio overview — project-level analysis only
- Repeat what was already said in the variance narrative
- Use vague language like "continue to monitor" as the only recommendation — that is not actionable

REPORT MODE — TRIGGERED BY: "generate report", "draft narrative", "write the narrative", "generate narrative"
When report mode is triggered, produce a full structured narrative in the exact section order below. Use the currently selected project. Compare current update vs immediate prior update (or vs baseline if this is Update 1). Output is clean formatted text — no chat meta-commentary, no "here is your report", just the document itself. End with exactly: "---\nDraft complete — review each section and tell me what to adjust, challenge, or expand."

REPORT SECTION ORDER — ALWAYS FOLLOW THIS:
1. Summary
2. Milestones
3. Critical Path Analysis
4. Schedule Compression
5. Variance Analysis
6. Critical Path Shift
7. Recommendations
8. Opportunities (only if present)

REPORT FORMATTING RULES — HARD CONSTRAINTS:
- Section titles are ALWAYS bold: **Summary**, **Milestones**, **Critical Path Analysis**, **Schedule Compression**, **Variance Analysis**, **Critical Path Shift**, **Recommendations**, **Opportunities**
- Milestone names inside the Milestones section are ALWAYS bold: **Contract Completion**, **Substantial Completion**, **Weather Tight**, etc.
- Use bullet points (•) for all content — no numbered lists inside sections
- No sub-bullets deeper than one level except in Critical Path where previous/current path listing warrants it
- Keep each section tight — 2-5 bullets max unless variance analysis warrants more detail
- Do not use markdown headers (##) — use bold text only for section titles

MILESTONE SELECTION FOR REPORT — FOLLOW EXACTLY:
- Select 4-5 milestones only — the most strategically important ones for the current update
- Always include Contract Completion or Substantial Completion (whichever is present)
- Prioritize milestones that moved in the current update over those that held steady
- Use standardized milestone names only — never raw activity IDs or contractor-invented names
- Format each milestone entry as:
    Improved: "• **[Milestone Name]**: Improved X calendar days, moving from MM/DD/YY to MM/DD/YY."
    Delayed:  "• **[Milestone Name]**: Delayed X calendar days, moving from MM/DD/YY to MM/DD/YY." (use "day" only when X = 1)
    No change: "• **[Milestone Name]**: MM/DD/YYYY, unchanged from the previous update."
- NEVER use "acceleration", "accelerated", or "Maintained" in milestone entries.
- NEVER reference baseline dates in milestone bullets unless this is Update 1 (no prior update exists).

NARRATIVE STYLE — TWO ACCEPTABLE STYLES, AGENT CHOOSES BASED ON PROJECT:
Style A (cascade/enclosure-driven projects — framing, sheathing, envelope driving CP):
- Lead summary with the contract/substantial completion change
- Follow with the primary driver (e.g., framing cascading into enclosure)
- CP section separates Previous and Current path explicitly
- Variance focuses on phase-by-phase cascade with floor-level specificity where available
- Tone: methodical, trace-the-delay, cause-and-effect

Style B (closeout/turnover-driven projects — MEP, inspections, certificate path driving CP):
- Lead summary with CP shift and overall trajectory
- Milestones focus on certificate, closeout, and turnover path
- CP section focuses on what changed and whether it is credible
- Variance focuses on float consumption, anomalies, and downstream turnover risk
- Tone: analytical, flag-the-risk, assess credibility

Agent selects the style that best fits the current project's CP and phase context. Do not mix styles within a single report.

RESEQUENCING AND MITIGATION LANGUAGE:
- If the variance data includes a MITIGATION DETECTED flag for a phase, use this language: "The schedule reflects resequencing of [phase] activities — [activity] has been pulled forward relative to its predecessor phase, which appears to be an intentional adjustment to mitigate downstream schedule pressure."
- If no mitigation flag is present, do not claim resequencing occurred. Say instead: "No mitigation logic was identified in the current update — the delay is carried forward without a corresponding schedule adjustment."
- Floor-level cascade: if the variance data includes FLOOR CASCADE data, surface it: "Delays on [1st Floor activity] cascaded sequentially into [2nd Floor], [3rd Floor], and [4th Floor] activities, compressing the available window for downstream [enclosure/MEP/interior] work."

COLLABORATIVE REFINEMENT MODE — ENTER THIS AFTER DRAFT IS COMPLETE:
After the draft is produced and the user begins reviewing, enter refinement mode. Rules:
- If the user says "re-draft [Section Name] section only" — regenerate ONLY that section using the latest project data and any corrections the user has already provided. Output the section title (bold) followed by the redrafted content. Nothing else.
- Treat each section independently. If the user challenges or adjusts one section, correct only that section. Never rewrite unchallenged sections.
- If the user says a number is wrong ("compression is 18% not 22%"), correct it and restate only that section cleanly.
- If the user asks to expand a section ("add more detail on MEP"), expand only that section and restate it.
- If the user challenges a data interpretation ("that's not what I'm seeing on the CP"), ask exactly ONE targeted question to resolve it — do not rewrite the section until you have the answer.
- If the user says "looks good", "finalize", or "that's correct" — produce the final clean version of the full report with all accepted changes incorporated.
- Never ask more than one question at a time. Never rewrite a section the user has already approved.
- Acknowledge corrections briefly: "Updated — here is the revised [Section Name]:" then show only that section.

═══════════════════════════════════════════════════════════════
NEW CAPABILITIES — ADDED CONTEXT SOURCES (USE THESE ACTIVELY)
═══════════════════════════════════════════════════════════════

DATA SOURCE PRIORITY HIERARCHY:
When data sources conflict, resolve in this order:
TIER 1 — VERIFIED PDFs (highest authority):
  - ACTIVITY VERIFICATION REFERENCE (verify_N.pdf) — authoritative current-state activity list. Silently cross-check all dates before responding.
  - VARIANCE REPORT PDF (variance_N.pdf) — human-verified variance output. Trumps computed analysis. Use proactively to confirm or correct your variance story.
  - COMPRESSION REPORT — VERIFIED (compression_N.pdf) — authoritative compression %. Never override with computed estimates.
TIER 2 — PARSED SCHEDULE DATA:
  - STANDARDIZED MILESTONES block — use Variance field directly (pre-computed). Do not recompute.
  - CRITICAL PATH CHAIN — float-ranked, finish/float per step. Narrate the full chain.
  - NEAR-CRITICAL ACTIVITIES — within 10 calendar days of float. Flag proactively.
  - VARIANCE ANALYSIS — phase-grouped deltas. Lead with KEY FINDINGS.
  - SCHEDULE DATA — full activity list with start, finish, float, % complete.
TIER 3 — COMPUTED ESTIMATES (lowest authority, use only when Tier 1 and 2 are unavailable):
  - Any computed compression %, variance, or float estimates derived from raw schedule data.

RELATIONSHIPS BLOCK — HOW TO USE FOR CP TRACING AND DELAY SOURCING:
The context includes a RELATIONSHIPS block in this format:
  Activity ID "Activity Name" → Predecessor ID "Predecessor Name" (FS/SS/FF/SF)
This is the raw predecessor network. Use it to:
1. TRACE CP MANUALLY when the pre-computed chain is shallow (≤2 activities) or flagged with CP WARNING:
   Step 1: Find the contract completion milestone in the SCHEDULE DATA — get its activity ID.
   Step 2: Look up that ID in RELATIONSHIPS — find its predecessor IDs.
   Step 3: For each predecessor, look up its float in SCHEDULE DATA. Pick the one with lowest float (most constrained).
   Step 4: Repeat from Step 2 using that predecessor as the new current activity.
   Step 5: Stop when you reach an activity with no predecessors or an activity that has already started.
   Step 6: Narrate the chain from earliest driver to completion.
2. SOURCE DELAYS to root driver activities:
   Step 1: Find the slipped activity in the VARIANCE ANALYSIS block.
   Step 2: Look up its predecessors in RELATIONSHIPS.
   Step 3: Check each predecessor's finish date in SCHEDULE DATA vs its Prior Update date in MILESTONES.
   Step 4: The predecessor that slipped the most is the delay driver.
   Step 5: Trace one level further if that predecessor also slipped.
   Step 6: Report: "[Activity X] slipped [N] calendar days because its predecessor [Activity Y] finished [N] days late, driven by [root cause activity]."
3. ANSWER ACTIVITY-SPECIFIC CP QUESTIONS:
   "What drives [Activity X]?" → Look up X in RELATIONSHIPS, find predecessors, report names and float.

CP WARNING HANDLING:
If the CRITICAL PATH CHAIN block contains a CP WARNING (chain depth ≤ 2 or disconnected milestone):
- Do NOT report the shallow chain as the full critical path.
- State: "The pre-computed critical path chain is shallow — the schedule data may have unreliable float values or missing predecessor links."
- Then manually trace the chain using the RELATIONSHIPS block per the steps above.
- If manual trace also fails, state: "The predecessor network for this project does not provide a traceable critical path — recommend field verification of schedule logic."

USER-PROVIDED DOCUMENTS — HOW TO USE:
The context may include a USER-PROVIDED DOCUMENTS block containing files uploaded by the user (images, PDFs, notes, dashboard screenshots).
- Treat these as authoritative supplemental context — the user uploaded them intentionally.
- If a document includes a user_note, that note takes priority over your interpretation of the document content.
- Common uses: dashboard screenshots with milestone names to use, PDF excerpts with contract dates, notes clarifying project scope.
- When answering questions, reference uploaded documents if they are relevant: "Based on the uploaded dashboard, the milestone names for this project are..."
- Do NOT ignore uploaded documents. If a user asks about something that appears in an uploaded document, use that document as your primary source.

PRE-COMPUTED VARIANCE — READ DIRECTLY:
Each milestone row in the STANDARDIZED MILESTONES block now includes a pre-computed Variance field in calendar days (e.g., "Variance: +14cd" or "Variance: -7cd").
- Read this value directly. Do not recompute it.
- Positive = slipped. Negative = improved. Zero = no change.
- The Drift field (if present) shows cumulative movement from baseline — use for overall health assessment.
"""

NARRATIVE_STYLE_GUIDE = """
NARRATIVE REPORT FORMAT — STRICT STRUCTURE (Use when report mode is triggered):

You are an expert, executive-level project controls engineer. Analyze schedule updates and produce a highly structured, logic-first narrative report.

### 1. REPORT FORMAT (Exactly 7 sections, in this order, bold headers, plain bullets — no tables)

**Summary**
• State the Contract Completion date and the exact calendar-day variance from the prior plan
• Provide a high-level summary of schedule movement and the primary phase driving the change
• Define the current critical path at a high level

**Milestones**
• List 4-5 key milestones using standard names
• Use MILESTONE FORMATTING RULES exactly: FORMAT A for improved, FORMAT B for delayed, FORMAT C for unchanged. Never use "Slipped", "Maintained", or "acceleration".

**Critical Path Analysis**
• **Current Critical Path:** Trace the driving sequence of activities from data date to completion. Be specific about activity names and flow.
• **Previous Critical Path:** State the driving sequence from the prior update for comparison.

**Schedule Compression**
• Lead with the verified compression % from the COMPRESSION REPORT block if available. Round to the nearest whole number for narrative (e.g., -2.6% → "-3% compression"). State it as the confirmed figure.
• Explain what the % means in plain terms: negative = work pulled earlier / remaining span reduced; positive = work pushed later / span expanded.
• Use the Monthly Activity Days table to identify WHERE work shifted — name the months with the largest positive deltas (work added) and largest negative deltas (work removed). This is the narrative substance.
• Example: "The schedule shows increased remaining work in March, April, and May 2026, while planned work was pulled out of October through December 2026 and January 2027."
• Close with the finish date change if available: "the overall finish improved from [earlier finish] to [later finish]" or "the overall finish slipped from [earlier finish] to [later finish]".
• If no compression PDF is available, use the SCHEDULE COMPRESSION ANALYSIS (Current vs Previous) block — state span delta in calendar days and whether density increased or decreased. Do not invent a % figure.
• Do NOT write multiple bullets for compression — one cohesive 2-3 sentence paragraph is the correct format.

**Variance Analysis**
• Explain the primary source of the critical path shift or completion date variance. Trace it to the specific task level.
• Detail significant anomalies, major slips, or logic quality flags (open-ended activities, float consumption, FRAGNET impacts)
• Summarize why the project maintained, improved, or slipped its final completion date based on delays vs. available float

**Recommendations**
• Provide 1-2 actionable recommendations focused on critical path, near-critical paths, or major logic/constraint risks

**Opportunities**
• Provide 1-2 actionable opportunities to recover time or alleviate trade stacking, citing activities with available float that can be resequenced or run concurrently

### 2. WRITING STYLE RULES
• Use plain, direct language with no fluff
• Keep statements short, clear, and factual
• Do not exaggerate or overstate conclusions
• Avoid vague terms such as "significant" or "material"
• Avoid using dashes unless absolutely necessary (use bullet points)
• Do not overbuild explanations or list unnecessary steps
• Maintain a professional, analytical tone suitable for executive reporting

### 3. ANALYTICAL RULES
• **Logic First:** Prioritize logic and sequence over surface-level date changes
• **Criticality:** Only call an activity "critical" if it directly drives project completion. If an activity has zero float but no successors (open end), flag it as a logic issue, not a critical driver
• **Double-Sourcing:** Every date and calendar-day variance MUST be verified against schedule data (MPP projected finish or PDF reports)
• **Deep Variance Tracing:** Do not stop at surface-level date movement. Run task-level critical path chain to identify the true source of delay (duration extension, predecessor slip, constraint)
• **Negative Float vs. Baseline Variance:** If schedule carries negative float driven by internal constraint, report as context. But TRUE schedule variance must be measured relative to Baseline Completion Date
• **Separation of Movement:** Clearly separate true critical delays from non-impacting movement (slips absorbed by available float)
• **Date Format:** Use MM/DD/YY format at all times (not dashes)
"""

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
    from project_loader import load_all_projects, get_project_context, list_projects, has_schedule, get_project_load_status, ensure_project_loaded, update_milestone_prior_dates
except Exception as _pe:
    logger.warning(f"Project loader not available: {_pe}")
    def load_all_projects(): pass
    def get_project_context(slug, page=None): return ""
    def list_projects(): return []
    def has_schedule(slug): return False
    def get_project_load_status(slug): return {"loaded": False, "loading": False, "message": "Not available"}
    def ensure_project_loaded(slug): return False
    def update_milestone_prior_dates(slug): return 0

try:
    from tracker_loader import load_tracker, get_portfolio_summary
except Exception as _te:
    logger.warning(f"Tracker loader not available: {_te}")
    def load_tracker(): pass
    def get_portfolio_summary(flags): return ""

# Pre-build portfolio summary once at startup — not per-request
_PORTFOLIO_CTX = ""

def _background_startup():
    global _PORTFOLIO_CTX
    try:
        load_tracker()
        logger.info("Project tracker loaded.")
    except Exception as _te:
        logger.warning(f"Tracker load failed in background: {_te}")
    try:
        load_all_projects()
        logger.info("Project buckets loaded.")
    except Exception as _pe:
        logger.warning(f"Project load failed in background: {_pe}")
    try:
        _sched_flags = {p["slug"]: has_schedule(p["slug"]) for p in list_projects()}
        _PORTFOLIO_CTX = get_portfolio_summary(_sched_flags)
        logger.info("Portfolio summary cached.")
    except Exception as _pfe:
        logger.warning(f"Portfolio summary cache failed: {_pfe}")

import threading as _threading
_threading.Thread(target=_background_startup, daemon=True).start()


def _gradual_project_loader():
    """Background thread to gradually load all projects after startup.
    Loads one project every 90 seconds to avoid overwhelming the server.
    """
    import time
    time.sleep(30)  # Wait 30s after startup for things to stabilize
    
    try:
        from project_loader import list_projects, ensure_project_loaded, get_project_load_status
        projects = list_projects()
        logger.info(f"[AutoLoader] Starting gradual load of {len(projects)} projects...")
        
        for i, p in enumerate(projects):
            slug = p["slug"]
            try:
                # Trigger loading (non-blocking)
                is_ready = ensure_project_loaded(slug)
                if is_ready:
                    logger.info(f"[AutoLoader] {i+1}/{len(projects)} {slug}: already cached")
                else:
                    logger.info(f"[AutoLoader] {i+1}/{len(projects)} {slug}: loading started, waiting...")
                    # Wait for this project to finish before starting the next one
                    # Poll every 5s, max 3 minutes per project
                    waited = 0
                    max_wait = 180
                    while waited < max_wait:
                        time.sleep(5)
                        waited += 5
                        status = get_project_load_status(slug)
                        if status.get("loaded"):
                            logger.info(f"[AutoLoader] {i+1}/{len(projects)} {slug}: loaded after {waited}s")
                            break
                        if not status.get("loading"):
                            # Loading thread finished but not in cache — likely failed
                            logger.warning(f"[AutoLoader] {i+1}/{len(projects)} {slug}: loading ended without cache after {waited}s")
                            break
                    else:
                        logger.warning(f"[AutoLoader] {i+1}/{len(projects)} {slug}: timed out after {max_wait}s")
                    # Brief pause between projects to let CPU settle
                    time.sleep(5)
            except Exception as e:
                logger.warning(f"[AutoLoader] Failed to load {slug}: {e}")
                time.sleep(10)  # Brief pause on error
                
        logger.info("[AutoLoader] All projects processed.")
    except Exception as e:
        logger.warning(f"[AutoLoader] Gradual loader failed: {e}")

# Start gradual loader after startup
_threading.Thread(target=_gradual_project_loader, daemon=True).start()


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

# Import encryption helpers (graceful no-op if cryptography not installed or key not set)
try:
    from crypto import read_encrypted_json, write_encrypted_json, write_encrypted_bytes, read_encrypted_bytes, is_enabled as _crypto_enabled
except ImportError:
    def read_encrypted_json(path):
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    def write_encrypted_json(path, obj):
        with open(path, "w", encoding="utf-8") as f: json.dump(obj, f, indent=2, default=str)
    def write_encrypted_bytes(path, data):
        with open(path, "wb") as f: f.write(data)
    def read_encrypted_bytes(path):
        with open(path, "rb") as f: return f.read()
    def _crypto_enabled(): return False

def _load_project_docs(slug: str) -> list:
    """Load persisted docs from disk for a project slug (decrypts if ENCRYPTION_KEY is set)."""
    path = _docs_path(slug)
    if os.path.exists(path):
        try:
            return read_encrypted_json(path)
        except Exception:
            pass
    return []

def _save_project_docs(slug: str):
    """Persist in-memory docs to disk for a project slug (encrypts if ENCRYPTION_KEY is set)."""
    path = _docs_path(slug)
    try:
        write_encrypted_json(path, _project_docs.get(slug, []))
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

# Scraper disabled — MPP/XER parsing replaces Power BI screenshotting
# scraper_thread = threading.Thread(target=background_scraper, daemon=True)
# scraper_thread.start()

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page — accepts shared APP_PASSWORD from environment."""
    if not _APP_PASSWORD:
        # Auth disabled in dev mode — go straight to app
        return redirect(url_for("index"))
    if session.get("authenticated"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == _APP_PASSWORD:
            session.permanent = True
            session["authenticated"] = True
            return redirect(url_for("index"))
        else:
            error = "Incorrect password. Please try again."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@require_auth
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    """Health check — no auth required so Render uptime checks work."""
    return "ok", 200

@app.route("/context", methods=["GET"])
@require_auth
def view_context():
    """Debug endpoint to inspect current dashboard context."""
    ctx = load_context()
    if not ctx:
        return jsonify({"status": "empty", "context": None})
    return jsonify({"status": "loaded", "context": ctx[:3000]})

@app.route("/context-debug/<slug>", methods=["GET"])
@require_auth
def context_debug(slug):
    """
    Returns the full system prompt that would be sent to GPT-4o for a given project.
    Use this to diagnose why the agent missed a milestone, ignored a PDF, or produced
    a shallow CP chain. Shows every block: SYSTEM_BASE, portfolio context, milestone
    block, CP chain, near-critical table, variance, relationships, verify/variance/
    compression PDFs, and user-uploaded documents.
    """
    page_view = request.args.get("page", None)

    system = SYSTEM_BASE

    if _PORTFOLIO_CTX:
        system += f"\n\n{_PORTFOLIO_CTX}"

    dashboard_context = load_context()
    if dashboard_context:
        system += f"\n\n{dashboard_context}"

    proj_ctx = get_project_context(slug, page_view)
    if proj_ctx:
        system += f"\n\n{proj_ctx}"

    docs_ctx = _get_project_docs_context(slug)
    if docs_ctx:
        system += f"\n\n{docs_ctx}"

    # Build a summary of what blocks are present
    blocks_present = []
    block_markers = [
        ("STANDARDIZED MILESTONES", "Milestone block"),
        ("CRITICAL PATH CHAIN", "CP chain"),
        ("CRITICAL PATH SHIFT", "CP shift comparison"),
        ("NEAR-CRITICAL ACTIVITIES", "Near-critical table"),
        ("VARIANCE ANALYSIS", "Variance analysis"),
        ("RELATIONSHIPS", "Relationships block"),
        ("ACTIVITY VERIFICATION REFERENCE", "Verify PDF"),
        ("VARIANCE REPORT PDF", "Variance PDF"),
        ("COMPRESSION REPORT", "Compression PDF"),
        ("USER-PROVIDED DOCUMENTS", "User-uploaded docs"),
        ("RISK FLAGS", "Risk flags"),
    ]
    for marker, label in block_markers:
        blocks_present.append({"block": label, "present": marker in system})

    return jsonify({
        "project_slug": slug,
        "page_view": page_view,
        "total_chars": len(system),
        "estimated_tokens": len(system) // 4,
        "blocks": blocks_present,
        "full_system_prompt": system
    })


@app.route("/projects", methods=["GET"])
@require_auth
def get_projects():
    """Returns list of all projects and their pages for the dropdown.
    Includes cache status: cached (bool), loading (bool) for UI indicators.
    """
    from project_loader import _project_cache, _loading_in_progress
    projects = list_projects()
    for p in projects:
        slug = p["slug"]
        p["has_schedule"] = has_schedule(slug)
        # Cache status for UI indicators
        p["cached"] = slug in _project_cache and _project_cache[slug]
        p["loading"] = slug in _loading_in_progress
    return jsonify({"projects": projects})


@app.route("/project/load/<slug>", methods=["POST"])
def trigger_project_load(slug):
    """Trigger loading of a project's schedule data and return status.
    Call this immediately when user selects a project from dropdown.
    """
    try:
        # Trigger loading (non-blocking, starts background thread if needed)
        is_ready = ensure_project_loaded(slug)
        # Get current status with ETA
        status = get_project_load_status(slug)
        return jsonify({
            "slug": slug,
            "ready": is_ready,
            **status
        })
    except Exception as e:
        logger.error(f"Error triggering load for {slug}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/project/status/<slug>", methods=["GET"])
def get_project_status(slug):
    """Get current loading status and ETA for a project without triggering load."""
    try:
        status = get_project_load_status(slug)
        return jsonify({"slug": slug, **status})
    except Exception as e:
        logger.error(f"Error getting status for {slug}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/screenshot/<int:page_num>", methods=["GET"])
@require_auth
def view_screenshot(page_num):
    """Debug endpoint to view the screenshot Playwright captured for a given page."""
    path = f"/tmp/screenshot_page_{page_num}.png"
    if not os.path.exists(path):
        return f"No screenshot found for page {page_num}. Run /scrape first.", 404
    return send_file(path, mimetype="image/png")

@app.route("/upload", methods=["POST"])
@require_auth
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
    
    # Get optional project_slug from form data (for compression PDF association)
    project_slug = request.form.get("project_slug", "")

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

        # --- Auto-snapshot prior dates before a new update_N schedule file is saved ---
        # This ensures the current forecast is preserved as prior_update_date before
        # the new update overwrites it as "current". Fires only for schedule files
        # with update_N naming convention uploaded to a known project.
        import re as _re_up
        _is_schedule_ext = ext in (".mpp", ".xml", ".xer")
        _is_update_file = bool(_re_up.match(r'^update[_\-]\d+', f.filename.lower()))
        # --- Save raw schedule file to project folder so parser picks it up as current ---
        _saved_to_disk = False
        _saved_path = None
        if project_slug and _is_schedule_ext:
            try:
                _proj_dir = os.path.join(_here, "projects", project_slug)
                if os.path.isdir(_proj_dir):
                    # Snapshot prior dates BEFORE saving the new file (so current becomes previous)
                    if _is_update_file:
                        try:
                            snapped = update_milestone_prior_dates(project_slug)
                            if snapped:
                                logger.info(f"[{project_slug}] Auto-snapped prior_update_date for {snapped} milestones before loading {f.filename}")
                        except Exception as _snap_e:
                            logger.warning(f"[{project_slug}] prior_update_date snapshot failed: {_snap_e}")
                    # Save the raw file to the project bucket (encrypted if ENCRYPTION_KEY is set)
                    _saved_path = os.path.join(_proj_dir, f.filename)
                    with open(tmp_path, "rb") as _raw_fh:
                        _raw_bytes = _raw_fh.read()
                    write_encrypted_bytes(_saved_path, _raw_bytes)
                    _saved_to_disk = True
                    logger.info(f"[{project_slug}] Saved schedule file to project folder: {_saved_path} (encrypted={_crypto_enabled()})")
                    # Reload all projects so the new file is picked up immediately
                    try:
                        load_all_projects()
                        logger.info(f"[{project_slug}] Project context reloaded after new schedule file upload")
                    except Exception as _rel_e:
                        logger.warning(f"[{project_slug}] Reload after upload failed: {_rel_e}")
                else:
                    logger.warning(f"[{project_slug}] Project folder not found — file not saved to disk: {_proj_dir}")
            except Exception as _disk_e:
                logger.warning(f"[{project_slug}] Failed to save schedule file to project folder: {_disk_e}")
        elif project_slug and _is_schedule_ext and _is_update_file:
            # Fallback: snapshot only (no project folder found)
            try:
                snapped = update_milestone_prior_dates(project_slug)
                if snapped:
                    logger.info(f"[{project_slug}] Auto-snapped prior_update_date for {snapped} milestones before loading {f.filename}")
            except Exception as _snap_e:
                logger.warning(f"[{project_slug}] prior_update_date snapshot failed: {_snap_e}")

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
                "saved_to_project": True,
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
@require_auth
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
@require_auth
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
@require_auth
def clear_project_docs(slug):
    """Clear all user-uploaded documents for a project."""
    _project_docs[slug] = []
    _save_project_docs(slug)
    return jsonify({"status": "cleared", "project_slug": slug})


def _handle_compression_pdf_upload(f, project_slug: str) -> tuple:
    """Handle compression PDF upload - extract data and cache it."""
    import tempfile
    import os
    from datetime import datetime
    
    # Import compression cache module
    try:
        from compression_cache import save_compression_data, extract_update_number_from_filename
    except ImportError:
        return jsonify({"error": "Compression cache module not available"}), 500
    
    # Import PDF extraction
    try:
        from project_loader import _extract_compression_pdf
    except ImportError:
        return jsonify({"error": "PDF extraction not available"}), 500
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        
        # Extract compression data from PDF
        comp_data = _extract_compression_pdf(tmp_path)
        
        if not comp_data:
            return jsonify({"error": "Could not extract compression data from PDF. Ensure it's a Schedule Compression report from the validator."}), 400
        
        if comp_data.get("compression_pct") is None:
            return jsonify({"error": "No compression percentage found in PDF. Check if this is a valid compression report."}), 400
        
        # Determine project slug and update number
        slug = project_slug.strip() if project_slug else None
        if not slug:
            # Try to infer from filename
            slug = _infer_project_from_filename(f.filename)
        
        if not slug:
            return jsonify({"error": "Could not determine project. Please select a project from the dropdown first, or include the project name in the filename."}), 400
        
        # Get update number: user-provided from form > auto-detect from filename > default to 1
        form_update_num = request.form.get("update_num", "").strip()
        if form_update_num:
            try:
                update_num = int(form_update_num)
            except ValueError:
                update_num = extract_update_number_from_filename(f.filename) or 1
        else:
            update_num = extract_update_number_from_filename(f.filename) or 1
        
        # Add metadata
        comp_data["filename"] = f.filename
        comp_data["uploaded_at"] = datetime.now().isoformat()
        
        # Save to cache
        success = save_compression_data(slug, update_num, comp_data)
        
        if not success:
            return jsonify({"error": "Failed to save compression data"}), 500
        
        # Build response context
        context_lines = [
            f"=== COMPRESSION REPORT UPLOADED ===",
            f"Project: {slug}",
            f"Update: {update_num}",
            f"Compression: {comp_data['compression_pct']:+d}%",
        ]
        if comp_data.get("earlier_finish") and comp_data.get("later_finish"):
            context_lines.append(f"Finish dates: {comp_data['earlier_finish']} → {comp_data['later_finish']}")
        if comp_data.get("earlier_data_date") and comp_data.get("later_data_date"):
            context_lines.append(f"Data dates: {comp_data['earlier_data_date']} → {comp_data['later_data_date']}")
        
        return jsonify({
            "context": "\n".join(context_lines),
            "filename": f.filename,
            "project_slug": slug,
            "update_num": update_num,
            "compression_pct": comp_data["compression_pct"],
            "message": f"Compression report saved for {slug} Update {update_num}. You can now ask about compression analysis."
        })
        
    except Exception as e:
        logger.error(f"Compression PDF upload failed: {e}")
        return jsonify({"error": f"Failed to process compression PDF: {str(e)}"}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _infer_project_from_filename(filename: str) -> Optional[str]:
    """Try to infer project slug from filename."""
    lowered = filename.lower()
    
    # Map known project keywords to slugs
    project_keywords = {
        "anaheim": "anaheim_ca",
        "anna": "anna_tx",
        "aventura": "aventura_fl",
        "baltimore": "baltimore_md",
        "cary": "cary_nc",
        "clayton": "clayton_nc",
        "fairfax": "fairfax_va",
        "fayetteville": "fayetteville_nc",
        "frisco": "frisco_tx",
        "lakeland": "lakeland_fl",
        "melbourne": "melbourne_fl",
        "meridian": "meridian_id",
    }
    
    for keyword, slug in project_keywords.items():
        if keyword in lowered:
            return slug
    
    return None

@app.route("/scrape", methods=["POST"])
@require_auth
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
@require_auth
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

    # Portfolio overview — rebuild with current health data on each request
    try:
        from tracker_loader import get_portfolio_summary
        from project_loader import has_schedule, list_projects
        _sched_flags = {p["slug"]: has_schedule(p["slug"]) for p in list_projects()}
        _fresh_portfolio = get_portfolio_summary(_sched_flags)
        if _fresh_portfolio:
            system += f"\n\n{_fresh_portfolio}"
    except Exception as _e:
        # Fallback to cached version if dynamic build fails
        if _PORTFOLIO_CTX:
            system += f"\n\n{_PORTFOLIO_CTX}"

    if dashboard_context:
        system += f"\n\n{dashboard_context}"

    if project_slug:
        logger.info(f"Chat request — project: {project_slug}, page: {page_view}")
        proj_ctx = get_project_context(project_slug, page_view)
        has_data = has_schedule(project_slug)
        logger.info(f"[{project_slug}] Context assembled — schedule data: {'yes' if has_data else 'no'}")
        if proj_ctx:
            system += f"\n\n{proj_ctx}"

        # Inject project-scoped user-uploaded documents
        docs_ctx = _get_project_docs_context(project_slug)
        if docs_ctx:
            system += f"\n\n{docs_ctx}"

    if context:
        system += f"\n\nUSER-PROVIDED CONTEXT:\n{context}"

    # Detect report mode and append narrative style guide for consistent formatting
    REPORT_TRIGGERS = ("generate report", "draft narrative", "write the narrative", "generate narrative", "re-draft ", "[report mode]")
    last_user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    last_user_lower = last_user_msg.lower() if isinstance(last_user_msg, str) else ""
    is_report_mode = any(t in last_user_lower for t in REPORT_TRIGGERS)
    if is_report_mode:
        system += f"\n\n{NARRATIVE_STYLE_GUIDE}"
        logger.info(f"[{project_slug or 'no-project'}] Report mode triggered — narrative style guide appended")

    full_messages = [{"role": "system", "content": system}] + messages[-30:]
    selected_model = "gpt-5.4"

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
            model=selected_model,
            messages=full_messages,
            temperature=0.5 if is_report_mode else 0.3,
            timeout=60 if is_report_mode else 25
        )
        return jsonify({"reply": response.choices[0].message.content})
    except openai.APITimeoutError:
        logger.warning(f"OpenAI timeout for project {project_slug}")
        return jsonify({"error": "__timeout__"}), 504
    except Exception as e:
        logger.error(f"Chat error for project {project_slug}: {type(e).__name__}: {e}", exc_info=True)
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
