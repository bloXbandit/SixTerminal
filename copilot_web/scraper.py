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

CONTEXT_FILE = os.path.join(os.path.dirname(__file__), "dashboard_context.json")


def scrape_and_extract() -> dict:
    """
    Opens the Power BI public embed URL in a headless browser,
    screenshots each report page, sends to GPT-4 Vision,
    and returns structured dashboard context as a dict.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("No OPENAI_API_KEY set — scraper cannot run.")
        return {}

    client = openai.OpenAI(api_key=api_key)
    pages_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        logger.info("Opening Power BI embed URL...")
        page.goto(PBI_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        for page_num in range(1, 6):
            try:
                logger.info(f"Scraping page {page_num}...")
                screenshot_bytes = page.screenshot(full_page=False)
                b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")

                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "This is a screenshot of a Power BI construction project dashboard. "
                                        "Extract ALL visible data precisely — project name, type, region, responsible person, "
                                        "baseline completion date, current completion date, schedule variance (days), "
                                        "work compression percentage, and the full milestone table with all columns "
                                        "(milestone name, baseline date, previous date, current date, variance days, trend, status). "
                                        "Return as structured JSON only, no markdown, no explanation."
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{b64_image}", "detail": "high"},
                                },
                            ],
                        }
                    ],
                    max_tokens=2000,
                )

                raw = response.choices[0].message.content.strip()
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"raw_text": raw}

                pages_data.append({"page": page_num, "data": parsed})

                next_btn = page.query_selector("button[aria-label='Next page']") or \
                           page.query_selector(".navigation-next") or \
                           page.query_selector("[title='Next Page']")
                if next_btn:
                    next_btn.click()
                    page.wait_for_timeout(4000)
                else:
                    break

            except Exception as e:
                logger.warning(f"Page {page_num} scrape failed: {e}")
                break

        browser.close()

    result = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "pages": pages_data,
    }

    with open(CONTEXT_FILE, "w") as f:
        json.dump(result, f, indent=2)

    logger.info(f"Dashboard context saved to {CONTEXT_FILE}")
    return result


def load_context() -> str:
    """
    Load the cached dashboard context as a formatted string for the system prompt.
    Returns empty string if no context file exists.
    """
    if not os.path.exists(CONTEXT_FILE):
        return ""

    try:
        with open(CONTEXT_FILE, "r") as f:
            data = json.load(f)

        scraped_at = data.get("scraped_at", "unknown")
        pages = data.get("pages", [])

        lines = [f"=== LIVE DASHBOARD DATA (scraped {scraped_at}) ==="]
        for p in pages:
            lines.append(f"\n--- Page {p['page']} ---")
            d = p.get("data", {})
            if "raw_text" in d:
                lines.append(d["raw_text"])
            else:
                lines.append(json.dumps(d, indent=2))

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to load context file: {e}")
        return ""
