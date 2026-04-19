"""
Mostafa CLI — internship hunter.

Profiles:
  python3 -u run.py                        # default: ai profile
  python3 -u run.py --profile electronics  # electronics only
  python3 -u run.py --profile all          # ai + electronics combined

Custom keywords (override profile):
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
    p.add_argument("keywords", nargs="*",
                   help="Role keywords (overrides --profile if given)")
    p.add_argument("--profile", choices=list(config.PROFILES.keys()), default="ai",
                   help="Keyword profile: ai (default), electronics, or all")
    p.add_argument("--season", default=config.DEFAULT_SEASON, help="summer / fall / winter / spring")
    p.add_argument("--year",   type=int, default=config.DEFAULT_YEAR)
    p.add_argument("--city",   default=config.DEFAULT_CITY)
    p.add_argument("--country", default=config.DEFAULT_COUNTRY)
    p.add_argument("--max-age", type=int, default=config.MAX_AGE_DAYS,
                   help="Maximum days since posting (default 90)")
    p.add_argument("--tab", default=None,
                   help="Google Sheet tab name to append to (default 'Mostafa Internships')")
    args = p.parse_args()

    # Explicit keywords override profile; otherwise use the selected profile
    keywords = args.keywords if args.keywords else config.PROFILES[args.profile]

    # Profile drives the sheet tab routing in sheets_appender._classify_lead.
    # Without this, the per-lead text classifier misroutes CE-aligned hardware
    # roles (Siemens EDA Verification Intern, etc.) into the Electronics tab.
    if not args.keywords:  # only force-route when running a named profile
        os.environ["MOSTAFA_PROFILE"] = args.profile

    if args.tab:
        os.environ["MOSTAFA_WORKSHEET_NAME"] = args.tab

    asyncio.run(run_mostafa(
        keywords=keywords,
        season=args.season,
        year=args.year,
        city=args.city,
        country=args.country,
        max_age_days=args.max_age,
    ))


if __name__ == "__main__":
    main()
