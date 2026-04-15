"""
JobRadar Deduplication Engine
Clusters identical jobs from different sources using fuzzy matching.
Keeps the best source and merges "also_on" metadata.
"""
import re
import json
import logging
from collections import defaultdict

from app.database import execute_query, get_connection

logger = logging.getLogger(__name__)

# Source priority (higher = preferred when deduplicating)
SOURCE_PRIORITY = {
    "careers": 10,      # Company career pages
    "naukri.com": 8,
    "linkedin.com": 7,
    "indeed.co.in": 6,
    "indeed.com": 6,
}


def deduplicate_jobs():
    """
    Find and cluster duplicate job listings across sources.
    Keeps the highest-priority source as primary and stores others in also_on.
    Returns the number of duplicates merged.
    """
    # Get all new/unprocessed jobs that haven't been clustered yet
    jobs = execute_query(
        "SELECT id, title, company, location, source_url, source_domain "
        "FROM jobs WHERE duplicate_cluster_id IS NULL AND status = 'new' "
        "ORDER BY id",
        fetch_all=True,
    )

    if len(jobs) < 2:
        return 0

    # Build clusters
    clusters = _build_clusters(jobs)

    # Merge duplicates
    merged_count = 0
    with get_connection() as conn:
        for cluster_id, cluster_jobs in enumerate(clusters):
            if len(cluster_jobs) < 2:
                # Single job — just mark it as clustered
                conn.execute(
                    "UPDATE jobs SET duplicate_cluster_id = ? WHERE id = ?",
                    (cluster_id, cluster_jobs[0]["id"]),
                )
                continue

            # Sort by source priority (highest first)
            cluster_jobs.sort(
                key=lambda j: _source_priority(j["source_domain"]),
                reverse=True,
            )

            # First job is the primary (best source)
            primary = cluster_jobs[0]
            duplicates = cluster_jobs[1:]

            # Collect "also on" sources from duplicates
            also_on = []
            for dup in duplicates:
                also_on.append({
                    "source": dup["source_domain"],
                    "url": dup["source_url"],
                })

            # Update primary job
            conn.execute(
                "UPDATE jobs SET duplicate_cluster_id = ?, also_on = ? WHERE id = ?",
                (cluster_id, json.dumps(also_on), primary["id"]),
            )

            # Archive duplicate jobs
            for dup in duplicates:
                conn.execute(
                    "UPDATE jobs SET duplicate_cluster_id = ?, status = 'archived' WHERE id = ?",
                    (cluster_id, dup["id"]),
                )
                merged_count += 1

        conn.commit()

    logger.info(f"Deduplicated: {merged_count} duplicates merged into clusters")
    return merged_count


def _build_clusters(jobs):
    """
    Group jobs into clusters of duplicates.
    Two jobs are considered duplicates if:
      - Company name similarity > 85%
      - Job title similarity > 80%
      - (Optional) Location matches
    """
    # Track which jobs have been assigned to a cluster
    assigned = set()
    clusters = []

    for i, job_a in enumerate(jobs):
        if job_a["id"] in assigned:
            continue

        cluster = [job_a]
        assigned.add(job_a["id"])

        for j in range(i + 1, len(jobs)):
            job_b = jobs[j]
            if job_b["id"] in assigned:
                continue

            if _is_duplicate(job_a, job_b):
                cluster.append(job_b)
                assigned.add(job_b["id"])

        clusters.append(cluster)

    return clusters


def _is_duplicate(job_a, job_b):
    """Check if two jobs are likely the same listing on different sources."""
    # Same source URL — definite duplicate
    if job_a["source_url"] == job_b["source_url"]:
        return True

    # Same source domain — less likely to be cross-source duplicates
    # (same portal usually doesn't list the same job twice)
    if job_a["source_domain"] == job_b["source_domain"]:
        return False

    # Compare company names
    company_a = _normalize_company(job_a.get("company", ""))
    company_b = _normalize_company(job_b.get("company", ""))

    if not company_a or not company_b:
        return False

    company_sim = _similarity(company_a, company_b)
    if company_sim < 0.75:
        return False

    # Compare job titles
    title_a = _normalize_title(job_a.get("title", ""))
    title_b = _normalize_title(job_b.get("title", ""))

    if not title_a or not title_b:
        return False

    title_sim = _similarity(title_a, title_b)
    if title_sim < 0.70:
        return False

    # If both company and title are similar enough, it's a duplicate
    combined = (company_sim * 0.4) + (title_sim * 0.6)
    return combined >= 0.78


def _normalize_company(name):
    """Normalize a company name for comparison."""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [
        "pvt ltd", "pvt. ltd.", "pvt. ltd", "private limited",
        "limited", "ltd", "ltd.", "inc", "inc.", "corp", "corp.",
        "corporation", "technologies", "technology", "tech",
        "solutions", "services", "consulting", "consultancy",
        "india", "global", "systems", "software",
        "(india)", "(p) ltd", "(p) ltd.",
    ]:
        name = name.replace(suffix, "")
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return name.strip()


def _normalize_title(title):
    """Normalize a job title for comparison."""
    if not title:
        return ""
    title = title.lower().strip()
    # Remove location info in parentheses
    title = re.sub(r"\(.*?\)", "", title)
    # Remove common noise words
    for word in ["urgent", "immediate", "hiring", "openings", "vacancy",
                 "opening", "requirement", "walk-in", "walkin"]:
        title = title.replace(word, "")
    title = re.sub(r"[^a-z0-9\s]", "", title)
    return title.strip()


def _similarity(str_a, str_b):
    """
    Compute similarity between two strings (0.0 to 1.0).
    Uses a simple token-overlap approach (Jaccard on words).
    Falls back to sequence matching for short strings.
    """
    if not str_a or not str_b:
        return 0.0

    if str_a == str_b:
        return 1.0

    # Token-based Jaccard similarity
    tokens_a = set(str_a.split())
    tokens_b = set(str_b.split())

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    jaccard = len(intersection) / len(union)

    # Also compute character-level overlap for short strings
    if len(str_a) < 30 or len(str_b) < 30:
        # Simple ratio: 2 * common_chars / total_chars
        from difflib import SequenceMatcher
        seq_ratio = SequenceMatcher(None, str_a, str_b).ratio()
        return max(jaccard, seq_ratio)

    return jaccard


def _source_priority(domain):
    """Get the priority score for a source domain."""
    if not domain:
        return 0
    domain = domain.lower()
    for key, priority in SOURCE_PRIORITY.items():
        if key in domain:
            return priority
    # Career pages get high priority
    if "career" in domain or "jobs" in domain:
        return 9
    return 5  # Default priority
