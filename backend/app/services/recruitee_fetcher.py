"""
JobRadar — Recruitee ATS Fetcher (Layer 17)
Fetches jobs from Recruitee's public offers API for known companies.

Free, no API key required. Public job listings are accessible without auth.

Docs: https://api.recruitee.com/offers
Note: Recruitee is popular with European startups and SMEs.
"""
import json
import time
import logging
import requests
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure

logger = logging.getLogger(__name__)

SOURCE_NAME = "recruitee"

# Recruitee companies — primarily EU-based startups
# These are company domain slugs as they appear in Recruitee URLs
RECRUITEE_COMPANIES = [
    "frontapp",      # Front — email collaboration
    "revolut",       # Revolut — fintech
    "transferwise",  # Wise — international transfers
    "bolt",          # Bolt — ride-hailing
    "gojek",         # Gojek — Indonesian super-app (has Recruitee)
    "glovo",         # Glovo — food delivery
    "turing",        # Turing — distributed engineering
]


def fetch_recruitee_jobs(profile: dict, delay: float = 0.3) -> list:
    """
    Fetch jobs from registered Recruitee companies and filter by profile.

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
    skipped_404 = 0

    for company_slug in RECRUITEE_COMPANIES:
        try:
            # Recruitee uses subdomain format: {company}.recruitee.com/api/offers
            url = f"https://{company_slug}.recruitee.com/api/offers"
            resp = requests.get(url, timeout=10, verify=False)
            if resp.status_code == 404:
                skipped_404 += 1
                continue
            if resp.status_code != 200:
                record_failure(SOURCE_NAME, f"{company_slug}: HTTP {resp.status_code}")
                continue
            data = resp.json()
        except Exception as e:
            record_failure(SOURCE_NAME, f"{company_slug}: {e}")
            logger.warning(f"[{SOURCE_NAME}] {company_slug} error: {e}")
            continue

        # Recruitee API returns offers as array
        offers = data if isinstance(data, list) else data.get("offers", [])

        for offer in offers:
            title = (offer.get("name") or "").strip()
            if not title:
                continue

            description = offer.get("description") or ""
            if isinstance(description, dict):
                # Sometimes description is nested in an object
                description = description.get("value", "") or offer.get("requirements", "")

            keep, _ = pf.should_keep(title, description)
            if not keep:
                continue

            # Build job URL
            offer_id = offer.get("id") or ""
            job_url = offer.get("url") or (
                f"https://{company_slug}.recruitee.com/o/{offer_id}" if offer_id else ""
            )
            if not job_url:
                continue

            location = offer.get("location") or {}
            if isinstance(location, str):
                location_str = location
            elif isinstance(location, dict):
                city = location.get("city") or ""
                country = location.get("country") or ""
                location_str = ", ".join(filter(None, [city, country])) or "Remote"
            else:
                location_str = "Remote"

            all_jobs.append({
                "title": title[:150],
                "company": company_slug.title()[:100],
                "location": location_str[:100],
                "source_url": job_url,
                "source_domain": "recruitee.com",
                "description_snippet": _strip_html(str(description))[:300],
                "posted_date": offer.get("created_at") or "",
                "skills_found": json.dumps([]),
            })

        time.sleep(delay)

    record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    logger.info(
        f"[{SOURCE_NAME}] {len(all_jobs)} jobs kept "
        f"(404 companies skipped: {skipped_404})"
    )
    return all_jobs


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()
