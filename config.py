"""
Mostafa — Internship Hunter Agent
Generic config. Override anything per-run via CLI flags in run.py
or via environment variables.

⚠️  No secrets in this file. All sensitive values come from environment
variables. See `.env.example` for the full list.
"""
import os
from pathlib import Path

# Load .env if present (no extra dep — minimal parser)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
        # Don't override variables already set in the real environment
        os.environ.setdefault(_k, _v)


# ─── User profile (override via env vars or by editing this file locally) ──
# These are defaults shown in Mostafa's system prompt so he understands who
# he's working for. They are NOT secrets — but they are personal, so the
# defaults below are placeholders. Set the real values in your local .env.
USER_NAME = os.environ.get("MOSTAFA_USER_NAME", "Your Name")
USER_SCHOOL = os.environ.get("MOSTAFA_USER_SCHOOL", "Your University")
USER_MAJOR = os.environ.get("MOSTAFA_USER_MAJOR", "Your Major, Your Year")
USER_BACKGROUND = os.environ.get(
    "MOSTAFA_USER_BACKGROUND",
    "List your stack and projects here so Mostafa can calibrate fit scores.",
)


# ─── Keyword profiles (select via --profile flag in run.py) ────────────
PROFILE_AI = [
    # ─ Original generalist coverage ─
    "software engineer", "ai", "machine learning",
    "backend", "full stack", "data engineer", "computer engineer",

    # ─ Tier 1 — AI / LLM / automation direct hits ─
    "ai engineer", "llm engineer", "ai agent engineer",
    "agentic ai", "applied ai", "generative ai",
    "automation engineer", "ai automation", "prompt engineer",

    # ─ Tier 2 — adjacent roles ─
    "machine learning engineer", "mlops",
    "workflow automation", "rpa developer",
    "process automation", "intelligent automation",
    "ai integration", "ai solutions engineer", "developer experience",

    # ─ Tier 3 — high-signal longtails (rare but high hit-rate) ─
    "langchain", "langgraph", "claude agent sdk",
    "playwright automation", "fastapi", "openai",
    "retrieval augmented generation", "ai orchestration",

    # ─ Tier 4 — portfolio-specific additions (May 2026, derived from
    #   Zeyad's GitHub: Ahmed/canvas-reminder/ical-whatsapp-reminder
    #   chatbots; content-creation-automation Remotion+Node;
    #   calc-react/woordle.react React work; cross-cutting Python+JS) ─
    "chatbot developer", "whatsapp automation",
    "automation specialist", "web scraping",
    "python developer", "node.js developer",
    "react developer", "product engineer",
]

PROFILE_ELECTRONICS = [
    "electronics engineer", "embedded systems", "firmware engineer",
    "FPGA", "VLSI", "ASIC design", "PCB design", "hardware engineer",
    "analog design", "digital design", "RF engineer", "power electronics",
    "signal processing", "embedded software", "microcontroller",
    "chip design", "verification engineer", "RTL design",
    "circuit design", "semiconductor",
    "supply chain", "communications engineer",
    "electronics and communications research",
    "electronics circuit design", "field test engineer",
    "network planning engineer", "service engineer",
    "signal processing engineer", "systems engineer", "technical director",
]

PROFILE_MECHATRONICS = [
    "mechatronics", "mechatronics engineer", "robotics engineer", "robotics",
    "control systems engineer", "control engineer", "motion control",
    "industrial automation", "automation engineer", "process automation",
    "manufacturing engineer", "production engineer", "smart manufacturing",
    "industry 4.0", "PLC programming", "PLC engineer", "SCADA engineer",
    "HMI engineer", "instrumentation engineer", "servo drives",
    "mechanical design engineer", "mechanical engineer", "CAD engineer",
    "robotic process automation", "drives engineer",
]

PROFILES = {
    "ai": PROFILE_AI,
    "electronics": PROFILE_ELECTRONICS,
    "mechatronics": PROFILE_MECHATRONICS,
    "all": PROFILE_AI + PROFILE_ELECTRONICS + PROFILE_MECHATRONICS,
}

