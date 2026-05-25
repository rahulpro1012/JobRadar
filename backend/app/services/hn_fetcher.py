"""
JobRadar — HackerNews "Who is Hiring" Fetcher (Layer 7.6)
Parses the monthly "Ask HN: Who is hiring?" thread via the official Algolia HN API.

Free, no API key required, officially supported.
The thread is posted once per month so we cache results for 24 hours.

Algolia HN API docs: https://hn.algolia.com/api
"""
import re
import json
import logging
import requests
from app.services.ats_fetcher import ProfileFilter
from app.services.source_health import is_healthy, record_success, record_failure
from app.services.search_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

SOURCE_NAME = "hn_whoishiring"
HN_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search"
    "?tags=story,author_whoishiring&hitsPerPage=12"
)
HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{}"

# Cache the whole thread for 24 h — it only updates once a month
CACHE_TTL_HOURS = 24


def fetch_hn_jobs(profile: dict, delay: float = 0.5) -> list:
    """
    Fetch the latest HN Who is Hiring thread and extract India/Remote-eligible postings.

    Args:
        profile: Parsed user profile dict.
        delay:   Seconds between API calls (Algolia is lenient but be polite).

    Returns:
        List of normalised job dicts ready for DB insertion.
    """
    if not is_healthy(SOURCE_NAME):
        logger.info(f"[{SOURCE_NAME}] circuit open — skipping this refresh")
        return []

    pf = ProfileFilter(profile)

    # ── Step 1: Find the latest "Who is Hiring" thread ──
    story_id = _get_latest_thread_id()
    if not story_id:
        record_failure(SOURCE_NAME, "Could not find 'Who is Hiring' thread")
        return []

    # ── Step 2: Check cache before fetching comments ──
    cache_key_query = f"thread_{story_id}"
    cached_comments = cache_get(SOURCE_NAME, cache_key_query, ttl_hours=CACHE_TTL_HOURS)
    if cached_comments is None:
        comments = _fetch_thread_comments(story_id)
        if comments is None:
            record_failure(SOURCE_NAME, f"Failed to fetch thread {story_id}")
            return []
        cache_set(SOURCE_NAME, cache_key_query, comments, ttl_hours=CACHE_TTL_HOURS)
    else:
        comments = cached_comments
        logger.info(f"[{SOURCE_NAME}] using cached thread {story_id} ({len(comments)} comments)")

    # ── Step 3: Parse comments into jobs ──
    jobs = []
    skipped = 0

    for comment in comments:
        text_html = comment.get("text") or ""
        if not text_html:
            continue

        plain = _html_to_text(text_html)

        # Only keep comments that mention Remote, India, or Worldwide
        if not re.search(r"\b(remote|india|worldwide|anywhere)\b", plain, re.I):
            skipped += 1
            continue

        title = _extract_title(plain)
        company = _extract_company(plain)
        url = _extract_first_url(plain) or f"https://news.ycombinator.com/item?id={comment.get('id', '')}"

        keep, reason = pf.should_keep(title, plain)
        if not keep:
            skipped += 1
            continue

        jobs.append({
            "title": title[:150],
            "company": company[:100],
            "location": "Remote / Various",
            "source_url": url,
            "source_domain": "news.ycombinator.com",
            "description_snippet": plain[:300],
            "posted_date": comment.get("created_at") or "",
            "skills_found": json.dumps([]),
        })

    record_success(SOURCE_NAME, jobs_returned=len(jobs))
    logger.info(f"[{SOURCE_NAME}] {len(jobs)} kept, {skipped} skipped")
    return jobs


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_latest_thread_id() -> str | None:
    """Return the objectID of the most recent 'Ask HN: Who is hiring?' story."""
    try:
        resp = requests.get(HN_SEARCH_URL, timeout=10, verify=False)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        for hit in hits:
            if "ask hn: who is hiring" in hit.get("title", "").lower():
                return hit["objectID"]
    except Exception as e:
        logger.warning(f"[{SOURCE_NAME}] thread search error: {e}")
    return None


def _fetch_thread_comments(story_id: str) -> list | None:
    """Fetch all top-level comments from the thread."""
    try:
        resp = requests.get(
            HN_ITEM_URL.format(story_id), timeout=20, verify=False
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("children", [])
    except Exception as e:
        logger.warning(f"[{SOURCE_NAME}] thread fetch error for {story_id}: {e}")
    return None


def _html_to_text(html: str) -> str:
    """Convert HN comment HTML to plain text."""
    # Replace <p> and <br> with newlines first
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace(
        "&gt;", ">"
    ).replace("&quot;", '"').replace("&#x27;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_company(text: str) -> str:
    """
    HN hiring posts usually start with: "CompanyName | Location | Stack | REMOTE"
    Extract the first pipe-delimited segment as the company name.
    """
    first_line = text.split("\n")[0].strip()
    if "|" in first_line:
        candidate = first_line.split("|")[0].strip()
        # Sanity check: reasonable company name length
        if 1 < len(candidate) < 80:
            return candidate
    return "Unknown (HN)"


def _extract_title(text: str) -> str:
    """
    Try to extract a recognisable job title from the posting body.
    Falls back to a generic label if nothing matches.
    """
    patterns = [
        r"(senior|junior|lead|staff|principal)?\s*(software|backend|frontend|full[\-\s]?stack|devops|platform|data)\s*(engineer|developer|architect)",
        r"(java|python|react|node|go|rust|kotlin|scala)\s+(developer|engineer)",
        r"(engineering manager|tech lead|cto|vp of engineering)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(0).strip().title()
    return "Software Engineer (HN posting)"


def _extract_first_url(text: str) -> str | None:
    """Return the first HTTP(S) URL found in the text."""
    m = re.search(r"https?://[^\s\)\]\>\"]+", text)
    if m:
        return m.group(0).rstrip(".,);\"'")
    return None
