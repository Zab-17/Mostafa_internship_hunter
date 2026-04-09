# Mostafa — The Internship Hunter Agent

Mostafa is the third agent in Zeyad's pipeline (after Hamed and Ghali). He scours company career portals, Wuzzuf, and LinkedIn for internships matching user-supplied keywords, reads each job description himself, applies 6 strict rules, and saves verdicts to a SQLite dedup cache.

## How to run Mostafa

```bash
python3 -u run.py "ai" "machine learning" "software engineer"
python3 -u run.py "data engineer" "backend" --season summer --year 2026
python3 -u run.py "frontend" --city Dubai --country UAE --max-age 60
```

When the user says "run mostafa", "mostafa find me internships", "wake up mostafa" — execute `python3 -u run.py` with whatever keywords and filters they pass.

## What Mostafa does

1. Walks a configured list of company career portals (Valeo, Siemens, Vodafone, Microsoft, Google, etc.) using Playwright in headless Chromium.
2. Also scrapes Wuzzuf + LinkedIn (Tier 3 fallback for smaller shops).
3. Filters every URL through a SQLite dedup cache so he NEVER re-processes a job he's seen before.
4. For each new URL, opens the live page, reads the full description and requirements text.
5. Judges against 6 hard rules: season+year, post ≤90 days, keyword relevance, city, direct URL, position open.
6. Quotes the exact sentence from the description that proves the rule passes.
7. Saves ACCEPT/REJECT verdicts to the cache.
8. Writes a markdown report to `output/mostafa_*.md`.

## Architecture (mirrors Hamed)

- `run.py` — CLI entry point with argparse
- `config.py` — company portal list, defaults, block terms
- `agent/orchestrator.py` — Mostafa's brain (system prompt, MCP tools, ClaudeSDKClient)
- `agent/browser.py` — singleton Playwright instance
- `agent/tools/scraper.py` — generic listing walker + per-job DOM reader
- `agent/tools/sheets_writer.py` — markdown report writer
- `db/cache.py` — SQLite dedup (`mostafa.db`)
- `output/` — generated reports

## Key design decisions

- The scraper is dumb. It only reads the DOM. The LLM (Mostafa) makes every relevance call.
- Dedup is URL-keyed and persistent — multiple runs across days never re-process the same job.
- Generic across majors: pass any keywords. The 6 rules are enforced regardless of field.
- Tier ordering: company portals first (highest quality), Wuzzuf + LinkedIn last (catches smaller shops).
