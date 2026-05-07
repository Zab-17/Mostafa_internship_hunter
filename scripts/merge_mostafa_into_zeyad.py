"""
One-shot merge: copy non-duplicate rows from the legacy Mostafa-named tabs
into Zeyad's renamed tabs, then delete the Mostafa tabs.

Mapping:
  "Mostafa Internships"  -->  "Zeyadmaher AI/CS Internships"
  "Mostafa Electronics"  -->  "Zeyadmaher Electronics Internships "   (trailing space — exact title)

Dedup key: (company.lower().strip(), title.lower().strip()).
When the same (company, title) exists on both tabs, the Zeyad row WINS — we
do not touch existing Zeyad rows, only append unseen Mostafa rows.

Run with:
    python3 -u scripts/merge_mostafa_into_zeyad.py            # dry-run preview
    python3 -u scripts/merge_mostafa_into_zeyad.py --apply    # actually merge + delete
"""
import argparse
import sys
from pathlib import Path

# Allow running as `python3 scripts/merge_mostafa_into_zeyad.py` from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
import config


MERGES = [
    # (source_tab,            destination_tab)
    ("Mostafa Internships",   "Zeyadmaher AI/CS Internships"),
    ("Mostafa Electronics",   "Zeyadmaher Electronics Internships "),
]


def _key(row: list[str]) -> tuple[str, str] | None:
    """Build dedup key from columns: [date, company, title, ...]."""
    if len(row) < 3:
        return None
    company = (row[1] or "").strip().lower()
    title = (row[2] or "").strip().lower()
    if not company and not title:
        return None
    return (company, title)


def merge_one(sh: gspread.Spreadsheet, src_name: str, dst_name: str, apply: bool):
    src = sh.worksheet(src_name)
    dst = sh.worksheet(dst_name)

    src_rows = src.get_all_values()
    dst_rows = dst.get_all_values()

    if not src_rows:
        print(f"  [{src_name!r}] empty — nothing to merge")
        return 0
    if not dst_rows:
        print(f"  [{dst_name!r}] empty — destination has no header, skipping for safety")
        return 0

    src_data = src_rows[1:]  # drop header
    dst_data = dst_rows[1:]

    existing_keys = {k for k in (_key(r) for r in dst_data) if k is not None}

    to_append = []
    skipped_dupe = 0
    for row in src_data:
        k = _key(row)
        if k is None:
            continue
        if k in existing_keys:
            skipped_dupe += 1
            continue
        existing_keys.add(k)  # prevent intra-batch dupes
        # Pad/truncate to dst header width
        dst_width = len(dst_rows[0])
        padded = (row + [""] * dst_width)[:dst_width]
        to_append.append(padded)

    print(f"  [{src_name!r} -> {dst_name!r}]")
    print(f"    source rows: {len(src_data)}  destination rows: {len(dst_data)}")
    print(f"    duplicates skipped: {skipped_dupe}")
    print(f"    new rows to append: {len(to_append)}")

    if apply and to_append:
        dst.append_rows(to_append, value_input_option="RAW")
        print(f"    ✅ appended {len(to_append)} rows to {dst_name!r}")

    return len(to_append)


def delete_tab(sh: gspread.Spreadsheet, name: str, apply: bool):
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        print(f"  [{name!r}] already gone")
        return
    if apply:
        sh.del_worksheet(ws)
        print(f"  🗑️  deleted tab {name!r}")
    else:
        print(f"  would delete tab {name!r}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="Actually perform the merge and delete (default is dry-run)")
    p.add_argument("--keep-source", action="store_true",
                   help="Skip deleting the Mostafa source tabs after merge")
    args = p.parse_args()

    if not config.GOOGLE_SHEETS_ID:
        sys.exit("GOOGLE_SHEETS_ID not configured — refusing to proceed")

    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)
    print(f"Spreadsheet: {sh.title!r}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    print("== Merge ==")
    total_appended = 0
    for src, dst in MERGES:
        total_appended += merge_one(sh, src, dst, args.apply)
        print()

    if not args.keep_source:
        print("== Delete legacy Mostafa tabs ==")
        for src, _ in MERGES:
            delete_tab(sh, src, args.apply)
        print()

    print(f"Total new rows appended: {total_appended}")
    if not args.apply:
        print("\n(Dry-run only. Re-run with --apply to actually perform the merge.)")


if __name__ == "__main__":
    main()
