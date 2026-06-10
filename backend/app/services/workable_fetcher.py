"""
JobRadar — Workable ATS Fetcher (Layer 15)
Fetches jobs from Workable's public widget API for known companies.

Free, no API key required. The widget endpoint is publicly accessible
and designed for embedding on company career pages.

Docs: https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true

Patch 1: Parallelized company probing.
"""
import json
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.services.ats_fetcher import ProfileFilter, _load_companies_for_ats
from app.services.source_health import is_healthy, record_success, record_failure

logger = logging.getLogger(__name__)

SOURCE_NAME = "workable"

WORKABLE_COMPANIES = [
    "deel",
    "remote",
    "automattic",
    "doist",
    "hotjar",
    "buffer",
    "toggl",
    "zapier",
    "typeform",
    "intercom",
    "netlify",
    "basecamp",
    "invision",
]


def fetch_workable_jobs(profile: dict, delay: float = 0.3) -> list:
    """
    Fetch jobs from registered Workable companies and filter by profile.

    Patch 1: Probes companies IN PARALLEL (max 8 workers) instead of sequentially.

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
    companies = _load_companies_for_ats(SOURCE_NAME)

    if not companies:
        return []

    all_jobs = []
    skipped_404 = 0

    # Patch 1: Parallel company probing
    logger.info(f"[{SOURCE_NAME}] Probing {len(companies)} companies in parallel")
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="workable") as executor:
        futures = {
            executor.submit(_fetch_one_workable_company, company_name, slug, pf): slug
            for company_name, slug in companies.items()
        }

        for future in as_completed(futures):
            slug = futures[future]
            try:
                jobs, is_404 = future.result(timeout=15)
                if is_404:
                    skipped_404 += 1
                else:
                    all_jobs.extend(jobs)
            except Exception as e:
                logger.warning(f"[{SOURCE_NAME}] {slug} error: {e}")
                record_failure(SOURCE_NAME, f"{slug}: {e}")

    record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    logger.info(
        f"[{SOURCE_NAME}] {len(all_jobs)} jobs kept "
        f"(404 companies skipped: {skipped_404}, parallel)"
    )
    return all_jobs


def _fetch_one_workable_company(company_display_name: str, slug: str, pf) -> tuple:
    """
    Fetch jobs from one Workable company and filter them.

    Patch 1: Helper for parallel company probing.

    Returns:
        Tuple of (jobs_list, is_404)
    """
    jobs = []
    is_404 = False

    try:
        url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
        resp = requests.get(url, timeout=10, verify=False)

        if resp.status_code == 404:
            return jobs, True

        if resp.status_code != 200:
            record_failure(SOURCE_NAME, f"{slug}: HTTP {resp.status_code}")
            return jobs, False

        data = resp.json()
        company_name = data.get("name") or slug

        for j in data.get("jobs", []):
            title = (j.get("title") or "").strip()
            if not title:
                continue

            location_data = j.get("location") or {}
            desc = j.get("description") or j.get("full_description") or ""
            if isinstance(desc, list):
                desc = " ".join(str(d) for d in desc)

            keep, _ = pf.should_keep(title, desc)
            if not keep:
                continue

            shortcode = j.get("shortcode") or ""
            job_url = j.get("url") or (
                f"https://apply.workable.com/{slug}/j/{shortcode}" if shortcode else ""
            )
            if not job_url:
                continue

            jobs.append({
                "title": title[:150],
                "company": company_name[:100],
                "location": (location_data.get("location_str") or "Remote")[:100],
                "source_url": job_url,
                "source_domain": "apply.workable.com",
                "description_snippet": _strip_html(str(desc))[:300],
                "posted_date": j.get("published_on") or "",
                "skills_found": json.dumps([]),
            })

    except Exception as e:
        logger.debug(f"[workable] {slug}: {e}")

    return jobs, False


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()
