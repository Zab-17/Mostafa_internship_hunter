"""
One-shot: remove rows from Electronics + Mechatronics tabs that are clearly
AI/CS roles (and likely already on the AI/CS tab). Caused by an old buggy
classifier that fanned every accept across all three tabs.

Run with:
    python3 -u scripts/dedupe_cross_tab.py [--dry-run]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
import config

AI_TAB = "Zeyadmaher AI/CS Internships"
ELEC_TAB = "Zeyadmaher Electronics Internships "
MECH_TAB = "Zeyadmaher Mechatronics Internships "

# Title substrings that signal a pure CS/AI role — these don't belong on
# Electronics or Mechatronics tabs even if the old classifier put them there.
AI_TITLE_SIGNALS = [
    "software developer", "software engineer", "software development",
    "backend", "back end", "back-end", "frontend", "front end", "front-end",
    "full stack", "fullstack", "full-stack",
    "data engineer", "data analytics", "data engineering",
    "ai/ml", "applied ai", "ai engineer", "ml engineer",
    "android", "ios", "mobile",
    "cloud engineering", "devops", "site reliability",
    "power platform", "applied scientist",
    "consulting engineer",  # Cisco
    "odoo developer",
    "react", "node.js",
    "machine learning",
]

# Title substrings that genuinely belong on Electronics (keep these on Elec)
ELEC_KEEP_SIGNALS = [
    "embedded", "firmware", "fpga", "vlsi", "asic", "pcb", "rtl",
    "hardware", "ic design", "verification engineer", "hardware verification",
    "rf engineer", "analog", "circuit", "semiconductor",
    "fit4rail",  # Siemens Mobility hardware-adjacent
]

# Title substrings that genuinely belong on Mechatronics
MECH_KEEP_SIGNALS = [
    "mechatronics", "robotics", "control system", "control engineer",
    "plc", "scada", "hmi", "servo", "actuator",
    "mechanical design", "mechanical engineer",
    "industrial automation", "manufacturing engineer", "production engineer",
    "instrumentation", "drives engineer",
]


def classify_title(title: str, tab_kind: str) -> str:
    """Return 'remove' if this row doesn't belong on `tab_kind`, else 'keep'."""
    t = title.lower()
    keep_signals = ELEC_KEEP_SIGNALS if tab_kind == "elec" else MECH_KEEP_SIGNALS
    if any(sig in t for sig in keep_signals):
        return "keep"
    if any(sig in t for sig in AI_TITLE_SIGNALS):
        return "remove"
    return "keep"  # be conservative — only remove obvious AI roles


def clean_tab(sh, tab_name: str, tab_kind: str, dry: bool):
    ws = sh.worksheet(tab_name)
    rows = ws.get_all_values()
    if not rows:
        return 0

    keep_indices = [0]  # always keep header (1-indexed externally, 0-indexed here)
    removed_titles = []
    for i, r in enumerate(rows[1:], start=1):
        title = r[2] if len(r) > 2 else ""
        verdict = classify_title(title, tab_kind)
        if verdict == "keep":
            keep_indices.append(i)
        else:
            removed_titles.append((r[1] if len(r) > 1 else "", title))

    print(f"\n=== {tab_name!r} ({tab_kind}) ===")
    print(f"  total: {len(rows)}, keep: {len(keep_indices)}, remove: {len(removed_titles)}")
    for co, ti in removed_titles:
        print(f"    - {co[:30]:30s} | {ti[:60]}")

    if dry or not removed_titles:
        return len(removed_titles)

    new_rows = [rows[i] for i in keep_indices]
    ws.clear()
    ws.update("A1", new_rows, value_input_option="RAW")
    print(f"  ✅ rewrote tab with {len(new_rows)} rows")
    return len(removed_titles)


def main():
    dry = "--dry-run" in sys.argv
    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)

    e = clean_tab(sh, ELEC_TAB, "elec", dry)
    m = clean_tab(sh, MECH_TAB, "mech", dry)
    print(f"\nTotal rows to remove: elec={e}, mech={m}")
    if dry:
        print("[dry run] no writes performed")


if __name__ == "__main__":
    main()
