"""
Batch scraper for Mostafa — collects job URLs from portals and fetches details.
Outputs JSON to stdout for Mostafa (the LLM) to review.

Usage:
  python3 batch_scrape.py collect <listing_url> [max_urls]
  python3 batch_scrape.py fetch <job_url>
  python3 batch_scrape.py fetch_batch <url1> <url2> ...
  python3 batch_scrape.py stats
  python3 batch_scrape.py save <json_string>
  python3 batch_scrape.py track <json_string>
  python3 batch_scrape.py report <run_label>
  python3 batch_scrape.py sweep              # run ALL portals sequentially
"""
import sys
import json
import asyncio
import traceback

# Add project root to path
sys.path.insert(0, "/Users/zeyadkhaled/Desktop/Mostafa_internship_hunter")

from agent.tools.scraper import collect_job_urls, fetch_job
from agent.browser import close_browser
from db.cache import (
    init_db, filter_unseen, remember, has_seen, get_accepted, stats,
    record_company_scan, get_scanned_companies,
)
from agent.tools.sheets_writer import write_markdown_report


ALL_PORTALS = [
    ("Valeo", "https://jobs.smartrecruiters.com/Valeo"),
    ("Siemens", "https://jobs.siemens.com/careers?location=Egypt&pid=&filter_include_remote=false"),
    ("Siemens EDA", "https://jobs.sw.siemens.com/locations/egy/jobs/"),
    ("Bosch", "https://jobs.smartrecruiters.com/BoschGroup?search=&country=Egypt"),
    ("Schneider Electric", "https://careers.se.com/jobs?keywords=&location=Egypt&page=1"),
    ("ABB", "https://careers.abb.com/global/en/search-results?keywords=&location=Egypt"),
    ("Garmin", "https://careers.garmin.com/careers-home/jobs?locations=Egypt"),
    ("Honeywell", "https://careers.honeywell.com/us/en/search-results?keywords=&country=Egypt"),
    ("Vodafone", "https://opportunities.vodafone.com/search/?createNewAlert=false&q=&locationsearch=Cairo&optionsFacetsDD_country=EG"),
    ("e&", "https://www.eand.com/en/about-us/careers.html"),
    ("Orange Egypt", "https://orange.jobs/jobs/search.aspx?LCID=1033&country=Egypt"),
    ("Ericsson", "https://jobs.ericsson.com/careers?location=Egypt&pid=&domain=ericsson.com&sort_by=relevance"),
    ("Nokia", "https://fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/requisitions?keyword=&location=Egypt"),
    ("Huawei", "https://career.huawei.com/reccampportal/portal5/social-recruitment.html?locationName=Egypt"),
    ("Microsoft", "https://jobs.careers.microsoft.com/global/en/search?lc=Egypt&et=Internship"),
    ("Google", "https://www.google.com/about/careers/applications/jobs/results/?location=Egypt&employment_type=INTERN"),
    ("Amazon", "https://www.amazon.jobs/en/search?base_query=intern&loc_query=Cairo&country%5B%5D=EGY"),
    ("IBM", "https://careers.ibm.com/search/?q=intern&country=EG"),
    ("Oracle", "https://eeho.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions?location=Egypt&locationLevel=country"),
    ("Dell", "https://jobs.dell.com/en/search-jobs/Egypt/375/2/2"),
    ("Cisco", "https://jobs.cisco.com/jobs/SearchJobs/?listFilterMode=1&21181=%5B%22Egypt%22%5D"),
    ("Synopsys", "https://careers.synopsys.com/search-jobs/Egypt/44805/1"),
    ("Cadence", "https://cadence.wd1.myworkdayjobs.com/External_Careers?locationCountry=Egypt"),
    ("SLB", "https://careers.slb.com/jobsearch?location=Egypt&keyword=intern"),
    ("Halliburton", "https://jobs.halliburton.com/search/?q=intern&locationsearch=Egypt"),
    ("Baker Hughes", "https://careers.bakerhughes.com/global/en/search-results?keywords=intern&country=Egypt"),
    ("PwC", "https://www.pwc.com/m1/en/careers/experienced-jobs/jobs-list.html"),
    ("Deloitte", "https://jobsmiddleeast.deloitte.com/middleeast/job-search-results/?keywords=intern&location=Egypt"),
    ("EY", "https://careers.ey.com/ey/search/?createNewAlert=false&q=intern&locationsearch=Egypt"),
    ("Accenture", "https://www.accenture.com/eg-en/careers/jobsearch?jk=intern&jl=Cairo"),
    ("Paymob", "https://paymob.com/en/careers"),
    ("MNT-Halan", "https://halan.com/careers"),
    ("Instabug", "https://instabug.com/jobs"),
    ("Swvl", "https://www.swvl.com/careers"),
    ("Wuzzuf", "https://wuzzuf.net/internships/in/cairo"),
    ("Wuzzuf", "https://wuzzuf.net/jobs/egypt/cairo?filters[post_date][0]=within_1_month"),
    ("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords=software%20engineer%20intern&location=Cairo%2C%20Egypt&f_TPR=r7776000&f_E=1&sortBy=DD"),
    ("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords=ai%20intern&location=Cairo%2C%20Egypt&f_TPR=r7776000&f_E=1&sortBy=DD"),
    ("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords=machine%20learning%20intern&location=Cairo%2C%20Egypt&f_TPR=r7776000&f_E=1&sortBy=DD"),
    ("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords=backend%20intern&location=Cairo%2C%20Egypt&f_TPR=r7776000&f_E=1&sortBy=DD"),
    ("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords=data%20engineer%20intern&location=Cairo%2C%20Egypt&f_TPR=r7776000&f_E=1&sortBy=DD"),
]


