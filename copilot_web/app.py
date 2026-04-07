from flask import Flask, render_template, request, jsonify
import openai
import os
import threading
import time
import logging

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

FALLBACK_CONTEXT = """
=== DASHBOARD DATA (Public Storage – Anaheim, CA) ===
Type: Construction | Region: West Coast | Responsible: Josh Pait | Data Date: Jan 8, 2026
Baseline Completion: 11/6/2026 | Current Completion: 1/11/2027
Schedule Variance: -66 days (Worsening) | Work Compression: -17.00% — NORMAL

CRITICAL PATH MILESTONES:
- Foundation Complete: Baseline 12/18/2025 → Current 2/27/2026 | Var: -71d | Delayed–Slipping
- 1st Floor Finishes Complete: 4/14/2026 → 6/19/2026 | Var: -66d | Delayed–Slipping
- 2nd Floor Finishes Complete: 5/15/2026 → 7/28/2026 | Var: -74d | Delayed–Slipping
- Structure Top Out: 6/2/2026 → 8/14/2026 | Var: -73d | Delayed–Slipping
- 3rd Floor Finishes Complete: 6/15/2026 → 8/25/2026 | Var: -71d | Delayed–Slipping
- 4th Floor Finishes Complete: 7/8/2026 → 9/16/2026 | Var: -70d | Delayed–Slipping
- Finish Electrical 5th Fl & Roof: 8/6/2026 → 10/15/2026 | Var: -70d | Delayed–Slipping
- Weather Tight: 8/28/2026 → 11/10/2026 | Var: -74d | Delayed–Slipping
- Hardscape/Landscape Complete: 10/9/2026 → 12/23/2026 | Var: -75d | Delayed–Slipping
- Elevator Complete: 10/15/2026 → 12/31/2026 | Var: -77d | Delayed–Slipping
- Contract Completion: 11/6/2026 → 1/11/2027 | Var: -66d | Delayed–Slipping
"""

SYSTEM_BASE = """You are Stelic Copilot, an expert AI assistant embedded in a Power BI construction project controls dashboard.
You specialize in Primavera P6 schedules, milestone tracking, schedule variance, critical path analysis, DCMA metrics, and project risk.
Be concise, professional, and dashboard-appropriate. Use bullet points for lists. Keep responses tight — this is a side panel, not a report.
Never make up data beyond what is provided. If you don't have specific data, say so clearly."""

SCRAPER_AVAILABLE = False
try:
    from scraper import load_context, scrape_and_extract
    SCRAPER_AVAILABLE = True
    logger.info("Scraper module loaded successfully.")
except ImportError:
    logger.warning("Scraper module not available — running without auto-context.")
    def load_context(): return ""
    def scrape_and_extract(): return {}

def background_scraper(interval_seconds=1800):
    """Runs scraper every interval_seconds (default 30 min) in a background thread."""
    if not SCRAPER_AVAILABLE:
        return
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

    client = get_client()
    if not client:
        return jsonify({"error": "No API key configured."}), 500

    dashboard_context = load_context() or FALLBACK_CONTEXT

    system = SYSTEM_BASE + f"\n\n{dashboard_context}"
    if context:
        system += f"\n\nUSER-PROVIDED CONTEXT:\n{context}"

    full_messages = [{"role": "system", "content": system}] + messages[-10:]

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=full_messages,
            temperature=0.3
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
