"""
JobRadar Job Fetcher v2
Layer 1:  Greenhouse API (free, no key)
Layer 2:  Lever API (free, no key)
Layer 2b: Ashby API (free, no key)
Layer 3:  Jooble API (free, key required)
Layer 4:  Indeed RSS (free)
Layer 5:  SerpApi Google Jobs (100/month)
Layer 6:  Career page search URLs
Layer 7:  SearxNG metasearch (NEW — replaces Google CSE)
Layer 8:  Yahoo Search fallback (NEW)
Layer 9:  Bing API (when key available)
Layer 10: DuckDuckGo (disabled, kept for future)
"""
import re
import time
import json
import logging
from datetime import datetime
from urllib.parse import quote_plus, urlparse

from app.database import (
    get_connection, execute_query,
    get_quota_usage, increment_quota,
)
from app.services.query_engine import (
    generate_queries, generate_site_queries, generate_rss_urls,
)

logger = logging.getLogger(__name__)

QUOTA_LIMITS = {
    "bing": 33,
}


def fetch_all_jobs(profile, config):
    """Main entry — fetches from all sources with AI queries + location awareness."""

    # Get AI-generated queries if available
    ai_queries = config.get("_ai_queries", [])
    queries = generate_queries(profile, ai_queries=ai_queries)

    # Build location list for search layers
    search_locations = _get_search_locations(profile)
    scrape_delay = config.get("SCRAPE_DELAY", 1.0)
    all_jobs = []

    # ── Layers 1, 2, 2b: ATS APIs (parallel) ──
    logger.info("Layers 1-2b: Fetching from Greenhouse + Lever + Ashby (parallel)...")
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch_greenhouse():
        try:
            from app.services.ats_fetcher import fetch_greenhouse_jobs
            return fetch_greenhouse_jobs(profile, delay=0.15)
        except Exception as e:
            logger.warning(f"Greenhouse failed: {e}")
            return []

    def _fetch_lever():
        try:
            from app.services.ats_fetcher import fetch_lever_jobs
            return fetch_lever_jobs(profile, delay=0.15)
        except Exception as e:
            logger.warning(f"Lever failed: {e}")
            return []

    def _fetch_ashby():
        try:
            from app.services.ats_fetcher import fetch_ashby_jobs
            return fetch_ashby_jobs(profile, delay=0.15)
        except Exception as e:
            logger.warning(f"Ashby failed: {e}")
            return []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_fetch_greenhouse): "Greenhouse",
            executor.submit(_fetch_lever): "Lever",
            executor.submit(_fetch_ashby): "Ashby",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                jobs = future.result(timeout=120)
                all_jobs.extend(jobs)
                logger.info(f"{name}: returned {len(jobs)} jobs")
            except Exception as e:
                logger.warning(f"{name} parallel fetch failed: {e}")

    # ── Layer 3: Jooble API ──
    jooble_key = config.get("JOOBLE_API_KEY", "")
    if jooble_key:
        logger.info("Layer 3: Fetching from Jooble API...")
        try:
            from app.services.job_api_fetcher import fetch_jooble_jobs
            all_jobs.extend(fetch_jooble_jobs(profile, jooble_key, delay=scrape_delay))
        except Exception as e:
            logger.warning(f"Jooble failed: {e}")

    # ── Layer 4: Indeed RSS ──
    logger.info("Layer 4: Fetching from Indeed RSS...")
    all_jobs.extend(_fetch_from_indeed_rss(profile, scrape_delay))

    # ── Layer 5: SerpApi Google Jobs ──
    serpapi_key = config.get("SERPAPI_API_KEY", "")
    if serpapi_key:
        logger.info("Layer 5: Fetching from SerpApi Google Jobs...")
        try:
            from app.services.job_api_fetcher import fetch_serpapi_jobs
            all_jobs.extend(fetch_serpapi_jobs(profile, serpapi_key, delay=scrape_delay))
        except Exception as e:
            logger.warning(f"SerpApi failed: {e}")

    # ── Layer 6: Career page search URLs ──
    logger.info("Layer 6: Generating career page search URLs...")
    all_jobs.extend(_fetch_from_career_pages(profile))

    # ── Layer 7: SearxNG Metasearch (replaces Google CSE) ──
    logger.info("Layer 7: Fetching from SearxNG...")
    try:
        from app.services.search_fetcher import fetch_from_searxng, build_search_queries
        # Build location-aware queries for job portals
        search_q = _build_portal_queries(profile, queries, search_locations)
        searxng_jobs = fetch_from_searxng(search_q, delay=1.5)
        all_jobs.extend(searxng_jobs)
    except Exception as e:
        logger.warning(f"SearxNG failed: {e}")

    # ── Layer 8: Yahoo Search Fallback ──
    logger.info("Layer 8: Fetching from Yahoo Search...")
    try:
        from app.services.search_fetcher import fetch_from_yahoo
        yahoo_q = _build_portal_queries(profile, queries, search_locations)[:4]
        yahoo_jobs = fetch_from_yahoo(yahoo_q, delay=1.5)
        all_jobs.extend(yahoo_jobs)
    except Exception as e:
        logger.warning(f"Yahoo failed: {e}")

    # ── Layer 9: Bing API ──
    bing_key = config.get("BING_API_KEY", "")
    if bing_key:
        today_usage = get_quota_usage("bing")
        remaining = QUOTA_LIMITS["bing"] - today_usage
        if remaining > 0:
            logger.info(f"Layer 9: Bing ({remaining} remaining)...")
            top_queries = [q for q in queries if q["tier"] <= 2][:3]
            site_queries = generate_site_queries(top_queries, ["naukri.com", "indeed.co.in"])
            max_calls = min(6, remaining, len(site_queries))
            for sq in site_queries[:max_calls]:
                jobs = _fetch_from_bing(sq["site_query"], bing_key, scrape_delay)
                all_jobs.extend(jobs)

    # ── Layer 10: DuckDuckGo (disabled, kept for future) ──
    # logger.info("Layer 10: DuckDuckGo...")
    # for q in queries[:3]:
    #     all_jobs.extend(_fetch_from_duckduckgo(q["query"], scrape_delay))

    # Store new jobs
    new_count = _store_jobs(all_jobs)
    logger.info(f"Fetched {len(all_jobs)} total, {new_count} new jobs stored.")
    return new_count


