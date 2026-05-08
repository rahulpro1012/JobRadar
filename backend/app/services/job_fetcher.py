"""
JobRadar Job Fetcher
Implements the multi-layer fetching strategy with source routing.

Layer 1: Greenhouse API (free, no key)      — actual job listings from 30+ companies
Layer 2: Lever API (free, no key)           — actual job listings from 15+ companies
Layer 3: Jooble API (free, key required)    — aggregates Naukri, Indeed, company sites
Layer 4: Indeed RSS feeds (free)            — unlimited
Layer 5: SerpApi Google Jobs (100/month)    — Google Jobs aggregates from ALL portals
Layer 6: Company career page search URLs    — pre-filtered search links
Layer 7: Google CSE API (100/day)           — site-scoped search
Layer 8: Bing API (1000/month)              — fallback search
Layer 9: DuckDuckGo (free, unlimited)       — general web search fallback
"""
import re
import time
import json
import logging
from datetime import datetime
from urllib.parse import quote_plus, urljoin, urlparse

from app.database import (
    get_connection,
    execute_query,
    get_quota_usage,
    increment_quota,
)
from app.services.query_engine import (
    generate_queries,
    generate_site_queries,
    generate_rss_urls,
)

logger = logging.getLogger(__name__)

QUOTA_LIMITS = {
    "google_cse": 100,
    "bing": 33,
    "google_scrape": 60,
}


# ============================================================
# Source Router
# ============================================================

