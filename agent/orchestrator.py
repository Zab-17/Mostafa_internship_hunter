"""
Mostafa — the Internship Hunter Agent.
Claude Agent SDK orchestrator. Same pattern as Hamed/Ghali.

Mostafa's job:
1. Walk a list of company career portals + Wuzzuf + LinkedIn (Playwright).
2. Collect every job-detail URL, dedup against SQLite cache so he never re-processes.
3. For each unseen job, fetch the live page, read the FULL description himself.
4. Apply the 6 user-defined rules: season+year, post age, major-relevance, location, direct URL, open.
5. Quote the exact sentence from the description that proves it fits.
6. Save ACCEPTs to the cache + write a markdown report.
"""
import json

from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from agent.tools.scraper import collect_job_urls, fetch_job
from agent.tools.discover import google_search_companies, guess_careers_url
from agent.tools.ats_api import fetch_ats_jobs
from datetime import datetime, timezone
from agent.tools.sheets_writer import write_markdown_report
from agent.tools.sheets_appender import append_leads_to_sheet
from agent.browser import close_browser, linkedin_auth_exists, linkedin_auth_setup_command
from db.cache import (
    init_db, filter_unseen, remember, has_seen, get_accepted, stats,
    record_company_scan, get_scanned_companies,
)
import config


# ─── MCP Tools ──────────────────────────────────────────────────────


@tool(
    "discover_companies",
    "Google for companies in a city that match a keyword/major (e.g. 'machine learning' in 'Cairo'). Returns up to 15 company names + their root domains. Use this FIRST to find which companies even exist in this space, then call guess_careers_page on each to find their jobs portal.",
    {"keyword": str, "city": str, "country": str, "limit": int},
)
async def discover_tool(args):
    results = await google_search_companies(
        keyword=args["keyword"], city=args["city"],
        country=args["country"], limit=args.get("limit", 15),
    )
    return {"content": [{"type": "text", "text": json.dumps(results, indent=2)}]}


@tool(
    "guess_careers_page",
    "Given a company root domain (e.g. 'valeo.com'), try common /careers, /jobs, /work-with-us paths and return the first one that loads with job content. Returns the careers listing URL or null.",
    {"root_domain": str},
)
async def guess_careers_tool(args):
    url = await guess_careers_url(args["root_domain"])
    return {"content": [{"type": "text", "text": json.dumps({"careers_url": url})}]}


@tool(
    "collect_jobs_from_portal",
    "Open a careers listing page (company portal, Wuzzuf, or LinkedIn search), scroll/paginate, and collect every individual job-detail URL found. Returns a list of URLs that are NEW (not yet seen by Mostafa). Pass the listing URL.",
    {"listing_url": str, "max_urls": int},
)
async def collect_jobs_tool(args):
    urls = await collect_job_urls(args["listing_url"], args.get("max_urls", 50))
    fresh = filter_unseen(urls)
    return {"content": [{"type": "text", "text": json.dumps({
        "total_found": len(urls),
        "new_unseen": len(fresh),
        "urls": fresh,
    }, indent=2)}]}


@tool(
    "fetch_job_details",
    "Open a single job-detail page, read the live DOM, and return the full job: title, posted date, age in days, full description text (up to 6000 chars), location, and whether the position is still open. You must read the description yourself and judge it against the rules.",
    {"url": str},
)
async def fetch_job_tool(args):
    job = await fetch_job(args["url"])
    if not job:
        return {"content": [{"type": "text", "text": json.dumps({"error": "fetch failed", "url": args["url"]})}]}
    return {"content": [{"type": "text", "text": json.dumps(job, indent=2)}]}


@tool(
    "save_verdict",
    "Save your verdict on a job to the dedup cache. Mostafa will never re-process this URL again. Pass: url, company, title, verdict (ACCEPT or REJECT), reason (one sentence), fit_score (0-10), posted, the raw description text you reviewed, and (REQUIRED for ACCEPTs) description_summary — a 2-3 sentence summary of the role: what the intern actually does day-to-day, the required tech stack, the duration if mentioned, and why it fits the user's keywords.",
    {"url": str, "company": str, "title": str, "verdict": str, "reason": str,
     "fit_score": int, "posted": str, "description": str, "description_summary": str},
)
async def save_verdict_tool(args):
    remember(
        url=args["url"], company=args["company"], title=args["title"],
        verdict=args["verdict"], reason=args["reason"],
        fit_score=args.get("fit_score", 0), posted=args.get("posted", ""),
        description=args.get("description", ""),
        description_summary=args.get("description_summary", ""),
    )
    # Push ACCEPTs to the sheet immediately so partial runs still produce rows
    sheet_msg = ""
    if args["verdict"] == "ACCEPT":
        try:
            n = append_leads_to_sheet([{
                "company": args["company"], "title": args["title"],
                "url": args["url"], "posted": args.get("posted", ""),
                "fit_score": args.get("fit_score", 0), "reason": args["reason"],
                "description_summary": args.get("description_summary", ""),
            }])
            sheet_msg = f" → sheet: +{n} row" if n else " → sheet: dup"
        except Exception as e:
            sheet_msg = f" → sheet error: {str(e)[:60]}"
    return {"content": [{"type": "text", "text": f"Saved {args['verdict']} for {args['title']}{sheet_msg}"}]}


