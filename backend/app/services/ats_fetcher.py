"""
JobRadar ATS Fetcher
Fetches actual job listings from company ATS platforms via their public APIs.
Supports Greenhouse and Lever — both free, no API key required.

Greenhouse API: GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
Lever API:      GET https://api.lever.co/v0/postings/{company}?mode=json
"""
import re
import json
import time
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ============================================================
# Company → ATS Mapping
# Known companies and their ATS board tokens
# ============================================================

# Greenhouse companies: {display_name: board_token}
GREENHOUSE_COMPANIES = {
    "Stripe": "stripe",
    "Cloudflare": "cloudflare",
    "Coinbase": "coinbase",
    "Figma": "figma",
    "Notion": "notion",
    "Discord": "discord",
    "Brex": "brex",
    "Plaid": "plaid",
    "Ramp": "ramp",
    "Airtable": "airtable",
    "Webflow": "webflow",
    "HashiCorp": "hashicorp",
    "GitLab": "gitlab",
    "Grafana Labs": "grafanalabs",
    "Postman": "postman",
    "Snyk": "snyk",
    "LaunchDarkly": "launchdarkly",
    "Kong": "kong",
    "PlanetScale": "planetscale",
    "Sourcegraph": "sourcegraph",
    "Vercel": "vercel",
    "Railway": "railway",
    "Retool": "retool",
    "Linear": "linear",
    "Dbt Labs": "daboraoriginc",
    "Supabase": "supabase",
    "Render": "render",
    "Fly.io": "fly-io",
    "Neon": "neon-inc",
    "Turso": "turso",
    "Cred": "cred",
    "Razorpay": "razorpay",
    "Swiggy": "swiggy",
    "Meesho": "meesho",
    "Dream11": "dream11",
    "MPL": "mobilepremierleague",
    "CRED": "cred",
    "Zerodha": "zerodha",
}

# Lever companies: {display_name: company_slug}
LEVER_COMPANIES = {
    "Netflix": "netflix",
    "Atlassian": "atlassian",
    "Twilio": "twilio",
    "Spotify": "spotify",
    "Shopify": "shopify",
    "Cloudinary": "cloudinary",
    "Workato": "workato",
    "Hasura": "hasura",
    "Postman": "postman",
    "BrowserStack": "browserstack",
    "Druva": "druva",
    "Freshworks": "freshworks",
    "PhonePe": "phonepe",
    "Groww": "groww",
    "Upstox": "upstox",
    "Slice": "sliceit",
    "Licious": "licious",
}


# ============================================================
# Greenhouse Fetcher
# ============================================================

def fetch_greenhouse_jobs(profile, delay=0.5):
    """
    Fetch jobs from all known Greenhouse companies.
    Filters by skills and role from the profile.
    Returns list of normalized job dicts.
    """
    import requests

    core_skills = _parse_skills(profile.get("core_skills", []))
    role = profile.get("primary_role", "").lower()
    location = profile.get("location", "").lower()
    skill_set = set(s.lower() for s in core_skills)

    all_jobs = []

    for company_name, board_token in GREENHOUSE_COMPANIES.items():
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "JobRadar/1.0 (personal job search tool)"
            })

            if resp.status_code != 200:
                logger.debug(f"Greenhouse {company_name}: HTTP {resp.status_code}")
                continue

            data = resp.json()
            jobs_list = data.get("jobs", [])

            for job in jobs_list:
                title = job.get("title", "")
                title_lower = title.lower()
                content = job.get("content", "")
                content_lower = content.lower() if content else ""
                job_location = job.get("location", {}).get("name", "")

                # Filter: must be a tech/dev role
                if not _is_relevant_role(title_lower):
                    continue

                # Filter: must match at least 1 skill in title or description
                searchable = title_lower + " " + content_lower
                matching_skills = [s for s in skill_set if s in searchable]
                if not matching_skills and not _role_matches(title_lower, role):
                    continue

                # Build clean description snippet
                desc = re.sub(r"<[^>]+>", " ", content)
                desc = re.sub(r"\s+", " ", desc).strip()[:300]

                all_jobs.append({
                    "title": title[:150],
                    "company": company_name,
                    "location": job_location[:100],
                    "source_url": job.get("absolute_url", ""),
                    "source_domain": "greenhouse.io",
                    "description_snippet": desc,
                    "posted_date": job.get("updated_at", "")[:10],
                    "skills_found": json.dumps(matching_skills[:8]),
                })

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"Greenhouse {company_name} error: {e}")
            continue

    logger.info(f"Greenhouse: fetched {len(all_jobs)} relevant jobs from {len(GREENHOUSE_COMPANIES)} companies")
    return all_jobs