def fetch_all_jobs(profile, config):
    """
    Main entry point — fetches jobs from all available sources.
    Routes through cheapest/best sources first.
    """
    # queries = generate_queries(profile)
    ai_queries = config.get("_ai_queries", [])
    queries = generate_queries(profile, ai_queries=ai_queries)

    scrape_delay = config.get("SCRAPE_DELAY", 1.0)
    all_jobs = []

    # ── Layer 1: Greenhouse API (free, no key, actual jobs) ──
    logger.info("Layer 1: Fetching from Greenhouse API...")
    try:
        from app.services.ats_fetcher import fetch_greenhouse_jobs
        gh_jobs = fetch_greenhouse_jobs(profile, delay=0.5)
        all_jobs.extend(gh_jobs)
    except Exception as e:
        logger.warning(f"Greenhouse layer failed: {e}")

    # ── Layer 2: Lever API (free, no key, actual jobs) ──
    logger.info("Layer 2: Fetching from Lever API...")
    try:
        from app.services.ats_fetcher import fetch_lever_jobs
        lever_jobs = fetch_lever_jobs(profile, delay=0.5)
        all_jobs.extend(lever_jobs)
    except Exception as e:
        logger.warning(f"Lever layer failed: {e}")
    
    # ── Layer 2b: Ashby API (free, no key, actual jobs + salary data) ──
    logger.info("Layer 2b: Fetching from Ashby API...")
    try:
        from app.services.ats_fetcher import fetch_ashby_jobs
        ashby_jobs = fetch_ashby_jobs(profile, delay=0.5)
        all_jobs.extend(ashby_jobs)
    except Exception as e:
        logger.warning(f"Ashby layer failed: {e}")

    # ── Layer 3: Jooble API (free, key required) ──
    jooble_key = config.get("JOOBLE_API_KEY", "")
    if jooble_key:
        logger.info("Layer 3: Fetching from Jooble API...")
        try:
            from app.services.job_api_fetcher import fetch_jooble_jobs
            jooble_jobs = fetch_jooble_jobs(profile, jooble_key, delay=scrape_delay)
            all_jobs.extend(jooble_jobs)
        except Exception as e:
            logger.warning(f"Jooble layer failed: {e}")
    else:
        logger.info("Layer 3: Jooble API key not set, skipping")

    # ── Layer 4: Indeed RSS (free, unlimited) ──
    logger.info("Layer 4: Fetching from Indeed RSS...")
    rss_jobs = _fetch_from_indeed_rss(profile, scrape_delay)
    all_jobs.extend(rss_jobs)

    # ── Layer 5: SerpApi Google Jobs (100/month free) ──
    serpapi_key = config.get("SERPAPI_API_KEY", "")
    if serpapi_key:
        logger.info("Layer 5: Fetching from SerpApi Google Jobs...")
        try:
            from app.services.job_api_fetcher import fetch_serpapi_jobs
            serp_jobs = fetch_serpapi_jobs(profile, serpapi_key, delay=scrape_delay)
            all_jobs.extend(serp_jobs)
        except Exception as e:
            logger.warning(f"SerpApi layer failed: {e}")
    else:
        logger.info("Layer 5: SerpApi key not set, skipping")

    # ── Layer 6: Company career page search URLs (free, instant) ──
    logger.info("Layer 6: Generating career page search URLs...")
    career_jobs = _fetch_from_career_pages(profile)
    all_jobs.extend(career_jobs)

    # ── Layer 7: Google CSE API (100/day, max 8 per refresh) ──
    google_key = config.get("GOOGLE_CSE_API_KEY", "")
    google_cx = config.get("GOOGLE_CSE_CX", "")
    if google_key and google_cx:
        today_usage = get_quota_usage("google_cse")
        remaining = QUOTA_LIMITS["google_cse"] - today_usage
        if remaining > 0:
            logger.info(f"Layer 7: Google CSE ({remaining} remaining)...")
            top_queries = [q for q in queries if q["tier"] <= 2][:3]
            print(f">>> top_queries count: {len(top_queries)}")
            top_sites = ["naukri.com", "linkedin.com/jobs"]
            site_queries = generate_site_queries(top_queries, top_sites)
            print(f">>> site_queries count: {len(site_queries)}")
            max_calls = min(8, remaining, len(site_queries))
            print(f">>> max_calls: {max_calls}")
            for sq in site_queries[:max_calls]:
                print(f">>> Calling Google CSE: {sq['site_query'][:80]}")
                jobs = _fetch_from_google_cse(sq["site_query"], google_key, google_cx, scrape_delay)
                all_jobs.extend(jobs)
    else:
        print(f">>> Google CSE SKIPPED: key={bool(google_key)}, cx={bool(google_cx)}")

    # ── Layer 8: Bing API (1000/month, max 6 per refresh) ──
    bing_key = config.get("BING_API_KEY", "")
    if bing_key:
        today_usage = get_quota_usage("bing")
        remaining = QUOTA_LIMITS["bing"] - today_usage
        if remaining > 0:
            logger.info(f"Layer 8: Bing ({remaining} remaining)...")
            top_queries = [q for q in queries if q["tier"] <= 2][:3]
            site_queries = generate_site_queries(top_queries, ["indeed.co.in"])
            max_calls = min(6, remaining, len(site_queries))
            for sq in site_queries[:max_calls]:
                jobs = _fetch_from_bing(sq["site_query"], bing_key, scrape_delay)
                all_jobs.extend(jobs)

    # ── Layer 9: DuckDuckGo (free, fallback) ──
    # logger.info("Layer 9: Fetching from DuckDuckGo...")
    # for q in queries[:3]:
    #     jobs = _fetch_from_duckduckgo(q["query"], scrape_delay)
    #     all_jobs.extend(jobs)

    # Store new jobs in database
    new_count = _store_jobs(all_jobs)
    logger.info(f"Fetched {len(all_jobs)} total, {new_count} new jobs stored.")
    return new_count


# ============================================================
# Layer 4: Indeed RSS
# ============================================================

def _fetch_from_indeed_rss(profile, delay=1.0):
    """Fetch job listings from Indeed RSS feeds."""
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
            logger.warning(f"RSS fetch failed for {url}: {e}")
            continue

    return jobs


def _parse_rss_feed(xml_text):
    """Parse an RSS feed XML string into job dicts."""
    try:
        import feedparser
        feed = feedparser.parse(xml_text)
    except ImportError:
        return _parse_rss_manual(xml_text)

    jobs = []
    for entry in feed.entries[:20]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        parts = title.split(" - ")
        job_title = parts[0].strip() if parts else title
        company = parts[1].strip() if len(parts) > 1 else ""
        location = parts[2].strip() if len(parts) > 2 else ""

        desc = entry.get("summary", entry.get("description", ""))
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()[:300]

        published = entry.get("published", entry.get("updated", ""))

        jobs.append({
            "title": job_title[:150],
            "company": company[:100],
            "location": location[:100],
            "source_url": link,
            "source_domain": "indeed.co.in",
            "description_snippet": desc,
            "posted_date": published,
        })

    return jobs


