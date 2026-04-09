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
    "Save your verdict on a job to the dedup cache. Mostafa will never re-process this URL again. Pass: url, company, title, verdict (ACCEPT or REJECT), reason (one sentence), fit_score (0-10), posted, and the description text you reviewed.",
    {"url": str, "company": str, "title": str, "verdict": str, "reason": str,
     "fit_score": int, "posted": str, "description": str},
)
async def save_verdict_tool(args):
    remember(
        url=args["url"], company=args["company"], title=args["title"],
        verdict=args["verdict"], reason=args["reason"],
        fit_score=args.get("fit_score", 0), posted=args.get("posted", ""),
        description=args.get("description", ""),
    )
    # Push ACCEPTs to the sheet immediately so partial runs still produce rows
    sheet_msg = ""
    if args["verdict"] == "ACCEPT":
        try:
            n = append_leads_to_sheet([{
                "company": args["company"], "title": args["title"],
                "url": args["url"], "posted": args.get("posted", ""),
                "fit_score": args.get("fit_score", 0), "reason": args["reason"],
            }])
            sheet_msg = f" → sheet: +{n} row" if n else " → sheet: dup"
        except Exception as e:
            sheet_msg = f" → sheet error: {str(e)[:60]}"
    return {"content": [{"type": "text", "text": f"Saved {args['verdict']} for {args['title']}{sheet_msg}"}]}


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

## THE 7 HARD RULES — every accepted job MUST satisfy ALL of them
1. **It is actually an internship / student role — NOT a full-time job.** This is the rule you've been failing on. Companies name internships many different things. ACCEPT all of these names: "intern", "internship", "trainee", "training program", "training programme", "summer program", "summer programme", "summer school", "vacation scheme", "industrial placement", "placement student", "co-op", "co operative", "apprenticeship", "working student", "student worker", "undergraduate program", "graduate program" (ONLY when it explicitly targets fresh graduates / final-year students, NOT experienced grads), "fixed-term student", "early careers", "early talent". REJECT anything that is clearly a permanent / senior role, regardless of how the company markets it. **HARD REJECT TRIGGERS — if ANY of these appear in the title or requirements, REJECT immediately:**
   - Title contains: "senior", "sr.", "lead", "principal", "staff", "manager", "director", "head of", "VP", "chief", "architect", "II", "III", "IV", "level 2", "level 3", "L2", "L3"
   - Requirements demand: "X+ years experience" where X ≥ 1, "minimum 2 years", "experienced professional", "proven track record", "extensive experience"
   - Description says: "permanent role", "full-time permanent", "indefinite contract", "regular employee" (without intern qualifier)
   - The contract type field shows: Full-time / Permanent / Regular (without "internship" or "fixed-term student" qualifier)

   **POSITIVE PROOF YOU MUST FIND IN THE DESCRIPTION before accepting** — at least ONE of these must be present:
   - "currently enrolled" / "currently pursuing" / "undergraduate student" / "graduate student" / "still studying"
   - "must be a student" / "for students" / "open to students"
   - "internship duration: X months" / "8-week program" / "12-week placement" / "6 months fixed-term"
   - "graduating in {year}" or "expected graduation"
   - "no prior experience required" / "entry-level for students"
   - Explicit category tag: Internship / Trainee / Student / Early Careers

   If you cannot find at least ONE of these positive proofs AND the title doesn't clearly say intern/trainee/placement/co-op → REJECT with reason "cannot confirm internship status".

2. **Season + year:** the job is a {season} {year} internship. Dates fall in {season} {year}, OR the post is fresh (≤30 days old) and clearly an intern role with no explicit dates — assume the upcoming {season} {year} cycle and ACCEPT.
3. **Posted ≤{max_age_days} days ago.** Read the live page. If the page says "Posted 6 months ago" → REJECT. If no date is shown but the post is on a fresh listing page sorted by date → infer recent and ACCEPT only if everything else is strong.
4. **Relevant to the user's keywords:** {kw_str}. The role's responsibilities and requirements section must clearly match at least one keyword. If the role is marketing, sales, HR, finance, design-only, BD, communications, brand, procurement, supply chain, customer success, or anything non-technical relative to the keywords → REJECT.
5. **Location:** {city}, {country} (or {city} hybrid). Reject other cities, remote-global, or roles where {city} isn't explicitly named.
6. **Direct individual job URL** with an Apply button. Already enforced by the scraper — if you somehow get a search/listing URL, REJECT.
7. **Position open.** The page does not say "no longer accepting", "closed", "expired", or 404.

