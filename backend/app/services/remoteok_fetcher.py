"""
JobRadar — RemoteOK Fetcher (Layer 7.5)
Fetches remote jobs from RemoteOK's public JSON API.

Free, no API key required. Returns the full feed in a single call.
We filter for India-eligible remote positions and run through ProfileFilter.

Docs: https://remoteok.com/api
"""
import json
import time
import logging
import requests
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure

logger = logging.getLogger(__name__)

REMOTEOK_URL = "https://remoteok.com/api"
SOURCE_NAME = "remoteok"

# RemoteOK blocks the default Python urllib User-Agent
HEADERS = {
    "User-Agent": "JobRadar/1.0 (personal job search tool; contact via github)",
    "Accept": "application/json",
}

# Geo-restrictions that indicate the role is NOT open to India/worldwide
_GEO_BLOCKLIST = [
    "us only", "usa only", "united states only",
    "eu only", "europe only", "uk only", "canada only",
    "australia only", "latin america only",
]


def fetch_remoteok_jobs(profile: dict, delay: float = 1.0) -> list:
    """
    Fetch remote jobs from RemoteOK and filter them for the user's profile.

    Args:
        profile: Parsed user profile dict.
        delay:   Seconds to wait after the API call (polite rate limiting).

    Returns:
        List of normalised job dicts ready for DB insertion.
    """
    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    pf = ProfileFilter(profile)

    try:
        resp = requests.get(
            REMOTEOK_URL,
            headers=HEADERS,
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        record_failure(SOURCE_NAME, str(e))
        logger.warning(f"[{SOURCE_NAME}] fetch error: {e}")
        return []

    # RemoteOK prepends a metadata object as item[0] — skip it
    items = raw[1:] if raw and isinstance(raw[0], dict) and "legal" in raw[0] else raw

    jobs = []
    filtered_geo = 0
    filtered_profile = 0
    # Sampling lists for debug logging — helps verify geo-filter is doing real work
    _loc_sample: list = []       # first 20 location strings seen (any)
    _loc_blocked: list = []      # location strings that triggered the blocklist

    for item in items:
        location_str = item.get("location", "") or ""

        # Collect location sample for debug output (no cost, tiny memory)
        if len(_loc_sample) < 20:
            _loc_sample.append(repr(location_str) if location_str else "(blank)")

        # Skip geo-restricted roles
        if not _india_eligible(location_str):
            filtered_geo += 1
            if len(_loc_blocked) < 10:
                _loc_blocked.append(repr(location_str))
            continue

        title = (item.get("position") or "").strip()
        company = (item.get("company") or "").strip()
        url = item.get("url") or item.get("apply_url") or ""
        description = _strip_html(item.get("description") or "")
        tags = item.get("tags") or []

        if not title or not url:
            continue

        keep, reason = pf.should_keep(title, description + " " + " ".join(tags))
        if not keep:
            filtered_profile += 1
            continue

        # Find skills that match user profile from the job's tag list
        all_user_skills = pf.core_skills + pf.secondary_skills + pf.tools
        matching_skills = [
            t for t in tags
            if any(t.lower() == s.lower() for s in all_user_skills)
        ]

        jobs.append({
            "title": title[:150],
            "company": company[:100],
            "location": (location_str or "Remote")[:100],
            "source_url": url,
            "source_domain": "remoteok.io",
            "description_snippet": description[:300],
            "posted_date": item.get("date") or item.get("epoch") or "",
            "skills_found": json.dumps(matching_skills[:8]),
        })

    time.sleep(delay)
    record_success(SOURCE_NAME, jobs_returned=len(jobs))
    logger.info(
        f"[{SOURCE_NAME}] {len(jobs)} kept "
        f"(geo-filtered: {filtered_geo}, profile-filtered: {filtered_profile})"
    )
    # Debug: show what location strings RemoteOK actually sends and what we blocked
    logger.debug(f"[{SOURCE_NAME}] Location sample (first 20): {_loc_sample}")
    if _loc_blocked:
        logger.debug(f"[{SOURCE_NAME}] Geo-blocked location strings: {_loc_blocked}")
    else:
        logger.debug(f"[{SOURCE_NAME}] Geo-filter: no locations blocked (all passed or blank)")
    return jobs


def _india_eligible(location_str: str) -> bool:
    """
    Return True for Worldwide / Asia / blank locations.
    Return False for explicit geo-restrictions that exclude India.
    """
    if not location_str:
        return True  # blank = assume worldwide remote
    loc = location_str.lower()
    return not any(blocker in loc for blocker in _GEO_BLOCKLIST)


def _strip_html(text: str) -> str:
    """Very lightweight HTML tag stripper."""
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()