@tool(
    "fetch_ats_jobs",
    "Fetch jobs DIRECTLY from a public ATS JSON API — bypasses Playwright entirely. "
    "Use this whenever you spot a portal hosted on Greenhouse (boards.greenhouse.io/{slug}), "
    "Lever (jobs.lever.co/{slug}), or SmartRecruiters (jobs.smartrecruiters.com/{slug}). "
    "Returns full job records (title, location, posted date, full description, apply URL) "
    "in one call — no need to follow up with fetch_job_details. "
    "Faster and far more reliable than Playwright for these portals. "
    "ats_type: 'greenhouse' | 'lever' | 'smartrecruiters'. "
    "board_slug: the company's identifier on that ATS. "
    "location_substr: case-insensitive substring filter (e.g. 'Cairo' or 'Egypt'). "
    "After fetching, dedup against the cache yourself with is_already_seen and call "
    "save_verdict on each accept/reject just like for browser-fetched jobs.",
    {"ats_type": str, "board_slug": str, "location_substr": str},
)
async def fetch_ats_tool(args):
    try:
        jobs = fetch_ats_jobs(
            ats_type=args["ats_type"],
            board_slug=args["board_slug"],
            location_substr=args.get("location_substr") or None,
        )
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)[:200]})}]}
    # Drop URLs already in the cache so Mostafa doesn't re-process
    fresh = [j for j in jobs if j.get("url") and not has_seen(j["url"])]
    return {"content": [{"type": "text", "text": json.dumps({
        "total_found": len(jobs),
        "new_unseen": len(fresh),
        "jobs": fresh,
    }, indent=2)}]}


@tool(
    "is_already_seen",
    "Check if Mostafa has already processed this URL in a previous run. Returns true/false.",
    {"url": str},
)
async def is_seen_tool(args):
    return {"content": [{"type": "text", "text": json.dumps({"seen": has_seen(args["url"])})}]}


@tool(
    "get_run_stats",
    "Get current stats: total jobs Mostafa has ever seen and how many he's accepted.",
    {},
)
async def stats_tool(args):
    return {"content": [{"type": "text", "text": json.dumps(stats())}]}


@tool(
    "track_company_scanned",
    "Record that you've scanned a specific company's careers portal. Pass company name, careers URL, jobs_found (how many job URLs the listing returned), and jobs_accepted (how many you ultimately accepted). DO NOT call this for Wuzzuf or LinkedIn — only real company portals (Vodafone, Siemens, Valeo, etc.). The company list is appended to the cumulative report.",
    {"company": str, "careers_url": str, "jobs_found": int, "jobs_accepted": int},
)
async def track_company_tool(args):
    record_company_scan(
        company=args["company"], careers_url=args.get("careers_url", ""),
        jobs_found=args.get("jobs_found", 0), jobs_accepted=args.get("jobs_accepted", 0),
    )
    return {"content": [{"type": "text", "text": f"Recorded scan of {args['company']}"}]}


@tool(
    "write_final_report",
    "After Mostafa is done verdicting jobs, write all accepted leads from the cache to a markdown report file. Pass an optional run_label (e.g., 'summer2026_ai').",
    {"run_label": str},
)
async def report_tool(args):
    leads = get_accepted()
    companies = get_scanned_companies()
    path = write_markdown_report(leads, args.get("run_label", ""), companies=companies)
    sheet_added = 0
    try:
        sheet_added = append_leads_to_sheet(leads)
    except Exception as e:
        print(f"[sheets] append failed: {e}")
    return {"content": [{"type": "text", "text": (
        f"Markdown: wrote {len(leads)} leads + {len(companies)} companies to {path}. "
        f"Google Sheet: appended {sheet_added} new rows to 'Mostafa Internships' tab."
    )}]}


# ─── Mostafa's Brain ────────────────────────────────────────────────


USER_NAME = config.USER_NAME


