"""
JobRadar Source Health — Circuit Breaker
Tracks per-source success/failure rates and automatically disables
unhealthy sources for a cool-down period to prevent wasted API calls.

Usage in any fetcher:
    from app.services.source_health import record_success, record_failure, is_healthy

    if not is_healthy("my_source"):
        return []
    try:
        ... fetch ...
        record_success("my_source", jobs_returned=len(jobs))
    except Exception as e:
        record_failure("my_source", str(e))
        return []
"""
import logging
from datetime import datetime, timedelta
from app.database import get_connection

logger = logging.getLogger(__name__)

# Number of consecutive failures before opening the circuit
FAILURE_THRESHOLD = 3
# How long to keep the circuit open (minutes)
CIRCUIT_OPEN_MINUTES = 60


def is_healthy(source: str) -> bool:
    """
    Return True if the source is currently usable.
    Call this as a gate before making any request.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT status, disabled_until FROM source_health WHERE source = ?",
                (source,)
            ).fetchone()

        if row is None:
            return True  # never used → assume healthy

        disabled_until = row["disabled_until"]
        if disabled_until:
            try:
                cutoff = datetime.fromisoformat(disabled_until)
                if cutoff > datetime.utcnow():
                    logger.debug(f"[{source}] circuit open until {disabled_until}, skipping")
                    return False
            except (ValueError, TypeError):
                pass

        return row["status"] != "unhealthy"
    except Exception as e:
        logger.warning(f"source_health.is_healthy error for {source}: {e}")
        return True  # fail open — don't block a source due to a DB error


def record_success(source: str, jobs_returned: int = 0):
    """Call after a successful fetch. Resets failure counter and re-closes the circuit."""
    try:
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO source_health
                    (source, status, consecutive_failures, last_success_at,
                     total_calls, jobs_returned_last_run, disabled_until)
                VALUES (?, 'healthy', 0, ?, 1, ?, NULL)
                ON CONFLICT(source) DO UPDATE SET
                    status                 = 'healthy',
                    consecutive_failures   = 0,
                    last_success_at        = excluded.last_success_at,
                    total_calls            = total_calls + 1,
                    jobs_returned_last_run = excluded.jobs_returned_last_run,
                    disabled_until         = NULL
            """, (source, now, jobs_returned))

            conn.execute("""
                INSERT INTO source_health_log (source, event_type, jobs_returned)
                VALUES (?, 'success', ?)
            """, (source, jobs_returned))

            conn.commit()
        logger.debug(f"[{source}] success recorded — {jobs_returned} jobs returned")
    except Exception as e:
        logger.warning(f"source_health.record_success error for {source}: {e}")


def record_failure(source: str, reason: str):
    """
    Call after a fetch error (HTTP error, timeout, parse error, etc.).
    After FAILURE_THRESHOLD consecutive failures the circuit opens for
    CIRCUIT_OPEN_MINUTES, skipping the source on all subsequent refreshes.
    """
    try:
        now = datetime.utcnow()
        now_iso = now.isoformat()
        disabled_until_iso = (now + timedelta(minutes=CIRCUIT_OPEN_MINUTES)).isoformat()

        with get_connection() as conn:
            # Upsert the health row
            conn.execute("""
                INSERT INTO source_health
                    (source, status, consecutive_failures, last_failure_at,
                     last_failure_reason, total_calls, total_failures)
                VALUES (?, 'degraded', 1, ?, ?, 1, 1)
                ON CONFLICT(source) DO UPDATE SET
                    consecutive_failures  = consecutive_failures + 1,
                    last_failure_at       = excluded.last_failure_at,
                    last_failure_reason   = excluded.last_failure_reason,
                    total_calls           = total_calls + 1,
                    total_failures        = total_failures + 1,
                    status = CASE
                        WHEN consecutive_failures + 1 >= ? THEN 'unhealthy'
                        ELSE 'degraded'
                    END,
                    disabled_until = CASE
                        WHEN consecutive_failures + 1 >= ? THEN ?
                        ELSE disabled_until
                    END
            """, (
                source, now_iso, reason,
                FAILURE_THRESHOLD,
                FAILURE_THRESHOLD, disabled_until_iso,
            ))

            conn.execute("""
                INSERT INTO source_health_log (source, event_type, detail)
                VALUES (?, 'failure', ?)
            """, (source, reason[:500]))

            conn.commit()

        logger.warning(f"[{source}] failure recorded — {reason[:120]}")
    except Exception as e:
        logger.warning(f"source_health.record_failure error for {source}: {e}")


def get_all_health() -> list:
    """
    Return a list of health dicts for all tracked sources.
    Used by the /api/admin/source-health endpoint.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    source,
                    status,
                    consecutive_failures,
                    last_success_at,
                    last_failure_at,
                    last_failure_reason,
                    total_calls,
                    total_failures,
                    jobs_returned_last_run,
                    disabled_until,
                    CASE
                        WHEN total_calls > 0 THEN
                            ROUND(100.0 * (total_calls - total_failures) / total_calls, 1)
                        ELSE NULL
                    END AS success_rate
                FROM source_health
                ORDER BY
                    CASE status
                        WHEN 'unhealthy' THEN 0
                        WHEN 'degraded'  THEN 1
                        ELSE 2
                    END,
                    source
            """).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"source_health.get_all_health error: {e}")
        return []


def reset_circuit(source: str):
    """
    Manually re-open a circuit that was disabled.
    Can be called from an admin endpoint if needed.
    """
    try:
        with get_connection() as conn:
            conn.execute("""
                UPDATE source_health
                SET status = 'healthy', consecutive_failures = 0, disabled_until = NULL
                WHERE source = ?
            """, (source,))
            conn.execute("""
                INSERT INTO source_health_log (source, event_type, detail)
                VALUES (?, 'circuit_close', 'manual reset')
            """, (source,))
            conn.commit()
        logger.info(f"[{source}] circuit manually reset to healthy")
    except Exception as e:
        logger.warning(f"source_health.reset_circuit error for {source}: {e}")
