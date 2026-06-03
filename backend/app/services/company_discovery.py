"""
JobRadar — Persistent Company Discovery
Auto-grows the ATS company registry by probing companies found in search results.

How it works:
1. When a job is fetched from search results, extract the company name
2. Try to find that company on known ATS platforms (Greenhouse, Lever, Ashby, Workable)
3. If found, persist to company_registry table for future direct ATS fetches
4. Idempotent: duplicate discoveries are silently ignored

Expected growth: 5-10 new companies per refresh cycle
Effect after 2-3 months: ATS coverage becomes significantly broader

Usage:
    # Call after fetching jobs from search sources
    for job in search_results:
        if job["source"] in ("search", "searxng", "linkedin_guest"):
            discover_company(job["company"])  # Fire-and-forget
"""
import logging
import requests
import time
from datetime import datetime
from urllib.parse import urlparse
from app.database import get_connection

logger = logging.getLogger(__name__)

# ── ATS API Endpoint Patterns ──
ATS_PROBES = {
    "greenhouse": lambda slug: f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": lambda slug: f"https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": lambda slug: f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "workable": lambda slug: f"https://apply.workable.com/api/v1/widget/accounts/{slug}",
}

# Request timeout
REQUEST_TIMEOUT = 8


def discover_company(company_name: str, background: bool = True) -> str:
    """
    Probe company across ATS platforms and persist if found.

    Args:
        company_name: Human-readable company name (e.g., "Acme Inc")
        background: If True, log discovery but don't block (async pattern).
                    If False, return ATS name immediately.

    Returns:
        ATS name if found ("greenhouse", "lever", "ashby", "workable"), or empty string.
    """
    if not company_name or not isinstance(company_name, str):
        return ""

    slug = _to_slug(company_name)
    if not slug or len(slug) < 2:
        return ""

    try:
        conn = get_connection()
        # Skip if already discovered
        row = conn.execute(
            "SELECT ats FROM company_registry WHERE slug = ?",
            (slug,)
        ).fetchone()

        if row:
            logger.debug(f"[discovery] {company_name} already registered on {row['ats']}")
            return row["ats"]
    except Exception as e:
        logger.debug(f"[discovery] DB check failed: {e}")
        return ""

    # Try each ATS in priority order (most popular first)
    ats_order = ["greenhouse", "lever", "ashby", "workable"]

    for ats in ats_order:
        try:
            url_fn = ATS_PROBES[ats]
            url = url_fn(slug)

            resp = requests.get(url, timeout=REQUEST_TIMEOUT, verify=False)

            # Status 200 + has jobs = found
            if resp.status_code == 200:
                if _has_jobs(resp.json(), ats):
                    _persist_discovery(slug, company_name, ats)
                    logger.info(f"[discovery] Found {company_name} on {ats}")
                    return ats
        except requests.Timeout:
            continue
        except Exception:
            continue

    logger.debug(f"[discovery] {company_name} not found on any ATS")
    return ""


def discover_company_batch(job_list: list, batch_delay: float = 0.1) -> int:
    """
    Discover companies from a batch of jobs (with small delays between probes).

    Args:
        job_list: List of job dicts with 'company' field.
        batch_delay: Seconds between probes (default 0.1s = minimal impact).

    Returns:
        Count of newly discovered companies.
    """
    discovered = 0
    seen = set()

    for job in job_list:
        company = job.get("company", "").strip()
        if not company or company in seen:
            continue

        seen.add(company)

        if discover_company(company):
            discovered += 1
            time.sleep(batch_delay)

    return discovered


def get_discovered_companies(limit: int = 50) -> list:
    """
    Get recently discovered companies from registry.

    Returns:
        List of dicts: {slug, name, ats, discovered_at, job_count}
    """
    try:
        conn = get_connection()
        rows = conn.execute("""
            SELECT slug, name, ats, discovered_at, job_count
            FROM company_registry
            WHERE discovered_at IS NOT NULL
            ORDER BY discovered_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"[discovery] failed to fetch discovered companies: {e}")
        return []


def _to_slug(name: str) -> str:
    """
    Convert company name to ATS slug format.

    Examples:
    - "Acme Inc" → "acme-inc"
    - "Company, Inc." → "company-inc"
    - "  Spaces  " → "spaces"
    """
    if not name:
        return ""

    slug = (
        name.lower()
        .strip()
        .replace(" ", "-")
        .replace(",", "")
        .replace(".", "")
        .replace("&", "and")
        .replace("_", "-")
    )

    # Remove consecutive dashes
    while "--" in slug:
        slug = slug.replace("--", "-")

    # Remove leading/trailing dashes
    slug = slug.strip("-")

    return slug


def _has_jobs(response_data, ats: str) -> bool:
    """
    Check if API response contains at least one job listing.

    Different ATS APIs return different structures.
    """
    if not response_data:
        return False

    if ats == "greenhouse":
        return bool(response_data.get("jobs"))

    elif ats == "lever":
        # Lever returns array of postings
        return isinstance(response_data, list) and len(response_data) > 0

    elif ats == "ashby":
        return bool(response_data.get("jobs"))

    elif ats == "workable":
        return bool(response_data.get("jobs"))

    return False


def _persist_discovery(slug: str, company_name: str, ats: str) -> None:
    """
    Save discovered company to registry (idempotent via INSERT OR IGNORE).
    """
    try:
        conn = get_connection()
        conn.execute("""
            INSERT OR IGNORE INTO company_registry
            (slug, name, ats, discovered_at)
            VALUES (?, ?, ?, ?)
        """, (slug, company_name, ats, datetime.utcnow().isoformat()))
        conn.commit()
        logger.debug(f"[discovery] Persisted {company_name} ({ats})")
    except Exception as e:
        logger.warning(f"[discovery] Failed to persist {company_name}: {e}")


def reset_discovery_history(before_days: int = 30) -> int:
    """
    Clear discovery history for companies discovered >N days ago.
    Useful for cleanup/testing.

    Returns:
        Number of records deleted.
    """
    try:
        conn = get_connection()
        from datetime import timedelta

        cutoff = (datetime.utcnow() - timedelta(days=before_days)).isoformat()

        cursor = conn.execute("""
            DELETE FROM company_registry
            WHERE discovered_at < ? AND discovered_at IS NOT NULL
        """, (cutoff,))

        count = cursor.rowcount
        conn.commit()

        logger.info(f"[discovery] Reset {count} discoveries older than {before_days} days")
        return count
    except Exception as e:
        logger.warning(f"[discovery] Reset failed: {e}")
        return 0