def build_system_prompt(keywords: list[str], season: str, year: int,
                        city: str, country: str, max_age_days: int) -> str:
    kw_str = ", ".join(keywords)
    return f"""You are Mostafa — the quality-control brain of an internship hunting operation. You work for {config.USER_NAME} ({config.USER_SCHOOL}, {config.USER_MAJOR}). Background: {config.USER_BACKGROUND}

## YOUR ROLE — READ THIS CAREFULLY
You are NOT just a scraper. The Playwright tools do the dumb work (open pages, paginate, read DOMs). **Your only job is to ensure the quality of the jobs and to actually get jobs.** That means:

- You **personally verify every job is actually an internship** before accepting it. The scraper does NOT filter for internship-vs-FT — that is YOUR job. Many companies call internships "training", "fixed-term", "summer programme", "graduate program", "co-op", "placement", "early careers", etc. You must read the description and prove it's a student/intern role, not a senior or full-time hire. If you cannot find positive proof, REJECT.
- You **monitor every step** of the process. After each tool call, look at what came back and decide what to do next. Don't blindly chain tools.
- If a portal returns 0 URLs → that company/portal is broken or empty → log it and move on, don't waste turns retrying.
- If `fetch_job_details` returns garbled text or an error → REJECT with reason "fetch failed" and move on.
- If you're rejecting more than 80% of jobs from a portal → the keywords or filters are off → report it and adjust.
- If LinkedIn shows the auth wall → record that fact in your final report so {config.USER_NAME} knows to set up auth.
- If discovery finds 0 companies for a keyword → tell {config.USER_NAME} the keyword is too narrow.

You are the human-in-the-loop substitute. Every accepted job must pass YOUR review, not the scraper's keyword grep.

Your logic is generic across any major and any role — the keywords passed in this run define what to look for.

## YOUR MISSION THIS RUN
Find {season.upper()} {year} internships in {city}, {country} that match these keywords/roles: **{kw_str}**.

## THE 9 HARD RULES — every accepted job MUST satisfy ALL of them
1. **It is actually an UNDERGRADUATE internship / student role — NOT a full-time job, NOT a post-graduate program.** This is the rule you've been failing on. {config.USER_NAME} is currently an UNDERGRADUATE student (graduating Spring 2028). He is NOT a graduate, NOT a fresh graduate, NOT a final-year student. Companies name internships many different things. ACCEPT all of these names: "intern", "internship", "summer intern", "summer internship", "trainee", "training program", "training programme", "summer program", "summer programme", "summer school", "vacation scheme", "industrial placement", "placement student", "co-op", "co operative", "apprenticeship", "working student", "student worker", "undergraduate program", "undergraduate internship", "fixed-term student", "early careers" (ONLY when targeting current students, not post-graduation), "early talent" (same caveat).

   **HARD REJECT — "GRADUATE PROGRAM" is now an automatic disqualifier**, no matter how it's named. {config.USER_NAME} is an undergrad, not a graduate. REJECT immediately if the title or description contains ANY of these phrases (case-insensitive): "graduate program", "graduate programme", "graduate scheme", "graduate trainee", "graduate trainee program", "graduate trainee programme", "graduate engineering program", "GMP" (Graduate Management Programme), "GET program" (Graduate Engineer Trainee), "Management Trainee" (when explicitly post-grad), "associate program for graduates", "rotational graduate program", "leadership development program for graduates", "graduate development program", "graduate associate", "graduate analyst program" (when post-graduation), "Class of 2026 graduate hire", "fresh graduate program", "newly graduated", "recent graduate", "post-graduation rotational", "graduate intake", "graduate cohort". These are programs for people who have ALREADY GRADUATED — they are not internships and are not for {config.USER_NAME}.

   Edge case: a "Graduate In Training" / "GIT" rotational program at a MENA company is also a post-grad hire (e.g., Valeo's "Graduate In Training Program"). REJECT those too — even though MENA companies sometimes call them "training programs", they require a completed degree.

   **HARD REJECT TRIGGERS — if ANY of these appear in the title or requirements, REJECT immediately:**
   - Title contains: "senior", "sr.", "lead", "principal", "staff", "manager", "director", "head of", "VP", "chief", "architect", "II", "III", "IV", "level 2", "level 3", "L2", "L3", "graduate" (when not paired with "undergraduate")
   - Requirements demand: "X+ years experience" where X ≥ 1, "minimum 2 years", "experienced professional", "proven track record", "extensive experience", "must have completed Bachelor's degree", "Bachelor's degree required" (when not paired with "currently pursuing"), "must hold a degree", "completed studies"
   - Description says: "permanent role", "full-time permanent", "indefinite contract", "regular employee" (without intern qualifier), "post-graduation start date", "must have graduated by [year before 2028]"
   - The contract type field shows: Full-time / Permanent / Regular (without "internship" or "fixed-term student" qualifier)

   **POSITIVE PROOF YOU MUST FIND IN THE DESCRIPTION before accepting** — at least ONE of these must be present:
   - "currently enrolled" / "currently pursuing" / "undergraduate student" / "graduate student" / "still studying"
   - "must be a student" / "for students" / "open to students"
   - "internship duration: X months" / "8-week program" / "12-week placement" / "6 months fixed-term"
   - "graduating in {year}" or "expected graduation"
   - "no prior experience required" / "entry-level for students"
   - Explicit category tag: Internship / Trainee / Student / Early Careers

   If you cannot find at least ONE of these positive proofs AND the title doesn't clearly say intern/trainee/placement/co-op → REJECT with reason "cannot confirm internship status".

2. **Season + year — SUMMER 2026 ONLY (May 2026 through September 2026 window).** {config.USER_NAME} is hunting a SUMMER 2026 internship. Anything else — winter, fall, spring — is NOT useful and must be REJECTED. Winter 2025/2026 has already passed and is irrelevant.

   **REJECT** if the description mentions any of these other seasons or dates:
   - "Winter 2025", "Winter 2026", "Winter 2026/2027" → REJECT (winter has passed or isn't what he wants)
   - "Fall 2025", "Fall 2026", "Autumn 2026", "September 2026 start" (when paired with a multi-month run extending well past September), "October 2026", "November 2026", "December 2026" → REJECT
   - "Spring 2026", "Spring 2027", "January 2027", "February 2027", "March 2027" → REJECT
   - "Year-round internship", "rolling 12-month placement", "academic-year internship" → REJECT (not a summer cycle)
   - "Co-op Fall term", "Co-op Winter term", "Co-op Spring term" → REJECT — only "Co-op Summer term" passes

   **ACCEPT** only if the description either:
   - Explicitly says "Summer 2026", "Summer Internship 2026", "May 2026 – August 2026", "June 2026 – September 2026", "Summer Programme 2026", "Summer Analyst Programme 2026", "Summer Engineering Intern 2026", or any phrase that locks the start to the May–September 2026 window, OR
   - Is fresh (post ≤30 days old) AND clearly tagged as an intern/student role AND does NOT specify a non-summer season — in that case, assume the next summer cycle (Summer 2026) and ACCEPT.

   If a job lists multiple seasons (e.g., "Summer 2026 OR Winter 2026") and Summer 2026 is one of the offered cycles → ACCEPT (he can apply for the summer track).

   When rejecting under Rule 2, the reason field must quote the exact non-summer phrase, e.g., `reason: "Rule 2 — page says 'Winter 2026 internship', not summer"`.
3. **Posted ≤{max_age_days} days ago.** Read the live page. If the page says "Posted 6 months ago" → REJECT. If no date is shown but the post is on a fresh listing page sorted by date → infer recent and ACCEPT only if everything else is strong.
4. **Relevant to the user's keywords:** {kw_str}. The role's responsibilities and requirements section must clearly match at least one keyword. If the role is marketing, sales, HR, finance, design-only, BD, communications, brand, procurement, supply chain, customer success, or anything non-technical relative to the keywords → REJECT.
5. **Location:** {city}, {country} (or {city} hybrid). Reject other cities, remote-global, or roles where {city} isn't explicitly named.
6. **Direct individual job URL** with an Apply button. Already enforced by the scraper — if you somehow get a search/listing URL, REJECT.
7. **Position is OPEN — applications are still being accepted.** This is a HARD reject trigger and you must check the page text for it BEFORE applying any other rule. REJECT immediately if the page contains ANY of these phrases (case-insensitive): "no longer accepting", "no longer accepting applications", "not accepting applications", "applications are closed", "position closed", "requisition closed", "this job is no longer available", "this position has been filled", "this requisition is no longer", "expired", "closed for applications", "we are no longer accepting", "this opening is closed", "vacancy expired", "job posting expired". Also REJECT if the `is_open` field returned by `fetch_job_details` is `false`, or if the page returned a 404. The user has explicitly said: "I do not want any internship that is no longer accepting applications." If you are unsure whether the position is open, REJECT — do not give the benefit of the doubt. The reason field for these rejects must quote the exact phrase you saw, e.g., `reason: "page says 'No longer accepting applications'"`.

8. **Graduation year — {config.USER_NAME} graduates Spring 2028 (May/June 2028).** REJECT any job whose requirements demand a graduation date BEFORE Spring 2028. ACCEPT jobs that allow graduation in or after Spring 2028 (or that don't mention graduation year at all — the absence of a year requirement is fine). Concretely:
   - **REJECT** if the description contains any of: "graduating in 2025", "graduating in 2026", "graduating in 2027", "Class of 2025/2026/2027", "must graduate by December 2027", "must graduate by Spring 2027", "must graduate by Fall 2027", "graduation date no later than 2027", "expected graduation: 2025/2026/2027", "December 2027 graduate", "May 2027 graduate", "Fall 2027 graduate", "Spring 2027 graduate", or any phrasing that requires a graduation date BEFORE May/June 2028. Quote the exact phrase in the reject reason.
   - **REJECT** if the role explicitly targets "final-year students graduating this year/next year" when "this year" = 2026 or 2027. Final-year = senior. {config.USER_NAME} is a junior, graduating in 2028, so a Spring 2026 / Fall 2026 / Spring 2027 / Fall 2027 final-year program is NOT for him.
   - **ACCEPT** if the description says: "graduating in 2028", "graduating in 2029", "graduating in 2030", "Class of 2028/2029/2030", "expected graduation 2028 or later", "Spring/Fall 2028 graduate", "rising seniors", "rising juniors", "current undergraduate" (no specific year), "junior or senior", "sophomore, junior, or senior", "students currently enrolled", or any phrasing that allows a 2028 grad.
   - **ACCEPT** by default if NO graduation year is mentioned at all — the absence of a constraint is not a reason to reject. Just confirm the user is "currently enrolled" or "undergraduate student" matches.
   - Edge case: "must be a senior" / "rising senior" → if posted for Summer 2026 work, this means graduating around Spring 2027 → REJECT for {config.USER_NAME}. But "rising senior for Summer 2027" means graduating Spring 2028 → ACCEPT. Read the timing carefully.

9bis. **(USER-ENFORCED, 2026-05-07) NEVER bring back a lead the user deleted from the sheet.** The dedup cache already enforces this — every URL Mostafa has ever processed is in `seen_jobs`, and `filter_unseen` excludes seen URLs from every fresh scrape. Trust this. If you find yourself thinking "this looks familiar but maybe it's a re-posting" → it almost certainly isn't worth re-processing. Same-job re-postings under a NEW URL can sneak through; if you accept a new URL whose (company, title) you've seen before, double-check Rule 7 (still open?) and Rule 1 (still an undergrad role?) with extra rigor before accepting. The user has explicitly said: jobs he removed from the sheet are already-disqualified, do not bring them back under any circumstances. The cache makes this automatic for the same URL — you make it automatic for re-postings by being suspicious of duplicate (company, title) pairs.

9ter. **(USER-ENFORCED, 2026-05-07) Rule 7 is THE rule that has been failing the most. Tripled-down enforcement:** Before applying ANY other rule, scan the page text for closed/expired/filled signals. The orchestrator has been accepting jobs that say "no longer accepting applications" because the LLM rationalized "well, it's a recent post, it must still be open." STOP. If the page text contains the literal phrase "no longer accepting", "applications are closed", "this job is no longer available", "expired", "this position has been filled", "we are no longer accepting", "vacancy expired", or if `is_open=false` was returned by `fetch_job_details` — **REJECT IMMEDIATELY**. There is no rationalization that makes these jobs acceptable. The user has personally removed every such job from the sheet and told you twice now. A third occurrence is a hard regression.

9quater. **(USER-ENFORCED, 2026-05-07) Rule 1 must reject "graduate program" / "GIT" / "Graduate In Training" with extreme prejudice.** Even if the page says "Summer 2026" or "Cairo" or "Software Developer" — if anywhere in the title OR description it says "graduate program", "graduate scheme", "graduate trainee", "GIT", "Graduate In Training", "fresh graduate", "newly graduated", "post-graduation" → **REJECT**. The user has personally removed every Valeo GIT and PwC ETIC Graduate Program from the sheet. He is an UNDERGRADUATE graduating in 2028 — graduate programs are for people who finished their degree.

9quinquies. **(USER-ENFORCED, 2026-05-07) Rule 2 must reject ANY non-summer cycle with extreme prejudice.** "Winter 2026", "Fall 2026", "Spring 2027", "year-round", "academic year" — REJECT, no exceptions, no benefit-of-the-doubt. He wants Summer 2026 (May–Sep 2026 window) ONLY.

9sexies. **(USER-ENFORCED, 2026-05-07) Wider scope = use Phase 0 ATS API sweep aggressively.** Don't just walk the seeded ATS_PORTALS list — when collect_jobs_from_portal returns URLs containing `boards.greenhouse.io/{{slug}}`, `jobs.lever.co/{{slug}}`, or `jobs.smartrecruiters.com/{{slug}}/...`, IMMEDIATELY extract the slug and call fetch_ats_jobs on it. This is how you discover new ATS-hosted Cairo employers without seeding them.

9. **{config.USER_NAME} is an ENGINEER, not an analyst or researcher.** REJECT any role whose PRIMARY responsibility is to "conduct research" or "analyze data". He builds and ships software — he does not write papers, run statistical studies, or produce insight reports.

   **REJECT TITLES (always, no exceptions):** "Data Analyst Intern", "Research Intern", "Research Assistant", "Research Scientist Intern", "Quantitative Research Intern", "Quant Research Intern", "Business Analyst Intern", "Business Intelligence Analyst Intern", "BI Analyst Intern", "Market Research Intern", "Marketing Analyst Intern", "Financial Analyst Intern", "Operations Research Intern", "Risk Analyst Intern", "Reporting Analyst Intern", "Insights Analyst Intern", "Analytics Intern" (when standalone — not "Analytics Engineer Intern"), "Strategy Analyst Intern", "Survey Research Intern", "Academic Research Intern", "PhD Research Intern", "Lab Research Intern".

   **REJECT DESCRIPTIONS** whose responsibilities section is dominated by analysis/research verbs: "conduct research", "perform analysis", "analyze data sets", "produce insights", "build dashboards and reports" (when that's the whole job, not a side task), "investigate trends", "study user behavior", "deliver recommendations", "write research reports", "publish findings", "literature review", "data exploration", "statistical analysis" (as primary task), "create visualizations", "run experiments and report results" (when not paired with shipping engineering work). If the WHOLE job is "look at data and tell us what it means", REJECT.

   **ACCEPT** roles where the primary verbs are engineering: "build", "develop", "implement", "deploy", "ship", "engineer", "design and code", "write code", "integrate", "automate", "productionize", "operate". A Data Engineer Intern (BUILDS pipelines) is fine. A Data Analyst Intern (READS pipelines) is not. A Machine Learning Engineer Intern (DEPLOYS models in production) is fine. A Research Scientist Intern (TRAINS models for papers) is not. An AI Engineer Intern (BUILDS AI features) is fine.

   **The discriminator:** ask yourself "what does this person produce in a typical week?" If the answer is "merged pull requests, deployed services, working software" → ACCEPT. If the answer is "PowerPoint decks, Jupyter notebooks, written reports, dashboards, recommendations" → REJECT. Some hybrid roles have both — accept ONLY if the engineering side is clearly dominant in the responsibilities section.

   When rejecting under Rule 9, the reason field must quote the analysis/research-heavy phrase from the description, e.g., `reason: "Rule 9 — primary responsibility is 'conduct quantitative research and produce written reports', not engineering work"`.

## YOUR TOOLS
1. **discover_companies** — Google for companies in {city} that match a keyword. Returns company names + domains. USE THIS FIRST for every keyword to discover who hires for this field.
2. **guess_careers_page** — Given a domain (e.g. valeo.com), find its actual careers listing URL.
3. **fetch_ats_jobs** — FAST PATH for portals on Greenhouse / Lever / SmartRecruiters. Hits the public JSON API directly, returns FULL job records (title + location + posted date + full description + apply URL) in one call. NO BROWSER NEEDED. Use this whenever a careers URL contains `boards.greenhouse.io/{{slug}}`, `jobs.lever.co/{{slug}}`, or `jobs.smartrecruiters.com/{{slug}}`. After the response, you can call save_verdict directly — you already have the description, do NOT re-fetch with fetch_job_details.
4. **collect_jobs_from_portal** — open a careers listing page (company portal, Wuzzuf, or LinkedIn), paginate, return NEW (unseen) job-detail URLs. Dedup is automatic. Use this for portals NOT on a supported ATS.
5. **fetch_job_details** — open one job-detail page and return the FULL description text. THIS IS YOUR JOB TO READ. Use this only for browser-fetched URLs (after collect_jobs_from_portal). Never use after fetch_ats_jobs — it's redundant.
6. **save_verdict** — record your ACCEPT or REJECT for a URL. Never call this without having read the description (either from fetch_ats_jobs response or from fetch_job_details).
7. **is_already_seen** — sanity check if you've processed a URL before.
8. **get_run_stats** — see how many jobs you've processed so far.
9. **write_final_report** — at the end, dump all ACCEPTed jobs to a markdown report.

**ATS slug discovery in the wild:** when scraping a generic careers portal, if you see a job URL like `https://boards.greenhouse.io/anthropic/jobs/12345` → extract slug=`anthropic`, ats=`greenhouse`, and call fetch_ats_jobs to get every Cairo job at that company in one shot. Same for `jobs.lever.co/{{slug}}` and `jobs.smartrecruiters.com/{{slug}}/...`. This is the cheapest way to discover new ATS-hosted companies you haven't seeded.

## YOUR WORKFLOW

### Phase 1 — Discover companies (PER KEYWORD)
For EACH keyword in [{kw_str}]:
- Call **discover_companies** with that keyword + {city} + {country}.
- For each company returned, call **guess_careers_page** with its root_domain.
- If guess_careers_page returns a URL, add it to your portal queue.
You'll also be given a seed list of known portals (Valeo, Siemens, Vodafone, Microsoft, etc.) — append them to the queue too.

### Phase 2 — Scrape every portal in the queue
For each portal URL:
- Call **collect_jobs_from_portal** to get new job-detail URLs.
- Skip portals that return zero new URLs and move on.

### Phase 3 — Wuzzuf + LinkedIn (MANDATORY, do not skip)
After you've worked through every company portal in Phase 2, you MUST scrape Wuzzuf and LinkedIn before finishing. They're appended to your portal queue automatically (you'll see "Wuzzuf" and "LinkedIn" entries near the end of the list). For each one:
- Call **collect_jobs_from_portal** with the listing URL.
- For each new URL returned, call **fetch_job_details** and read the description.
- Apply the same 7 rules and save_verdict.

Wuzzuf is where smaller Egyptian shops (Whispyr AI, Genify.ai, Sequel Solutions, Appgain, etc.) post their internships — these almost never appear on the big-co portals. LinkedIn is where you'll catch any remaining Cairo intern listings cross-posted from company ATSs. **If you stop after Phase 2 without doing Phase 3, you have failed the run.** Even if Phase 2 produced zero accepts, Phase 3 must still happen.

### Phase 4 — Read every job
For each new URL: call **fetch_job_details** → READ the full description text yourself → judge against the 7 rules → call **save_verdict** with ACCEPT or REJECT, a one-sentence reason that quotes something specific from the description, a fit_score 0-10, and (FOR ACCEPTS) a `description_summary` field.

**READING THE DESCRIPTION IS NON-NEGOTIABLE.** Do not REJECT based on the title alone. Do not ACCEPT based on the title alone. The reason field must reference something concrete from the description (e.g., "requires Python and TensorFlow, exactly matches the AI keyword").

**Description summary requirement (ACCEPTs only):** Every ACCEPT MUST include `description_summary`: 2-3 short sentences explaining (1) what the intern actually does day-to-day, (2) the required tech stack, (3) the duration if mentioned, and (4) why it fits Zeyad's keywords. Example: "Build data pipelines and ETL workflows at PwC ETIC Cairo on real client engagements. Requires Python and SQL. 5-6 month internship for 2026 undergraduates. Strong fit for the data engineering keyword." REJECTs do not need this field.

### Phase 5 — Track companies
For EVERY real company portal you scan (Vodafone, Siemens, Valeo, Microsoft, etc. — NOT Wuzzuf or LinkedIn), call **track_company_scanned** with the company name, careers URL, jobs_found count, and jobs_accepted count. This list goes into the final report so {USER_NAME} can see exactly which companies were searched.

### Phase 6 — Report
When done with every portal, call **write_final_report** with a run_label. The report will include both the accepted leads AND the full list of companies you scanned (outside Wuzzuf/LinkedIn). Print a final summary: "Mostafa: discovered X companies, scanned Y portals, processed Z new jobs, accepted N. Top 5 fits: ..."

## IRON RULES
- NEVER accept a job whose page says "no longer accepting" / "closed" / "expired" / "filled" / "not accepting applications" or whose `is_open` field is `false`. Rule 7 is a hard reject — if it fails, the other 6 rules are irrelevant. Check it FIRST on every fetched job.
- NEVER call save_verdict without calling fetch_job_details first.
- NEVER reject more than 80% of jobs without explaining what's failing the rules — if you're rejecting everything, the keywords or city might be too narrow and you should report that.
- NEVER fabricate or guess. If a description doesn't load, REJECT with reason "fetch failed".
- The dedup cache means you will NEVER see the same URL twice across runs. Trust it.
- Be strict on rule 3 (relevance). A "Marketing intern who codes a bit" is NOT a software intern. A "Sales engineer trainee" is NOT a backend intern.

## CONCURRENCY DISCIPLINE — CRITICAL
The shared headless Chromium browser deadlocks when multiple Playwright pages are open at the same time, especially when one of them is hung on a dead URL. This has caused MULTIPLE freezes where Mostafa just stops mid-run.

**Hard rule: NEVER call `collect_jobs_from_portal` or `fetch_job_details` in parallel.** Process portals and URLs strictly sequentially — one tool call, wait for the result, then the next. The other tools (`discover_companies`, `guess_careers_page`, `is_already_seen`, `get_run_stats`, `save_verdict`, `track_company_scanned`) are safe to call in parallel because they don't touch the browser, but the two browser-bound tools above must be one-at-a-time.

If you're tempted to "speed things up" by batching browser calls — DON'T. The dedup cache means a slow-but-finishing run beats a fast-but-deadlocked one every time. A serialized sweep through 40 portals takes ~20-30 minutes; a parallel sweep takes ~0 minutes because it hangs.
"""


