# Mostafa — Internship Hunter Agent

> A Claude Agent SDK orchestrator that scours company career portals, Wuzzuf, and LinkedIn for internships matching keywords you supply, reads every job description himself, and verdicts each one against 7 strict rules.

Mostafa is generic — pass any keywords (`"ai"`, `"data engineer"`, `"civil engineer"`, `"mechanical"`, anything), any city, any season, any year. He defaults to whatever you put in your `.env`.

---

## The story — why this exists

I'm a Computer Engineering junior. Looking for a Summer 2026 internship in Cairo, I tried what every student tries first: LinkedIn search, Wuzzuf, the AUC career portal, "Cairo software intern 2026" on Google. Within an hour I had a familiar pile of garbage:

- **7-year-old listings.** Google indexes everything forever. Half the "Cairo software intern" results were from 2019.
- **Senior roles disguised as "graduate program."** Companies love to call a 5-year-experience role a "Graduate Engineer Programme."
- **Aggregators with no fresh signal.** Wuzzuf and LinkedIn returned the same 30 listings I'd already seen, half of them closed.
- **Nothing from the companies that actually hire CE interns.** Valeo, Siemens, Vodafone, Synopsys, Cadence, Schneider, etc. — they post on their own ATS portals, not on Wuzzuf. Aggregator-first hunting misses them entirely.
- **No memory.** Every time I checked back, I re-evaluated the same jobs. No deduplication, no progress.

So I prompted Claude with "find me Cairo Summer 2026 internships" and watched it return more 7-year-old results from Google, give up at LinkedIn's auth wall, and pad the list with marketing roles. The classic LLM web-search failure mode: snippets are stale, anti-bot walls are real, and Google doesn't actually know what's posted right now.

I needed something that:
1. Walked **company career portals directly**, not aggregators.
2. Actually opened pages in a real browser, not WebFetch.
3. Read every job description **end to end** with an LLM, not keyword-grepping the title.
4. Knew the difference between a real internship and a "Senior Engineer (Graduate Programme)."
5. Remembered what it had already seen across runs so I could check daily without re-processing.
6. Worked for **any major** — not just CE — by taking keywords as input.

That's Mostafa.

---

## How Mostafa works (the architecture)

