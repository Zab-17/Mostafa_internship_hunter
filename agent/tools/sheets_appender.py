"""
Append-only Google Sheets writer for Mostafa.

Writes accepted leads to a "Mostafa Internships" tab in the spreadsheet
identified by GOOGLE_SHEETS_ID. Creates the tab + header row if missing.
Never wipes — every run appends new rows for jobs not yet on the sheet.

Columns: Scrape Date | Company | Job Title | Posted | Fit Score | Reason | Apply URL | Source

Sheet writes are silently skipped if GOOGLE_SHEETS_ID or the credentials
file are not configured — in that case Mostafa still writes the local
markdown report.
"""
import os
from datetime import datetime, timezone
import gspread

import config

DEFAULT_WORKSHEET_NAME = "Mostafa Internships"
HEADERS = ["Scrape Date", "Company", "Job Title", "Posted", "Fit Score",
           "Reason", "Apply URL", "Source", "Job Description"]


def _worksheet_name() -> str:
    """Per-run worksheet selection — MOSTAFA_WORKSHEET_NAME env wins over default."""
    return os.environ.get("MOSTAFA_WORKSHEET_NAME") or DEFAULT_WORKSHEET_NAME


def _is_configured() -> bool:
    return bool(config.GOOGLE_SHEETS_ID) and os.path.exists(config.GOOGLE_CREDENTIALS_PATH)


def _get_worksheet() -> gspread.Worksheet:
    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)
    name = _worksheet_name()
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


def append_leads_to_sheet(leads: list[dict]) -> int:
    """Append accepted leads to the Mostafa Internships worksheet. Skips URLs already present.
    Returns 0 silently if Sheets is not configured."""
    if not leads or not _is_configured():
        return 0
    ws = _get_worksheet()
    existing = _existing_urls(ws)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    new_rows = []
    for L in leads:
        url = L.get("url", "")
        if not url or url in existing:
            continue
        new_rows.append([
            today,
            L.get("company", ""),
            L.get("title", ""),
            L.get("posted", ""),
            L.get("fit_score", ""),
            L.get("reason", ""),
            url,
            _detect_source(url),
            L.get("description_summary", ""),
        ])
    if not new_rows:
        return 0
    ws.append_rows(new_rows, value_input_option="RAW")
    return len(new_rows)
