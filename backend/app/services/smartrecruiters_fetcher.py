"""
JobRadar — SmartRecruiters ATS Fetcher (Layer 16)
Fetches jobs from SmartRecruiters' public postings API for known companies.

Free, no API key required. Public job listings are accessible without auth.

Note: Full job descriptions require a separate per-job API call.
We skip that to avoid excessive calls and rely on title-based filtering.

Docs: https://dev.smartrecruiters.com/customer-api/live-docs/posting-api/
"""
import json
import time
import logging
import requests
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure

logger = logging.getLogger(__name__)

SOURCE_NAME = "smartrecruiters"

SMARTRECRUITERS_COMPANIES = [
    # Replaced enterprise companies with active mid-market tech + fintech companies
    "adobe",           # Active hiring, engineering-heavy
    "shopify",         # Platform company, many eng roles
    "slack",           # High hiring volume
    "stripe",          # Financial infrastructure (may overlap with Greenhouse but good backup)
    "notion",          # Strong remote-first culture
    "figma",           # Design + eng roles
    "twilio",          # Communications platform
    "elastic",         # Search/observability
    "datadog",         # Observability, fast-growing
    "github",          # Developer tools
]


def fetch_smartrecruiters_jobs(profile: dict, delay: float = 0.3) -> list:
    """
    Fetch jobs from registered SmartRecruiters companies and filter by profile.

    Args:
        profile: Parsed user profile dict.
        delay:   Seconds to sleep between company fetches (rate courtesy).

    Returns:
        List of normalised job dicts ready for DB insertion.
    """
    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    pf = ProfileFilter(profile)
    all_jobs = []
    skipped = 0

    for company_id in SMARTRECRUITERS_COMPANIES:
        try:
            url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
            resp = requests.get(url, params={"limit": 100}, timeout=10, verify=False)
            if resp.status_code in (404, 403):
                skipped += 1
                continue
            if resp.status_code != 200:
                record_failure(SOURCE_NAME, f"{company_id}: HTTP {resp.status_code}")
                continue
            data = resp.json()
            logger.info(f"[{SOURCE_NAME}] raw keys: {list(data.keys())}, sample: {json.dumps(data)[:300]}")
        except Exception as e:
            record_failure(SOURCE_NAME, f"{company_id}: {e}")
            logger.warning(f"[{SOURCE_NAME}] {company_id} error: {e}")
            continue

        for j in data.get("content", []):
            title = (j.get("name") or "").strip()
            if not title:
                continue

            # Description requires a second call — skip for now, title-only matching
            keep, _ = pf.should_keep(title, "")
            if not keep:
                continue

            location = j.get("location") or {}
            city = location.get("city") or ""
            country = location.get("country") or ""
            location_str = ", ".join(filter(None, [city, country])) or "Various"

            job_id = j.get("id") or ""
            job_url = j.get("ref") or (
                f"https://jobs.smartrecruiters.com/{company_id}/{job_id}" if job_id else ""
            )
            if not job_url:
                continue

            all_jobs.append({
                "title": title[:150],
                "company": company_id.title()[:100],
                "location": location_str[:100],
                "source_url": job_url,
                "source_domain": "jobs.smartrecruiters.com",
                "description_snippet": "",
                "posted_date": j.get("releasedDate") or "",
                "skills_found": json.dumps([]),
            })

        time.sleep(delay)

    record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    logger.info(
        f"[{SOURCE_NAME}] {len(all_jobs)} jobs kept "
        f"(404/403 companies skipped: {skipped})"
    )
    return all_jobs