# ============================================================
# Location Helpers
# ============================================================

def _get_search_locations(profile):
    """Extract search locations from profile."""
    locations = []

    # Primary location
    loc = profile.get("location", "")
    if loc:
        locations.append(loc)

    # Additional locations from search_locations field
    extra = profile.get("search_locations", "")
    if extra:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (json.JSONDecodeError, TypeError):
                extra = [x.strip() for x in extra.split(",") if x.strip()]
        if isinstance(extra, list):
            locations.extend(extra)

    # Always include India and Remote
    if "India" not in locations:
        locations.append("India")
    if "Remote" not in locations:
        locations.append("Remote")

    return locations


def _build_portal_queries(profile, queries, locations):
    """Build site-scoped queries for SearxNG/Yahoo targeting job portals."""
    role = profile.get("primary_role", "Developer")
    core_skills = profile.get("core_skills", [])
    if isinstance(core_skills, str):
        try:
            core_skills = json.loads(core_skills)
        except (json.JSONDecodeError, TypeError):
            core_skills = []

    sites = ["naukri.com", "linkedin.com/jobs"]
    portal_queries = []
    seen = set()

    # Use top tier queries with site: prefix
    for q in queries[:3]:
        query_text = q["query"] if isinstance(q, dict) else q
        for site in sites:
            full = f"site:{site} {query_text}"
            if full.lower() not in seen:
                seen.add(full.lower())
                portal_queries.append(full)

    # Add location-specific queries
    for loc in locations[:3]:
        if loc.lower() in ("india", "remote"):
            query = f"site:naukri.com {role} {loc}"
        else:
            query = f"site:naukri.com {role} {loc}"
        if query.lower() not in seen:
            seen.add(query.lower())
            portal_queries.append(query)

    return portal_queries[:8]


# ============================================================
# Layer 4: Indeed RSS
# ============================================================

def _fetch_from_indeed_rss(profile, delay=1.0):
    import requests

    rss_urls = generate_rss_urls(profile)
    jobs = []

    for url in rss_urls:
        try:
            resp = requests.get(url, timeout=15, verify=False, headers={
                "User-Agent": "Mozilla/5.0 (compatible; JobRadar/1.0)"
            })
            if resp.status_code != 200:
                continue
            parsed_jobs = _parse_rss_feed(resp.text)
            jobs.extend(parsed_jobs)
            increment_quota("rss")
            time.sleep(delay)
        except Exception as e:
            logger.warning(f"RSS fetch failed: {e}")
            continue
    return jobs


