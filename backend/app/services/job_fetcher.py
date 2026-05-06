"""
JobRadar Job Fetcher
Implements the 6-layer fetching strategy with source routing.

Layer 1: Company career pages (direct scrape) — unlimited, free
Layer 2: Indeed RSS feeds — unlimited, free
Layer 3: Google Custom Search API — 100/day free
Layer 4: Bing Web Search API — 1000/month free
Layer 5: DuckDuckGo API — unlimited, free
Layer 6: Google scrape fallback — ~50-80 before block
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

# Quota limits
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
    Routes queries through the cheapest available source first.

    Args:
        profile: parsed resume profile dict
        config: Flask app config dict

    Returns:
        int: number of new jobs fetched
    """
    queries = generate_queries(profile)
    scrape_delay = config.get("SCRAPE_DELAY", 1.0)
    all_jobs = []

    # Layer 1: Company career pages (unlimited, free)
    logger.info("Layer 1: Fetching from company career pages...")
    career_jobs = _fetch_from_career_pages(profile, scrape_delay)
    all_jobs.extend(career_jobs)

    # Layer 2: Indeed RSS (unlimited, free)
    logger.info("Layer 2: Fetching from Indeed RSS...")
    rss_jobs = _fetch_from_indeed_rss(profile, scrape_delay)
    all_jobs.extend(rss_jobs)

    # Layer 3: Google Custom Search API (100/day)
    # Budget: max 8 calls per refresh → supports 12+ refreshes/day
    google_key = config.get("GOOGLE_CSE_API_KEY", "")
    google_cx = config.get("GOOGLE_CSE_CX", "")
    if google_key and google_cx:
        today_usage = get_quota_usage("google_cse")
        remaining = QUOTA_LIMITS["google_cse"] - today_usage
        if remaining > 0:
            logger.info(f"Layer 3: Google CSE ({remaining} calls remaining)...")
            # Only use Tier 1 + top Tier 2 queries, and only top 2 sites (naukri, linkedin)
            top_queries = [q for q in queries if q["tier"] <= 2][:3]
            top_sites = ["naukri.com", "linkedin.com/jobs"]
            site_queries = generate_site_queries(top_queries, top_sites)
            max_calls = min(8, remaining, len(site_queries))
            for sq in site_queries[:max_calls]:
                jobs = _fetch_from_google_cse(sq["site_query"], google_key, google_cx, scrape_delay)
                all_jobs.extend(jobs)
        else:
            logger.info("Layer 3: Google CSE quota exhausted, skipping.")

    # Layer 4: Bing Web Search API (1000/month)
    # Budget: max 6 calls per refresh
    bing_key = config.get("BING_API_KEY", "")
    if bing_key:
        today_usage = get_quota_usage("bing")
        remaining = QUOTA_LIMITS["bing"] - today_usage
        if remaining > 0:
            logger.info(f"Layer 4: Bing ({remaining} calls remaining)...")
            top_queries = [q for q in queries if q["tier"] <= 2][:3]
            site_queries = generate_site_queries(top_queries, ["indeed.co.in"])
            max_calls = min(6, remaining, len(site_queries))
            for sq in site_queries[:max_calls]:
                jobs = _fetch_from_bing(sq["site_query"], bing_key, scrape_delay)
                all_jobs.extend(jobs)
        else:
            logger.info("Layer 4: Bing quota exhausted, skipping.")

    # Layer 5: DuckDuckGo (unlimited, free)
    logger.info("Layer 5: Fetching from DuckDuckGo...")
    for q in queries[:4]:  # Limit to top 4 queries
        jobs = _fetch_from_duckduckgo(q["query"], scrape_delay)
        all_jobs.extend(jobs)

    # Layer 6: Google scrape fallback (if we didn't get enough results)
    if len(all_jobs) < 10:
        today_usage = get_quota_usage("google_scrape")
        remaining = QUOTA_LIMITS["google_scrape"] - today_usage
        if remaining > 0:
            logger.info(f"Layer 6: Google scrape fallback ({remaining} remaining)...")
            for q in queries[:3]:
                jobs = _fetch_from_google_scrape(q["query"], scrape_delay)
                all_jobs.extend(jobs)

    # Store new jobs in database
    new_count = _store_jobs(all_jobs)
    logger.info(f"Fetched {len(all_jobs)} total, {new_count} new jobs stored.")
    return new_count


