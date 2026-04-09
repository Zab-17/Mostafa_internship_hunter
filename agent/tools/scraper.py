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
    "/job/", "/jobs/", "/careers/", "/career/", "/requisition", "/req/",
    "JobDetail", "jobdetail", "jobId=", "job_id=", "JobID=", "reqId=",
    "/opportunity/", "/opportunities/", "/internship/", "/position/",
    "/positions/", "/openings/", "/opening/", "/vacancy/", "/vacancies/",
    "/posting/", "/postings/", "/role/", "/roles/", "/listing/",
    # ATS-specific
    "greenhouse.io/", "lever.co/", "ashbyhq.com/", "workable.com/",
    "myworkdayjobs.com/", "smartrecruiters.com/", "icims.com/jobs/",
    "successfactors.com/career", "taleo.net/careersection",
]

# Per-ATS job-link selectors. Mostafa tries these in order.
# Adding more here is the cheapest way to fix "0 URLs" portals.
ATS_JOB_SELECTORS = [
    # Workday
    'a[data-automation-id="jobTitle"]',
    # Greenhouse
    "a.opening__link", ".opening a", "div.opening a",
    # Lever
    "a.posting-title", "a[href*='jobs.lever.co']",
    # SmartRecruiters
    'a[data-test="job-link"]', "a.job-title-link",
    # Phenom (Valeo, Dell, Honeywell, Synopsys, Cisco, Accenture, Capgemini, etc.)
    "a.job-title-link", "a.list-job-link", ".job-title a",
    # Eightfold (Ericsson)
    "a.position-title-link", ".position-card a",
    # SuccessFactors (Schneider, EY, Honeywell)
    "a[id*='jobTitle']", "a.jobTitle-link",
    # iCIMS
    "a.iCIMS_Anchor", ".iCIMS_JobsTable a",
    # Avature (Vodafone)
    ".jobTitle-link", "a[href*='/jobdetail']",
    # Ashby
    "a[href*='/jobs/']",
    # Workable
    "a.styles__job-link",
    # Generic fallbacks
    "h2 a", "h3 a", "article a", ".job-listing a",
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
    """
    Open a careers listing page, wait for SPA content, scroll/paginate,
    and collect every job-detail href found via either ATS-specific selectors
    or the generic anchor sweep.
    """
    page = await get_page()
    try:
        # Two-stage navigation: domcontentloaded first (fast fail on DNS/cert),
        # then wait for network idle so SPAs have a chance to render.
        try:
            await page.goto(listing_url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"  ! goto failed: {str(e)[:120]}")
            await page.close()
            return []

        # Wait for SPAs to populate. Try networkidle, fall back to fixed wait.
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            await page.wait_for_timeout(4000)

        # Try to wait for ANY known ATS job selector to appear (proves jobs loaded)
        for sel in ATS_JOB_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=2000)
                break
            except Exception:
                continue

        # Scroll aggressively to load lazy content (some portals lazy-load on scroll)
        for _ in range(8):
            await page.mouse.wheel(0, 5000)
            await page.wait_for_timeout(600)

        # Click "load more" / "show more" / "next page" buttons up to 6 times
        for _ in range(6):
            try:
                btn = page.locator(
                    "button:has-text('Load more'), button:has-text('Show more'), "
                    "button:has-text('See more'), button:has-text('More results'), "
                    "a:has-text('Next'), button[aria-label*='next' i]"
                ).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await page.wait_for_timeout(2000)
                else:
                    break
            except Exception:
                break

        urls: set[str] = set()

        # 1) Try ATS-specific selectors first (high precision)
        for sel in ATS_JOB_SELECTORS:
            try:
                els = await page.query_selector_all(sel)
                for el in els:
                    href = await el.get_attribute("href")
                    if href:
                        urls.add(_normalize(href, listing_url))
            except Exception:
                continue

        # 2) Fall back to generic anchor sweep with broad URL patterns
        anchors = await page.query_selector_all("a")
        for a in anchors:
            href = await a.get_attribute("href")
            if not href:
                continue
            if any(p in href for p in JOB_URL_PATTERNS):
                normalized = _normalize(href, listing_url)
                if normalized:
                    urls.add(normalized)
            if len(urls) >= max_urls * 2:
                break

        # 3) JavaScript fallback — for hash-router SPAs that don't expose hrefs
        # to query_selector_all (rare but happens with old Backbone/Knockout sites)
        try:
            js_hrefs = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                    .map(a => a.href)
                    .filter(h => h && (h.includes('/job') || h.includes('/req') || h.includes('jobid') || h.includes('JobID')))
            """)
            for h in js_hrefs:
                normalized = _normalize(h, listing_url)
                if normalized:
                    urls.add(normalized)
        except Exception:
            pass

        await page.close()
        # Filter out the listing URL itself + any obvious search/results pages
        clean = [
            u for u in urls
            if u != listing_url
            and "search" not in u.lower().split("?")[0]
            and "results" not in u.lower().split("?")[0]
            and "category" not in u.lower().split("?")[0]
        ]
        return clean[:max_urls]
    except Exception as e:
        try:
            await page.close()
        except Exception:
            pass
        print(f"  ! collect failed: {str(e)[:120]}")
        return []


def _normalize(href: str, base: str) -> str | None:
    """Normalize a job-link href: resolve relative, strip fragment, sanity check."""
    if not href:
        return None
    href = href.strip()
    if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("#"):
        return None
    if href.startswith("/") or not href.startswith("http"):
        href = urljoin(base, href)
    href = href.split("#")[0]
    return href


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
