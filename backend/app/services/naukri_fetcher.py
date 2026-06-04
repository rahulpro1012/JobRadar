"""
JobRadar — Naukri JSON API Fetcher (Layer 19)
Fetches jobs from Naukri (India's largest job portal) using undocumented internal API.

⚠️ WARNING: This API is undocumented and reverse-engineered.
Risk: High. Naukri may block IPs or change API anytime.
Safeguards: Circuit breaker (3-failure threshold), strict rate limiting, cache TTL.

Endpoint: https://www.naukri.com/jobapi/v3/search
Headers: appid=109, systemid=Naukri (required for API access)
Rate limit: 2-4 second delays between requests (randomized)
Max pages: 1 per query (20 jobs max) to minimize detection risk
Circuit breaker: Automatic 1-hour cooldown after 3 failures

This is the largest India-specific job source with 75M+ registered job seekers.
Expected: 10-20 jobs per query in target cities (Pune, Delhi, Bangalore, Mumbai).
"""
import json
import time
import random
import logging
import requests
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure
from app.services.search_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

SOURCE_NAME = "naukri"

# User-Agent pool for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

ENDPOINT = "https://www.naukri.com/jobapi/v3/search"


def fetch_naukri_jobs(
    profile: dict,
    queries: list[str] = None,
    location: str = "pune",
    experience: int = 2,
    max_pages: int = 1,
    delay_range: tuple = (2, 4),
) -> list:
    """
    Fetch jobs from Naukri using undocumented internal API.

    Args:
        profile: Parsed user profile dict.
        queries: List of search queries. If None, uses role from profile.
        location: Base location (lowercase: "pune", "delhi", "bangalore", "mumbai").
        experience: Experience years filter (default 2).
        max_pages: Max pages per query (default 1 = 20 jobs). Keep low!
        delay_range: (min, max) seconds delay between requests. Default (2, 4).

    Returns:
        List of normalised job dicts ready for DB insertion.

    Note:
        This API is undocumented and may break anytime. Circuit breaker active.
        Max 1 page per query to avoid IP blocks.
    """
    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    if queries is None:
        role = profile.get("primary_role", "Developer")
        queries = [role, f"{role} India"]

    pf = ProfileFilter(profile)
    all_jobs = []

    for query in queries:
        # Strip quotes from query
        query = query.replace('"', '').replace("'", "")

        # Check cache first
        cached = cache_get(SOURCE_NAME, query, location, ttl_hours=6)
        if cached is not None:
            logger.info(f"[{SOURCE_NAME}] cache hit for '{query}' / {location}")
            all_jobs.extend(cached)
            continue

        page_jobs = []

        # Only fetch page 1 per query to minimize detection risk
        page = 1
        try:
            # Naukri API params
            params = {
                "noOfResults": 20,              # Max per page
                "urlType": "search_by_keyword",
                "searchType": "adv",
                "keyword": query,
                "location": location.lower(),
                "experience": experience,
                "pageNo": page,
                "k": query,                     # Duplicate keyword param
            }

            # Headers with appid/systemid and additional browser headers for compatibility
            headers = {
                "appid": "109",
                "systemid": "Naukri",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": random.choice(USER_AGENTS),
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.naukri.com/",
                "X-Requested-With": "XMLHttpRequest",
            }

            resp = requests.get(
                ENDPOINT,
                params=params,
                headers=headers,
                timeout=15,
                verify=False,
            )

            # Rate limit or block detection
            if resp.status_code in (403, 429):
                record_failure(SOURCE_NAME, f"HTTP {resp.status_code} - possible IP block")
                logger.warning(f"[{SOURCE_NAME}] {resp.status_code} - may be rate limited/blocked")
                break

            # Other HTTP errors
            if resp.status_code != 200:
                record_failure(SOURCE_NAME, f"HTTP {resp.status_code} for '{query}'")
                logger.warning(f"[{SOURCE_NAME}] {query}: HTTP {resp.status_code}")
                break

            # Parse JSON response
            data = resp.json()

        except Exception as e:
            record_failure(SOURCE_NAME, str(e))
            logger.warning(f"[{SOURCE_NAME}] {query} fetch error: {e}")
            break

        # Extract jobs from response
        job_details = data.get("jobDetails", [])

        if not job_details:
            logger.debug(f"[{SOURCE_NAME}] no jobs returned for '{query}' / {location}")

        for job in job_details:
            try:
                title = (job.get("title") or "").strip()
                if not title:
                    continue

                company = (job.get("companyName") or "").strip()
                if not company:
                    company = "Unknown"

                # Complex field parsing: placeholders array
                placeholders = job.get("placeholders", [])
                location_str = location

                if placeholders and len(placeholders) > 0:
                    # placeholders[0] usually has location info
                    location_obj = placeholders[0].get("label", "")
                    if location_obj and "|" in location_obj:
                        # Pipe-delimited cities: "Pune | Mumbai | Delhi"
                        location_str = " / ".join(
                            [loc.strip() for loc in location_obj.split("|")]
                        )
                    elif location_obj:
                        location_str = location_obj

                # Salary in placeholders[1] if available
                salary_label = ""
                if len(placeholders) > 1:
                    salary_label = placeholders[1].get("label", "")

                # URL construction
                jd_url = job.get("jdURL", "")
                job_url = f"https://www.naukri.com{jd_url}" if jd_url else ""
                if not job_url:
                    continue

                # ProfileFilter matching on title only (no full description)
                keep, _ = pf.should_keep(title, "")
                if not keep:
                    continue

                # Extract experience requirement
                experience_text = job.get("experienceText", "")

                # Extract skills
                skills_str = job.get("tagsAndSkills", "")
                skills = [s.strip() for s in skills_str.split(",") if s.strip()] if skills_str else []

                page_jobs.append({
                    "title": title[:150],
                    "company": company[:100],
                    "location": location_str[:100],
                    "source_url": job_url,
                    "source_domain": "naukri.com",
                    "description_snippet": salary_label[:300] if salary_label else "",
                    "posted_date": job.get("footerPlaceholderLabel", ""),
                    "skills_found": json.dumps(skills[:8]),
                })
            except (KeyError, IndexError, AttributeError, TypeError) as e:
                logger.debug(f"[{SOURCE_NAME}] failed to parse job: {e}")
                continue

        # Cache results
        cache_set(SOURCE_NAME, query, page_jobs, location, ttl_hours=6)
        all_jobs.extend(page_jobs)

        # Delay between queries
        delay = random.uniform(delay_range[0], delay_range[1])
        time.sleep(delay)

    # Record success/failure
    if all_jobs:
        record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    else:
        record_failure(SOURCE_NAME, "no jobs returned")

    logger.info(f"[{SOURCE_NAME}] {len(all_jobs)} jobs from {len(queries)} queries / {location}")
    return all_jobs