async def sweep():
    """Run ALL portals sequentially, fetch job details, output JSON summary."""
    init_db()
    results = {"portals": [], "jobs": []}

    for company, url in ALL_PORTALS:
        print(f"\n--- {company}: {url[:70]}...", file=sys.stderr)
        try:
            urls = await collect_job_urls(url, max_urls=20)
            fresh = filter_unseen(urls)
            print(f"    Found {len(urls)} URLs, {len(fresh)} new", file=sys.stderr)

            portal = {
                "company": company,
                "listing_url": url,
                "total_found": len(urls),
                "new_unseen": len(fresh),
            }
            results["portals"].append(portal)

            # Fetch details for new URLs (max 10 per portal)
            for job_url in fresh[:10]:
                print(f"    Fetch: {job_url[:70]}...", file=sys.stderr)
                try:
                    job = await fetch_job(job_url)
                    if job:
                        job["source_company"] = company
                        results["jobs"].append(job)
                        print(f"    -> {job.get('title', '?')[:50]}", file=sys.stderr)
                    else:
                        results["jobs"].append({"url": job_url, "source_company": company, "error": "fetch_failed"})
                except Exception as e:
                    results["jobs"].append({"url": job_url, "source_company": company, "error": str(e)[:150]})

        except Exception as e:
            print(f"    ! FAILED: {str(e)[:100]}", file=sys.stderr)
            results["portals"].append({
                "company": company, "listing_url": url,
                "total_found": 0, "new_unseen": 0, "error": str(e)[:200],
            })

    await close_browser()
    print(json.dumps(results, indent=2))


async def main():
    init_db()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "collect":
        url = sys.argv[2]
        max_urls = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        urls = await collect_job_urls(url, max_urls)
        fresh = filter_unseen(urls)
        print(json.dumps({
            "total_found": len(urls),
            "new_unseen": len(fresh),
            "urls": fresh,
        }))
        await close_browser()

    elif cmd == "fetch":
        url = sys.argv[2]
        job = await fetch_job(url)
        if job:
            print(json.dumps(job))
        else:
            print(json.dumps({"error": "fetch failed", "url": url}))
        await close_browser()

    elif cmd == "fetch_batch":
        urls = sys.argv[2:]
        results = []
        for url in urls:
            job = await fetch_job(url)
            if job:
                results.append(job)
            else:
                results.append({"error": "fetch failed", "url": url})
        print(json.dumps(results))
        await close_browser()

    elif cmd == "stats":
        print(json.dumps(stats()))

    elif cmd == "save":
        data = json.loads(sys.argv[2])
        remember(
            url=data["url"], company=data["company"], title=data["title"],
            verdict=data["verdict"], reason=data["reason"],
            fit_score=data.get("fit_score", 0), posted=data.get("posted", ""),
            description=data.get("description", ""),
        )
        print(json.dumps({"saved": True, "verdict": data["verdict"], "title": data["title"]}))

    elif cmd == "track":
        data = json.loads(sys.argv[2])
        record_company_scan(
            company=data["company"], careers_url=data["careers_url"],
            jobs_found=data["jobs_found"], jobs_accepted=data["jobs_accepted"],
        )
        print(json.dumps({"tracked": True, "company": data["company"]}))

    elif cmd == "report":
        label = sys.argv[2] if len(sys.argv) > 2 else "summer2026"
        leads = get_accepted()
        companies = get_scanned_companies()
        path = write_markdown_report(leads, label, companies=companies)
        print(json.dumps({"report_path": path, "leads": len(leads), "companies": len(companies)}))

    elif cmd == "is_seen":
        url = sys.argv[2]
        print(json.dumps({"seen": has_seen(url)}))

    elif cmd == "sweep":
        await sweep()

    else:
        print("Usage: batch_scrape.py [collect|fetch|fetch_batch|stats|save|track|report|is_seen|sweep]")


if __name__ == "__main__":
    asyncio.run(main())
