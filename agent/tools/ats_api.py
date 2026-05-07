"""
Direct ATS JSON fetchers — bypass Playwright entirely for portals hosted on
public ATSs that expose unauthenticated read endpoints.

Why: many career portals (Microsoft, Vodafone, Schneider, Bosch, Valeo...) are
JS-heavy SPAs that the Playwright walker can't render reliably, returning 0
job links. But the ATS underneath each one (Greenhouse, Lever, SmartRecruiters)
exposes the same listings as plain JSON. This module hits those endpoints
directly — faster, more reliable, and returns full descriptions so Mostafa
doesn't need a second per-job fetch.

Public, no-auth endpoints supported:
- Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
- Lever:      https://api.lever.co/v0/postings/{slug}?mode=json
- SmartRecruiters: https://api.smartrecruiters.com/v1/companies/{slug}/postings

Returned shape (for every backend):
    {
        "url": str,            # apply / detail URL
        "title": str,
        "location": str,       # "Cairo, Egypt" or "Remote" etc.
        "posted": str,         # ISO date string or empty
        "department": str,
        "description": str,    # plain-text description (may be HTML-stripped)
    }
"""
from __future__ import annotations

import re
from html import unescape

import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = httpx.Timeout(20.0)


def _strip_html(text: str) -> str:
    """Quick-and-dirty HTML strip — sufficient for ATS description fields."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def _matches_location(location: str, location_substr: str | None) -> bool:
    if not location_substr:
        return True
    return location_substr.lower() in (location or "").lower()


# ─── Greenhouse ─────────────────────────────────────────────────────────
def fetch_greenhouse_jobs(slug: str, location_substr: str | None = None) -> list[dict]:
    """slug example: 'stripe' (from boards.greenhouse.io/stripe)."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"  ! greenhouse {slug} failed: {str(e)[:100]}")
        return []

    out = []
    for j in r.json().get("jobs", []):
        loc = (j.get("location") or {}).get("name") or ""
        if not _matches_location(loc, location_substr):
            continue
        out.append({
            "url": j.get("absolute_url", ""),
            "title": j.get("title", "").strip(),
            "location": loc,
            "posted": j.get("updated_at", "") or j.get("first_published", ""),
            "department": ", ".join(d.get("name", "") for d in j.get("departments", [])),
            "description": _strip_html(j.get("content", "")),
        })
    return out


# ─── Lever ───────────────────────────────────────────────────────────────
def fetch_lever_jobs(slug: str, location_substr: str | None = None) -> list[dict]:
    """slug example: 'palantir' (from jobs.lever.co/palantir)."""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"  ! lever {slug} failed: {str(e)[:100]}")
        return []

    out = []
    for j in r.json():
        cats = j.get("categories", {}) or {}
        loc = cats.get("location", "") or ""
        if not _matches_location(loc, location_substr):
            continue
        # Lever ms-since-epoch -> ISO best effort
        created_ms = j.get("createdAt") or 0
        posted_iso = ""
        if created_ms:
            from datetime import datetime, timezone
            posted_iso = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
        out.append({
            "url": j.get("hostedUrl", ""),
            "title": (j.get("text") or "").strip(),
            "location": loc,
            "posted": posted_iso,
            "department": cats.get("team", "") or cats.get("department", ""),
            "description": j.get("descriptionPlain") or _strip_html(j.get("description", "")),
        })
    return out


# ─── SmartRecruiters ────────────────────────────────────────────────────
def fetch_smartrecruiters_jobs(slug: str, location_substr: str | None = None,
                               country_code: str = "eg") -> list[dict]:
    """slug example: 'BoschGroup' (from jobs.smartrecruiters.com/BoschGroup).

    Filters by country at the API level (country_code='eg' for Egypt) so we
    don't pull the global firehose. Then optionally narrows by location_substr.
    """
    listing_url = (f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
                   f"?country={country_code}&limit=100")
    try:
        r = httpx.get(listing_url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"  ! smartrecruiters {slug} listing failed: {str(e)[:100]}")
        return []

    listings = r.json().get("content", [])
    out = []
    for j in listings:
        loc_obj = j.get("location") or {}
        loc = ", ".join(filter(None, [loc_obj.get("city"), loc_obj.get("country", {}).get("code") if isinstance(loc_obj.get("country"), dict) else loc_obj.get("country")]))
        if not _matches_location(loc, location_substr):
            continue

        posting_id = j.get("id") or j.get("uuid")
        # Pull full job ad for the description. Best-effort — skip on failure.
        description = ""
        if posting_id:
            try:
                d = httpx.get(
                    f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}",
                    headers={"User-Agent": UA}, timeout=TIMEOUT,
                )
                if d.status_code == 200:
                    sections = (d.json().get("jobAd") or {}).get("sections") or {}
                    parts = []
                    for k in ("jobDescription", "qualifications", "additionalInformation"):
                        sec = sections.get(k) or {}
                        if sec.get("text"):
                            parts.append(_strip_html(sec["text"]))
                    description = "\n\n".join(parts)
            except Exception:
                pass

        out.append({
            "url": j.get("ref") or f"https://jobs.smartrecruiters.com/{slug}/{posting_id}",
            "title": (j.get("name") or "").strip(),
            "location": loc,
            "posted": j.get("releasedDate", ""),
            "department": (j.get("department") or {}).get("label", ""),
            "description": description,
        })
    return out


# ─── Dispatcher ──────────────────────────────────────────────────────────
def fetch_ats_jobs(ats_type: str, board_slug: str,
                   location_substr: str | None = None) -> list[dict]:
    """One call to fetch from any supported ATS.

    ats_type: 'greenhouse' | 'lever' | 'smartrecruiters'
    board_slug: company identifier on that ATS
    location_substr: optional case-insensitive substring filter (e.g. 'Cairo')
    """
    t = (ats_type or "").lower().strip()
    if t == "greenhouse":
        return fetch_greenhouse_jobs(board_slug, location_substr)
    if t == "lever":
        return fetch_lever_jobs(board_slug, location_substr)
    if t == "smartrecruiters":
        # SmartRecruiters has a country-code filter built-in; if the user
        # passed an Egypt-ish substring, also narrow at the API level.
        cc = "eg"
        if location_substr and location_substr.lower() not in ("cairo", "egypt", "eg"):
            cc = ""  # caller wants something else, drop the country pre-filter
        return fetch_smartrecruiters_jobs(board_slug, location_substr, country_code=cc or "eg")
    raise ValueError(f"unsupported ats_type: {ats_type!r}")