def _parse_rss_feed(xml_text):
    jobs = []
    items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)

    for item in items[:20]:
        title = _xml_tag(item, "title")
        link = _xml_tag(item, "link")
        desc = _xml_tag(item, "description")
        pub_date = _xml_tag(item, "pubDate")

        if not title or not link:
            continue

        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()[:300]

        parts = title.split(" - ")
        job_title = parts[0].strip()
        company = parts[1].strip() if len(parts) > 1 else ""
        location = parts[2].strip() if len(parts) > 2 else ""

        jobs.append({
            "title": job_title[:150],
            "company": company[:100],
            "location": location[:100],
            "source_url": link,
            "source_domain": "indeed.co.in",
            "description_snippet": desc,
            "posted_date": pub_date,
        })
    return jobs


def _xml_tag(text, tag):
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL)
    if match:
        content = match.group(1).strip()
        cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>", content, re.DOTALL)
        return cdata.group(1).strip() if cdata else content
    return ""


# ============================================================
# Layer 6: Career Page Search URLs
# ============================================================

def _fetch_from_career_pages(profile):
    companies = execute_query(
        "SELECT * FROM company_sources WHERE enabled = 1", fetch_all=True
    )
    if not companies:
        return []

    role = profile.get("primary_role", "developer")
    location = profile.get("location", "")
    core_skills = profile.get("core_skills", [])
    if isinstance(core_skills, str):
        try:
            core_skills = json.loads(core_skills)
        except (json.JSONDecodeError, TypeError):
            core_skills = []

    search_queries = [role]
    if core_skills:
        search_queries.append(f"{core_skills[0]} Developer")

    jobs = []
    for company in companies:
        search_pattern = company.get("search_pattern", "")
        if not search_pattern:
            continue

        for query_text in search_queries[:2]:
            encoded_query = quote_plus(query_text)
            encoded_location = quote_plus(location) if location else ""

            search_url = search_pattern.replace("{query}", encoded_query)
            search_url = search_url.replace("{location}", encoded_location)

            title = f"{query_text} at {company['company_name']}"
            if location:
                title += f" — {location}"

            domain = urlparse(company["careers_url"]).hostname or ""
            domain = domain.replace("www.", "")

            jobs.append({
                "title": title[:150],
                "company": company["company_name"],
                "location": location,
                "source_url": search_url,
                "source_domain": domain,
                "description_snippet": f"Search {company['company_name']} careers for {query_text} positions.",
                "posted_date": datetime.now().strftime("%Y-%m-%d"),
            })

    increment_quota("direct_scrape")
    return jobs


# ============================================================
# Layer 9: Bing API
# ============================================================

def _fetch_from_bing(query, api_key, delay=1.0):
    import requests

    try:
        resp = requests.get(
            "https://api.bing.microsoft.com/v7.0/search",
            headers={"Ocp-Apim-Subscription-Key": api_key},
            params={"q": query, "count": 10, "mkt": "en-IN"},
            timeout=15, verify=False,
        )
        increment_quota("bing")

        if resp.status_code != 200:
            return []

        data = resp.json()
        jobs = []
        for item in data.get("webPages", {}).get("value", []):
            from app.services.search_fetcher import _parse_search_result
            parsed = _parse_search_result(
                item.get("name", ""), item.get("url", ""), item.get("snippet", "")
            )
            if parsed:
                jobs.append(parsed)

        time.sleep(delay)
        return jobs
    except Exception as e:
        logger.warning(f"Bing error: {e}")
        return []


# ============================================================
# Database Storage
# ============================================================

def _store_jobs(jobs):
    if not jobs:
        return 0

    new_count = 0
    with get_connection() as conn:
        for job in jobs:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE source_url = ?", (job["source_url"],)
            ).fetchone()

            if existing:
                continue

            try:
                conn.execute("""
                    INSERT INTO jobs (
                        title, company, location, source_url, source_domain,
                        description_snippet, skills_found, posted_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')
                """, (
                    job["title"], job["company"], job["location"],
                    job["source_url"], job["source_domain"],
                    job["description_snippet"], job.get("skills_found", "[]"),
                    job.get("posted_date", ""),
                ))
                new_count += 1
            except Exception as e:
                logger.warning(f"Failed to insert job: {e}")
                continue

        conn.commit()
    return new_count
