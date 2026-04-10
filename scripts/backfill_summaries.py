"""
Backfill Job Description summaries for sheet rows that don't have one.

The currently-running Mostafa is using an old in-memory append_leads_to_sheet
that doesn't write the description column. This script polls the cache for
new ACCEPTs and adds a placeholder summary for them based on the cached
description text. Run it in a loop while Mostafa is still active:

    python3 scripts/backfill_summaries.py --watch

Or once-off:
    python3 scripts/backfill_summaries.py
"""
import sys
import time
import sqlite3
from pathlib import Path

import gspread

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import config

WORKSHEET_NAME = "Mostafa Internships"


def first_n_sentences(text: str, n: int = 3) -> str:
    """Extract the first N sentence-like chunks from a description."""
    if not text:
        return ""
    text = text.strip().replace("\n", " ")
    parts = []
    current = ""
    for ch in text:
        current += ch
        if ch in ".!?" and len(current.strip()) > 20:
            parts.append(current.strip())
            current = ""
            if len(parts) >= n:
                break
    if current.strip():
        parts.append(current.strip())
    return " ".join(parts[:n])[:600]


def get_cache_descriptions() -> dict[str, tuple[str, str, str]]:
    """url -> (company, title, description) for ACCEPT rows."""
    c = sqlite3.connect(str(ROOT / "db" / "mostafa.db"))
    rows = c.execute(
        "SELECT url, company, title, description FROM seen_jobs WHERE verdict='ACCEPT'"
    ).fetchall()
    c.close()
    return {url: (co, ti, desc or "") for url, co, ti, desc in rows}


def backfill_once() -> int:
    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)
    ws = sh.worksheet(WORKSHEET_NAME)
    all_rows = ws.get_all_values()
    if not all_rows:
        return 0
    cache = get_cache_descriptions()
    updates = []
    for i, row in enumerate(all_rows):
        if i == 0:
            continue
        url = row[6] if len(row) > 6 else ""
        existing_summary = row[8] if len(row) > 8 else ""
        if not url or existing_summary.strip():
            continue
        if url not in cache:
            continue
        co, ti, desc = cache[url]
        summary = first_n_sentences(desc, 3)
        if not summary:
            summary = f"Internship at {co}: {ti[:80]}"
        updates.append({"range": f"I{i+1}", "values": [[summary]]})
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    return len(updates)


def main():
    watch = "--watch" in sys.argv
    interval = 60
    while True:
        try:
            n = backfill_once()
            if n:
                print(f"[{time.strftime('%H:%M:%S')}] backfilled {n} summaries")
            elif watch:
                print(f"[{time.strftime('%H:%M:%S')}] no rows to backfill")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] error: {e}")
        if not watch:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
