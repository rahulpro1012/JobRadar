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


def _fetch_linkedin_variant(
    query: str,
    location: str,
    remote_only: bool,
    max_pages: int,
    pf: ProfileFilter,
) -> list:
    """
    Fetch jobs for a single query variant.

    Issue 3: Helper to run both remote-only and location-only variants.
    """
    variant_name = "remote" if remote_only else "local"
    variant_location = "Worldwide" if remote_only else location
    variant_work_type = WORK_TYPES["remote"] if remote_only else None

    # Check cache first
    cache_key = f"{query}|{variant_name}"
    cached = cache_get(SOURCE_NAME, cache_key, variant_location, ttl_hours=6)
    if cached is not None:
        logger.debug(f"[{SOURCE_NAME}] cache hit for '{query}' ({variant_name}) / {variant_location}")
        return cached

    variant_jobs = []

    for page in range(max_pages):
        try:
            params = {
                "keywords": query,
                "location": variant_location,
                "f_TPR": TIME_FILTERS["week"],
                "start": page * 25,
            }

            # Issue 3: Only add f_WT for remote-only variant
            if remote_only:
                params["f_WT"] = variant_work_type

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
                logger.warning(f"[{SOURCE_NAME}] 429 rate limit hit ({variant_name}), stopping")
                break

            # Other HTTP errors
            if resp.status_code != 200:
                logger.debug(f"[{SOURCE_NAME}] {query} ({variant_name}): HTTP {resp.status_code}")
                break

            # Parse HTML response
            soup = BeautifulSoup(resp.text, "html.parser")
            job_cards = soup.select("li div.base-card") or soup.select(".job-search-card")

            if not job_cards:
                logger.debug(f"[{SOURCE_NAME}] no job cards found on page {page} ({variant_name})")
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
                    job_location = location_el.get_text(strip=True) if location_el else variant_location
                    job_url = link_el.get("href", "").split("?")[0]
                    posted_date = date_el.get("datetime", "") if date_el else ""

                    if not job_url:
                        continue

                    # ProfileFilter matching
                    keep, _ = pf.should_keep(title, "")
                    if not keep:
                        continue

                    variant_jobs.append({
                        "title": title[:150],
                        "company": company[:100],
                        "location": job_location[:100],
                        "source_url": job_url,
                        "source_domain": "linkedin.com",
                        "description_snippet": "",
                        "posted_date": posted_date[:10] if posted_date else "",
                        "skills_found": json.dumps([]),
                    })

                except Exception:
                    continue

            time.sleep(random.uniform(2, 4))  # Small delay between pages

        except Exception as e:
            logger.debug(f"[{SOURCE_NAME}] {query} ({variant_name}) fetch error: {e}")
            break

    # Cache results
    if variant_jobs:
        cache_set(SOURCE_NAME, cache_key, variant_jobs, variant_location, ttl_hours=6)

    return variant_jobs


def fetch_linkedin_guest_jobs(
    profile: dict,
    queries: list[str] = None,
    location: str = "Pune",
    max_pages: int = 2,
    delay_range: tuple = (5, 10),
) -> list:
    """
    Fetch jobs from LinkedIn jobs-guest endpoint with strict rate limiting.

    Issue 3: Runs BOTH remote-only and location-only variants per query.

    Args:
        profile: Parsed user profile dict.
        queries: List of search queries. If None, uses common defaults.
        location: Base location for searches (e.g., "Pune", "India", "Remote").
        max_pages: Max pages per query (default 2 = 50 jobs). Increase cautiously.
        delay_range: (min, max) seconds delay between requests. Default (5, 10).

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
    seen_urls = set()  # Dedupe across variants

    for query in queries:
        # Strip quotes and filler, truncate to 5 words
        query = query.replace('"', '').replace("'", "")
        query = " ".join(query.split()[:5])

        # Issue 3: Run BOTH variants
        # Variant 1: Remote-only (f_WT=2, location=Worldwide)
        remote_jobs = _fetch_linkedin_variant(query, location, remote_only=True, max_pages=max_pages, pf=pf)

        # Variant 2: Location-only (no f_WT, location=Pune/India)
        local_jobs = _fetch_linkedin_variant(query, location, remote_only=False, max_pages=max_pages, pf=pf)

        # Dedupe and combine
        for job in remote_jobs + local_jobs:
            url = job["source_url"]
            if url not in seen_urls:
                seen_urls.add(url)
                all_jobs.append(job)

        # Delay between queries
        time.sleep(random.uniform(delay_range[0], delay_range[1]))

    # Record success
    if all_jobs:
        record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    else:
        record_failure(SOURCE_NAME, "no jobs returned")

    logger.info(f"[{SOURCE_NAME}] {len(all_jobs)} jobs from {len(queries)} queries")
    return all_jobs
