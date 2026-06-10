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

Parallelization (Patch 2):
    # Call discover_companies_batch for ~25 candidates at refresh time
    results = discover_companies_batch(candidate_names, max_workers=8)
"""
import logging
import requests
import time
from datetime import datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Garbage data blacklist (Issue 1: Company Discovery Garbage Data)
LOCATION_BLACKLIST = {
    'pune', 'bengaluru', 'delhi', 'mumbai', 'bangalore',
    'india', 'remote', 'worldwide', 'global', 'international',
    'onsite', 'hybrid', 'across', 'various', 'multiple'
}


def _is_valid_company_name(name: str) -> bool:
    """
    Sanity filter to reject garbage company names from discovery feed.

    Rejects:
    - Names with punctuation indicating concatenation (locations, job titles)
    - Obvious location names (Pune, Bengaluru, Delhi, etc.)
    - Very short or very long names

    Keeps: Legitimate company names like "Razorpay", "BCforward", "3M"
    """
    if not name or len(name) < 2 or len(name) > 60:
        return False

    name_lower = name.lower()

    # Reject obvious locations
    if name_lower in LOCATION_BLACKLIST:
        return False

    # Reject multi-part strings (location + description: "Location, Role 6-8 years")
    if any(p in name for p in [",", "(", ")", "/"]):
        return False

    return True


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

    # Issue 1: Reject garbage names (locations, concatenated strings)
    if not _is_valid_company_name(company_name):
        logger.debug(f"[discovery] Rejected garbage company name: {company_name}")
        return ""

    slug = _to_slug(company_name)
    if not slug or len(slug) < 2:
        return ""

    try:
        with get_connection() as conn:
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

    # Patch 2: Probe all 4 ATSes concurrently
    ats_list = ["greenhouse", "lever", "ashby", "workable"]

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix=f"probe-{slug[:10]}") as executor:
        futures = {
            executor.submit(_probe_ats, ats, slug): ats
            for ats in ats_list
        }
        for future in as_completed(futures):
            ats = futures[future]
            try:
                job_count = future.result(timeout=8)
                if job_count is not None:
                    # Found! Persist and return immediately
                    _persist_discovery(slug, company_name, ats, job_count)
                    if job_count > 0:
                        logger.info(f"[discovery] Found {company_name} on {ats} with {job_count} jobs")
                    else:
                        logger.debug(f"[discovery] Found {company_name} on {ats} (no current jobs)")
                    return ats
            except Exception:
                continue

    logger.debug(f"[discovery] {company_name} not found on any ATS")
    return ""


def _probe_ats(ats: str, slug: str) -> int | None:
    """
    Probe a single ATS for a company slug. Returns job count if found (including 0),
    None if not found (404).

    Patch 2: Helper for parallel ATS discovery.
    """
    try:
        url_fn = ATS_PROBES[ats]
        url = url_fn(slug)

        resp = requests.get(url, timeout=REQUEST_TIMEOUT, verify=False)

        # Issue 2: Distinguish 0-jobs (status 200, empty response) from 404 (not found)
        if resp.status_code == 200:
            data = resp.json()
            job_count = _count_jobs(data, ats)
            return job_count  # Found (0 or more jobs)

        # 404 or other error = not found
        return None
    except requests.Timeout:
        return None
    except Exception:
        return None


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


def discover_companies_batch_parallel(candidate_names: list, max_workers: int = 8) -> dict:
    """Patch 2: Probe many candidate company names in parallel.

    Each candidate is probed across all 4 ATSes (Greenhouse, Lever, Ashby, Workable).
    Returns: {"discovered": int, "rejected": int, "persisted": list[str]}

    Args:
        candidate_names: List of company names to probe.
        max_workers: Number of parallel probing threads (default 8).
    """
    if not candidate_names:
        return {"discovered": 0, "rejected": 0, "persisted": []}

    # Filter garbage names BEFORE spending HTTP calls
    valid = [n for n in candidate_names if _is_valid_company_name(n)]
    rejected = len(candidate_names) - len(valid)
    if rejected:
        logger.debug(f"[discovery] Pre-filter rejected {rejected} garbage names")

    if not valid:
        return {"discovered": 0, "rejected": rejected, "persisted": []}

    logger.info(f"[discovery] Probing {len(valid)} candidates with {max_workers} parallel workers")

    persisted = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="discovery") as executor:
        future_to_name = {
            executor.submit(discover_company, name): name
            for name in valid
        }

        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result = future.result(timeout=15)
                if result:
                    persisted.append(result)
            except Exception as e:
                logger.debug(f"[discovery] {name} failed: {e}")

    logger.info(f"[discovery] Found {len(persisted)} new companies (out of {len(valid)} probed)")
    return {
        "discovered": len(persisted),
        "rejected": rejected,
        "persisted": persisted,
    }


def get_discovered_companies(limit: int = 50) -> list:
    """
    Get recently discovered companies from registry.

    Returns:
        List of dicts: {slug, name, ats, discovered_at, job_count}
    """
    try:
        with get_connection() as conn:
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


def _count_jobs(response_data, ats: str) -> int:
    """
    Count jobs in API response.

    Issue 2: Used to distinguish "exists with 0 jobs" from "doesn't exist".
    Different ATS APIs return different structures.
    """
    if not response_data:
        return 0

    if ats == "greenhouse":
        jobs = response_data.get("jobs", [])
        return len(jobs) if isinstance(jobs, list) else 0

    elif ats == "lever":
        # Lever returns array of postings
        return len(response_data) if isinstance(response_data, list) else 0

    elif ats == "ashby":
        jobs = response_data.get("jobs", [])
        return len(jobs) if isinstance(jobs, list) else 0

    elif ats == "workable":
        jobs = response_data.get("jobs", [])
        return len(jobs) if isinstance(jobs, list) else 0

    return 0


def _has_jobs(response_data, ats: str) -> bool:
    """
    Check if API response contains at least one job listing.

    Different ATS APIs return different structures.
    """
    return _count_jobs(response_data, ats) > 0


def _persist_discovery(slug: str, company_name: str, ats: str, job_count: int = 0) -> None:
    """
    Save discovered company to registry (idempotent via INSERT OR IGNORE).

    Issue 2: Tracks job_count to distinguish "exists with 0 jobs" from "doesn't exist".
    Also updates job_count on re-discovery for existing companies.
    """
    try:
        with get_connection() as conn:
            # Try insert first (new company)
            cursor = conn.execute("""
                INSERT OR IGNORE INTO company_registry
                (slug, name, ats, discovered_at, job_count, last_checked)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (slug, company_name, ats, datetime.utcnow().isoformat(), job_count, datetime.utcnow().isoformat()))

            # If insert did nothing (already exists), update job_count
            if cursor.rowcount == 0:
                conn.execute("""
                    UPDATE company_registry
                    SET job_count = ?, last_checked = ?
                    WHERE slug = ?
                """, (job_count, datetime.utcnow().isoformat(), slug))

            conn.commit()
            logger.debug(f"[discovery] Persisted {company_name} ({ats}) with {job_count} jobs")
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
        with get_connection() as conn:
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
