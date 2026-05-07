"""
Append-only Google Sheets writer for Mostafa.

Writes accepted leads to Zeyad's profile-specific tabs:
  - "Zeyadmaher AI/CS Internships"             — CS / CE / software / AI / data
  - "Zeyadmaher Electronics Internships "      — electronics / hardware / EDA / chip
  - "Zeyadmaher Mechatronics Internships "     — mechatronics / robotics / control / automation

Note: the Electronics and Mechatronics tab names have a trailing space — that
is the EXACT title in the live spreadsheet and gspread is whitespace-sensitive.
Do not "fix" it without renaming the tab on the sheet first.

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
from db.cache import filter_unpushed, mark_urls_pushed

TAB_AI = "Zeyadmaher AI/CS Internships"
TAB_ELECTRONICS = "Zeyadmaher Electronics Internships "
TAB_MECHATRONICS = "Zeyadmaher Mechatronics Internships "
HEADERS = ["Scrape Date", "Company", "Job Title", "Posted", "Fit Score",
           "Reason", "Apply URL", "Source", "Job Description"]

# Keywords that signal an electronics/hardware role
_ELECTRONICS_SIGNALS = {
    "electronics", "embedded", "firmware", "fpga", "vlsi", "asic", "pcb",
    "hardware", "analog", "digital design", "rf engineer", "power electronics",
    "signal processing", "microcontroller", "chip design", "verification engineer",
    "rtl", "circuit", "semiconductor", "communications engineer", "field test",
    "network planning", "service engineer", "technical director",
}

# Keywords that signal a mechatronics / robotics / control / automation role
_MECHATRONICS_SIGNALS = {
    "mechatronics", "robotics", "control system", "control engineer",
    "motion control", "industrial automation", "plc", "scada", "hmi",
    "servo", "actuator", "mechanical design", "mechanical engineer",
    "smart manufacturing", "industry 4.0", "automation engineer",
    "process automation engineer", "manufacturing engineer", "production engineer",
    "instrumentation", "drives engineer", "robotic process",
}


def _classify_lead(lead: dict) -> str:
    """Return 'ai', 'electronics', or 'mechatronics'.

    Active profile (MOSTAFA_PROFILE env var) is the source of truth when set
    explicitly to one of those three. Otherwise (profile == 'all' or unset)
    fall back to a per-lead text classifier on title + reason.

    The fallback was wrong about CS/CE-aligned hardware roles (e.g. Siemens EDA
    "Hardware Verification Intern" — accepted under `computer engineer`), so the
    explicit profile is honored as the source of truth when chosen.
    """
    profile = (os.environ.get("MOSTAFA_PROFILE") or "").lower()
    if profile == "ai":
        return "ai"
    if profile == "electronics":
        return "electronics"
    if profile == "mechatronics":
        return "mechatronics"
    blob = (lead.get("title", "") + " " + lead.get("reason", "")).lower()
    # Check mechatronics first — it's narrower than electronics, so a hit here
    # is more specific and should win over the electronics fallback.
    for signal in _MECHATRONICS_SIGNALS:
        if signal in blob:
            return "mechatronics"
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
    """Append accepted leads to AI/Electronics/Mechatronics tabs. Deduplicates
    by (company, title). Returns 0 silently if Sheets is not configured.

    Source-of-truth for "have I pushed this URL once?" is the SQLite
    `seen_jobs.pushed_to_sheet` column, NOT the live sheet contents. This way
    a user can manually delete rows from the sheet without us re-appending
    them on the next run.
    """
    if not leads or not _is_configured():
        return 0

    # Filter out leads whose URL is already marked pushed in SQLite.
    # This is the new "never re-push, even if user deleted from the sheet" gate.
    incoming_urls = [L.get("url", "") for L in leads if L.get("url")]
    unpushed = set(filter_unpushed(incoming_urls))
    leads = [L for L in leads if L.get("url", "") in unpushed]
    if not leads:
        return 0

    # Deduplicate input
    leads = _dedup_leads(leads)

    # Classify into buckets
    ai_leads = []
    elec_leads = []
    mech_leads = []
    for L in leads:
        bucket = _classify_lead(L)
        if bucket == "electronics":
            elec_leads.append(L)
        elif bucket == "mechatronics":
            mech_leads.append(L)
        else:
            ai_leads.append(L)

    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_new = 0

    # Also support legacy --tab override: if set, write everything to that tab
    override_tab = os.environ.get("MOSTAFA_WORKSHEET_NAME")

    pushed_urls_this_call: list[str] = []

    for tab_name, bucket in [
        (TAB_AI, ai_leads),
        (TAB_ELECTRONICS, elec_leads),
        (TAB_MECHATRONICS, mech_leads),
    ]:
        if not bucket:
            continue
        target_tab = override_tab or tab_name
        ws = _get_worksheet(sh, target_tab)
        existing_keys = _existing_keys(ws)
        existing_urls = _existing_urls(ws)

        new_rows = []
        new_urls_for_tab: list[str] = []
        for L in bucket:
            url = L.get("url", "")
            company = L.get("company", "").strip()
            title = L.get("title", "").strip()
            key = (company.lower(), title.lower())

            if key in existing_keys or url in existing_urls:
                # Already on the sheet. Mark it pushed so we never try again,
                # even though we're not appending now.
                if url:
                    pushed_urls_this_call.append(url)
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
            new_urls_for_tab.append(url)
            existing_keys.add(key)  # prevent intra-batch dupes

        if new_rows:
            ws.append_rows(new_rows, value_input_option="RAW")
            total_new += len(new_rows)
            pushed_urls_this_call.extend(new_urls_for_tab)

    # Mark every URL we either appended or saw already-on-sheet as pushed.
    # Future calls will skip these via filter_unpushed().
    if pushed_urls_this_call:
        mark_urls_pushed([u for u in pushed_urls_this_call if u])

    return total_new