def _parse_rss_manual(xml_text):
    """Fallback RSS parser using regex."""
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
    """Extract text content of an XML tag."""
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL)
    if match:
        content = match.group(1).strip()
        cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>", content, re.DOTALL)
        if cdata:
            return cdata.group(1).strip()
        return content
    return ""


# ============================================================
# Layer 6: Company Career Page Search URLs
# ============================================================

def _fetch_from_career_pages(profile):
    """Generate pre-filtered search URLs for company career pages."""
    companies = execute_query(
        "SELECT * FROM company_sources WHERE enabled = 1",
        fetch_all=True,
    )
    if not companies:
        return []

    role = profile.get("primary_role", "developer")
    location = profile.get("location", "")
    core_skills = json.loads(profile["core_skills"]) if isinstance(profile.get("core_skills"), str) else profile.get("core_skills", [])

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
# Layer 7: Google CSE API
# ============================================================

def _fetch_from_google_cse(query, api_key, cx, delay=1.0):
    """Fetch results from Google Custom Search JSON API."""
    import requests

    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": cx, "q": query, "num": 10}

    try:
        resp = requests.get(url, params=params, timeout=15, verify=False)
        increment_quota("google_cse")

        if resp.status_code != 200:
            print(f">>> Google CSE HTTP {resp.status_code}: {resp.text[:200]}")
            return []

        data = resp.json()
        items = data.get("items", [])
        print(f">>> Google CSE: {len(items)} raw results for: {query[:80]}")

        jobs = []
        for item in items:
            parsed = _parse_search_result(
                item.get("title", ""),
                item.get("link", ""),
                item.get("snippet", ""),
            )
            if parsed:
                jobs.append(parsed)
            else:
                print(f">>>   FILTERED OUT: {item.get('title', '')[:60]} | {item.get('link', '')[:60]}")

        print(f">>> Google CSE: {len(jobs)} kept after filtering")
        time.sleep(delay)
        return jobs
    except Exception as e:
        logger.warning(f"Google CSE error: {e}")
        return []


# ============================================================
# Layer 8: Bing API
# ============================================================

def _fetch_from_bing(query, api_key, delay=1.0):
    """Fetch results from Bing Web Search API."""
    import requests

    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": query, "count": 10, "mkt": "en-IN"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15, verify=False)
        increment_quota("bing")

        if resp.status_code != 200:
            return []

        data = resp.json()
        jobs = []
        for item in data.get("webPages", {}).get("value", []):
            parsed = _parse_search_result(
                item.get("name", ""),
                item.get("url", ""),
                item.get("snippet", ""),
            )
            if parsed:
                jobs.append(parsed)

        time.sleep(delay)
        return jobs
    except Exception as e:
        logger.warning(f"Bing error: {e}")
        return []


# ============================================================
# Layer 9: DuckDuckGo
# ============================================================

def _fetch_from_duckduckgo(query, delay=1.0):
    """Fetch results from DuckDuckGo HTML search."""
    import requests
    from bs4 import BeautifulSoup

    url = "https://html.duckduckgo.com/html/"
    data = {"q": f"{query} jobs", "kl": "in-en"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        resp = requests.post(url, data=data, headers=headers, timeout=15, verify=False)
        increment_quota("duckduckgo")

        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.find_all("a", class_="result__a")
        jobs = []

        for result in results[:10]:
            title = result.get_text(strip=True)
            link = result.get("href", "")
            actual_url = _extract_ddg_url(link)
            if not actual_url:
                continue

            snippet = ""
            snippet_el = result.find_parent("div")
            if snippet_el:
                snippet_span = snippet_el.find("a", class_="result__snippet")
                if snippet_span:
                    snippet = snippet_span.get_text(strip=True)[:300]

            parsed = _parse_search_result(title, actual_url, snippet)
            if parsed:
                jobs.append(parsed)

        time.sleep(delay)
        return jobs
    except Exception as e:
        logger.warning(f"DuckDuckGo error: {e}")
        return []


def _extract_ddg_url(ddg_link):
    """Extract actual URL from DuckDuckGo redirect link."""
    match = re.search(r"uddg=([^&]+)", ddg_link)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))
    if ddg_link.startswith("http"):
        return ddg_link
    return None


# ============================================================
# Search Result Parser (shared by Layers 7-9)
# ============================================================

