"""
JobRadar Search Engine Fetcher
Layer 7: SearxNG metasearch (free, no key, JSON responses)
Layer 8: Yahoo Search fallback (free, HTML scraping)

Both support site: operator for targeting Naukri, LinkedIn, Indeed.
"""
import os
import re
import time
import json
import logging
from urllib.parse import urlparse, quote_plus

from app.database import increment_quota

logger = logging.getLogger(__name__)

# Self-hosted instance (primary when SEARXNG_URL is set in .env) + public fallbacks
_self_hosted = os.environ.get("SEARXNG_URL", "").rstrip("/")
SEARXNG_INSTANCES = [u for u in [
    _self_hosted,                       # self-hosted on Render (preferred)
    "https://search.indst.eu",
    "https://search.einfachzocken.eu",
    "https://search.hbubli.cc",
    "https://search.im-in.space",
    "https://search.federicociro.com",
    "https://ooglester.com",
    "https://metacat.online",
    "https://search.canine.tools",
] if u]  # drop empty string when SEARXNG_URL is not set


# ============================================================
# Layer 7: SearxNG Metasearch
# ============================================================

def fetch_from_searxng(queries, delay=1.5):
    """
    Search via SearxNG metasearch engine.
    Returns structured JSON from Google+Bing+Yahoo simultaneously.
    """
    import requests

    if not SEARXNG_INSTANCES:
        logger.debug("[searxng] No instances configured — skipping")
        return []

    # Warmup ping for self-hosted Render instance (cold-starts take ~30s)
    primary = SEARXNG_INSTANCES[0]
    if "onrender.com" in primary:
        try:
            requests.get(f"{primary}/healthz", timeout=5, verify=False)
            logger.debug("[searxng] Warmup ping sent to self-hosted instance")
        except Exception:
            pass  # fire-and-forget

    all_jobs = []
    instance_idx = 0

    for query in queries[:6]:  # Max 6 queries per refresh
        instance_url = SEARXNG_INSTANCES[instance_idx % len(SEARXNG_INSTANCES)]

        try:
            resp = requests.get(
                f"{instance_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general",
                    "language": "en",
                },
                headers={"User-Agent": "JobRadar/1.0"},
                timeout=8,
                verify=False,
            )
            increment_quota("searxng")

            if resp.status_code != 200:
                # Try next instance
                instance_idx += 1
                continue

            data = resp.json()
            results = data.get("results", [])
            print(f">>> SearxNG: {len(results)} results for: {query[:60]}")

            for item in results[:10]:
                parsed = _parse_search_result(
                    item.get("title", ""),
                    item.get("url", ""),
                    item.get("content", ""),
                )
                if parsed:
                    all_jobs.append(parsed)

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"SearxNG error ({instance_url}): {e}")
            instance_idx += 1  # Rotate to next instance
            continue

    logger.info(f"SearxNG: fetched {len(all_jobs)} jobs from {min(len(queries), 6)} queries")
    return all_jobs


# ============================================================
# Layer 8: Yahoo Search Fallback
# ============================================================

def fetch_from_yahoo(queries, delay=1.5):
    """
    Scrape Yahoo Search results as fallback.
    Yahoo has weaker bot protection than Google.
    """
    import requests
    from bs4 import BeautifulSoup

    all_jobs = []

    for query in queries[:4]:  # Max 4 queries per refresh
        try:
            url = f"https://search.yahoo.com/search?p={quote_plus(query)}"
            resp = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=15,
                verify=False,
            )
            increment_quota("yahoo")

            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Yahoo organic results are in different possible containers
            results = soup.find_all("div", class_="algo-sr") or soup.find_all("div", class_="dd")

            for result in results[:10]:
                # Extract title and link
                title_el = result.find("h3")
                if not title_el:
                    title_el = result.find("a")
                if not title_el:
                    continue

                link_el = result.find("a", href=True)
                if not link_el:
                    continue

                title = title_el.get_text(strip=True)
                link = link_el.get("href", "")

                # Yahoo wraps URLs in redirects
                actual_url = _extract_yahoo_url(link)
                if not actual_url:
                    continue

                # Extract snippet
                snippet = ""
                snippet_el = result.find("p") or result.find("span", class_="fc-falcon")
                if snippet_el:
                    snippet = snippet_el.get_text(strip=True)[:300]

                parsed = _parse_search_result(title, actual_url, snippet)
                if parsed:
                    all_jobs.append(parsed)

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"Yahoo search error: {e}")
            continue

    logger.info(f"Yahoo: fetched {len(all_jobs)} jobs from {min(len(queries), 4)} queries")
    return all_jobs


def _extract_yahoo_url(yahoo_link):
    """Extract actual URL from Yahoo redirect."""
    # Yahoo redirect format: /RU=actual_url/RK=...
    match = re.search(r"RU=([^/]+)", yahoo_link)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))
    if yahoo_link.startswith("http"):
        return yahoo_link
    return None


# ============================================================
# Shared Search Result Parser
# ============================================================

def _parse_search_result(title, url, snippet=""):
    """Parse a search result into a job dict. Rejects non-job URLs."""
    if not title or not url:
        return None

    domain = ""
    try:
        domain = urlparse(url).hostname or ""
        domain = domain.replace("www.", "")
    except Exception:
        return None

    # Skip non-job domains
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

    # Skip non-job content
    skip_keywords = [
        "how to", "tutorial", "guide", "salary", "review",
        "interview questions", "vs ", "what is", "best ", "top 10",
        "course", "certification", "resume template",
    ]
    if any(kw in title_lower for kw in skip_keywords):
        return None

    # Reject aggregation pages
    if re.search(r"\d{2,}[+,]?\s*(?:full|java|react|spring|developer|engineer|software|backend|frontend)", title_lower):
        return None
    if re.search(r"(?:urgent|latest|new|top|best|apply)[\s!]*(?:full|java|react|developer|engineer|software|jobs)", title_lower):
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

    # Clean portal names from title/company
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
        "description_snippet": snippet[:300] if snippet else "",
        "posted_date": "",
    }


# ============================================================
# Query Builder for Search Engines
# ============================================================

def build_search_queries(profile_queries, sites=None, locations=None):
    """
    Build site-scoped search queries for SearxNG/Yahoo.
    Combines profile queries with site: operators and locations.
    """
    if sites is None:
        sites = ["naukri.com", "linkedin.com/jobs", "indeed.co.in"]

    search_queries = []
    seen = set()

    for q in profile_queries:
        query_text = q.get("query", q) if isinstance(q, dict) else q

        for site in sites:
            full_query = f"site:{site} {query_text}"
            if full_query.lower() not in seen:
                seen.add(full_query.lower())
                search_queries.append(full_query)

    return search_queries[:12]  # Cap total queries