# Default profile is "ai" (profile 1)
DEFAULT_KEYWORDS = PROFILE_AI
DEFAULT_CITY = os.environ.get("MOSTAFA_DEFAULT_CITY", "Cairo")
DEFAULT_COUNTRY = os.environ.get("MOSTAFA_DEFAULT_COUNTRY", "Egypt")
DEFAULT_SEASON = os.environ.get("MOSTAFA_DEFAULT_SEASON", "summer")
DEFAULT_YEAR = int(os.environ.get("MOSTAFA_DEFAULT_YEAR", "2026"))
MAX_AGE_DAYS = int(os.environ.get("MOSTAFA_MAX_AGE_DAYS", "90"))
MIN_LEADS_TARGET = int(os.environ.get("MOSTAFA_MIN_LEADS", "15"))


# ─── Auth state for LinkedIn ──────────────────────────────────────────
# If this file exists, Mostafa logs in as you automatically.
# Generate with:
#   playwright codegen --save-storage=$HOME/.linkedin_auth.json https://www.linkedin.com/login
LINKEDIN_AUTH_PATH = os.environ.get(
    "LINKEDIN_AUTH_PATH",
    str(Path.home() / ".linkedin_auth.json"),
)


# ─── Google Sheets (optional) ─────────────────────────────────────────
# Mostafa appends accepted leads to a "Mostafa Internships" tab in this
# spreadsheet. If GOOGLE_SHEETS_ID is unset, sheet writes are skipped
# and only the local markdown report is produced.
GOOGLE_SHEETS_ID = os.environ.get("GOOGLE_SHEETS_ID", "")
GOOGLE_CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_CREDENTIALS_PATH",
    str(Path(__file__).parent / "credentials.json"),
)


