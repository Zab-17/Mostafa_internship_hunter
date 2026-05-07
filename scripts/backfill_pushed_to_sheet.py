"""
One-shot backfill: read the URLs currently on the three Zeyad tabs and mark
each one as pushed_to_sheet=1 in SQLite.

Why: we just added a `pushed_to_sheet` column. Without this backfill, the next
run would push every accepted lead in the cache (68 of them) to the sheet
again as 'unpushed', creating duplicates.

Run with:
    python3 -u scripts/backfill_pushed_to_sheet.py
"""
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
import config
from db.cache import init_db, DB_PATH

ZEYAD_TABS = [
    "Zeyadmaher AI/CS Internships",
    "Zeyadmaher Electronics Internships ",
    "Zeyadmaher Mechatronics Internships ",
]


def main():
    if not config.GOOGLE_SHEETS_ID:
        sys.exit("GOOGLE_SHEETS_ID not configured")

    # Make sure schema migration ran (adds pushed_to_sheet column)
    init_db()

    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)

    sheet_urls: set[str] = set()
    for tab in ZEYAD_TABS:
        try:
            ws = sh.worksheet(tab)
        except gspread.WorksheetNotFound:
            print(f"  ! tab not found: {tab!r}")
            continue
        col = ws.col_values(7)  # Apply URL column (1-indexed)
        # skip header
        for u in col[1:]:
            u = (u or "").strip()
            if u:
                sheet_urls.add(u)
        print(f"  [{tab!r}] urls on sheet: {len(col)-1}")

    print(f"\nTotal unique URLs across Zeyad tabs: {len(sheet_urls)}")

    # Find which of those URLs exist in SQLite
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" * len(sheet_urls)) if sheet_urls else "''"
    rows = conn.execute(
        f"SELECT url, pushed_to_sheet FROM seen_jobs WHERE url IN ({placeholders})",
        list(sheet_urls),
    ).fetchall() if sheet_urls else []
    matched = {r[0] for r in rows}
    already_marked = {r[0] for r in rows if r[1] == 1}
    missing_from_db = sheet_urls - matched

    print(f"  matched in SQLite:        {len(matched)}")
    print(f"  already pushed_to_sheet=1:{len(already_marked)}")
    print(f"  not in SQLite at all:     {len(missing_from_db)}")
    if missing_from_db:
        print("  (these came from manual edits / older runs not in cache; safe to ignore)")
        for u in list(missing_from_db)[:5]:
            print(f"    - {u[:100]}")

    if matched:
        conn.execute(
            f"UPDATE seen_jobs SET pushed_to_sheet = 1 WHERE url IN ({placeholders})",
            list(sheet_urls),
        )
        conn.commit()
        print(f"\n✅ Marked {len(matched)} URLs as pushed_to_sheet=1 in SQLite")

    # Also mark every accepted URL — the safest sweep. Even if a lead was
    # accepted but the user deleted it from the sheet, "already pushed once"
    # is exactly the policy we want.
    n_accepted = conn.execute(
        "UPDATE seen_jobs SET pushed_to_sheet = 1 WHERE verdict = 'ACCEPT' AND pushed_to_sheet = 0"
    ).rowcount
    conn.commit()
    print(f"✅ Also marked {n_accepted} additional accepted-but-not-yet-marked leads as pushed (covers user-deleted rows)")

    conn.close()


if __name__ == "__main__":
    main()
