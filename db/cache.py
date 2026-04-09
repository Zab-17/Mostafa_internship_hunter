"""SQLite dedup cache — Mostafa never re-processes a URL he's already seen."""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "mostafa.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            url TEXT PRIMARY KEY,
            company TEXT,
            title TEXT,
            verdict TEXT,
            reason TEXT,
            fit_score INTEGER,
            posted TEXT,
            first_seen TEXT,
            description TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scanned_companies (
            company TEXT PRIMARY KEY,
            careers_url TEXT,
            jobs_found INTEGER,
            jobs_accepted INTEGER,
            last_scanned TEXT
        )
    """)
    conn.commit()
    conn.close()


def record_company_scan(company: str, careers_url: str,
                        jobs_found: int = 0, jobs_accepted: int = 0):
    """Track which companies Mostafa has scanned (excludes Wuzzuf/LinkedIn aggregators)."""
    if company.lower() in ("wuzzuf", "linkedin"):
        return
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute(
        "SELECT jobs_found, jobs_accepted FROM scanned_companies WHERE company = ?",
        (company,),
    ).fetchone()
    if existing:
        jobs_found += existing[0] or 0
        jobs_accepted += existing[1] or 0
    conn.execute(
        "INSERT OR REPLACE INTO scanned_companies VALUES (?, ?, ?, ?, ?)",
        (company, careers_url, jobs_found, jobs_accepted, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_scanned_companies() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM scanned_companies ORDER BY jobs_accepted DESC, company ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_seen(url: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT 1 FROM seen_jobs WHERE url = ?", (url,)).fetchone()
    conn.close()
    return row is not None


def filter_unseen(urls: list[str]) -> list[str]:
    if not urls:
        return []
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" * len(urls))
    rows = conn.execute(f"SELECT url FROM seen_jobs WHERE url IN ({placeholders})", urls).fetchall()
    conn.close()
    seen = {r[0] for r in rows}
    return [u for u in urls if u not in seen]


def remember(url: str, company: str, title: str, verdict: str, reason: str,
             fit_score: int, posted: str, description: str = ""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO seen_jobs VALUES (?,?,?,?,?,?,?,?,?)",
        (url, company, title, verdict, reason, fit_score, posted,
         datetime.utcnow().isoformat(), description[:2000]),
    )
    conn.commit()
    conn.close()


def get_accepted() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM seen_jobs WHERE verdict='ACCEPT' ORDER BY fit_score DESC, first_seen DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
    accepted = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE verdict='ACCEPT'").fetchone()[0]
    conn.close()
    return {"total_seen": total, "accepted": accepted}