Mostafa is the third agent in a personal pipeline (after **Hamed**, a lead-gen agent for a web design business, and **Ghali**, a website-builder agent that turns Hamed's leads into deployable cinematic sites). All three follow the same architecture: a **Claude Agent SDK orchestrator** with an in-process MCP server, a small set of focused Playwright tools, a SQLite dedup cache, and persistent output. Mostafa just points the same architecture at a different problem.

```
run.py                     CLI — argparse, defaults from .env
config.py                  User profile + portal seed list + env-driven knobs
agent/
  orchestrator.py          Mostafa's brain: system prompt, MCP tools, ClaudeSDKClient
  browser.py               Singleton Playwright Chromium (auto-loads LinkedIn auth)
  tools/
    discover.py            Google search → company names → guess careers page
    scraper.py             Generic listing walker + per-job DOM reader
    sheets_writer.py       Cumulative markdown report (master + per-run snapshots)
    sheets_appender.py     Optional Google Sheets append-only writer
db/
  cache.py                 SQLite: seen_jobs (URL-keyed) + scanned_companies tracker
output/                    Generated reports (gitignored)
```

### Key design decision #1 — Mostafa is the brain, the tools are dumb

Every previous attempt at this failed because the *scraper* tried to decide what was relevant. Keyword filters always misfire: they accept "Marketing Intern who codes a bit in Python" and reject "Embedded Trainee" because the title doesn't say "intern" in English.

So Mostafa flips the responsibility. The Playwright tools have **one job**: open a page, read the live DOM, return the raw text. They never decide if a job is good. **Mostafa reads every description himself** and applies the rules. This is the only way to consistently catch the edge cases (training programs, fixed-term student contracts, "early careers" tracks, etc.) without false positives.

### Key design decision #2 — Company portals first, aggregators last

The internships I want live on Valeo's, Siemens', Vodafone's, and Synopsys' own career portals. They almost never duplicate to Wuzzuf. So Mostafa's primary loop walks ~30 company portals from the seed list in `config.py` first, then falls back to Wuzzuf and LinkedIn for smaller shops.

### Key design decision #3 — Discovery before scraping

Instead of hardcoding companies, Mostafa Googles `top "{keyword}" companies in {city} careers` for every keyword you pass and dynamically builds a list of companies to scan. Then he calls `guess_careers_page(domain)` which tries `/careers`, `/jobs`, `/work-with-us`, `/about/careers`, etc., until one returns a page with job content.

So if you pass `"civil engineer"`, Mostafa discovers Hassan Allam, Orascom Construction, Arab Contractors, etc. — not just the seed list. The seed list is a *floor*, not a ceiling.

### Key design decision #4 — Persistent dedup is non-negotiable

A SQLite cache (`db/mostafa.db`) keys every URL Mostafa has ever seen with the verdict, reason, fit_score, and raw description. On every new run, `filter_unseen()` removes URLs from previous runs *before* Mostafa fetches them. The cumulative report is rebuilt from the entire cache, so it grows over time and never wipes.

You can run Mostafa daily. He only burns time on new postings. The output file just grows.

### Key design decision #5 — Auto-heal LinkedIn auth

LinkedIn's guest wall blocks job-detail pages. The fix is `playwright codegen --save-storage`, which records your logged-in cookies into a JSON file. Mostafa's `browser.py` auto-detects that file at startup and attaches it to every Playwright context — so once you set it up once, every future run scrapes LinkedIn as you. If the file is missing, Mostafa prints the exact one-line command to generate it and continues in guest mode.

### Key design decision #6 — The 7 hard rules

Earlier versions had 6 rules. I added a 7th (Rule 1) after Mostafa kept returning senior full-time roles labeled as "graduate program":

1. **It is actually an internship / student role — NOT a full-time job.** Mostafa must find positive proof in the description (currently enrolled, must be a student, internship duration, "no prior experience required") OR a clearly intern title. He hard-rejects on senior, lead, principal, manager, "X+ years experience", permanent contract, etc.
2. **Season + year** — defaults to summer 2026.
3. **Posted ≤ N days ago** — defaults to 90, configurable.
4. **Relevant to the user's keywords.** Mostafa rejects marketing/HR/sales/finance/etc. when the keywords are technical.
5. **City + country** explicit match.
6. **Direct individual job URL** with an Apply button — no listing/search pages.
7. **Position still open** — page does not say "no longer accepting" / "closed" / "expired" / 404.

For each ACCEPT, Mostafa is forced to quote a specific sentence from the description as evidence. This stops hallucinated approvals — if he can't quote the proof, he didn't actually read it.

---

## Setup

```bash
# 1. Clone
git clone https://github.com/Zab-17/Mostafa_internship_hunter.git
cd Mostafa_internship_hunter

# 2. Install
pip install -r requirements.txt
playwright install chromium

# 3. Configure
cp .env.example .env
# Edit .env with your name, default city, default keywords, etc.

# 4. (Recommended) Set up LinkedIn auth — one time
playwright codegen --save-storage=$HOME/.linkedin_auth.json https://www.linkedin.com/login
# Log in inside the window that pops up, then close it.
# Mostafa auto-detects the file on every future run.

# 5. (Optional) Set up Google Sheets output
# - Create a Google Cloud service account, download its JSON key as credentials.json
# - Create a Google Sheet, share it with the service account email
# - Set GOOGLE_SHEETS_ID in .env
```

## Usage

```bash
# Default sweep using your .env defaults
python3 -u run.py

# Custom keywords
python3 -u run.py "ai" "machine learning" "computer vision"

# Different city / season / year / max age
python3 -u run.py "data engineer" --city Dubai --country UAE --season fall --year 2026 --max-age 60

# Any major works — Mostafa is generic
python3 -u run.py "civil engineer" "structural engineer"
python3 -u run.py "mechanical engineer" "automotive"
python3 -u run.py "biomedical" "biotech"
```

## What Mostafa actually does on each run

1. **Discover** — for every keyword you pass, Google for companies in your city, then guess each one's careers page (`/careers`, `/jobs`, `/work-with-us`, etc.).
2. **Scrape** — walk every discovered portal + the seed list in `config.py` (Valeo, Siemens, Vodafone, Microsoft, Google, IBM, Synopsys, Cadence, Schneider, ABB, Orange, Ericsson, Nokia, Huawei, Honeywell, SLB, PwC, Deloitte, Paymob, MNT-Halan, Instabug, Swvl, etc.) + Wuzzuf + LinkedIn search per keyword.
3. **Read** — for each NEW URL (auto-deduped against the SQLite cache), open the page in headless Chromium, extract title + full description + requirements text, then personally read it.
4. **Verdict** — apply the 7 hard rules. Save ACCEPT or REJECT with a one-sentence reason that quotes a specific sentence from the description as evidence.
5. **Track** — record every real company portal scanned (Vodafone, Siemens, etc.) so the report shows where the leads came from.
6. **Report** — append accepted leads to:
   - `output/mostafa_all_leads.md` — cumulative master file (rebuilt from cache, never wiped, only grows)
   - Google Sheet "Mostafa Internships" tab — append-only, columns: Scrape Date | Company | Job Title | Posted | Fit Score | Reason | Apply URL | Source

## Security notes

- **Never commit `credentials.json`, `.env`, `linkedin_auth.json`, or `db/*.db`** — all gitignored.
- The Google service account JSON gives full access to any sheet shared with its email. Treat it like a password.
- LinkedIn auth state contains your full session cookies. Treat it like a password too.
- Mostafa runs in headless mode by default. He never submits forms, never clicks "Apply" — he only reads.
- Rate-limit yourself: don't run him more than once every few hours per IP, or LinkedIn/Wuzzuf will throttle.

## Sister agents

Mostafa is part of a three-agent pipeline by the same author:
- **Hamed** — lead generation for a web design agency (scrapes Google Maps for businesses needing new websites).
- **Ghali** — website builder (generates + deploys cinematic static sites for Hamed's leads).
- **Mostafa** — internship hunter (this repo).

All three share the same architecture: Claude Agent SDK orchestrator + in-process MCP server + Playwright tools + SQLite dedup + persistent output. Reference one when implementing another.

## License

MIT
