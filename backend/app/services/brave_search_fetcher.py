"""
JobRadar — Brave Search API Fetcher (Layer 20)
Replaces fragile Yahoo HTML scraping with reliable Brave Search API.

Free tier: 2000 queries/month (~67/day, very generous)
No rate limiting needed (monthly quota only)

Endpoint: https://api.search.brave.com/res/v1/web/search
Auth: Header X-Subscription-Token: <api_key>
Response: Structured JSON (no HTML parsing)

This is a drop-in replacement for Yahoo layer that was fragile.
Brave Search prioritizes privacy and returns clean structured results.

Risk: Very low. Official API with documented SDKs.
"""
import json
import logging
import requests
from app.services.source_health import is_healthy, record_success, record_failure
from app.services.search_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

SOURCE_NAME = "brave_search"

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

# Domains to reject (non-job sites)
REJECTED_DOMAINS = {
    "youtube.com",
    "github.com",
    "stackoverflow.com",
    "medium.com",
    "dev.to",
    "wikipedia.org",
    "twitter.com",
    "facebook.com",
    "instagram.com",
}

# Content patterns to reject (not job listings)
REJECTED_PATTERNS = [
    "course",
    "tutorial",
    "how to",
    "guide",
    "salary",
    "skills you need",
    "career advice",
]


def fetch_brave_search_jobs(
    profile: dict,
    queries: list[str] = None,
    api_key: str = "",
    max_results: int = 20,
) -> list:
    """
    Fetch jobs using Brave Search API.

    Args:
        profile: Parsed user profile dict (for company name extraction).
        queries: List of search queries (e.g., ["Python developer Pune", ...]).
        api_key: Brave Search API key (required).
        max_results: Max results per query (default 20).

    Returns:
        List of normalised job dicts ready for DB insertion.

    Note:
        Free tier: 2000/month quota. Very generous, no special rate limiting needed.
        Cache: 6h TTL to avoid redundant searches.
    """
    if not api_key:
        logger.info(f"[{SOURCE_NAME}] no API key configured, skipping")
        return []

    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    if queries is None:
        queries = [profile.get("primary_role", "Developer")]

    all_jobs = []

    for query in queries:
        # Check cache
        cached = cache_get(SOURCE_NAME, query, ttl_hours=6)
        if cached is not None:
            logger.info(f"[{SOURCE_NAME}] cache hit for '{query}'")
            all_jobs.extend(cached)
            continue

        try:
            # Build API request
            params = {
                "q": query,
                "count": max_results,
            }

            headers = {
                "X-Subscription-Token": api_key,
                "Accept": "application/json",
            }

            resp = requests.get(
                ENDPOINT,
                params=params,
                headers=headers,
                timeout=15,
                verify=False,
            )

            if resp.status_code == 401:
                record_failure(SOURCE_NAME, "invalid API key")
                logger.warning(f"[{SOURCE_NAME}] 401 Unauthorized - check API key")
                break

            if resp.status_code != 200:
                record_failure(SOURCE_NAME, f"HTTP {resp.status_code}")
                logger.warning(f"[{SOURCE_NAME}] {query}: HTTP {resp.status_code}")
                continue

            data = resp.json()

        except Exception as e:
            record_failure(SOURCE_NAME, str(e))
            logger.warning(f"[{SOURCE_NAME}] {query} fetch error: {e}")
            continue

        # Extract results
        results = data.get("results", [])
        query_jobs = []

        for result in results:
            try:
                title = result.get("title", "").strip()
                url = result.get("url", "").strip()
                description = result.get("description", "").strip()

                if not title or not url:
                    continue

                # Extract domain from URL
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()

                # Reject non-job domains
                if any(blocked in domain for blocked in REJECTED_DOMAINS):
                    continue

                # Reject job listing patterns that aren't actual jobs
                if any(
                    pattern in description.lower() or pattern in title.lower()
                    for pattern in REJECTED_PATTERNS
                ):
                    continue

                # Require job keywords in title
                job_keywords = ["developer", "engineer", "programmer", "architect", "lead", "senior", "junior", "designer", "analyst"]
                if not any(kw in title.lower() for kw in job_keywords):
                    continue

                # Extract company from title pattern ("Title - Company" or "Title at Company")
                company = _extract_company_from_title(title)
                if not company:
                    company = domain.split(".")[0].title()

                # Normalize location from title or use generic
                location = _extract_location_from_title(title) or "Various"

                query_jobs.append({
                    "title": title[:150],
                    "company": company[:100],
                    "location": location[:100],
                    "source_url": url,
                    "source_domain": domain,
                    "description_snippet": description[:300],
                    "posted_date": "",  # Brave doesn't provide publish dates
                    "skills_found": json.dumps([]),
                })

            except (KeyError, AttributeError, ValueError) as e:
                logger.debug(f"[{SOURCE_NAME}] failed to parse result: {e}")
                continue

        # Cache results
        cache_set(SOURCE_NAME, query, query_jobs, ttl_hours=6)
        all_jobs.extend(query_jobs)

    # Record success/failure
    if all_jobs:
        record_success(SOURCE_NAME, jobs_returned=len(all_jobs))
    else:
        record_failure(SOURCE_NAME, "no jobs returned")

    logger.info(f"[{SOURCE_NAME}] {len(all_jobs)} jobs from {len(queries)} queries")
    return all_jobs


def _extract_company_from_title(title: str) -> str:
    """
    Extract company name from job title.

    Patterns:
    - "Title - Company Name"
    - "Title at Company Name"
    - "Company Name: Title"
    """
    # Try "Title - Company" pattern
    if " - " in title:
        parts = title.split(" - ")
        if len(parts) >= 2:
            return parts[-1].strip()

    # Try "Title at Company" pattern
    if " at " in title:
        parts = title.split(" at ")
        if len(parts) >= 2:
            return parts[-1].strip()

    # Try "Company: Title" pattern
    if ":" in title:
        parts = title.split(":")
        if len(parts) >= 2 and len(parts[0]) > 2 and len(parts[0]) < 50:
            return parts[0].strip()

    return ""


def _extract_location_from_title(title: str) -> str:
    """
    Extract location from job title if present.

    Looks for patterns like "Remote", "Pune", "Bangalore", etc.
    """
    common_locations = [
        "remote",
        "pune",
        "bangalore",
        "mumbai",
        "delhi",
        "kolkata",
        "hyderabad",
        "india",
        "us",
        "uk",
        "canada",
        "europe",
        "worldwide",
    ]

    title_lower = title.lower()
    for loc in common_locations:
        if f" {loc}" in title_lower or f"({loc})" in title_lower:
            return loc.title()

    return ""
