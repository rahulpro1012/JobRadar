"""
JobRadar Job API Fetcher
Integrates with job search APIs that aggregate listings from multiple portals.

Jooble API:  Free, API key required (free signup at jooble.org)
             Aggregates from Naukri, Indeed, company sites across India
             POST https://jooble.org/api/{api_key}

SerpApi:     Free tier: 100 searches/month
             Google Jobs endpoint aggregates from ALL job portals
             GET https://serpapi.com/search?engine=google_jobs
"""
import re
import json
import time
import logging
from datetime import datetime

from app.database import get_quota_usage, increment_quota

logger = logging.getLogger(__name__)

JOOBLE_QUOTA_KEY = "jooble"
SERPAPI_QUOTA_KEY = "serpapi"


# ============================================================
# Jooble API
# ============================================================

def fetch_jooble_jobs(profile, api_key, delay=1.0):
    """
    Search jobs via Jooble API.
    Jooble aggregates from Naukri, Indeed, Glassdoor, and thousands
    of company career pages across India.

    API format:
        POST https://jooble.org/api/{api_key}
        Body: {"keywords": "...", "location": "...", "page": 1}
        Response: {"totalCount": N, "jobs": [...]}
    """
    import requests

    if not api_key:
        logger.info("Jooble: No API key configured, skipping")
        return []

    core_skills = _parse_field(profile.get("core_skills", []))
    role = profile.get("primary_role", "Software Developer")
    location = profile.get("location", "India")
    role_variants = _parse_field(profile.get("role_variants", []))

    # Generate 2-3 search queries
    search_queries = [role]
    if core_skills:
        search_queries.append(f"{core_skills[0]} Developer")
    if len(core_skills) >= 2:
        search_queries.append(f"{core_skills[0]} {core_skills[1]}")

    all_jobs = []
    url = f"https://jooble.org/api/{api_key}"

    for query in search_queries[:3]:
        try:
            payload = {
                "keywords": query,
                "location": "India",
                "page": 1,
            }

            resp = requests.post(
                url,
                json=payload,
                timeout=15,
                verify=False,
                headers={"Content-Type": "application/json"},
            )
            increment_quota(JOOBLE_QUOTA_KEY)

            if resp.status_code != 200:
                logger.warning(f"Jooble returned HTTP {resp.status_code}")
                continue

            data = resp.json()
            jobs_list = data.get("jobs", [])

            for job in jobs_list:
                title = job.get("title", "").strip()
                if not title:
                    continue

                # Clean HTML from title and snippet
                title = re.sub(r"<[^>]+>", "", title).strip()
                snippet = job.get("snippet", "")
                snippet = re.sub(r"<[^>]+>", " ", snippet)
                snippet = re.sub(r"\s+", " ", snippet).strip()[:300]

                company = job.get("company", "").strip()
                job_location = job.get("location", "").strip()
                link = job.get("link", "")
                updated = job.get("updated", "")

                # Extract source domain from the link
                source_domain = "jooble.org"
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(link)
                    if parsed.hostname:
                        source_domain = parsed.hostname.replace("www.", "")
                except Exception:
                    pass

                all_jobs.append({
                    "title": title[:150],
                    "company": company[:100],
                    "location": job_location[:100],
                    "source_url": link,
                    "source_domain": source_domain,
                    "description_snippet": snippet,
                    "posted_date": updated[:10] if updated else "",
                })

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"Jooble error for query '{query}': {e}")
            continue

    logger.info(f"Jooble: fetched {len(all_jobs)} jobs across {len(search_queries)} queries")
    return all_jobs


# ============================================================
# SerpApi — Google Jobs
# ============================================================

def fetch_serpapi_jobs(profile, api_key, delay=1.0):
    """
    Search Google Jobs via SerpApi.
    Google Jobs aggregates from Indeed, LinkedIn, Naukri, Glassdoor,
    ZipRecruiter, and company career pages.

    Free tier: 100 searches/month.

    API format:
        GET https://serpapi.com/search
        Params: engine=google_jobs, q=..., location=..., api_key=...
        Response: {"jobs_results": [...]}
    """
    import requests

    if not api_key:
        logger.info("SerpApi: No API key configured, skipping")
        return []

    # Check monthly quota (100/month)
    today = datetime.now().strftime("%Y-%m")
    monthly_usage = get_quota_usage(SERPAPI_QUOTA_KEY, today)
    if monthly_usage >= 100:
        logger.info("SerpApi: Monthly quota exhausted (100/month)")
        return []

    core_skills = _parse_field(profile.get("core_skills", []))
    role = profile.get("primary_role", "Software Developer")
    location = profile.get("location", "India")

    # Generate 2 search queries (to save quota)
    search_queries = [f"{role} {location}"]
    if core_skills:
        search_queries.append(f"{core_skills[0]} Developer {location}")

    all_jobs = []

    for query in search_queries[:2]:
        try:
            params = {
                "engine": "google_jobs",
                "q": query,
                "location": location + ", India" if "india" not in location.lower() else location,
                "api_key": api_key,
                "hl": "en",
            }

            resp = requests.get(
                "https://serpapi.com/search",
                params=params,
                timeout=20,
                verify=False,
            )
            increment_quota(SERPAPI_QUOTA_KEY, today)

            if resp.status_code != 200:
                logger.warning(f"SerpApi returned HTTP {resp.status_code}")
                continue

            data = resp.json()
            jobs_results = data.get("jobs_results", [])

            for job in jobs_results:
                title = job.get("title", "").strip()
                company = job.get("company_name", "").strip()
                job_location = job.get("location", "").strip()
                description = job.get("description", "")[:300]

                # Get the best apply link
                apply_options = job.get("apply_options", [])
                apply_link = ""
                if apply_options:
                    apply_link = apply_options[0].get("link", "")
                    source_domain = apply_options[0].get("title", "").lower()
                else:
                    # Fallback: Google share link
                    apply_link = job.get("share_link", "")
                    source_domain = "google.com"

                # Extract source domain
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(apply_link)
                    if parsed.hostname:
                        source_domain = parsed.hostname.replace("www.", "")
                except Exception:
                    source_domain = "google.com"

                # Extract posted date
                extensions = job.get("detected_extensions", {})
                posted = extensions.get("posted_at", "")

                if title:
                    all_jobs.append({
                        "title": title[:150],
                        "company": company[:100],
                        "location": job_location[:100],
                        "source_url": apply_link,
                        "source_domain": source_domain,
                        "description_snippet": description,
                        "posted_date": posted,
                    })

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"SerpApi error for query '{query}': {e}")
            continue

    logger.info(f"SerpApi: fetched {len(all_jobs)} jobs across {len(search_queries)} queries")
    return all_jobs


# ============================================================
# Helpers
# ============================================================

def _parse_field(value):
    """Parse a JSON string or return list as-is."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return value if isinstance(value, list) else []
