"""
Mostafa CLI — internship hunter.

Examples:
  python3 -u run.py "ai" "machine learning" "software engineer"
  python3 -u run.py "data engineer" "backend" --season summer --year 2026 --city Cairo
  python3 -u run.py "frontend" "ui" --city Dubai --country UAE --max-age 60
"""
import argparse
import asyncio
import os

from agent.orchestrator import run_mostafa
import config


def main():
    p = argparse.ArgumentParser(description="Mostafa — generic internship hunter agent")
    p.add_argument("keywords", nargs="*", default=config.DEFAULT_KEYWORDS,
                   help="Role keywords (ai, ml, software, backend, frontend, data, etc.)")
    p.add_argument("--season", default=config.DEFAULT_SEASON, help="summer / fall / winter / spring")
    p.add_argument("--year",   type=int, default=config.DEFAULT_YEAR)
    p.add_argument("--city",   default=config.DEFAULT_CITY)
    p.add_argument("--country", default=config.DEFAULT_COUNTRY)
    p.add_argument("--max-age", type=int, default=config.MAX_AGE_DAYS,
                   help="Maximum days since posting (default 90)")
    p.add_argument("--tab", default=None,
                   help="Google Sheet tab name to append to (default 'Mostafa Internships')")
    args = p.parse_args()

    if args.tab:
        os.environ["MOSTAFA_WORKSHEET_NAME"] = args.tab

    asyncio.run(run_mostafa(
        keywords=args.keywords,
        season=args.season,
        year=args.year,
        city=args.city,
        country=args.country,
        max_age_days=args.max_age,
    ))


if __name__ == "__main__":
    main()
