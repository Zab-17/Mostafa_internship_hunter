"""
Company discovery — Mostafa Googles for companies that match the user's keywords,
then guesses their careers page URLs.
"""
import re
from urllib.parse import quote_plus, urlparse
from agent.browser import get_page


CAREERS_PATHS = [
    "/careers", "/careers/", "/careers/jobs", "/jobs", "/job-search",
    "/en/careers", "/about/careers", "/company/careers", "/work-with-us",
]


async def google_search_companies(keyword: str, city: str, country: str,
                                   limit: int = 15) -> list[dict]:
    """
    Search Google for companies matching the keyword in the city.
    Returns list of {company_name, root_domain, source_url}.
    """
    query = f'top "{keyword}" companies in {city} {country} careers OR jobs'
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=30&hl=en"

    page = await get_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)
        anchors = await page.query_selector_all("a")
        seen_domains = set()
        results = []
        for a in anchors:
            href = await a.get_attribute("href")
            if not href or not href.startswith("http"):
                continue
            # Skip Google internal + common junk
            host = urlparse(href).netloc.lower()
            if not host or any(b in host for b in [
                "google.", "youtube.", "wikipedia.", "facebook.", "twitter.",
                "linkedin.", "instagram.", "reddit.", "quora.", "wuzzuf.",
                "indeed.", "glassdoor.", "bayt.", "naukri.",
            ]):
                continue
            root = ".".join(host.split(".")[-2:])
            if root in seen_domains:
                continue
            seen_domains.add(root)
            try:
                text = (await a.inner_text()).strip().split("\n")[0][:80]
            except Exception:
                text = root
            results.append({
                "company_name": text or root,
                "root_domain": host,
                "source_url": href,
            })
            if len(results) >= limit:
                break
        return results
    except Exception as e:
        print(f"  ! discover failed: {str(e)[:100]}")
        return []
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def guess_careers_url(root_domain: str) -> str | None:
    """
    Given a root domain (e.g., 'valeo.com'), try common /careers paths
    until one returns 200. Returns the first that loads.
    """
    base = f"https://{root_domain}" if not root_domain.startswith("http") else root_domain
    page = await get_page()
    try:
        for path in CAREERS_PATHS:
            url = base.rstrip("/") + path
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                if resp and resp.status < 400:
                    body = await page.locator("body").inner_text()
                    if any(w in body.lower() for w in ["job", "career", "vacanc", "position", "opening"]):
                        return url
            except Exception:
                continue
        return None
    finally:
        try:
            await page.close()
        except Exception:
            pass
