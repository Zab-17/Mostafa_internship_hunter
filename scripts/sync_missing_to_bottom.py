"""
One-shot reconciliation: find every cache ACCEPT that is NOT on any of the
three Zeyad tabs (by URL or by company+title), then insert them at the TOP
of the AI/CS tab (row 2 onward), newest first. Marks pushed_to_sheet=1.

Run with:
    python3 -u scripts/sync_missing_to_top.py [--dry-run]
"""
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
import config
from db.cache import DB_PATH, init_db

AI_TAB = "Zeyadmaher AI/CS Internships"
ALL_TABS = [
    "Zeyadmaher AI/CS Internships",
    "Zeyadmaher Electronics Internships ",
    "Zeyadmaher Mechatronics Internships ",
]
HEADERS = ["Scrape Date", "Company", "Job Title", "Posted", "Fit Score",
           "Reason", "Apply URL", "Source", "Job Description"]


def _detect_source(url: str) -> str:
    u = (url or "").lower()
    if "wuzzuf" in u: return "wuzzuf"
    if "linkedin" in u: return "linkedin"
    if "greenhouse" in u: return "greenhouse"
    if "lever.co" in u: return "lever"
    if "ashbyhq" in u: return "ashby"
    if "myworkdayjobs" in u: return "workday"
    if "smartrecruiters" in u: return "smartrecruiters"
    return "company portal"


def main():
    dry = "--dry-run" in sys.argv
    if not config.GOOGLE_SHEETS_ID:
        sys.exit("GOOGLE_SHEETS_ID not configured")

    init_db()

    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)

    sheet_urls: set[str] = set()
    sheet_keys: set[tuple[str, str]] = set()
    for tab in ALL_TABS:
        rows = sh.worksheet(tab).get_all_values()
        for r in rows[1:]:
            if len(r) >= 7 and r[6]:
                sheet_urls.add(r[6].strip())
            if len(r) >= 3:
                sheet_keys.add((r[1].strip().lower(), r[2].strip().lower()))
    print(f"Sheet URLs: {len(sheet_urls)}, keys: {len(sheet_keys)}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    accepts = [dict(r) for r in conn.execute(
        "SELECT * FROM seen_jobs WHERE verdict='ACCEPT'"
    ).fetchall()]

    missing = []
    for L in accepts:
        url = (L.get("url") or "").strip()
        co = (L.get("company") or "").strip()
        ti = (L.get("title") or "").strip()
        if url in sheet_urls:
            continue
        if (co.lower(), ti.lower()) in sheet_keys:
            continue
        missing.append(L)

    missing.sort(key=lambda L: (L.get("first_seen") or ""), reverse=True)

    seen_keys = set()
    deduped = []
    for L in missing:
        key = ((L.get("company") or "").strip().lower(),
               (L.get("title") or "").strip().lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(L)
    if len(deduped) != len(missing):
        print(f"Intra-batch dedup: {len(missing)} -> {len(deduped)}")
    missing = deduped

    print(f"Missing accepts to backfill: {len(missing)}")
    for L in missing:
        print(f"  {(L.get('first_seen') or '')[:19]}  {L['company'][:30]:30s}  |  {L['title'][:60]}")

    if not missing:
        conn.close()
        return

    if dry:
        print("\n[dry run] no writes performed")
        conn.close()
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_rows = []
    for L in missing:
        new_rows.append([
            today,
            (L.get("company") or "").strip(),
            (L.get("title") or "").strip(),
            L.get("posted") or "",
            L.get("fit_score") or "",
            L.get("reason") or "",
            (L.get("url") or "").strip(),
            _detect_source(L.get("url") or ""),
            L.get("description_summary") or "",
        ])

    # Append at the BOTTOM — never insert at top. The user manually annotates
    # column J onward (application status). insert_rows would shift those
    # markers down and re-align them to the wrong jobs. append_rows leaves
    # every existing row's column J+ untouched.
    ws = sh.worksheet(AI_TAB)
    ws.append_rows(new_rows, value_input_option="RAW")
    print(f"\n✅ Appended {len(new_rows)} rows at the bottom of {AI_TAB!r}")

    urls_to_mark = [r[6] for r in new_rows if r[6]]
    placeholders = ",".join("?" * len(urls_to_mark))
    conn.execute(
        f"UPDATE seen_jobs SET pushed_to_sheet = 1 WHERE url IN ({placeholders})",
        urls_to_mark,
    )
    conn.commit()
    print(f"✅ Marked {len(urls_to_mark)} URLs pushed_to_sheet=1 in cache")
    conn.close()


if __name__ == "__main__":
    main()
