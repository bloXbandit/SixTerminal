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

CONTEXT_DIR = "/tmp/dashboard_cache"
CONTEXT_FILE = "/tmp/dashboard_context.json"

PAGE_LABELS = {
    1: "Landing Page – Project Overview & Milestones",
    2: "Risk Report",
    3: "Schedule Performance Report",
    4: "Calendar View",
    5: "Schedule Detail",
}

VISION_PROMPT = """Please read all the text and numbers visible in this image and return them as a JSON object.

I need the following fields if visible:
- page_title: the title or name of the page/report shown
- project: the project name shown
- filters_active: any filter or dropdown selections visible
- kpis: key metrics shown as cards (dates, percentages, day counts)
- milestones: any table rows showing milestone names, dates, and variance values
- risks: any risk items listed
- other_data: anything else visible on the page

Return ONLY valid JSON. No markdown fences, no explanation.
If a field has no data, use an empty array or object for it.
Example: {"page_title": "Overview", "project": "Anaheim", "kpis": {}, "milestones": [], "risks": [], "filters_active": {}, "other_data": {}}"""


def _extract_page_label(page_obj, page_num: int) -> str:
    """Try to read the ACTIVE page tab label from the Power BI nav."""
    try:
        selectors = [
            "[aria-selected='true'] span",
            ".navItem.active span",
            ".reportPageName.selected",
            "[class*='active'] .reportPageName",
        ]
        for sel in selectors:
            el = page_obj.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    return text
        tabs = page_obj.query_selector_all(".reportPageName, [data-testid='page-tab'] span")
        if tabs and page_num - 1 < len(tabs):
            text = tabs[page_num - 1].inner_text().strip()
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
        page.wait_for_timeout(20000)
        try:
            page.wait_for_selector(
                "visual-container, .visualContainer, [class*='visual'], iframe[title]",
                timeout=20000
            )
            logger.info("Power BI visuals detected in DOM.")
        except Exception:
            logger.warning("Visual selector not found — proceeding with screenshot anyway.")
        page.wait_for_timeout(5000)

        for page_num in range(1, 6):
            try:
                label = _extract_page_label(page, page_num)
                logger.info(f"Scraping page {page_num}: {label}")

                screenshot_bytes = page.screenshot(full_page=False)
                screenshot_path = f"/tmp/screenshot_page_{page_num}.png"
                with open(screenshot_path, "wb") as sf:
                    sf.write(screenshot_bytes)
                logger.info(f"Screenshot saved → {screenshot_path} ({len(screenshot_bytes)} bytes)")
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
