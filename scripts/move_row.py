"""
One-off: move the Siemens EDA "HAV R&D Hardware Verification Intern" row
from the "Mostafa Electronics" tab to "Mostafa Internships". The IC Design
Consultant Intern row stays in Electronics (it's actually for EE undergrads).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
import config

TARGET_TITLE_FRAGMENT = "hav r&d hardware verification"
SRC_TAB = "Mostafa Electronics"
DST_TAB = "Mostafa Internships"

gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)
src = sh.worksheet(SRC_TAB)
dst = sh.worksheet(DST_TAB)

rows = src.get_all_values()
header = rows[0] if rows else []
print(f"Source tab '{SRC_TAB}' has {len(rows)-1} data rows")

target_row_idx = None
target_row_values = None
for i, row in enumerate(rows[1:], start=2):  # start=2 because gspread is 1-indexed and row 1 is header
    if len(row) >= 3 and TARGET_TITLE_FRAGMENT in row[2].lower():
        target_row_idx = i
        target_row_values = row
        break

if target_row_idx is None:
    print(f"❌ No row matching '{TARGET_TITLE_FRAGMENT}' found in {SRC_TAB}")
    sys.exit(1)

print(f"Found at row {target_row_idx}: {target_row_values[1]} — {target_row_values[2]}")

# Check it isn't already on destination
dst_rows = dst.get_all_values()
dst_urls = {r[6] for r in dst_rows[1:] if len(r) >= 7}
target_url = target_row_values[6] if len(target_row_values) >= 7 else ""
if target_url and target_url in dst_urls:
    print(f"⚠️  URL already on '{DST_TAB}', will only delete from source")
else:
    dst.append_row(target_row_values, value_input_option="RAW")
    print(f"✅ Appended to '{DST_TAB}'")

src.delete_rows(target_row_idx)
print(f"✅ Deleted row {target_row_idx} from '{SRC_TAB}'")