## YOUR TOOLS
1. **discover_companies** — Google for companies in {city} that match a keyword. Returns company names + domains. USE THIS FIRST for every keyword to discover who hires for this field.
2. **guess_careers_page** — Given a domain (e.g. valeo.com), find its actual careers listing URL.
3. **collect_jobs_from_portal** — open a careers listing page (company portal, Wuzzuf, or LinkedIn), paginate, return NEW (unseen) job-detail URLs. Dedup is automatic.
4. **fetch_job_details** — open one job-detail page and return the FULL description text. THIS IS YOUR JOB TO READ.
5. **save_verdict** — record your ACCEPT or REJECT for a URL. Never call this without first calling fetch_job_details and actually reading the description.
6. **is_already_seen** — sanity check if you've processed a URL before.
7. **get_run_stats** — see how many jobs you've processed so far.
8. **write_final_report** — at the end, dump all ACCEPTed jobs to a markdown report.

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

### Phase 3 — Also scrape Wuzzuf + LinkedIn
For the broad Wuzzuf listings AND for each keyword on LinkedIn (the seed list already includes them), do the same: collect_jobs_from_portal → fetch_job_details → save_verdict.

### Phase 4 — Read every job
For each new URL: call **fetch_job_details** → READ the full description text yourself → judge against the 6 rules → call **save_verdict** with ACCEPT or REJECT, a one-sentence reason that quotes something specific from the description, and a fit_score 0-10.

**READING THE DESCRIPTION IS NON-NEGOTIABLE.** Do not REJECT based on the title alone. Do not ACCEPT based on the title alone. The reason field must reference something concrete from the description (e.g., "requires Python and TensorFlow, exactly matches the AI keyword").

### Phase 5 — Track companies
For EVERY real company portal you scan (Vodafone, Siemens, Valeo, Microsoft, etc. — NOT Wuzzuf or LinkedIn), call **track_company_scanned** with the company name, careers URL, jobs_found count, and jobs_accepted count. This list goes into the final report so {USER_NAME} can see exactly which companies were searched.

### Phase 6 — Report
When done with every portal, call **write_final_report** with a run_label. The report will include both the accepted leads AND the full list of companies you scanned (outside Wuzzuf/LinkedIn). Print a final summary: "Mostafa: discovered X companies, scanned Y portals, processed Z new jobs, accepted N. Top 5 fits: ..."

## IRON RULES
- NEVER call save_verdict without calling fetch_job_details first.
- NEVER reject more than 80% of jobs without explaining what's failing the rules — if you're rejecting everything, the keywords or city might be too narrow and you should report that.
- NEVER fabricate or guess. If a description doesn't load, REJECT with reason "fetch failed".
- The dedup cache means you will NEVER see the same URL twice across runs. Trust it.
- Be strict on rule 3 (relevance). A "Marketing intern who codes a bit" is NOT a software intern. A "Sales engineer trainee" is NOT a backend intern.
"""


async def run_mostafa(keywords: list[str], season: str, year: int,
                      city: str, country: str, max_age_days: int):
    init_db()

    print("\n" + "=" * 60)
    print("  🎯 MOSTAFA — Internship Hunter")
    print(f"  Keywords: {', '.join(keywords)}")
    print(f"  Target:   {season} {year} · {city}, {country} · ≤{max_age_days}d old")
    print("=" * 60 + "\n")

    server = create_sdk_mcp_server(
        "mostafa-tools",
        tools=[
            discover_tool, guess_careers_tool,
            collect_jobs_tool, fetch_job_tool, save_verdict_tool,
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

    prompt = (
        f"Mostafa, run a full internship sweep with the rules in your system prompt.\n\n"
        f"Work through these portals one by one:\n{portal_block}\n\n"
        f"For each portal, collect new job URLs, then for each URL fetch and READ the description, "
        f"then save your verdict. At the end, write the final markdown report and give me a summary."
    )

    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(keywords, season, year, city, country, max_age_days),
        mcp_servers={"mostafa": server},
        permission_mode="bypassPermissions",
        max_turns=400,
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
        await close_browser()
        print("\nBrowser closed. Mostafa signing off.")
