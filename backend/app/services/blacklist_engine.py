"""
JobRadar Blacklist Engine
Filters jobs against the multi-level blacklist (domain, company, keyword).
Runs after fetching but before scoring to avoid wasting computation.
"""
import re
import json
import logging

from app.database import execute_query, get_connection

logger = logging.getLogger(__name__)


def apply_blacklist():
    """
    Apply all blacklist rules to new/unfiltered jobs.
    Marks blocked jobs as 'archived' with a reason.
    Returns the number of jobs filtered out.

    Processing order:
    1. Domain check (exact match on source_domain)
    2. Company check (fuzzy match on company name)
    3. Keyword check (substring match on title + description)
    """
    # Load all blacklist entries
    blacklist = execute_query(
        "SELECT * FROM blacklist ORDER BY type",
        fetch_all=True,
    )
    if not blacklist:
        return 0

    # Organize by type
    blocked_domains = set()
    blocked_companies = set()
    blocked_keywords = set()

    for entry in blacklist:
        value = entry["value"].lower().strip()
        if entry["type"] == "domain":
            blocked_domains.add(value)
        elif entry["type"] == "company":
            blocked_companies.add(value)
        elif entry["type"] == "keyword":
            blocked_keywords.add(value)

    # Get all new jobs to check
    jobs = execute_query(
        "SELECT id, title, company, source_domain, description_snippet "
        "FROM jobs WHERE status = 'new'",
        fetch_all=True,
    )
    if not jobs:
        return 0

    filtered_count = 0
    blocked_ids = []

    for job in jobs:
        block_reason = _check_blacklist(
            job=job,
            blocked_domains=blocked_domains,
            blocked_companies=blocked_companies,
            blocked_keywords=blocked_keywords,
        )

        if block_reason:
            blocked_ids.append((job["id"], block_reason))
            filtered_count += 1

    # Archive blocked jobs
    if blocked_ids:
        with get_connection() as conn:
            for job_id, reason in blocked_ids:
                conn.execute(
                    "UPDATE jobs SET status = 'archived' WHERE id = ?",
                    (job_id,),
                )
            conn.commit()

    if filtered_count > 0:
        logger.info(f"Blacklist filtered {filtered_count} jobs")

    return filtered_count


def _check_blacklist(job, blocked_domains, blocked_companies, blocked_keywords):
    """
    Check a single job against all blacklist rules.
    Returns the block reason string, or None if the job passes.
    """
    # 1. Domain check (fastest — exact match)
    source_domain = (job.get("source_domain") or "").lower().strip()
    if source_domain:
        for blocked in blocked_domains:
            if blocked in source_domain or source_domain in blocked:
                return f"domain:{blocked}"

    # 2. Company check (fuzzy — handles variations)
    company = (job.get("company") or "").lower().strip()
    if company:
        company_normalized = _normalize_company(company)
        for blocked in blocked_companies:
            blocked_normalized = _normalize_company(blocked)
            if not blocked_normalized:
                continue
            # Check containment in both directions
            if (blocked_normalized in company_normalized
                    or company_normalized in blocked_normalized):
                return f"company:{blocked}"
            # Check word overlap for multi-word company names
            if _company_match(company_normalized, blocked_normalized):
                return f"company:{blocked}"

    # 3. Keyword check (substring on title + description)
    searchable_text = (
        (job.get("title") or "") + " " + (job.get("description_snippet") or "")
    ).lower()

    if searchable_text.strip():
        for keyword in blocked_keywords:
            if keyword in searchable_text:
                return f"keyword:{keyword}"

    return None


def _normalize_company(name):
    """Normalize a company name for blacklist matching."""
    if not name:
        return ""
    name = name.lower().strip()
    for suffix in [
        "pvt ltd", "pvt. ltd.", "pvt. ltd", "private limited",
        "limited", "ltd", "ltd.", "inc", "inc.", "corp",
        "technologies", "technology", "tech",
        "solutions", "services", "consulting",
        "india", "global", "systems", "software",
    ]:
        name = name.replace(suffix, "")
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return name.strip()


def _company_match(company_a, company_b):
    """
    Check if two company names match loosely.
    Uses word overlap — if 80%+ of words match, it's a match.
    """
    words_a = set(company_a.split())
    words_b = set(company_b.split())

    if not words_a or not words_b:
        return False

    # Use the shorter name's words as the reference
    shorter = words_a if len(words_a) <= len(words_b) else words_b
    longer = words_b if shorter is words_a else words_a

    if not shorter:
        return False

    overlap = shorter & longer
    ratio = len(overlap) / len(shorter)

    return ratio >= 0.8


def check_single_job(job, blacklist_entries=None):
    """
    Check a single job dict against the blacklist.
    Useful for real-time filtering in the fetcher before storing.

    Args:
        job: dict with title, company, source_domain, description_snippet
        blacklist_entries: list of dicts (pre-loaded), or None to load from DB

    Returns:
        True if the job should be blocked, False if it passes.
    """
    if blacklist_entries is None:
        blacklist_entries = execute_query(
            "SELECT * FROM blacklist",
            fetch_all=True,
        )

    blocked_domains = set()
    blocked_companies = set()
    blocked_keywords = set()

    for entry in blacklist_entries:
        value = entry["value"].lower().strip()
        if entry["type"] == "domain":
            blocked_domains.add(value)
        elif entry["type"] == "company":
            blocked_companies.add(value)
        elif entry["type"] == "keyword":
            blocked_keywords.add(value)

    reason = _check_blacklist(
        job=job,
        blocked_domains=blocked_domains,
        blocked_companies=blocked_companies,
        blocked_keywords=blocked_keywords,
    )
    return reason is not None