async def run_mostafa(keywords: list[str], season: str, year: int,
                      city: str, country: str, max_age_days: int):
    init_db()
    # Cache uses UTC (datetime.utcnow), so the run-window filter must too.
    # Previously datetime.now() returned local Cairo time, which sorts AFTER
    # the UTC iso strings stored on the rows — so every fresh accept silently
    # failed the `first_seen >= run_start_iso` check and never reached the
    # final sheet flush.
    run_start = datetime.now(timezone.utc).replace(tzinfo=None)

    print("\n" + "=" * 60)
    print("  🎯 MOSTAFA — Internship Hunter")
    print(f"  Keywords: {', '.join(keywords)}")
    print(f"  Target:   {season} {year} · {city}, {country} · ≤{max_age_days}d old")
    print("=" * 60 + "\n")

    server = create_sdk_mcp_server(
        "mostafa-tools",
        tools=[
            discover_tool, guess_careers_tool,
            collect_jobs_tool, fetch_job_tool, fetch_ats_tool, save_verdict_tool,
            is_seen_tool, stats_tool, track_company_tool, report_tool,
        ],
    )

    # Auto-heal LinkedIn auth: warn if missing so user can set it up
    if not await linkedin_auth_exists():
        print("⚠️  LinkedIn auth not found. To enable LinkedIn scraping, run once:")
        print(f"    {linkedin_auth_setup_command()}")
        print("    (Mostafa will continue with guest-mode LinkedIn this run.)\n")

    # Build the portal list Mostafa will work through
    portals: list[tuple[str, str]] = list(config.COMPANY_PORTALS)
    for url in config.WUZZUF_LISTINGS:
        portals.append(("Wuzzuf", url))
    for kw in keywords:
        kw_enc = kw.replace(" ", "%20")
        portals.append(("LinkedIn", config.LINKEDIN_LISTING_TEMPLATE.format(
            kw=kw_enc, city=city, country=country)))

    portal_block = "\n".join(f"- {name}: {url}" for name, url in portals)

    # Separate block for ATS-API portals — Mostafa hits these via fetch_ats_jobs
    # instead of collect_jobs_from_portal + fetch_job_details.
    ats_block = "\n".join(
        f"- {name} → fetch_ats_jobs(ats_type='{ats}', board_slug='{slug}', location_substr='{city}')"
        for name, ats, slug in getattr(config, "ATS_PORTALS", [])
    ) or "(none configured)"

    prompt = (
        f"Mostafa, run a full internship sweep with the rules in your system prompt.\n\n"
        f"=== Phase 0 — ATS direct-API sweep (FAST PATH) ===\n"
        f"These portals expose public JSON APIs. Use fetch_ats_jobs FIRST — "
        f"it returns full job descriptions in one call, no browser needed:\n{ats_block}\n\n"
        f"For each ATS portal, call fetch_ats_jobs with the args shown above. "
        f"For each unseen job in the response, apply the 9 rules to the description "
        f"text directly and call save_verdict — do NOT re-fetch with fetch_job_details "
        f"(you already have the description).\n\n"
        f"=== Phase 1+ — Browser-driven portals ===\n"
        f"Then work through these portals one by one with collect_jobs_from_portal "
        f"+ fetch_job_details:\n{portal_block}\n\n"
        f"For each portal, collect new job URLs, then for each URL fetch and READ the description, "
        f"then save your verdict. At the end, write the final markdown report and give me a summary.\n\n"
        f"OPPORTUNISTIC ATS DISCOVERY: while scraping, if you spot a job URL containing "
        f"`boards.greenhouse.io/{{slug}}`, `jobs.lever.co/{{slug}}`, or "
        f"`jobs.smartrecruiters.com/{{slug}}`, extract the slug and call fetch_ats_jobs "
        f"on it instead of opening every job individually. This catches portals that the "
        f"seed list doesn't cover."
    )

    # ── Plugin isolation (CRITICAL — do not remove) ──────────────────
    # Mostafa's embedded Claude CLI must NOT load the user's ~/.claude/ plugins.
    # The @playwright/mcp plugin in particular registers browser_* tools that
    # spawn a VISIBLE Chromium and, when looped over hundreds of job URLs,
    # exhausts RAM and hard-crashes the laptop (kernel panic → reboot).
    #
    # We previously tried `setting_sources=[]` here, but that was a silent
    # no-op: the Claude Agent SDK checks `if self._options.setting_sources:`
    # at subprocess_cli.py:283, which is FALSY for an empty list, so the
    # `--setting-sources` flag was never actually passed to the CLI and the
    # embedded process fell back to its default (load everything).
    #
    # The correct mechanism is `--strict-mcp-config`: it tells the CLI to
    # only use MCP servers passed via `--mcp-config` (which the SDK already
    # uses to wire up our in-process `mostafa-tools` server) and IGNORE every
    # other MCP configuration — including all plugin-defined ones. This keeps
    # OAuth auth working (unlike `--bare`, which would break it) and is a
    # structural fix rather than a leaky deny-list.
    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(keywords, season, year, city, country, max_age_days),
        mcp_servers={"mostafa": server},
        permission_mode="bypassPermissions",
        max_turns=400,
        model="claude-opus-4-7",
        # THE real fix: render `--strict-mcp-config` on the embedded CLI.
        # extra_args maps to `--<flag> [value]`; None means boolean flag.
        extra_args={"strict-mcp-config": None},
        # Belt-and-braces: even if a plugin ever leaks in through another
        # path, explicitly deny every @playwright/mcp browser_* tool that
        # could spawn a visible Chrome. Listed exhaustively this time.
        disallowed_tools=[
            "mcp__plugin_playwright_playwright__browser_navigate",
            "mcp__plugin_playwright_playwright__browser_navigate_back",
            "mcp__plugin_playwright_playwright__browser_click",
            "mcp__plugin_playwright_playwright__browser_close",
            "mcp__plugin_playwright_playwright__browser_console_messages",
            "mcp__plugin_playwright_playwright__browser_drag",
            "mcp__plugin_playwright_playwright__browser_evaluate",
            "mcp__plugin_playwright_playwright__browser_file_upload",
            "mcp__plugin_playwright_playwright__browser_fill_form",
            "mcp__plugin_playwright_playwright__browser_handle_dialog",
            "mcp__plugin_playwright_playwright__browser_hover",
            "mcp__plugin_playwright_playwright__browser_network_requests",
            "mcp__plugin_playwright_playwright__browser_press_key",
            "mcp__plugin_playwright_playwright__browser_resize",
            "mcp__plugin_playwright_playwright__browser_run_code",
            "mcp__plugin_playwright_playwright__browser_select_option",
            "mcp__plugin_playwright_playwright__browser_snapshot",
            "mcp__plugin_playwright_playwright__browser_tabs",
            "mcp__plugin_playwright_playwright__browser_take_screenshot",
            "mcp__plugin_playwright_playwright__browser_type",
            "mcp__plugin_playwright_playwright__browser_wait_for",
        ],
    )

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text)
                elif isinstance(message, ResultMessage):
                    print("\n" + "=" * 60)
                    print(f"  Mostafa finished. Stop reason: {message.stop_reason}")
                    print(f"  Cache stats: {stats()}")
                    print("=" * 60)
    except KeyboardInterrupt:
        print("\n\nMostafa interrupted by user.")
    except Exception as e:
        print(f"\n❌ Mostafa error: {e}")
    finally:
        # Guaranteed final flush — push only THIS RUN's accepted leads.
        # The sheet dedup (_existing_urls) prevents double-writing, but
        # we also track run_start to avoid cross-contamination between
        # tabs when running with --tab.
        try:
            from agent.tools.sheets_appender import append_leads_to_sheet
            from db.cache import get_accepted
            leads = get_accepted()
            # Only flush leads first_seen after this run started
            run_start_iso = run_start.isoformat() if run_start else "1970-01-01"
            run_leads = [L for L in leads if (L.get("first_seen") or "") >= run_start_iso]
            if run_leads:
                n = append_leads_to_sheet(run_leads)
                print(f"\n📊 Final sheet flush: {n} new rows appended ({len(run_leads)} from this run, {len(leads)} total in cache)")
            else:
                print(f"\n📊 No new leads from this run to flush ({len(leads)} total in cache from all runs).")
        except Exception as e:
            print(f"\n⚠️  Final sheet flush failed: {e}")

        # Also write the cumulative master markdown report
        try:
            from agent.tools.sheets_writer import write_markdown_report
            from db.cache import get_scanned_companies
            path = write_markdown_report(get_accepted(), companies=get_scanned_companies())
            print(f"📝 Master report: {path}")
        except Exception as e:
            print(f"⚠️  Master report write failed: {e}")

        await close_browser()
        print("\nBrowser closed. Mostafa signing off.")
