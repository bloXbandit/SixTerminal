import os
import json
import base64
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright
import openai

logger = logging.getLogger(__name__)

PBI_URL = (
    "https://app.powerbi.com/view?r=eyJrIjoiZGY0MGRiMzUtYjNjYS00ZjUwLWE4NGUtZDUxZjNmNzk3"
    "OWYzIiwidCI6IjNjMDI3MWIxLWNjMWQtNGRlZC05ZWFlLWQwYzVlNDViZmExNiIsImMiOjZ9"
)

CONTEXT_DIR = os.path.join(os.path.dirname(__file__), "dashboard_cache")
CONTEXT_FILE = os.path.join(os.path.dirname(__file__), "dashboard_context.json")

PAGE_LABELS = {
    1: "Landing Page – Project Overview & Milestones",
    2: "Risk Report",
    3: "Schedule Performance Report",
    4: "Calendar View",
    5: "Schedule Detail",
}

VISION_PROMPT = """This is a screenshot of a Power BI construction project dashboard page.
Extract ALL visible data as precisely as possible including:
- Page title or type (e.g. Landing Page, Risk Report, Schedule, Calendar)
- Project name, type, region, responsible person, data date
- All KPI cards (baseline date, current date, variance days, work compression %)
- Full milestone/activity tables with ALL columns and ALL rows visible
- Any risk items, schedule metrics, or other visible data
- Any filter selections currently active (e.g. selected project name)

Return ONLY a JSON object with this structure:
{
  "page_title": "...",
  "project": "...",
  "filters_active": {...},
  "kpis": {...},
  "milestones": [...],
  "risks": [...],
  "other_data": {...}
}
No markdown, no explanation, just the JSON."""


def _extract_page_label(page_obj, page_num: int) -> str:
    """Try to read the active page tab label from the Power BI nav."""
    try:
        tabs = page_obj.query_selector_all(".reportPageName, [data-testid='page-tab'] span, .pageNavigation span")
        for i, tab in enumerate(tabs):
            text = tab.inner_text().strip()
            if text:
                return text
    except Exception:
        pass
    return PAGE_LABELS.get(page_num, f"Page {page_num}")


def scrape_and_extract() -> dict:
    """
    Opens the Power BI public embed URL, navigates all pages,
    screenshots each, sends to GPT-4 Vision, saves per-page JSON buckets
    and a combined context file.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("No OPENAI_API_KEY — scraper cannot run.")
        return {}

    os.makedirs(CONTEXT_DIR, exist_ok=True)
    client = openai.OpenAI(api_key=api_key)
    all_pages = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        logger.info("Opening Power BI embed URL...")
        page.goto(PBI_URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(15000)

        for page_num in range(1, 6):
            try:
                label = _extract_page_label(page, page_num)
                logger.info(f"Scraping page {page_num}: {label}")

                screenshot_bytes = page.screenshot(full_page=False)
                b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")

                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{b64_image}",
                                "detail": "high"
                            }},
                        ],
                    }],
                    max_tokens=2500,
                )

                raw = response.choices[0].message.content.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]

                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"raw_text": raw}

                parsed["_page_num"] = page_num
                parsed["_page_label"] = label
                parsed["_scraped_at"] = datetime.utcnow().isoformat() + "Z"

                bucket_file = os.path.join(CONTEXT_DIR, f"page_{page_num}.json")
                with open(bucket_file, "w") as f:
                    json.dump(parsed, f, indent=2)

                all_pages.append(parsed)
                logger.info(f"Page {page_num} saved → {bucket_file}")

                next_btn = (
                    page.query_selector("button[aria-label='Next page']") or
                    page.query_selector(".navigation-next") or
                    page.query_selector("[title='Next Page']") or
                    page.query_selector("button[title='Next page']")
                )
                if next_btn:
                    next_btn.click()
                    page.wait_for_timeout(5000)
                else:
                    logger.info("No next page button found — stopping pagination.")
                    break

            except Exception as e:
                logger.warning(f"Page {page_num} scrape failed: {e}")
                break

        browser.close()

    combined = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "total_pages": len(all_pages),
        "pages": all_pages,
    }

    with open(CONTEXT_FILE, "w") as f:
        json.dump(combined, f, indent=2)

    logger.info(f"Combined context saved → {CONTEXT_FILE} ({len(all_pages)} pages)")
    return combined


def load_context() -> str:
    """
    Load all scraped page buckets and assemble into an organized
    system prompt block, grouped by page/project.
    Returns empty string if nothing scraped yet.
    """
    if not os.path.exists(CONTEXT_FILE):
        return ""

    try:
        with open(CONTEXT_FILE, "r") as f:
            data = json.load(f)

        scraped_at = data.get("scraped_at", "unknown")
        pages = data.get("pages", [])
        if not pages:
            return ""

        lines = [f"=== LIVE POWER BI DASHBOARD DATA (last scraped: {scraped_at}) ==="]
        lines.append("The following data was automatically extracted from the Power BI report.")
        lines.append("Use this to answer questions about projects, schedules, milestones, and risks.\n")

        for pg in pages:
            label = pg.get("_page_label", f"Page {pg.get('_page_num', '?')}")
            project = pg.get("project", "")
            lines.append(f"--- {label} ---")
            if project:
                lines.append(f"Project: {project}")

            kpis = pg.get("kpis", {})
            if kpis:
                lines.append("KPIs: " + json.dumps(kpis))

            milestones = pg.get("milestones", [])
            if milestones:
                lines.append(f"Milestones ({len(milestones)} total):")
                for m in milestones:
                    lines.append("  " + json.dumps(m))

            risks = pg.get("risks", [])
            if risks:
                lines.append(f"Risks ({len(risks)} items):")
                for r in risks:
                    lines.append("  " + json.dumps(r))

            other = pg.get("other_data", {})
            if other:
                lines.append("Other: " + json.dumps(other))

            raw = pg.get("raw_text", "")
            if raw:
                lines.append(raw[:1000])

            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to load context: {e}")
        return ""