# ─── Tier 1 — Company-owned career portals ───────────────────────────
# Each entry: (company_name, careers_listing_url)
# Mostafa walks every URL with Playwright, collects job detail links, reads them.
# Edit this list freely — it's not a secret.
COMPANY_PORTALS = [
    # Automotive / hardware / embedded — verified URLs (Apr 2026)
    ("BMW Group",            "https://www.bmwgroup.jobs/global/en/jobs.html?country=Egypt"),
    ("Bavarian Auto Group",  "https://bag.com.eg/careers/"),
    ("Valeo",                "https://jobs.smartrecruiters.com/Valeo"),
    ("Siemens",              "https://jobs.siemens.com/careers?location=Egypt&pid=&filter_include_remote=false"),
    ("Siemens EDA",          "https://jobs.sw.siemens.com/locations/egy/jobs/"),
    ("Bosch",                "https://jobs.smartrecruiters.com/BoschGroup?search=&country=Egypt"),
    ("Schneider Electric",   "https://careers.se.com/jobs?keywords=&location=Egypt&page=1"),
    ("ABB",                  "https://careers.abb.com/global/en/search-results?keywords=&location=Egypt"),
    ("Garmin",               "https://careers.garmin.com/careers-home/jobs?locations=Egypt"),
    ("Honeywell",            "https://careers.honeywell.com/us/en/search-results?keywords=&country=Egypt"),

    # Telecom — verified
    ("Vodafone",             "https://opportunities.vodafone.com/search/?createNewAlert=false&q=&locationsearch=Cairo&optionsFacetsDD_country=EG"),
    ("e&",                   "https://www.eand.com/en/about-us/careers.html"),
    ("Orange Egypt",         "https://orange.jobs/jobs/search.aspx?LCID=1033&country=Egypt"),
    ("Ericsson",             "https://jobs.ericsson.com/careers?location=Egypt&pid=&domain=ericsson.com&sort_by=relevance"),
    ("Nokia",                "https://fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/requisitions?keyword=&location=Egypt"),
    ("Huawei",               "https://career.huawei.com/reccampportal/portal5/social-recruitment.html?locationName=Egypt"),

    # Big Tech
    ("Microsoft",            "https://jobs.careers.microsoft.com/global/en/search?lc=Egypt&et=Internship"),
    ("Google",               "https://www.google.com/about/careers/applications/jobs/results/?location=Egypt&employment_type=INTERN"),
    ("Amazon",               "https://www.amazon.jobs/en/search?base_query=intern&loc_query=Cairo&country%5B%5D=EGY"),
    ("IBM",                  "https://careers.ibm.com/search/?q=intern&country=EG"),
    ("Oracle",               "https://eeho.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions?location=Egypt&locationLevel=country"),
    ("Dell",                 "https://jobs.dell.com/en/search-jobs/Egypt/375/2/2"),
    ("Cisco",                "https://jobs.cisco.com/jobs/SearchJobs/?listFilterMode=1&21181=%5B%22Egypt%22%5D"),

    # Chip design / EDA
    ("Synopsys",             "https://careers.synopsys.com/search-jobs/Egypt/44805/1"),
    ("Cadence",              "https://cadence.wd1.myworkdayjobs.com/External_Careers?locationCountry=Egypt"),

    # Energy / oilfield
    ("SLB (Schlumberger)",   "https://careers.slb.com/jobsearch?location=Egypt&keyword=intern"),
    ("Halliburton",          "https://jobs.halliburton.com/search/?q=intern&locationsearch=Egypt"),
    ("Baker Hughes",         "https://careers.bakerhughes.com/global/en/search-results?keywords=intern&country=Egypt"),

    # Consulting tech arms
    ("PwC Middle East",      "https://www.pwc.com/m1/en/careers/experienced-jobs/jobs-list.html"),
    ("Deloitte",             "https://jobsmiddleeast.deloitte.com/middleeast/job-search-results/?keywords=intern&location=Egypt"),
    ("EY",                   "https://careers.ey.com/ey/search/?createNewAlert=false&q=intern&locationsearch=Egypt"),
    ("Accenture",            "https://www.accenture.com/eg-en/careers/jobsearch?jk=intern&jl=Cairo"),

    # Electronics / semiconductors — added Apr 2026
    ("Intel",                "https://jobs.intel.com/en/search-jobs/Egypt"),
    ("Alcatel-Lucent Enterprise", "https://www.al-enterprise.com/en/company/careers"),

    # Consulting / industrial — added Apr 2026
    ("Booz Allen Hamilton",  "https://careers.boozallen.com/jobs/search?location=Egypt"),
    ("P&G",                  "https://www.pgcareers.com/global/en/search-results?keywords=&country=Egypt"),

    # MENA tech
    ("ITWorx",               "https://www.itworx.com/careers/"),

    # MENA scaleups (often have own ATS)
    ("Paymob",               "https://paymob.com/en/careers"),
    ("MNT-Halan",            "https://halan.com/careers"),
    ("Instabug",             "https://instabug.com/jobs"),
    ("Swvl",                 "https://www.swvl.com/careers"),

    # ─── Apr 2026 expansion — high-yield Cairo CS/CE/AI sources ───
    # Egyptian banks with formal tech/IT internship programs
    ("CIB Egypt",            "https://careers.cibeg.com/jobs"),
    ("QNB Alahli",           "https://www.qnbalahli.com/sites/qnb/qnbegypt/page/careers"),
    ("Banque Misr",          "https://www.banquemisr.com/en/careers"),
    ("NBE",                  "https://www.nbe.com.eg/NBE/E/#/EN/CareerOpportunities"),
    ("EFG Hermes",           "https://efghermes.bamboohr.com/careers"),
    ("Beltone Holding",      "https://beltoneholding.com/careers/"),

    # Chip / EDA / semiconductor R&D — strong Cairo presence
    ("AMD",                  "https://careers.amd.com/careers-home/jobs?location=Egypt"),
    ("ARM",                  "https://careers.arm.com/search-jobs/Egypt"),
    ("Mentor (legacy)",      "https://careers.mentor.com/search-jobs/Egypt"),
    ("Qualcomm",             "https://careers.qualcomm.com/careers/SearchJobs/?listFilterMode=1&21181=%5B%22Egypt%22%5D"),

    # Big enterprise — Cairo offices that hire interns
    ("SAP Egypt",            "https://jobs.sap.com/search/?q=&locationsearch=Cairo&country=EG"),
    ("Capgemini Egypt",      "https://www.capgemini.com/jobs/?query=&category=&location=Cairo"),
    ("Atos",                 "https://atos.net/en/careers/job-search?location_country=Egypt"),
    ("DXC Technology",       "https://careers.dxc.com/global/en/search-results?keywords=&location=Egypt"),
    ("KPMG Egypt",           "https://www.kpmg.com/eg/en/home/careers.html"),

    # Fintech / startups in Cairo
    ("Fawry",                "https://fawry.com/careers/"),
    ("Khazna",               "https://khazna.app/careers/"),
    ("Sympl",                "https://sympl.ai/careers"),
    ("Trella",               "https://www.trella.app/careers"),
    ("MaxAB",                "https://maxab.io/careers"),
    ("Breadfast",            "https://breadfast.com/careers"),
    ("Aramex",               "https://www.aramex.com/careers"),

    # MENA software houses with intern programs
    ("Sumerge",              "https://sumerge.com/careers/"),
    ("Robusta Studio",       "https://robustastudio.com/careers"),
    ("Cequens",              "https://www.cequens.com/careers"),
    ("Almentor",             "https://www.almentor.net/careers"),

    # Telco — additional
    ("Telecom Egypt (WE)",   "https://www.te.eg/wps/portal/te/Personal/Discover_more/About_Us/careers"),
    ("Etisalat Misr",        "https://www.eand.com/en/about-us/careers.html"),

    # Cloud / SaaS with MENA hiring
    ("ServiceNow",           "https://careers.servicenow.com/jobs/?country=Egypt"),
    ("Salesforce",           "https://careers.salesforce.com/en/jobs/?location=Egypt"),
]

