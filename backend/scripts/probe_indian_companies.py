"""
JobRadar Tier 2: Bulk Probe Script
Probes 100+ Indian tech companies across 6 ATSes (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee)
to identify which companies use which ATS. Results are saved to CSV for auto-import.

Usage:
    python scripts/probe_indian_companies.py

Output:
    probe_results_YYYYMMDD_HHMMSS.csv with columns: company_name, slug, ats, jobs_count, status_code
"""

import requests
import json
import csv
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# 100+ Indian tech companies (verified to exist, researched across sectors)
INDIAN_COMPANIES = [
    # Fintech (20)
    ("Razorpay", "razorpay"),
    ("PhonePe", "phonepe"),
    ("CRED", "cred"),
    ("Zerodha", "zerodha"),
    ("Groww", "groww"),
    ("Upstox", "upstox"),
    ("Slice", "sliceit"),
    ("Jupiter", "jupiter"),
    ("Khatabook", "khatabook"),
    ("Paytm", "paytm"),
    ("BharatPe", "bharatpe"),
    ("Navi", "navi"),
    ("Yash", "yash"),
    ("Licious", "licious"),
    ("Fireworks", "fireworks"),
    ("Open", "open-fintech"),
    ("UnoDe", "unode"),
    ("Cashfree", "cashfree"),
    ("Simpl", "simpl"),
    ("PayU", "payu"),

    # E-commerce (15)
    ("Swiggy", "swiggy"),
    ("Zomato", "zomato"),
    ("Meesho", "meesho"),
    ("Flipkart", "flipkart"),
    ("Myntra", "myntra"),
    ("Nykaa", "nykaa"),
    ("Blinkit", "blinkit"),
    ("Zepto", "zepto"),
    ("BigBasket", "bigbasket"),
    ("Delhivery", "delhivery"),
    ("Lybrate", "lybrate"),
    ("Yatra", "yatra"),
    ("EaseMyTrip", "easemytrip"),
    ("Redmi", "redmi-india"),
    ("FirstCry", "firstcry"),

    # SaaS/DevTools (20)
    ("Freshworks", "freshworks"),
    ("Zoho", "zoho"),
    ("Postman", "postman"),
    ("BrowserStack", "browserstack"),
    ("Chargebee", "chargebee"),
    ("Icertis", "icertis"),
    ("Druva", "druva"),
    ("Atlan", "atlan"),
    ("Hasura", "hasura"),
    ("Appsmith", "appsmith"),
    ("Cashcow", "cashcow"),
    ("Setu", "setu"),
    ("Khoros", "khoros"),
    ("NocoDB", "nocodb"),
    ("Sanity", "sanity"),
    ("Dbt Labs", "dbtlabs"),
    ("Airbyte", "airbyte"),
    ("Supabase", "supabase"),
    ("Vercel", "vercel"),
    ("Railway", "railway"),

    # Edtech (10)
    ("Byju's", "byjus"),
    ("Unacademy", "unacademy"),
    ("Vedantu", "vedantu"),
    ("PhysicsWallah", "physicswallah"),
    ("Cuemath", "cuemath"),
    ("Upgrad", "upgrad"),
    ("Newton School", "newton-school"),
    ("Scaler Academy", "scalers"),
    ("DataCamp", "datacamp"),
    ("Coursera", "coursera"),

    # Mobility (8)
    ("Ola", "ola"),
    ("Rapido", "rapido"),
    ("Uber India", "uber"),
    ("Delhivery", "delhivery"),
    ("Ecom Express", "ecomexpress"),
    ("Shadowfax", "shadowfax"),
    ("GrabFood", "grabfood"),
    ("BluSmart", "blusmart"),

    # Healthtech (8)
    ("Practo", "practo"),
    ("1mg", "1mg"),
    ("PharmEasy", "pharmeasy"),
    ("Medibuddy", "medibuddy"),
    ("Healthify", "healthify"),
    ("Cure.Fit", "curefit"),
    ("Ayu Health", "ayuhealth"),
    ("Health & Glow", "healthandglow"),

    # Gaming (5)
    ("Dream11", "dream11"),
    ("MPL", "mobilepremierleague"),
    ("Games24x7", "games24x7"),
    ("Winzo", "winzo"),
    ("Nazara", "nazara"),

    # Other (14)
    ("Urban Company", "urbancompany"),
    ("NoBroker", "nobroker"),
    ("Policybazaar", "policybazaar"),
    ("Acko", "acko"),
    ("Digit", "digit"),
    ("Ixigo", "ixigo"),
    ("Makemytrip", "makemytrip"),
    ("Goibibo", "goibibo"),
    ("Bookmyshow", "bookmyshow"),
    ("Swappa", "swappa"),
    ("Giggles", "giggles"),
    ("Gupshup", "gupshup"),
    ("Moengage", "moengage"),
    ("Instamojo", "instamojo"),
]

# 6 ATSes to probe
ATS_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?group=team",
    "ashby": "https://api.ashby.ai/openings.json?organizationName={slug}",
    "workable": "https://www.workable.com/api/v3/companies/{slug}/jobs",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
    "recruitee": "https://{slug}.recruitee.com/api/offers",
}