# ============================================================
# Lever Fetcher
# ============================================================

def fetch_lever_jobs(profile, delay=0.5):
    """
    Fetch jobs from all known Lever companies.
    Filters by skills and role from the profile.
    Returns list of normalized job dicts.
    """
    import requests

    core_skills = _parse_skills(profile.get("core_skills", []))
    role = profile.get("primary_role", "").lower()
    location = profile.get("location", "").lower()
    skill_set = set(s.lower() for s in core_skills)

    all_jobs = []

    for company_name, slug in LEVER_COMPANIES.items():
        try:
            url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "JobRadar/1.0 (personal job search tool)"
            })

            if resp.status_code != 200:
                logger.debug(f"Lever {company_name}: HTTP {resp.status_code}")
                continue

            postings = resp.json()
            if not isinstance(postings, list):
                continue

            for posting in postings:
                title = posting.get("text", "")
                title_lower = title.lower()
                categories = posting.get("categories", {})
                department = categories.get("department", "")
                team = categories.get("team", "")
                job_location = categories.get("location", "")
                commitment = categories.get("commitment", "")

                # Build searchable text from title + department + team
                searchable = f"{title_lower} {department.lower()} {team.lower()}"

                # Filter: must be a tech/dev role
                if not _is_relevant_role(searchable):
                    continue

                # Filter: match skills or role
                desc_text = posting.get("descriptionPlain", "")
                full_searchable = searchable + " " + desc_text.lower()
                matching_skills = [s for s in skill_set if s in full_searchable]
                if not matching_skills and not _role_matches(title_lower, role):
                    continue

                # Apply URL
                apply_url = posting.get("hostedUrl", "") or posting.get("applyUrl", "")

                all_jobs.append({
                    "title": title[:150],
                    "company": company_name,
                    "location": job_location[:100],
                    "source_url": apply_url,
                    "source_domain": "lever.co",
                    "description_snippet": desc_text[:300],
                    "posted_date": "",
                    "skills_found": json.dumps(matching_skills[:8]),
                })

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"Lever {company_name} error: {e}")
            continue

    logger.info(f"Lever: fetched {len(all_jobs)} relevant jobs from {len(LEVER_COMPANIES)} companies")
    return all_jobs


# ============================================================
# Helpers
# ============================================================

def _parse_skills(skills):
    """Parse skills from JSON string or list."""
    if isinstance(skills, str):
        try:
            return json.loads(skills)
        except (json.JSONDecodeError, TypeError):
            return []
    return skills if isinstance(skills, list) else []


def _is_relevant_role(text):
    """Check if text contains a tech/engineering role keyword."""
    role_keywords = {
        "developer", "engineer", "programmer", "architect",
        "sde", "swe", "devops", "sre", "qa", "tester",
        "full stack", "fullstack", "frontend", "front-end",
        "backend", "back-end", "software", "data", "cloud",
        "platform", "infrastructure", "security", "mobile",
        "web", "api", "microservice", "machine learning",
        "ml ", "ai ", "analyst", "consultant",
    }
    return any(kw in text for kw in role_keywords)


def _role_matches(title, user_role):
    """Check if a job title matches the user's role or its variants."""
    if not user_role:
        return False
    # Check if key words from user's role appear in the title
    role_words = set(user_role.split())
    title_words = set(title.split())
    overlap = role_words & title_words
    return len(overlap) >= 2
