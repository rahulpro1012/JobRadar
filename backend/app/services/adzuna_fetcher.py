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
import re
import time
import logging
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure
from app.services.search_cache import cache_get, cache_set
from app.database import get_quota_usage, increment_quota

logger = logging.getLogger(__name__)

SOURCE_NAME = "adzuna"
BASE_URL = "https://api.adzuna.com/v1/api/jobs/in/search/1"

# 3 queries × 3 locations = 9 API calls max per refresh (run in parallel)
MAX_QUERIES_PER_REFRESH = 3
# Daily budget: 36 calls/day ≈ 1080/month (still within 250-1000 free tier)
DAILY_LIMIT = 36
CACHE_TTL_HOURS = 12

# Rotate across these cities — title-case matches Adzuna's location field.
# "Remote" dropped: Adzuna India returns an empty (78-byte) payload for it.
SEARCH_LOCATIONS = ["Pune", "Bangalore", "Mumbai"]

# Per-call read timeout (start at 15s for cold-run testing; tune toward 10 later)
REQUEST_TIMEOUT = 15
# Parallel workers for the (query × location) call matrix
MAX_WORKERS = 6


def fetch_adzuna_jobs(
    profile: dict,
    queries: list,
    config: dict,
    delay: float = 1.5,
) -> list:
    """
    Query Adzuna India for the top N queries across SEARCH_LOCATIONS cities.

    Runs up to MAX_QUERIES_PER_REFRESH (3) queries × len(SEARCH_LOCATIONS) (4) cities
    = 12 API calls max per refresh. Results are cached per (query, location) pair
    so repeated refreshes within 6 h cost zero calls.

    Args:
        profile: Parsed user profile dict.
        queries: List of query dicts from generate_queries(), e.g. [{"query": "...", "tier": 1}]
        config:  Flask app.config dict (needs ADZUNA_APP_ID, ADZUNA_APP_KEY).
        delay:   Seconds between live API calls.

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

    # Pick top-tier queries, deduplicated, with city names stripped
    # (we're rotating through SEARCH_LOCATIONS in the location param, so redundancy wastes calls)
    query_texts = []
    seen = set()
    for q in queries:
        text = q["query"] if isinstance(q, dict) else q
        # Strip city names to avoid "Java Pune" × location="Pune" redundancy
        text = _strip_city_names(text)
        if text.lower() not in seen:
            seen.add(text.lower())
            query_texts.append(text)

    # Build the (query, location) call matrix, capped by remaining daily quota.
    # Cache hits are served first (cheap) and don't count against the live-call budget.
    max_calls = min(MAX_QUERIES_PER_REFRESH * len(SEARCH_LOCATIONS), remaining_quota)
    all_jobs = []
    live_tasks = []  # (query_text, location) pairs that need a live API call

    for query_text in query_texts[:MAX_QUERIES_PER_REFRESH]:
        query_text = _clean_for_adzuna(query_text)
        for location in SEARCH_LOCATIONS:
            cached = cache_get(
                SOURCE_NAME, query_text, location=location.lower(), ttl_hours=CACHE_TTL_HOURS
            )
            if cached is not None:
                logger.debug(f"[{SOURCE_NAME}] cache hit: '{query_text[:40]}' @ {location}")
                all_jobs.extend([j for j in cached if _profile_matches(j, pf)])
            else:
                live_tasks.append((query_text, location))

    # Respect the daily quota cap on live calls
    live_tasks = live_tasks[:max_calls]
    calls_made = 0

    # Patch: run the live (query × location) calls in parallel instead of sequentially.
    if live_tasks:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="adzuna") as executor:
            future_to_task = {
                executor.submit(_fetch_one_adzuna, q, loc, app_id, app_key, today): (q, loc)
                for q, loc in live_tasks
            }
            for future in as_completed(future_to_task):
                q, loc = future_to_task[future]
                try:
                    normalised = future.result(timeout=REQUEST_TIMEOUT + 5)
                except Exception as e:
                    record_failure(SOURCE_NAME, f"query='{q[:40]}' loc={loc}: {e}")
                    logger.warning(f"[{SOURCE_NAME}] API error '{q[:40]}' @ {loc}: {e}")
                    continue
                if normalised is None:
                    continue
                calls_made += 1
                all_jobs.extend([j for j in normalised if _profile_matches(j, pf)])

    if all_jobs:
        record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    logger.info(
        f"[{SOURCE_NAME}] {len(all_jobs)} jobs from {calls_made} live API calls "
        f"(quota today: {used_today + calls_made}/{DAILY_LIMIT}, "
        f"locations: {SEARCH_LOCATIONS})"
    )
    return all_jobs


def _fetch_one_adzuna(query_text, location, app_id, app_key, today):
    """Fetch + normalise + cache one (query, location) Adzuna call.

    Returns the normalised job list (cached for future refreshes), or raises
    on HTTP/transport error so the caller can record the failure. Runs inside
    a ThreadPoolExecutor worker.
    """
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": query_text,
        "where": location,
        "results_per_page": 50,
        "max_days_old": 30,
        "sort_by": "date",
    }
    resp = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT, verify=False)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    increment_quota(SOURCE_NAME, today)

    normalised = [_normalise(r) for r in results if r.get("title")]
    cache_set(
        SOURCE_NAME, query_text, normalised,
        location=location.lower(), ttl_hours=CACHE_TTL_HOURS,
    )
    return normalised


def _clean_for_adzuna(query: str) -> str:
    """
    Clean query for Adzuna API: strip quotes, city names, filler words, truncate to 5 words.
    Example: "Java" "Spring Boot" Developer Pune with experience → Java Spring Boot Developer
    """
    if not query:
        return ""

    q = query.strip()

    # Remove all quotes (both " and ')
    q = q.replace('"', '').replace("'", '')

    # Remove Indian city names
    cities = ["pune", "bangalore", "mumbai", "delhi", "hyderabad", "ahmedabad", "kolkata", "remote", "india"]
    q_lower = q.lower()
    for city in cities:
        q_lower = re.sub(rf"\b{city}\b", "", q_lower)

    # Remove common filler words
    fillers = ["with", "in", "for", "expertise", "required", "experience", "position", "role", "job"]
    words = q_lower.split()
    words = [w for w in words if w.lower() not in fillers and w.strip()]

    # Keep only first 5 words
    words = words[:5]

    # Clean up and return
    result = " ".join(words).strip()
    return result if result else query


def _strip_city_names(query: str) -> str:
    """
    Remove city names from query to avoid redundancy with location param.
    Example: "Java Developer Pune" → "Java Developer"
    This prevents wasting API calls on redundant city×query combinations.
    """
    # Remove Indian city names (case-insensitive)
    cities = ["pune", "bangalore", "mumbai", "delhi", "hyderabad", "ahmedabad", "kolkata"]
    q_lower = query.lower()
    for city in cities:
        q_lower = re.sub(rf"\b{city}\b", "", q_lower)
    # Clean up extra spaces and return original-cased version (minus the removed cities)
    result = " ".join(q_lower.split()).strip()
    return query.replace(query.lower(), result) if result else query


def _normalise(raw: dict) -> dict:
    """Normalize Adzuna API response to canonical job dict."""
    company_obj = raw.get("company") or {}
    location_obj = raw.get("location") or {}
    return {
        "title": (raw.get("title") or "")[:150],
        "company": (company_obj.get("display_name") or "")[:100],
        "location": (location_obj.get("display_name") or "Various")[:100],
        "source_url": raw.get("redirect_url", ""),
        "source_domain": "adzuna.com",
        "description_snippet": (raw.get("description") or "")[:300],
        "posted_date": raw.get("created", ""),
        "skills_found": json.dumps([]),
    }


def _profile_matches(job: dict, pf: "ProfileFilter") -> bool:
    """Check if job matches user's profile using ProfileFilter."""
    keep, _ = pf.should_keep(job["title"], job["description_snippet"])
    return keep


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
