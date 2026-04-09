"""
Mostafa — Internship Hunter Agent
Generic config. Override anything per-run via CLI flags in run.py
or via environment variables.

⚠️  No secrets in this file. All sensitive values come from environment
variables. See `.env.example` for the full list.
"""
import os
from pathlib import Path


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


# ─── Default search parameters (overridden by CLI flags in run.py) ────
DEFAULT_KEYWORDS = [
    "software engineer", "ai", "machine learning",
    "backend", "full stack", "data engineer", "computer engineer",
]
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
    # Automotive / hardware / embedded
    ("Valeo",                "https://jobs.valeo.com/en/search-jobs/Egypt"),
    ("Siemens",              "https://jobs.siemens.com/jobs?location=Egypt"),
    ("Siemens EDA",          "https://jobs.sw.siemens.com/locations/egy/jobs/"),
    ("Bosch",                "https://www.bosch.com/careers/job-search/?language=en&country=EG"),
    ("Schneider Electric",   "https://careers.se.com/jobs?location=Egypt"),
    ("ABB",                  "https://careers.abb.com/global/en/search-results?location=Egypt"),
    ("Garmin",               "https://careers.garmin.com/careers-home/jobs?locations=Egypt"),
    ("Honeywell",            "https://careers.honeywell.com/us/en/search-results?location=Egypt"),

    # Telecom
    ("Vodafone",             "https://opportunities.vodafone.com/search/?createNewAlert=false&q=&locationsearch=cairo"),
    ("e&",                   "https://careers.eand.com/search/?q=&locationsearch=cairo"),
    ("Orange Egypt",         "https://orange.jobs/jobs/search.aspx?LCID=1033&country=Egypt"),
    ("Ericsson",             "https://jobs.ericsson.com/careers?location=Egypt"),
    ("Nokia",                "https://www.nokia.com/about-us/careers/job-search/?country=Egypt"),
    ("Huawei",               "https://career.huawei.com/reccampportal/portal5/social-recruitment.html?locationName=Egypt"),

    # Big Tech
    ("Microsoft",            "https://jobs.careers.microsoft.com/global/en/search?lc=Egypt"),
    ("Google",               "https://www.google.com/about/careers/applications/jobs/results/?location=Egypt"),
    ("Amazon",               "https://www.amazon.jobs/en/search?loc_query=Cairo"),
    ("IBM",                  "https://careers.ibm.com/search/?q=&location=Egypt"),
    ("Oracle",               "https://eeho.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions?location=Egypt"),
    ("Dell",                 "https://jobs.dell.com/search-jobs/Egypt"),
    ("Cisco",                "https://jobs.cisco.com/jobs/SearchJobs/?21178=%5B169594%5D&21178_format=6020&listFilterMode=1"),

    # Chip design / EDA
    ("Synopsys",             "https://careers.synopsys.com/search-jobs/Egypt"),
    ("Cadence",              "https://cadence.wd1.myworkdayjobs.com/External_Careers?locations=Egypt"),

    # Energy / oilfield
    ("SLB (Schlumberger)",   "https://careers.slb.com/jobsearch?location=Egypt"),
    ("Halliburton",          "https://jobs.halliburton.com/search/?q=&locationsearch=Egypt"),
    ("Baker Hughes",         "https://careers.bakerhughes.com/global/en/search-results?location=Egypt"),

    # Consulting tech arms
    ("PwC Middle East",      "https://www.pwc.com/m1/en/careers/students.html"),
    ("Deloitte",             "https://jobs2.deloitte.com/global/en/search-results?location=Egypt"),
    ("EY",                   "https://careers.ey.com/ey/search/?createNewAlert=false&q=&locationsearch=Egypt"),
    ("Accenture",            "https://www.accenture.com/eg-en/careers/jobsearch"),

    # MENA scaleups (often have own ATS)
    ("Paymob",               "https://paymob.com/en/careers"),
    ("MNT-Halan",            "https://halan.com/careers"),
    ("Instabug",             "https://instabug.com/jobs"),
    ("Swvl",                 "https://www.swvl.com/careers"),
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
