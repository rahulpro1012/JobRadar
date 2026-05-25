"""
JobRadar — Adzuna India Fetcher (Layer 7.8)
Fetches jobs from the Adzuna India API — a legitimate aggregator with salary data.

Requires: ADZUNA_APP_ID + ADZUNA_APP_KEY (free, sign up at https://developer.adzuna.com)
Free tier: ~250-1000 calls/month depending on plan.

We cache results per query (6 h TTL) and cap to max_queries per refresh to
preserve the monthly quota.

API docs: https://api.adzuna.com/
"""
import json
import time
import logging
import requests
from datetime import datetime
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure
from app.services.search_cache import cache_get, cache_set
from app.database import get_quota_usage, increment_quota

logger = logging.getLogger(__name__)

SOURCE_NAME = "adzuna"
BASE_URL = "https://api.adzuna.com/v1/api/jobs/in/search/1"

# Keep at most this many queries per refresh to protect the monthly quota
MAX_QUERIES_PER_REFRESH = 5
# Self-imposed daily limit (250 calls/month ÷ 30 days ≈ 8, we stay conservative)
DAILY_LIMIT = 8
CACHE_TTL_HOURS = 6

# Locations to cycle through for Adzuna searches (lowercase, as Adzuna expects)
SEARCH_LOCATIONS = ["pune", "bangalore", "mumbai", "hyderabad", "remote"]


def fetch_adzuna_jobs(
    profile: dict,
    queries: list,
    config: dict,
    delay: float = 1.5,
) -> list:
    """
    Query Adzuna India for the top N queries, caching results per query.

    Args:
        profile: Parsed user profile dict.
        queries: List of query dicts from generate_queries(), e.g. [{"query": "...", "tier": 1}]
        config:  Flask app.config dict (needs ADZUNA_APP_ID, ADZUNA_APP_KEY).
        delay:   Seconds between API calls.

    Returns:
        List of normalised job dicts ready for DB insertion.
    """
    app_id = config.get("ADZUNA_APP_ID", "")
    app_key = config.get("ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        logger.debug(f"[{SOURCE_NAME}] no API credentials — skipping")
        return []

    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    # Daily quota gate
    today = datetime.now().strftime("%Y-%m-%d")
    used_today = get_quota_usage(SOURCE_NAME, today)
    remaining_quota = DAILY_LIMIT - used_today
    if remaining_quota <= 0:
        logger.info(f"[{SOURCE_NAME}] daily quota exhausted ({used_today}/{DAILY_LIMIT})")
        return []

    pf = ProfileFilter(profile)
    exp_years = int(profile.get("experience_years", 2))

    # Pick top-tier queries, deduplicated
    query_texts = []
    seen = set()
    for q in queries:
        text = q["query"] if isinstance(q, dict) else q
        if text.lower() not in seen:
            seen.add(text.lower())
            query_texts.append(text)

    all_jobs = []
    calls_made = 0
    max_calls = min(MAX_QUERIES_PER_REFRESH, remaining_quota)

    for query_text in query_texts[:max_calls]:
        # Try cache first — no API call if we have a fresh result
        cached = cache_get(SOURCE_NAME, query_text, location="india", ttl_hours=CACHE_TTL_HOURS)
        if cached is not None:
            logger.debug(f"[{SOURCE_NAME}] cache hit for '{query_text[:50]}'")
            filtered = [j for j in cached if _profile_matches(j, pf)]
            all_jobs.extend(filtered)
            continue

        try:
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": query_text,
                "where": "India",
                "results_per_page": 50,
                "max_days_old": 30,
                "sort_by": "date",
            }
            resp = requests.get(
                BASE_URL,
                params=params,
                timeout=20,
                verify=False,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            increment_quota(SOURCE_NAME, today)
            calls_made += 1
        except Exception as e:
            record_failure(SOURCE_NAME, f"query='{query_text[:50]}': {e}")
            logger.warning(f"[{SOURCE_NAME}] API error for '{query_text[:50]}': {e}")
            time.sleep(delay)
            continue

        normalised = [_normalise(r) for r in results if r.get("title")]

        # Cache the raw normalised results (before profile filter)
        cache_set(SOURCE_NAME, query_text, normalised, location="india", ttl_hours=CACHE_TTL_HOURS)

        filtered = []
        for job in normalised:
            keep, reason = pf.should_keep(job["title"], job["description_snippet"])
            if keep:
                filtered.append(job)

        all_jobs.extend(filtered)
        time.sleep(delay)

    if all_jobs:
        record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    logger.info(
        f"[{SOURCE_NAME}] {len(all_jobs)} jobs from {calls_made} API calls "
        f"(quota: {used_today + calls_made}/{DAILY_LIMIT})"
    )
    return all_jobs


def _normalise(r: dict) -> dict:
    """Map Adzuna response fields to JobRadar's canonical job dict."""
    company = (r.get("company") or {}).get("display_name") or ""
    location_obj = r.get("location") or {}
    location_parts = location_obj.get("area") or []
    location_str = ", ".join(str(p) for p in location_parts[-2:]) if location_parts else "India"

    description = r.get("description") or ""
    # Adzuna descriptions can be HTML
    import re
    description = re.sub(r"<[^>]+>", " ", description).strip()

    salary_min = r.get("salary_min")
    salary_max = r.get("salary_max")

    return {
        "title": (r.get("title") or "").strip()[:150],
        "company": company.strip()[:100],
        "location": location_str[:100],
        "source_url": r.get("redirect_url") or "",
        "source_domain": "adzuna.com",
        "description_snippet": description[:300],
        "posted_date": r.get("created") or "",
        "skills_found": json.dumps([]),
        # Extra fields (stored in description_snippet if present)
        "_salary_min": salary_min,
        "_salary_max": salary_max,
    }


def _profile_matches(job: dict, pf: ProfileFilter) -> bool:
    """Re-apply ProfileFilter to a cached normalised job dict."""
    keep, _ = pf.should_keep(job.get("title", ""), job.get("description_snippet", ""))
    return keep
