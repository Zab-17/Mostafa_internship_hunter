"""
Generic Playwright walker — works on any careers portal, Wuzzuf, and LinkedIn.

Two functions:
- collect_job_urls(listing_url) -> list of detail URLs found on the listing page
- fetch_job(url) -> {title, posted, age_days, description, location_text, is_open}

The walker is dumb. It does NOT decide if a job is relevant — that's Mostafa's job.
It just opens the page, scrolls/paginates, reads the live DOM, returns text.
"""
import re
from urllib.parse import urljoin
from agent.browser import get_page


JOB_URL_PATTERNS = [
    "/job/", "/jobs/", "/careers/", "/requisition", "JobDetail",
    "jobId=", "job_id=", "/opportunity/", "/internship/", "/position/",
    "/openings/", "/vacancy/",
]


def parse_age_days(text: str) -> int:
    if not text:
        return -1
    text = text.lower()
    if "today" in text or "hour" in text or "minute" in text:
        return 0
    m = re.search(r"(\d+)\s*(day|week|month)", text)
    if not m:
        return -1
    n, unit = int(m.group(1)), m.group(2)
    return {"day": n, "week": n * 7, "month": n * 30}[unit]


async def collect_job_urls(listing_url: str, max_urls: int = 50) -> list[str]:
    """Open a careers listing page, scroll/paginate, collect every job-detail href."""
    page = await get_page()
    try:
        await page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        await page.close()
        print(f"  ! goto failed: {str(e)[:100]}")
        return []
    await page.wait_for_timeout(3000)

    # Scroll to load lazy content
    for _ in range(6):
        await page.mouse.wheel(0, 4000)
        await page.wait_for_timeout(700)

    # Click "load more" / "show more" buttons up to 5 times
    for _ in range(5):
        try:
            btn = page.locator("button:has-text('more'), button:has-text('Load'), button:has-text('Show')").first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                await page.wait_for_timeout(1500)
            else:
                break
        except Exception:
            break

    anchors = await page.query_selector_all("a")
    urls = set()
    for a in anchors:
        href = await a.get_attribute("href")
        if not href:
            continue
        if any(p in href for p in JOB_URL_PATTERNS):
            if href.startswith("/"):
                href = urljoin(listing_url, href)
            href = href.split("#")[0]
            if "search" in href.lower() or "results" in href.lower():
                continue
            urls.add(href)
        if len(urls) >= max_urls:
            break

    await page.close()
    return list(urls)


async def fetch_job(url: str) -> dict | None:
    """Open one job detail page and return {title, description, posted, age_days, location_text, is_open}."""
    page = await get_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)

        title_el = await page.query_selector("h1")
        title = (await title_el.inner_text()) if title_el else url

        body = await page.locator("body").inner_text()

        # Try to grab description + requirements as separate sections; fall back to body
        description = ""
        requirements = ""
        for sel in ["[class*='description']", "[class*='Description']",
                    "[id*='description']", "[data-automation-id*='jobPostingDescription']",
                    "section:has(h2:has-text('Description'))",
                    "section:has(h2:has-text('About'))"]:
            try:
                el = await page.query_selector(sel)
                if el:
                    description = await el.inner_text()
                    if len(description) > 200:
                        break
            except Exception:
                pass
        for sel in ["[class*='requirement']", "[class*='Requirement']", "[class*='qualifications']",
                    "[class*='Qualifications']",
                    "section:has(h2:has-text('Requirements'))",
                    "section:has(h2:has-text('Qualifications'))"]:
            try:
                el = await page.query_selector(sel)
                if el:
                    requirements = await el.inner_text()
                    if len(requirements) > 100:
                        break
            except Exception:
                pass

        full_text = (description + "\n\n" + requirements).strip()
        if len(full_text) < 300:
            full_text = body

        age_match = re.search(
            r"(?:posted|published|date)\D{0,30}(\d+\s*(?:day|week|month)s?\s*ago|today)",
            body, re.I,
        )
        posted = age_match.group(1) if age_match else ""
        age_days = parse_age_days(posted) if posted else -1

        is_closed = bool(re.search(
            r"no longer accepting|position closed|requisition closed|expired|not accepting applications",
            body, re.I,
        ))

        await page.close()
        return {
            "url": url,
            "title": title.strip()[:200],
            "posted": posted or "date not shown",
            "age_days": age_days,
            "description": full_text[:6000],
            "location_text": (body[:500]).replace("\n", " "),
            "is_open": not is_closed,
        }
    except Exception as e:
        try:
            await page.close()
        except Exception:
            pass
        print(f"  ! fetch failed {url}: {str(e)[:100]}")
        return None