# ─── Tier 1.5 — ATS direct-API portals ───────────────────────────────
# Each entry: (display_name, ats_type, board_slug)
# ats_type ∈ {"greenhouse", "lever", "smartrecruiters"}
# Mostafa hits these via JSON, no browser. Filter by Cairo/Egypt server-side.
# Add new ones whenever you discover them (e.g. spotted a `boards.greenhouse.io/{x}`
# link → append ("Company", "greenhouse", "x")).
ATS_PORTALS = [
    # SmartRecruiters — verified country=eg filter works
    ("Bosch (ATS API)", "smartrecruiters", "BoschGroup"),
    ("Valeo (ATS API)", "smartrecruiters", "Valeo"),

    # Greenhouse — discover slugs by spotting `boards.greenhouse.io/{slug}` URLs
    # in the wild. Many MENA-hiring companies route through Greenhouse:
    ("Stripe (ATS API)", "greenhouse", "stripe"),
    ("GitLab (ATS API)", "greenhouse", "gitlab"),
    ("Zendesk (ATS API)", "greenhouse", "zendesk"),

    # Lever — discover slugs by spotting `jobs.lever.co/{slug}` URLs
    # (Mostafa can extract these from Google search results).
]


# ─── Tier 3 — Aggregators (Wuzzuf + LinkedIn) ────────────────────────
WUZZUF_LISTINGS = [
    "https://wuzzuf.net/internships/in/cairo",
    "https://wuzzuf.net/jobs/egypt/cairo?filters[post_date][0]=within_1_month",
]
LINKEDIN_LISTING_TEMPLATE = (
    "https://www.linkedin.com/jobs/search/?keywords={kw}"
    "&location={city}%2C%20{country}&f_TPR=r7776000&f_E=1&sortBy=DD"
)

# ─── Filters ─────────────────────────────────────────────────────────
BLOCK_TERMS = [
    "marketing", "sales", "hr ", "human resources", "graphic", "content writer",
    "social media", "business development", "accountant", "finance", "legal",
    "procurement", "supply chain", "communications", "brand", "customer success",
]
INTERN_SIGNALS = [
    "intern", "internship", "trainee", "graduate", "co-op",
    "summer programme", "summer program", "placement", "vacation scheme",
    "early careers", "early talent", "working student", "apprenticeship",
]
