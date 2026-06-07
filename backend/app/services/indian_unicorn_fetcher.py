"""
JobRadar Tier 3a: Indian Unicorn Fetcher
Searches Indian unicorn career pages using SearxNG site: operator to discover jobs not in standard ATSes.

For each unicorn company, runs a site-specific search like:
  site:razorpay.com "engineer" OR "developer" OR "hiring"

Returns normalized job results filtered by user profile.
"""

import json
import time
import logging
import requests
from typing import List
from app.services.ats_fetcher import ProfileFilter
from app.services.search_cache import cache_get, cache_set
from app.services.source_health import is_healthy, record_success, record_failure
from app.services.indian_unicorn_sites import INDIAN_UNICORN_SITES

logger = logging.getLogger(__name__)

SOURCE_NAME = "indian_unicorns"

# Get SearxNG URL from environment
import os
SEARXNG_URL = os.environ.get("SEARXNG_URL", "https://searxng-jobradar.onrender.com")

# Search keywords for unicorn sites
UNICORN_SEARCH_KEYWORDS = [
    "engineer hiring",
    "developer jobs",
    "software engineer",
    "careers",
    "hiring",
]

HEADERS = {
    "User-Agent": "JobRadar/1.0 (Indian unicorn job discovery)",
    "Accept": "application/json",
}


def fetch_indian_unicorns(profile: dict, queries: List[str] = None, max_companies: int = 20) -> List[dict]:
    """
    Search Indian unicorn career pages for job listings using SearxNG.

    Args:
        profile: User profile dict with skills, experience, etc.
        queries: Optional list of search queries (unused, for interface compatibility)
        max_companies: Max unicorn sites to probe per refresh (for rate limiting)

    Returns:
        List of normalized job dicts
    """
    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    pf = ProfileFilter(profile)
    all_jobs = []
    companies_searched = 0
    jobs_found = 0
    errors = 0

    # Limit companies per refresh to avoid rate limiting
    companies_to_search = INDIAN_UNICORN_SITES[:max_companies]

    for company in companies_to_search:
        if companies_searched >= max_companies:
            break

        company_name = company["name"]
        site_domain = company["site"]

        try:
            # Try each search keyword until we find results
            jobs_for_company = []

            for keyword in UNICORN_SEARCH_KEYWORDS:
                # Check cache first
                cache_key = f"{SOURCE_NAME}:{company_name}:{keyword}"
                cached_jobs = cache_get(SOURCE_NAME, company_name, ttl_hours=12)

                if cached_jobs:
                    logger.debug(f"[{SOURCE_NAME}] Cache hit: {company_name}")
                    jobs_for_company = json.loads(cached_jobs) if isinstance(cached_jobs, str) else cached_jobs
                    break

                # Build site-specific search query
                search_query = f'site:{site_domain} "{keyword}"'

                # Search via SearxNG
                try:
                    resp = requests.get(
                        f"{SEARXNG_URL}/search",
                        params={
                            "q": search_query,
                            "format": "json",
                            "pageno": 1,
                            "results_on_new_tab": False,
                        },
                        headers=HEADERS,
                        timeout=15,
                        verify=False,
                    )

                    if resp.status_code != 200:
                        logger.debug(f"[{SOURCE_NAME}] {company_name}: SearxNG HTTP {resp.status_code}")
                        continue

                    data = resp.json()
                    results = data.get("results", [])

                    if not results:
                        logger.debug(f"[{SOURCE_NAME}] {company_name}: No results for '{keyword}'")
                        continue

                    # Parse results (SearxNG returns: title, url, content)
                    for result in results[:5]:  # Limit to top 5 results per keyword
                        title = result.get("title", "")
                        url = result.get("url", "")
                        content = result.get("content", "")

                        # Try to extract job title from page title or content
                        if not title or "job" not in title.lower():
                            continue  # Skip non-job results

                        # Profile filter
                        keep, reason = pf.should_keep(title, content)
                        if not keep:
                            continue

                        jobs_for_company.append({
                            "title": title[:150],
                            "company": company_name,
                            "location": "India",  # All unicorns are India-based
                            "source_url": url,
                            "source_domain": site_domain,
                            "description_snippet": content[:300],
                            "posted_date": "",
                            "skills_found": json.dumps([]),
                        })

                    # Cache results for this company
                    if jobs_for_company:
                        cache_set(
                            SOURCE_NAME,
                            company_name,
                            json.dumps(jobs_for_company),
                            location="India",
                            ttl_hours=12,
                        )
                        break  # Found jobs, stop trying other keywords

                except requests.Timeout:
                    logger.warning(f"[{SOURCE_NAME}] {company_name}: SearxNG timeout")
                    errors += 1
                except Exception as e:
                    logger.warning(f"[{SOURCE_NAME}] {company_name}: {str(e)}")
                    errors += 1

                # Polite delay between searches
                time.sleep(0.5)

            all_jobs.extend(jobs_for_company)
            if jobs_for_company:
                jobs_found += len(jobs_for_company)
                logger.debug(f"[{SOURCE_NAME}] {company_name}: {len(jobs_for_company)} jobs")

            companies_searched += 1

            # Delay between companies
            time.sleep(1.0)

        except Exception as e:
            logger.warning(f"[{SOURCE_NAME}] {company_name} error: {e}")
            errors += 1
            continue

    # Record success/failure
    if errors > len(companies_to_search) / 2:
        record_failure(SOURCE_NAME, f"High error rate: {errors}/{companies_searched}")
    else:
        record_success(SOURCE_NAME, jobs_returned=len(all_jobs))

    logger.info(
        f"[{SOURCE_NAME}] {len(all_jobs)} jobs from {companies_searched} companies "
        f"(searched {jobs_found} results, {errors} errors)"
    )

    return all_jobs
