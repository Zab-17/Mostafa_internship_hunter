"""
Write accepted leads to markdown.

Two outputs every run:
- output/mostafa_all_leads.md  ← MASTER file. Cumulative across all runs. Never wiped.
- output/mostafa_<run_label>.md ← Per-run snapshot for this specific run.

The master file is rebuilt from the SQLite cache each run, so it always reflects
EVERY accepted lead Mostafa has ever found. Since the cache is append-only and
URL-keyed, leads accumulate naturally — you can run Mostafa daily and the master
file grows without ever losing or duplicating anything.
"""
from pathlib import Path
from datetime import datetime

OUT_DIR = Path(__file__).parent.parent.parent / "output"
MASTER_FILE = "mostafa_all_leads.md"


def _render(leads: list[dict], title: str, companies: list[dict] | None = None) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    lines = [f"# {title}", f"Last updated: {ts} UTC", f"Total leads: {len(leads)}", ""]

    # Companies scanned section (real company portals, not Wuzzuf/LinkedIn)
    if companies:
        lines.append("## Companies searched (outside Wuzzuf / LinkedIn)")
        lines.append("")
        lines.append("| Company | Jobs found | Jobs accepted | Last scanned | Careers URL |")
        lines.append("|---|---|---|---|---|")
        for c in companies:
            lines.append(
                f"| {c.get('company','?')} "
                f"| {c.get('jobs_found',0)} "
                f"| {c.get('jobs_accepted',0)} "
                f"| {(c.get('last_scanned','') or '')[:10]} "
                f"| {c.get('careers_url','')} |"
            )
        lines.append("")

    lines.append("## Accepted internship leads")
    lines.append("")
    by_company: dict[str, list[dict]] = {}
    for L in leads:
        by_company.setdefault(L["company"], []).append(L)
    for company, jobs in sorted(by_company.items()):
        lines.append(f"### {company}")
        for j in jobs:
            lines.append(f"- **{j['title']}**")
            lines.append(f"  - Posted: {j.get('posted','?')}    Fit: {j.get('fit_score','?')}/10")
            lines.append(f"  - First seen: {j.get('first_seen','?')}")
            lines.append(f"  - Why: {j.get('reason','')}")
            lines.append(f"  - Apply: {j['url']}")
            lines.append("")
    return "\n".join(lines)


def write_markdown_report(leads: list[dict], run_label: str = "",
                          companies: list[dict] | None = None) -> str:
    """
    Write the master cumulative file (always) and a per-run snapshot (if labeled).
    Returns the path of the master file.
    """
    OUT_DIR.mkdir(exist_ok=True)

    # 1) Master cumulative file — overwritten with the FULL cache contents.
    #    Because the cache is append-only, this file only ever grows.
    master_path = OUT_DIR / MASTER_FILE
    master_path.write_text(
        _render(leads, "Mostafa — All Accepted Leads (cumulative)", companies=companies),
        encoding="utf-8",
    )

    # 2) Per-run snapshot for this run only (still useful for review).
    if run_label:
        snap = OUT_DIR / f"mostafa_{run_label}.md"
        snap.write_text(
            _render(leads, f"Mostafa — Run: {run_label}", companies=companies),
            encoding="utf-8",
        )

    return str(master_path)
