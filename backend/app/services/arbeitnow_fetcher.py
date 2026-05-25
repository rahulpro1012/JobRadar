"""
JobRadar — Arbeitnow Fetcher (Layer 7.7)
Fetches jobs from Arbeitnow's public job board API.

Free, no API key required.
EU-heavy but includes global remote roles.

API docs: https://www.arbeitnow.com/api/job-board-api
"""
import json
import time
import logging
import requests
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure

logger = logging.getLogger(__name__)

SOURCE_NAME = "arbeitnow"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


def fetch_arbeitnow_jobs(profile: dict, delay: float = 1.0) -> list:
    """
    Fetch jobs from Arbeitnow and filter for profile relevance.

    Args:
        profile: Parsed user profile dict.
        delay:   Seconds to wait after the API call.

    Returns:
        List of normalised job dicts ready for DB insertion.
    """
    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    pf = ProfileFilter(profile)

    try:
        resp = requests.get(
            ARBEITNOW_URL,
            timeout=20,
            verify=False,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        items = resp.json().get("data", [])
    except Exception as e:
        record_failure(SOURCE_NAME, str(e))
        logger.warning(f"[{SOURCE_NAME}] fetch error: {e}")
        return []

    jobs = []
    filtered = 0

    for item in items:
        title = (item.get("title") or "").strip()
        company = (item.get("company_name") or "").strip()
        url = (item.get("url") or "").strip()
        location = (item.get("location") or "Remote").strip()
        description = _strip_html(item.get("description") or "")
        tags = item.get("tags") or []
        is_remote = bool(item.get("remote", False))

        if not title or not url:
            continue

        # Combine description + tags for ProfileFilter context
        searchable = description + " " + " ".join(tags)
        keep, reason = pf.should_keep(title, searchable)
        if not keep:
            filtered += 1
            continue

        # Match user skills against Arbeitnow tags
        all_user_skills = pf.core_skills + pf.secondary_skills + pf.tools
        matching_skills = [
            t for t in tags
            if any(t.lower() == s.lower() for s in all_user_skills)
        ]

        # Normalise location label
        if is_remote and "remote" not in location.lower():
            location = f"Remote / {location}"

        jobs.append({
            "title": title[:150],
            "company": company[:100],
            "location": location[:100],
            "source_url": url,
            "source_domain": "arbeitnow.com",
            "description_snippet": description[:300],
            "posted_date": item.get("created_at") or "",
            "skills_found": json.dumps(matching_skills[:8]),
        })

    time.sleep(delay)
    record_success(SOURCE_NAME, jobs_returned=len(jobs))
    logger.info(f"[{SOURCE_NAME}] {len(jobs)} kept, {filtered} profile-filtered")
    return jobs


def _strip_html(text: str) -> str:
    """Lightweight HTML tag stripper."""
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()