def _parse_search_result(title, url, snippet=""):
    """Parse a search result into a normalized job dict. Rejects non-job URLs."""
    domain = urlparse(url).hostname or ""
    domain = domain.replace("www.", "")

    skip_domains = [
        "youtube.com", "facebook.com", "twitter.com", "instagram.com",
        "wikipedia.org", "quora.com", "reddit.com", "medium.com",
        "stackoverflow.com", "github.com", "geeksforgeeks.org",
        "glassdoor.com", "ambitionbox.com", "payscale.com",
        "coursera.org", "udemy.com", "w3schools.com",
    ]
    if any(sd in domain for sd in skip_domains):
        return None

    title_lower = title.lower()
    skip_keywords = [
        "how to", "tutorial", "guide", "salary", "review",
        "interview questions", "vs ", "what is", "best ", "top 10",
        "course", "certification", "resume template",
    ]
    if any(kw in title_lower for kw in skip_keywords):
        return None

    # Reject search result pages / aggregation titles
    garbage_patterns = [
        r"\d+\+?\s*(?:full stack|java|react|developer|engineer|software)",  # "1,000+ Full Stack Developer"
        r"(?:jobs|vacancies|openings)\s+(?:in|at|near)\s+",  # "jobs in Pune"
        r"freelance.*contractor.*jobs",  # "Freelance Contractor Jobs"
        r"(?:latest|new|top|best)\s+\d+",  # "Latest 500 jobs"
        r"(?:apply to|explore|browse)\s+\d+",  # "Apply to 200+ jobs"
    ]
    if any(re.search(p, title_lower) for p in garbage_patterns):
        return None
    
    # Reject aggregation/listing page titles
    if re.search(r"\d{2,}[+,]?\s*(?:full|java|react|spring|developer|engineer|software|backend|frontend)", title_lower):
        return None
    if re.search(r"(?:urgent|latest|new|top|best|apply)[\s!]*(?:full|java|react|developer|engineer|software|jobs)", title_lower):
        return None
    if re.search(r"jobs?\s+(?:in|at|near|for)\s+\w+", title_lower) and not re.search(r"at\s+[A-Z]", title):
        return None

    # Must have a role keyword
    role_keywords = [
        "developer", "engineer", "architect", "analyst", "designer",
        "manager", "lead", "intern", "trainee", "consultant",
        "devops", "sre", "qa", "tester", "programmer",
        "sde", "swe", "full stack", "frontend", "backend",
    ]
    if not any(kw in title_lower for kw in role_keywords):
        return None

    # Extract company from title
    company = ""
    job_title = title
    for sep in [" - ", " | ", " — ", " – "]:
        if sep in title:
            parts = title.split(sep)
            job_title = parts[0].strip()
            if len(parts) > 1:
                company = parts[1].strip()
            break

    at_match = re.search(r"^(.+?)\s+at\s+(.+?)(?:\s*[\-|]|$)", title, re.IGNORECASE)
    if at_match and not company:
        job_title = at_match.group(1).strip()
        company = at_match.group(2).strip()

    for suffix in ["| Naukri.com", "| Indeed", "| LinkedIn", "- LinkedIn",
                    "- Naukri.com", "- Indeed.co.in", "Naukri.com", "LinkedIn"]:
        job_title = job_title.replace(suffix, "").strip()
        company = company.replace(suffix, "").strip()

    job_title = job_title.strip(" -|–—")
    company = company.strip(" -|–—")

    if not job_title or len(job_title) < 5:
        return None

    return {
        "title": job_title[:150],
        "company": company[:100],
        "location": "",
        "source_url": url,
        "source_domain": domain,
        "description_snippet": snippet[:300],
        "posted_date": "",
    }


# ============================================================
# Database Storage
# ============================================================

def _store_jobs(jobs):
    """Store fetched jobs, skip duplicates by URL. Returns new count."""
    if not jobs:
        return 0

    new_count = 0
    with get_connection() as conn:
        for job in jobs:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE source_url = ?",
                (job["source_url"],),
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
                    job["title"],
                    job["company"],
                    job["location"],
                    job["source_url"],
                    job["source_domain"],
                    job["description_snippet"],
                    job.get("skills_found", "[]"),
                    job.get("posted_date", ""),
                ))
                new_count += 1
            except Exception as e:
                logger.warning(f"Failed to insert job: {e}")
                continue

        conn.commit()

    return new_count