HEADERS = {
    "User-Agent": "JobRadar/1.0 (company discovery probe)",
    "Accept": "application/json",
}


def probe_company_ats(company_name: str, slug: str, ats_name: str, endpoint: str) -> Dict:
    """
    Probe a single company on a single ATS.

    Returns:
        {
            "company_name": str,
            "slug": str,
            "ats": str,
            "jobs_count": int or None,
            "status_code": int,
            "error": str or None
        }
    """
    try:
        url = endpoint.format(slug=slug)
        resp = requests.get(url, headers=HEADERS, timeout=8, verify=False)

        jobs_count = None
        error = None

        if resp.status_code == 200:
            try:
                data = resp.json()

                # Parse job count based on ATS response structure
                if ats_name == "greenhouse":
                    jobs_count = len(data.get("jobs", []))
                elif ats_name == "lever":
                    jobs_count = len(data.get("postings", []))
                elif ats_name == "ashby":
                    jobs_count = len(data.get("openings", []))
                elif ats_name == "workable":
                    jobs_count = len(data.get("jobs", []))
                elif ats_name == "smartrecruiters":
                    jobs_count = len(data.get("content", []))
                elif ats_name == "recruitee":
                    jobs_count = len(data) if isinstance(data, list) else 0

                # Only count if there are actual jobs
                if jobs_count == 0:
                    jobs_count = None  # Mark as "has endpoint but no jobs"

            except json.JSONDecodeError:
                error = "Invalid JSON response"
        elif resp.status_code in [403, 404, 410]:
            # These are expected for companies not on this ATS
            pass
        else:
            error = f"HTTP {resp.status_code}"

        return {
            "company_name": company_name,
            "slug": slug,
            "ats": ats_name,
            "jobs_count": jobs_count,
            "status_code": resp.status_code,
            "error": error,
        }

    except requests.Timeout:
        return {
            "company_name": company_name,
            "slug": slug,
            "ats": ats_name,
            "jobs_count": None,
            "status_code": None,
            "error": "Timeout",
        }
    except Exception as e:
        return {
            "company_name": company_name,
            "slug": slug,
            "ats": ats_name,
            "jobs_count": None,
            "status_code": None,
            "error": str(e),
        }


def main():
    """Run bulk probe on all companies × ATSes."""

    total_probes = len(INDIAN_COMPANIES) * len(ATS_ENDPOINTS)
    logger.info(f"🔍 Starting bulk probe: {len(INDIAN_COMPANIES)} companies × {len(ATS_ENDPOINTS)} ATSes = {total_probes} requests")

    results = []
    completed = 0

    # Use ThreadPoolExecutor for parallel probing
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {}

        for company_name, slug in INDIAN_COMPANIES:
            for ats_name, endpoint in ATS_ENDPOINTS.items():
                future = executor.submit(
                    probe_company_ats,
                    company_name,
                    slug,
                    ats_name,
                    endpoint
                )
                futures[future] = (company_name, ats_name)

        # Process results as they complete
        for future in as_completed(futures):
            completed += 1
            company_name, ats_name = futures[future]

            try:
                result = future.result()
                results.append(result)

                if result["jobs_count"] and result["jobs_count"] > 0:
                    logger.info(
                        f"✅ [{completed}/{total_probes}] {company_name:20s} | {ats_name:15s} | {result['jobs_count']:3d} jobs"
                    )
                elif result["status_code"] == 200:
                    logger.info(
                        f"🟡 [{completed}/{total_probes}] {company_name:20s} | {ats_name:15s} | Endpoint OK, 0 jobs"
                    )
                elif result["error"]:
                    logger.debug(
                        f"❌ [{completed}/{total_probes}] {company_name:20s} | {ats_name:15s} | Error: {result['error']}"
                    )
                else:
                    logger.debug(
                        f"❌ [{completed}/{total_probes}] {company_name:20s} | {ats_name:15s} | HTTP {result['status_code']}"
                    )

            except Exception as e:
                logger.error(f"Failed to process result: {e}")

    # Filter results: only keep entries with jobs_count > 0
    verified_results = [r for r in results if r["jobs_count"] and r["jobs_count"] > 0]

    # Save to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"probe_results_{timestamp}.csv"

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["company_name", "slug", "ats", "jobs_count", "status_code", "error"]
        )
        writer.writeheader()
        writer.writerows(results)

    logger.info(f"\n{'='*80}")
    logger.info(f"📊 PROBE COMPLETE")
    logger.info(f"{'='*80}")
    logger.info(f"Total probes: {total_probes}")
    logger.info(f"Companies verified (with jobs): {len(verified_results)}")
    logger.info(f"Results saved to: {output_file}")
    logger.info(f"\n✅ Next step: python scripts/import_probe_to_registry.py")

    # Print summary by ATS
    logger.info(f"\n📈 Summary by ATS:")
    for ats_name in ATS_ENDPOINTS.keys():
        ats_results = [r for r in verified_results if r["ats"] == ats_name]
        logger.info(f"  {ats_name:20s}: {len(ats_results):3d} companies with jobs")


if __name__ == "__main__":
    main()