# ============================================================
# Layer 1: Company Career Pages
# ============================================================

def _fetch_from_career_pages(profile, delay=1.0):
    """Scrape company career pages from the registry."""
    companies = execute_query(
        "SELECT * FROM company_sources WHERE enabled = 1",
        fetch_all=True,
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

    search_terms = [role] + core_skills[:2]
    jobs = []

    for company in companies:
        try:
            url = company["careers_url"]
            company_name = company["company_name"]

            # Try to fetch the career page and extract job links
            page_jobs = _scrape_career_page(url, company_name, search_terms, location)
            jobs.extend(page_jobs)

            # Update last_scraped timestamp
            execute_query(
                "UPDATE company_sources SET last_scraped = CURRENT_TIMESTAMP WHERE id = ?",
                (company["id"],),
            )

            time.sleep(delay)
        except Exception as e:
            logger.warning(f"Failed to scrape {company['company_name']}: {e}")
            continue

    increment_quota("direct_scrape")
    return jobs


def _scrape_career_page(url, company_name, search_terms, location):
    """
    Scrape a company career page for job listings.
    Most career pages are JS-rendered SPAs, so instead of trying to scrape
    individual job links (which usually fail), we generate direct search
    URLs that the user can click to see filtered results on the career page.
    """
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []

    search_lower = [t.lower() for t in search_terms]
    location_lower = location.lower() if location else ""

    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        text_lower = text.lower()
        href = link["href"]
        href_lower = href.lower()

        # Skip non-job links
        if len(text) < 8 or len(text) > 150:
            continue
        if any(skip in href_lower for skip in ["#", "javascript:", "mailto:", "login", "signup", "privacy", "terms", "contact", "about"]):
            continue

        # Build full URL
        full_url = href if href.startswith("http") else urljoin(url, href)

        # CRITICAL: Check if this is an actual job listing vs a navigation link
        if not _is_valid_job_url(full_url):
            continue

        # Must have a developer/engineer keyword in the link text
        has_dev_keyword = any(kw in text_lower for kw in [
            "developer", "engineer", "programmer", "architect", "analyst",
            "sde", "swe", "intern", "lead", "manager", "designer",
            "devops", "qa", "tester", "consultant",
        ])

        if not has_dev_keyword:
            continue

        # Extract location if visible near the link
        parent = link.parent
        loc_text = ""
        if parent:
            parent_text = parent.get_text(strip=True).lower()
            if location_lower and location_lower in parent_text:
                loc_text = location

        jobs.append({
            "title": text[:150],
            "company": company_name,
            "location": loc_text or location,
            "source_url": full_url,
            "source_domain": urlparse(url).hostname.replace("www.", "") if urlparse(url).hostname else "",
            "description_snippet": "",
            "posted_date": "",
        })

        if len(jobs) >= 10:  # Cap per company
            break

    return jobs


def _is_valid_job_url(url):
    """
    Check if a URL looks like an actual job listing page
    (not a homepage, search page, or navigation link).
    
    Valid job URLs typically have:
      - A job ID or slug in the path (e.g., /job/12345, /position/java-developer-pune)
      - Query parameters with job IDs (e.g., ?jobId=12345)
    
    Invalid URLs:
      - Career homepages (e.g., /careers, /jobs)
      - Search/listing pages (e.g., /search-jobs, /job-search)
      - Generic navigation (e.g., /about, /benefits)
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.lower().rstrip("/")
        query = parsed.query.lower()
    except Exception:
        return False

    path_parts = [p for p in path.split("/") if p]

    # ── Early accepts (before any rejection) ──

    # Known job-viewing paths with query params (e.g., indeed.co.in/viewjob?jk=...)
    job_view_paths = ["/viewjob", "/job-detail", "/jobdetail", "/job-view"]
    if any(path.startswith(p) for p in job_view_paths) and query:
        return True

    # URL has a job ID in query string (e.g., ?jk=abc, ?jobId=123)
    if re.search(r"(?:job|id|ref|position|jk|vjk|fccid)\w*=", query):
        return True

    # ── Rejections ──

    # Path is too short (likely a homepage)
    if len(path_parts) < 2:
        return False

    # Known navigation/listing patterns
    reject_paths = [
        "/careers", "/career", "/jobs", "/job-search", "/search-jobs",
        "/search", "/all-jobs", "/joblist", "/job-list", "/openings",
        "/opportunities", "/join-us", "/work-with-us", "/life-at",
        "/benefits", "/culture", "/about", "/teams", "/locations",
        "/hiring", "/recruitment", "/apply",
    ]
    if path in reject_paths:
        return False

    # Last segment is a generic listing/navigation keyword
    last_segment = path_parts[-1] if path_parts else ""
    reject_segments = [
        "jobs", "careers", "openings", "positions", "search",
        "results", "listings", "all", "index", "home",
        "collections", "recommended", "saved", "applied", "list",
    ]
    if last_segment in reject_segments and not query:
        return False

    # ── Accepts ──

    # Job ID in path (e.g., /job/12345)
    if re.search(r"/\d{4,}", path):
        return True

    # Slug pattern (e.g., /java-developer-pune)
    if re.search(r"/[a-z]+-[a-z]+-[a-z]+", path):
        return True

    # Deep path (3+ segments = likely specific page)
    if len(path_parts) >= 3:
        return True

    return False


# ============================================================
# Layer 2: Indeed RSS
# ============================================================

def _fetch_from_indeed_rss(profile, delay=1.0):
    """Fetch job listings from Indeed RSS feeds."""
    import requests

    rss_urls = generate_rss_urls(profile)
    jobs = []

    for url in rss_urls:
        try:
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (compatible; JobRadar/1.0)"
            })
            if resp.status_code != 200:
                continue

            # Parse RSS/XML
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
        # Fallback: manual XML parsing
        return _parse_rss_manual(xml_text)

    jobs = []
    for entry in feed.entries[:20]:  # Cap at 20 per feed
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        # Extract company from title (Indeed format: "Title - Company - Location")
        parts = title.split(" - ")
        job_title = parts[0].strip() if parts else title
        company = parts[1].strip() if len(parts) > 1 else ""
        location = parts[2].strip() if len(parts) > 2 else ""

        # Description
        desc = entry.get("summary", entry.get("description", ""))
        # Strip HTML tags
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()[:300]

        # Published date
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
    """Fallback RSS parser using regex (no feedparser dependency)."""
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
        # Handle CDATA
        cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>", content, re.DOTALL)
        if cdata:
            return cdata.group(1).strip()
        return content
    return ""


# ============================================================
# Layer 3: Google Custom Search API
# ============================================================

def _fetch_from_google_cse(query, api_key, cx, delay=1.0):
    """Fetch results from Google Custom Search JSON API."""
    import requests

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": 10,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        increment_quota("google_cse")

        if resp.status_code != 200:
            logger.warning(f"Google CSE returned {resp.status_code}")
            return []

        data = resp.json()
        items = data.get("items", [])

        jobs = []
        for item in items:
            title = item.get("title", "").strip()
            link = item.get("link", "").strip()
            snippet = item.get("snippet", "").strip()

            if not title or not link:
                continue

            # Parse job info from title and snippet
            parsed = _parse_search_result(title, link, snippet)
            if parsed:
                jobs.append(parsed)

        time.sleep(delay)
        return jobs

    except Exception as e:
        logger.warning(f"Google CSE error: {e}")
        return []


# ============================================================
# Layer 4: Bing Web Search API
# ============================================================

def _fetch_from_bing(query, api_key, delay=1.0):
    """Fetch results from Bing Web Search API."""
    import requests

    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": query, "count": 10, "mkt": "en-IN"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        increment_quota("bing")

        if resp.status_code != 200:
            logger.warning(f"Bing returned {resp.status_code}")
            return []

        data = resp.json()
        results = data.get("webPages", {}).get("value", [])

        jobs = []
        for item in results:
            title = item.get("name", "").strip()
            link = item.get("url", "").strip()
            snippet = item.get("snippet", "").strip()

            if not title or not link:
                continue

            parsed = _parse_search_result(title, link, snippet)
            if parsed:
                jobs.append(parsed)

        time.sleep(delay)
        return jobs

    except Exception as e:
        logger.warning(f"Bing error: {e}")
        return []


# ============================================================
# Layer 5: DuckDuckGo
# ============================================================

def _fetch_from_duckduckgo(query, delay=1.0):
    """
    Fetch results from DuckDuckGo.
    Uses the HTML search page since the Instant Answer API
    doesn't return web results for job queries.
    """
    import requests
    from bs4 import BeautifulSoup

    url = "https://html.duckduckgo.com/html/"
    data = {"q": f"{query} jobs", "kl": "in-en"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        resp = requests.post(url, data=data, headers=headers, timeout=15)
        increment_quota("duckduckgo")

        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.find_all("a", class_="result__a")

        jobs = []
        for result in results[:10]:
            title = result.get_text(strip=True)
            link = result.get("href", "")

            if not title or not link:
                continue

            # DuckDuckGo wraps URLs in a redirect
            actual_url = _extract_ddg_url(link)
            if not actual_url:
                continue

            # Get snippet
            snippet_el = result.find_parent("div")
            snippet = ""
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
    # DDG links look like: //duckduckgo.com/l/?uddg=ACTUAL_URL&...
    match = re.search(r"uddg=([^&]+)", ddg_link)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))

    # Sometimes it's a direct link
    if ddg_link.startswith("http"):
        return ddg_link

    return None


# ============================================================
# Layer 6: Google Scrape Fallback
# ============================================================

def _fetch_from_google_scrape(query, delay=1.0):
    """
    Scrape Google search results directly.
    Use sparingly — Google may CAPTCHA or block after 50-80 requests.
    """
    import requests
    from bs4 import BeautifulSoup

    url = "https://www.google.com/search"
    params = {"q": f"{query} jobs", "num": 10, "hl": "en"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        increment_quota("google_scrape")

        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []

        # Google search result divs
        for g in soup.find_all("div", class_="g"):
            link_el = g.find("a", href=True)
            if not link_el:
                continue

            href = link_el["href"]
            if not href.startswith("http"):
                continue

            title_el = g.find("h3")
            title = title_el.get_text(strip=True) if title_el else ""

            snippet_el = g.find("div", class_="VwiC3b")
            snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""

            if title:
                parsed = _parse_search_result(title, href, snippet)
                if parsed:
                    jobs.append(parsed)

        time.sleep(delay * 2)  # Extra delay for Google scraping
        return jobs

    except Exception as e:
        logger.warning(f"Google scrape error: {e}")
        return []


# ============================================================
# Shared Helpers
# ============================================================

def _parse_search_result(title, url, snippet=""):
    """
    Parse a search result into a normalized job dict.
    Extracts company, location, and domain from the result.
    Rejects non-job URLs (homepages, search pages, blog posts).
    """
    domain = urlparse(url).hostname or ""
    domain = domain.replace("www.", "")

    # Skip non-job domains
    skip_domains = ["youtube.com", "facebook.com", "twitter.com", "instagram.com",
                    "wikipedia.org", "quora.com", "reddit.com", "medium.com",
                    "stackoverflow.com", "github.com", "geeksforgeeks.org",
                    "glassdoor.com", "ambitionbox.com", "payscale.com",
                    "coursera.org", "udemy.com", "w3schools.com"]
    if any(sd in domain for sd in skip_domains):
        return None

    # Skip non-job title patterns
    title_lower = title.lower()
    skip_title_keywords = [
        "how to", "tutorial", "guide", "salary", "review", "interview questions",
        "vs ", "what is", "best ", "top 10", "course", "certification",
        "resume template", "cover letter",
    ]
    if any(kw in title_lower for kw in skip_title_keywords):
        return None

    # For job portal URLs, validate they point to specific listings
    job_portals = ["naukri.com", "indeed.co.in", "indeed.com", "linkedin.com"]
    is_portal = any(p in domain for p in job_portals)
    if is_portal and not _is_valid_job_url(url):
        return None

    # Try to extract company from title patterns
    company = ""
    job_title = title

    for sep in [" - ", " | ", " — ", " – "]:
        if sep in title:
            parts = title.split(sep)
            job_title = parts[0].strip()
            if len(parts) > 1:
                company = parts[1].strip()
            break

    # "at Company" pattern
    at_match = re.search(r"^(.+?)\s+at\s+(.+?)(?:\s*[\-|]|$)", title, re.IGNORECASE)
    if at_match and not company:
        job_title = at_match.group(1).strip()
        company = at_match.group(2).strip()

    # Clean up title — remove domain suffixes
    for suffix in ["| Naukri.com", "| Indeed", "| Indeed.com", "| LinkedIn",
                    "- LinkedIn", "- Naukri.com", "- Indeed.co.in",
                    "Naukri.com", "Indeed.co.in", "LinkedIn"]:
        job_title = job_title.replace(suffix, "").strip()
        company = company.replace(suffix, "").strip()

    # Remove trailing punctuation
    job_title = job_title.strip(" -|–—")
    company = company.strip(" -|–—")

    # Extract location from snippet
    location = ""
    loc_match = re.search(
        r"(?:location|city|place|in)\s*[:\-]?\s*([A-Z][a-z]+(?:\s*,\s*[A-Z][a-z]+)?)",
        snippet,
    )
    if loc_match:
        location = loc_match.group(1).strip()[:100]

    if not job_title or len(job_title) < 5:
        return None

    # Final check: title should look like a job role, not a page title
    has_role_word = any(kw in title_lower for kw in [
        "developer", "engineer", "architect", "analyst", "designer",
        "manager", "lead", "intern", "trainee", "consultant", "specialist",
        "administrator", "devops", "sre", "qa", "tester", "programmer",
        "sde", "swe", "full stack", "frontend", "backend",
    ])
    if not has_role_word:
        return None

    return {
        "title": job_title[:150],
        "company": company[:100],
        "location": location[:100],
        "source_url": url,
        "source_domain": domain,
        "description_snippet": snippet[:300],
        "posted_date": "",
    }


# ============================================================
# Database Storage
# ============================================================

def _store_jobs(jobs):
    """
    Store fetched jobs in the database.
    Skips duplicates based on source_url.
    Returns count of newly inserted jobs.
    """
    if not jobs:
        return 0

    new_count = 0

    with get_connection() as conn:
        for job in jobs:
            # Check for duplicate by URL
            existing = conn.execute(
                "SELECT id FROM jobs WHERE source_url = ?",
                (job["source_url"],)
            ).fetchone()

            if existing:
                continue

            try:
                conn.execute("""
                    INSERT INTO jobs (
                        title, company, location, source_url, source_domain,
                        description_snippet, posted_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
                """, (
                    job["title"],
                    job["company"],
                    job["location"],
                    job["source_url"],
                    job["source_domain"],
                    job["description_snippet"],
                    job.get("posted_date", ""),
                ))
                new_count += 1
            except Exception as e:
                logger.warning(f"Failed to insert job: {e}")
                continue

        conn.commit()

    return new_count
