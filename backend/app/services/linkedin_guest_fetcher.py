"""
JobRadar — LinkedIn jobs-guest API Fetcher (Layer 18)
Fetches jobs from LinkedIn public job search without authentication.

This is a semi-official public endpoint used by LinkedIn's job search page.
No API key required, but requires strict rate limiting to avoid blocks.

Endpoint: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
Rate limit: 3-6 seconds between requests (randomized)
Max pages: 2 per query (50 jobs max) to minimize detection risk
Circuit breaker: Automatic 1-hour cooldown after 3 failures

Risk: Medium. LinkedIn actively blocks scrapers. Use with UA rotation + delays.
"""
import json
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure
from app.services.search_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

SOURCE_NAME = "linkedin_guest"

# User-Agent pool: rotate to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Time range filters: f_TPR values
TIME_FILTERS = {
    "24h": "r86400",
    "week": "r604800",
    "month": "r2592000",
}

# Work type filters: f_WT values
WORK_TYPES = {
    "remote": 2,
    "onsite": 1,
    "hybrid": 3,
}


def fetch_linkedin_guest_jobs(
    profile: dict,
    queries: list[str] = None,
    location: str = "Pune",
    max_pages: int = 2,
    delay_range: tuple = (3, 6),
) -> list:
    """
    Fetch jobs from LinkedIn jobs-guest endpoint with strict rate limiting.

    Args:
        profile: Parsed user profile dict.
        queries: List of search queries. If None, uses common defaults.
        location: Base location for searches (e.g., "Pune", "India", "Remote").
        max_pages: Max pages per query (default 2 = 50 jobs). Increase cautiously.
        delay_range: (min, max) seconds delay between requests. Default (3, 6).

    Returns:
        List of normalised job dicts ready for DB insertion.

    Note:
        Circuit breaker opens after 3 failures. Respects source_health module.
    """
    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    if queries is None:
        queries = [
            profile.get("primary_role", "Software Developer"),
            f"{profile.get('primary_role', 'Software Developer')} India",
            f"{profile.get('primary_role', 'Software Developer')} Remote",
        ]

    pf = ProfileFilter(profile)
    all_jobs = []

    for query in queries:
        # Check cache first
        cached = cache_get(SOURCE_NAME, query, location, ttl_hours=6)
        if cached is not None:
            logger.info(f"[{SOURCE_NAME}] cache hit for '{query}' / {location}")
            all_jobs.extend(cached)
            continue

        page_jobs = []

        for page in range(max_pages):
            try:
                # Build request with defensive params
                params = {
                    "keywords": query,
                    "location": location,
                    "f_TPR": TIME_FILTERS["month"],  # Last 30 days
                    "f_WT": WORK_TYPES["remote"],    # Remote jobs only
                    "start": page * 25,
                }
                headers = {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml",
                    "Referer": "https://www.linkedin.com/jobs/",
                }

                resp = requests.get(
                    ENDPOINT,
                    params=params,
                    headers=headers,
                    timeout=15,
                    verify=False,
                )

                # Rate limit detection
                if resp.status_code == 429:
                    record_failure(SOURCE_NAME, f"429 rate_limited at page {page}")
                    logger.warning(f"[{SOURCE_NAME}] 429 rate limit hit, stopping this query")
                    break

                # Other HTTP errors
                if resp.status_code != 200:
                    record_failure(SOURCE_NAME, f"HTTP {resp.status_code} for '{query}'")
                    logger.warning(f"[{SOURCE_NAME}] {query}: HTTP {resp.status_code}")
                    break

                # Parse HTML response
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                record_failure(SOURCE_NAME, str(e))
                logger.warning(f"[{SOURCE_NAME}] {query} fetch error: {e}")
                break

            # Extract job cards from HTML
            # LinkedIn uses dynamic selectors; try multiple options
            job_cards = soup.select("li div.base-card") or soup.select(".job-search-card")

            if not job_cards:
                logger.debug(f"[{SOURCE_NAME}] no job cards found on page {page}")
                break

            for card in job_cards:
                try:
                    title_el = card.select_one(".base-search-card__title")
                    company_el = card.select_one(".base-search-card__subtitle")
                    location_el = card.select_one(".job-search-card__location")
                    link_el = card.select_one("a.base-card__full-link")
                    date_el = card.select_one("time")

                    if not (title_el and link_el):
                        continue

                    title = title_el.get_text(strip=True)
                    company = company_el.get_text(strip=True) if company_el else "Unknown"
                    job_location = (
                        location_el.get_text(strip=True) if location_el else location
                    )
                    job_url = link_el.get("href", "").split("?")[0]
                    posted_date = date_el.get("datetime", "") if date_el else ""

                    if not job_url:
                        continue

                    # ProfileFilter matching on title only (no full description available)
                    keep, _ = pf.should_keep(title, "")
                    if not keep:
                        continue

                    page_jobs.append({
                        "title": title[:150],
                        "company": company[:100],
                        "location": job_location[:100],
                        "source_url": job_url,
                        "source_domain": "linkedin.com/jobs",
                        "description_snippet": "",
                        "posted_date": posted_date,
                        "skills_found": json.dumps([]),
                    })
                except (AttributeError, KeyError, IndexError) as e:
                    logger.debug(f"[{SOURCE_NAME}] failed to parse card: {e}")
                    continue

            # Polite delay before next page
            if page < max_pages - 1 and page_jobs:
                delay = random.uniform(delay_range[0], delay_range[1])
                time.sleep(delay)

        # Cache results for this query
        cache_set(SOURCE_NAME, query, page_jobs, location, ttl_hours=6)
        all_jobs.extend(page_jobs)

        # Delay between queries
        delay = random.uniform(delay_range[0], delay_range[1])
        time.sleep(delay)

    # Record success
    if all_jobs:
        record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    else:
        record_failure(SOURCE_NAME, "no jobs returned")

    logger.info(f"[{SOURCE_NAME}] {len(all_jobs)} jobs from {len(queries)} queries")
    return all_jobs
