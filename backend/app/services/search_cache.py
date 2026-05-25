"""
JobRadar Search Cache
Caches API search results to prevent redundant calls within a TTL window.
Particularly useful for rate-limited sources (Adzuna, SerpApi, Jooble).

Usage:
    from app.services.search_cache import cache_get, cache_set, purge_expired

    cached = cache_get("adzuna", query, location="Pune", ttl_hours=6)
    if cached is not None:
        return cached          # [] is a valid cached result (empty page)

    results = _do_actual_fetch(query)
    cache_set("adzuna", query, results, location="Pune", ttl_hours=6)
"""
import json
import hashlib
import logging
from datetime import datetime, timedelta
from app.database import get_connection

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Key generation
# ──────────────────────────────────────────────

def _make_key(source: str, query: str, location: str = "") -> str:
    """Deterministic cache key — first 32 hex chars of SHA-256."""
    raw = f"{source}::{query.lower().strip()}::{location.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def cache_get(source: str, query: str, location: str = "", ttl_hours: int = 6):
    """
    Return cached results if a non-expired entry exists, else None.
    Note: returns [] (empty list) when the cache holds an empty result —
    that is intentional (empty = "we tried, found nothing").
    """
    try:
        key = _make_key(source, query, location)
        now_iso = datetime.utcnow().isoformat()

        with get_connection() as conn:
            row = conn.execute("""
                SELECT results_json FROM search_cache
                WHERE cache_key = ? AND expires_at > ?
            """, (key, now_iso)).fetchone()

        if row is None:
            return None  # cache miss

        return json.loads(row["results_json"])
    except Exception as e:
        logger.warning(f"search_cache.get error ({source}|{query[:40]}): {e}")
        return None  # treat errors as cache misses


def cache_set(
    source: str,
    query: str,
    results: list,
    location: str = "",
    ttl_hours: int = 6,
):
    """Persist results to cache with an expiry timestamp."""
    try:
        key = _make_key(source, query, location)
        now = datetime.utcnow()
        expires = now + timedelta(hours=ttl_hours)

        with get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO search_cache
                    (cache_key, source, query, location, results_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                key, source, query[:500], location[:100],
                json.dumps(results),
                now.isoformat(),
                expires.isoformat(),
            ))
            conn.commit()
    except Exception as e:
        logger.warning(f"search_cache.set error ({source}|{query[:40]}): {e}")


def purge_expired():
    """
    Delete all rows past their expiry. Run this as a maintenance task
    (e.g., once per day, or at the start of each full refresh).
    """
    try:
        now_iso = datetime.utcnow().isoformat()
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM search_cache WHERE expires_at < ?", (now_iso,)
            )
            conn.commit()
            deleted = cursor.rowcount
        if deleted:
            logger.info(f"search_cache: purged {deleted} expired entries")
    except Exception as e:
        logger.warning(f"search_cache.purge_expired error: {e}")


def get_cache_stats() -> dict:
    """Return cache statistics for the admin dashboard."""
    try:
        now_iso = datetime.utcnow().isoformat()
        with get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM search_cache").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM search_cache WHERE expires_at > ?", (now_iso,)
            ).fetchone()[0]
            by_source = conn.execute("""
                SELECT source, COUNT(*) as cnt
                FROM search_cache WHERE expires_at > ?
                GROUP BY source ORDER BY cnt DESC
            """, (now_iso,)).fetchall()
        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": total - active,
            "by_source": [dict(r) for r in by_source],
        }
    except Exception as e:
        logger.warning(f"search_cache.get_cache_stats error: {e}")
        return {}
