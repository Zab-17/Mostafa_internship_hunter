"""
Append-only Google Sheets writer for Mostafa.

Writes accepted leads to profile-specific tabs:
  - "AI Internships" for AI/software leads
  - "Electronics Internships" for electronics/hardware leads

Creates tabs + header rows if missing.
Never wipes — every run appends new rows for jobs not yet on the sheet.
Deduplicates by (company, title) pair to avoid multiple URLs for the same job.

Columns: Scrape Date | Company | Job Title | Posted | Fit Score | Reason | Apply URL | Source | Job Description

Sheet writes are silently skipped if GOOGLE_SHEETS_ID or the credentials
file are not configured — in that case Mostafa still writes the local
markdown report.
"""
import os
import re
from datetime import datetime, timezone
import gspread

import config

TAB_AI = "Mostafa Internships"
TAB_ELECTRONICS = "Mostafa Electronics"
HEADERS = ["Scrape Date", "Company", "Job Title", "Posted", "Fit Score",
           "Reason", "Apply URL", "Source", "Job Description"]

# Keywords that signal an electronics/hardware role
_ELECTRONICS_SIGNALS = {
    "electronics", "embedded", "firmware", "fpga", "vlsi", "asic", "pcb",
    "hardware", "analog", "digital design", "rf engineer", "power electronics",
    "signal processing", "microcontroller", "chip design", "verification engineer",
    "rtl", "circuit", "semiconductor", "communications engineer", "field test",
    "network planning", "service engineer", "systems engineer", "technical director",
}


def _classify_lead(lead: dict) -> str:
    """Return 'electronics' or 'ai' based on the active profile, falling back
    to a per-lead text classifier only when profile is 'all' or unset.

    The text classifier misroutes CE-aligned hardware roles (e.g. Siemens EDA
    "Hardware Verification Intern" — accepted under the `computer engineer`
    keyword) into the Electronics tab, which is wrong: the AI profile owns
    those because the user is CS/CE. So when MOSTAFA_PROFILE is explicitly
    'ai' or 'electronics', honor it as the source of truth.
    """
    profile = (os.environ.get("MOSTAFA_PROFILE") or "").lower()
    if profile == "ai":
        return "ai"
    if profile == "electronics":
        return "electronics"
    blob = (lead.get("title", "") + " " + lead.get("reason", "")).lower()
    for signal in _ELECTRONICS_SIGNALS:
        if signal in blob:
            return "electronics"
    return "ai"


def _is_configured() -> bool:
    return bool(config.GOOGLE_SHEETS_ID) and os.path.exists(config.GOOGLE_CREDENTIALS_PATH)


def _get_worksheet(sh: gspread.Spreadsheet, name: str) -> gspread.Worksheet:
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=2000, cols=len(HEADERS))
        ws.append_row(HEADERS, value_input_option="RAW")
    # Ensure header row exists
    first = ws.row_values(1)
    if first[:1] != HEADERS[:1]:
        ws.insert_row(HEADERS, index=1, value_input_option="RAW")
    return ws


def _existing_keys(ws: gspread.Worksheet) -> set[tuple[str, str]]:
    """Return set of (company_lower, title_lower) already on the sheet."""
    try:
        all_rows = ws.get_all_values()
        keys = set()
        for row in all_rows[1:]:  # skip header
            if len(row) >= 3:
                keys.add((row[1].strip().lower(), row[2].strip().lower()))
        return keys
    except Exception:
        return set()


def _existing_urls(ws: gspread.Worksheet) -> set[str]:
    try:
        col = ws.col_values(7)  # Apply URL column (1-indexed)
        return set(col[1:])     # skip header
    except Exception:
        return set()


def _detect_source(url: str) -> str:
    u = url.lower()
    if "wuzzuf" in u: return "wuzzuf"
    if "linkedin" in u: return "linkedin"
    if "greenhouse" in u: return "greenhouse"
    if "lever.co" in u: return "lever"
    if "ashbyhq" in u: return "ashby"
    if "myworkdayjobs" in u: return "workday"
    if "smartrecruiters" in u: return "smartrecruiters"
    return "company portal"


def _dedup_leads(leads: list[dict]) -> list[dict]:
    """Keep only the first (highest fit_score) lead per (company, title) pair."""
    seen = {}
    for L in leads:
        key = (L.get("company", "").strip().lower(),
               L.get("title", "").strip().lower())
        existing = seen.get(key)
        if existing is None or (L.get("fit_score", 0) or 0) > (existing.get("fit_score", 0) or 0):
            seen[key] = L
    return list(seen.values())


def append_leads_to_sheet(leads: list[dict]) -> int:
    """Append accepted leads to AI/Electronics tabs. Deduplicates by (company, title).
    Returns 0 silently if Sheets is not configured."""
    if not leads or not _is_configured():
        return 0

    # Deduplicate input
    leads = _dedup_leads(leads)

    # Classify into buckets
    ai_leads = []
    elec_leads = []
    for L in leads:
        if _classify_lead(L) == "electronics":
            elec_leads.append(L)
        else:
            ai_leads.append(L)

    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_new = 0

    # Also support legacy --tab override: if set, write everything to that tab
    override_tab = os.environ.get("MOSTAFA_WORKSHEET_NAME")

    for tab_name, bucket in [(TAB_AI, ai_leads), (TAB_ELECTRONICS, elec_leads)]:
        if not bucket:
            continue
        target_tab = override_tab or tab_name
        ws = _get_worksheet(sh, target_tab)
        existing_keys = _existing_keys(ws)
        existing_urls = _existing_urls(ws)

        new_rows = []
        for L in bucket:
            url = L.get("url", "")
            company = L.get("company", "").strip()
            title = L.get("title", "").strip()
            key = (company.lower(), title.lower())

            if key in existing_keys or url in existing_urls:
                continue

            new_rows.append([
                today,
                company,
                title,
                L.get("posted", ""),
                L.get("fit_score", ""),
                L.get("reason", ""),
                url,
                _detect_source(url),
                L.get("description_summary", ""),
            ])
            existing_keys.add(key)  # prevent intra-batch dupes

        if new_rows:
            ws.append_rows(new_rows, value_input_option="RAW")
            total_new += len(new_rows)

    return total_new
