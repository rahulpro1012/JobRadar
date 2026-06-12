"""Jobs API routes — AI-enhanced with location awareness."""
import json
import logging
from flask import Blueprint, request, jsonify
from app.database import execute_query, get_connection

jobs_bp = Blueprint("jobs", __name__)
logger = logging.getLogger(__name__)


@jobs_bp.route("/jobs", methods=["GET"])
def get_jobs():
    status = request.args.get("status")
    min_score = request.args.get("min_score", type=int)
    source = request.args.get("source")
    days = request.args.get("days", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    include_dismissed = request.args.get("include_dismissed", "false").lower() == "true"
    via_email = request.args.get("via_email", "false").lower() == "true"

    conditions, params = [], []

    if status and status != "all":
        conditions.append("j.status = ?"); params.append(status)
    if min_score is not None:
        conditions.append("j.adjusted_score >= ?"); params.append(min_score)
    if source:
        conditions.append("j.source_domain LIKE ?"); params.append(f"%{source}%")
    if days:
        conditions.append("j.fetched_date >= datetime('now', ?)"); params.append(f"-{days} days")
    if via_email:
        conditions.append("j.via_email = 1")
    # Dismiss feature: hide dismissed jobs unless explicitly requested
    if not include_dismissed:
        conditions.append("j.dismissed_at IS NULL")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * per_page

    # Count is unaffected by the LEFT JOIN (job_ai_analysis is 1:0..1 on job_id)
    count_result = execute_query(f"SELECT COUNT(*) as total FROM jobs j {where}", params, fetch_one=True)
    total = count_result["total"] if count_result else 0

    # C1: LEFT JOIN structured analysis so reasons/flags arrive with the list.
    # fit_summary aliased to ai_fit_summary to avoid confusion with jobs.ai_reason.
    jobs = execute_query(
        f"""SELECT j.*,
                   a.apply_reasons, a.skip_reasons, a.red_flags,
                   a.fit_summary AS ai_fit_summary, a.analyzed_at
            FROM jobs j
            LEFT JOIN job_ai_analysis a ON a.job_id = j.id
            {where}
            ORDER BY j.adjusted_score DESC, j.fetched_date DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset], fetch_all=True
    )

    return jsonify({
        "jobs": jobs,
        "pagination": {"page": page, "per_page": per_page, "total": total,
                        "pages": (total + per_page - 1) // per_page}
    })


@jobs_bp.route("/jobs/<int:job_id>", methods=["GET"])
def get_job(job_id):
    job = execute_query(
        """SELECT j.*,
                  a.apply_reasons, a.skip_reasons, a.red_flags,
                  a.fit_summary AS ai_fit_summary, a.analyzed_at
           FROM jobs j
           LEFT JOIN job_ai_analysis a ON a.job_id = j.id
           WHERE j.id = ?""",
        (job_id,), fetch_one=True
    )
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@jobs_bp.route("/jobs/<int:job_id>/analysis", methods=["GET"])
def get_job_analysis(job_id):
    """C1: Get structured AI analysis with reasoning for a job."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM job_ai_analysis WHERE job_id = ?", (job_id,)
        ).fetchone()

    if not row:
        return jsonify({"analysis": None}), 200

    analysis = {
        "job_id": row["job_id"],
        "score": row["ai_score"],
        "apply_reasons": json.loads(row["apply_reasons"] or "[]"),
        "skip_reasons": json.loads(row["skip_reasons"] or "[]"),
        "fit_summary": row["fit_summary"],
        "red_flags": json.loads(row["red_flags"] or "[]"),
        "analyzed_at": row["analyzed_at"],
    }
    return jsonify({"analysis": analysis}), 200


# ============================================================
# Dismiss feature (Phase 1): single + bulk dismiss/undismiss
# ============================================================

@jobs_bp.route("/jobs/<int:job_id>/dismiss", methods=["POST"])
def dismiss_job(job_id):
    """Mark a single job as dismissed (hidden from default views)."""
    from datetime import datetime as _dt
    now = _dt.utcnow().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE jobs SET dismissed_at = ? WHERE id = ? AND dismissed_at IS NULL",
            (now, job_id),
        )
        conn.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "Job not found or already dismissed"}), 404
    return jsonify({"success": True, "job_id": job_id, "dismissed_at": now}), 200


@jobs_bp.route("/jobs/<int:job_id>/undismiss", methods=["POST"])
def undismiss_job(job_id):
    """Restore a dismissed job (used by undo)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE jobs SET dismissed_at = NULL WHERE id = ?", (job_id,)
        )
        conn.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"success": True, "job_id": job_id}), 200


@jobs_bp.route("/jobs/bulk-dismiss", methods=["POST"])
def bulk_dismiss_jobs():
    """Dismiss multiple jobs at once. Body: {"job_ids": [1, 2, 3]}"""
    data = request.get_json() or {}
    job_ids = data.get("job_ids", [])
    if not job_ids or not isinstance(job_ids, list):
        return jsonify({"error": "job_ids must be a non-empty list"}), 400
    if len(job_ids) > 200:
        return jsonify({"error": "Maximum 200 jobs per bulk operation"}), 400
    try:
        job_ids = [int(j) for j in job_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "All job_ids must be integers"}), 400

    from datetime import datetime as _dt
    now = _dt.utcnow().isoformat()
    placeholders = ",".join("?" * len(job_ids))
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE jobs SET dismissed_at = ? "
            f"WHERE id IN ({placeholders}) AND dismissed_at IS NULL",
            [now] + job_ids,
        )
        conn.commit()
    return jsonify({
        "success": True,
        "dismissed_count": cur.rowcount,
        "requested_count": len(job_ids),
        "job_ids": job_ids,
    }), 200


@jobs_bp.route("/jobs/bulk-undismiss", methods=["POST"])
def bulk_undismiss_jobs():
    """Undo a bulk dismiss. Body: {"job_ids": [1, 2, 3]}"""
    data = request.get_json() or {}
    job_ids = data.get("job_ids", [])
    if not job_ids or not isinstance(job_ids, list):
        return jsonify({"error": "job_ids required"}), 400
    try:
        job_ids = [int(j) for j in job_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "All job_ids must be integers"}), 400

    placeholders = ",".join("?" * len(job_ids))
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE jobs SET dismissed_at = NULL WHERE id IN ({placeholders})",
            job_ids,
        )
        conn.commit()
    return jsonify({"success": True, "undismissed_count": cur.rowcount, "job_ids": job_ids}), 200


# ============================================================
# Retention + manual job-table management
# ============================================================

@jobs_bp.route("/jobs/retention", methods=["GET"])
def get_retention():
    """Get the auto-cleanup retention window (days)."""
    from app.database import get_setting
    try:
        days = int(get_setting("retention_days", 15))
    except (TypeError, ValueError):
        days = 15
    return jsonify({"retention_days": days})


@jobs_bp.route("/jobs/retention", methods=["PUT"])
def set_retention():
    """Set the auto-cleanup retention window (days). 0 disables auto-purge."""
    from app.database import set_setting
    data = request.get_json() or {}
    try:
        days = int(data.get("retention_days"))
    except (TypeError, ValueError):
        return jsonify({"error": "retention_days must be an integer"}), 400
    if days < 0 or days > 365:
        return jsonify({"error": "retention_days must be between 0 and 365"}), 400
    set_setting("retention_days", days)
    return jsonify({"retention_days": days})


@jobs_bp.route("/jobs/purge", methods=["POST"])
def purge_jobs_endpoint():
    """Manual purge. Body one of:
       {"older_than_days": N} | {"status": "..."} | {"source": "..."} | {"all": true, "confirm": true}
    """
    from app.services.job_fetcher import purge_jobs
    data = request.get_json() or {}

    if data.get("all"):
        if not data.get("confirm"):
            return jsonify({"error": "Clearing ALL jobs requires confirm: true"}), 400
        deleted = purge_jobs({"all": True})
    elif "older_than_days" in data:
        try:
            days = int(data["older_than_days"])
        except (TypeError, ValueError):
            return jsonify({"error": "older_than_days must be an integer"}), 400
        deleted = purge_jobs({"older_than_days": days})
    elif data.get("status"):
        valid = {"new", "saved", "applied", "skipped", "archived"}
        if data["status"] not in valid:
            return jsonify({"error": "Invalid status"}), 400
        deleted = purge_jobs({"status": data["status"]})
    elif data.get("source"):
        deleted = purge_jobs({"source": data["source"]})
    else:
        return jsonify({"error": "No valid purge criteria provided"}), 400

    return jsonify({"deleted": deleted})


@jobs_bp.route("/jobs/<int:job_id>/status", methods=["PATCH"])
def update_job_status(job_id):
    data = request.get_json()
    new_status = data.get("status") if data else None
    valid = {"new", "saved", "applied", "skipped", "archived"}
    if new_status not in valid:
        return jsonify({"error": f"Invalid status"}), 400

    job = execute_query("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch_one=True)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    with get_connection() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
        if new_status in {"applied", "saved", "skipped"}:
            conn.execute("INSERT INTO user_signals (job_id, action) VALUES (?, ?)", (job_id, new_status))
        conn.commit()

    if new_status in {"applied", "saved", "skipped"}:
        try:
            from app.services.scorer import update_preference_weights
            update_preference_weights(job_id, new_status)
        except Exception:
            pass

    return jsonify({"message": f"Status updated to '{new_status}'", "job_id": job_id})


@jobs_bp.route("/jobs/stats", methods=["GET"])
def get_job_stats():
    # Dismiss feature: counts reflect ACTIVE (non-dismissed) jobs so the UI's
    # tab/stat numbers match the default list (which hides dismissed).
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs WHERE dismissed_at IS NULL").fetchone()[0]
        dismissed = conn.execute("SELECT COUNT(*) FROM jobs WHERE dismissed_at IS NOT NULL").fetchone()[0]
        status_counts = {}
        for row in conn.execute("SELECT status, COUNT(*) FROM jobs WHERE dismissed_at IS NULL GROUP BY status"):
            status_counts[row[0]] = row[1]
        excellent = conn.execute("SELECT COUNT(*) FROM jobs WHERE dismissed_at IS NULL AND adjusted_score >= 80").fetchone()[0]
        good = conn.execute("SELECT COUNT(*) FROM jobs WHERE dismissed_at IS NULL AND adjusted_score >= 60 AND adjusted_score < 80").fetchone()[0]
        partial = conn.execute("SELECT COUNT(*) FROM jobs WHERE dismissed_at IS NULL AND adjusted_score >= 40 AND adjusted_score < 60").fetchone()[0]
        low = conn.execute("SELECT COUNT(*) FROM jobs WHERE dismissed_at IS NULL AND adjusted_score < 40").fetchone()[0]
        source_counts = {}
        for row in conn.execute("SELECT source_domain, COUNT(*) FROM jobs WHERE dismissed_at IS NULL GROUP BY source_domain"):
            source_counts[row[0]] = row[1]

    return jsonify({
        "total": total, "dismissed": dismissed, "by_status": status_counts,
        "by_score": {"excellent": excellent, "good": good, "partial": partial, "low": low},
        "by_source": source_counts
    })


@jobs_bp.route("/jobs/refresh", methods=["POST"])
def refresh_jobs():
    """Full pipeline: AI Queries → Fetch → Blacklist → Dedup → Score → AI Score"""
    profile = execute_query("SELECT * FROM profiles ORDER BY id DESC LIMIT 1", fetch_one=True)
    if not profile:
        return jsonify({"error": "No profile found. Upload a resume first."}), 400

    from flask import current_app
    from app.services.job_fetcher import fetch_all_jobs
    from app.services.blacklist_engine import apply_blacklist
    from app.services.deduplicator import deduplicate_jobs
    from app.services.scorer import score_all_jobs

    try:
        # ── Step 0: Query generation ──
        # C1 429 fix: the legacy ai_generate_queries() Groq call was removed here.
        # fetch_all_jobs() already generates A2 source-aware queries internally
        # (ai_generate_source_aware_queries), so a second query-gen call only
        # burned ~900 tokens/min of Groq's TPM budget and starved C1 batches.
        ai_query_count = 0

        # ── Step 1: Fetch ──
        new_count = fetch_all_jobs(profile, current_app.config)

        # ── Step 2: Blacklist ──
        filtered = apply_blacklist()

        # ── Step 3: Dedup ──
        deduped = deduplicate_jobs()

        # Log cluster coverage by source so we can verify new sources (RemoteOK,
        # Arbeitnow, HN) are actually being matched against Greenhouse/Lever.
        try:
            cluster_stats = execute_query(
                "SELECT source_domain, COUNT(*) as cnt FROM jobs "
                "WHERE duplicate_cluster_id IS NOT NULL "
                "GROUP BY source_domain ORDER BY cnt DESC",
                fetch_all=True,
            )
            if cluster_stats:
                stat_str = ", ".join(
                    f"{r['source_domain']}:{r['cnt']}" for r in cluster_stats
                )
                logger.info(f"Dedup: {deduped} clusters. Clustered jobs by source → {stat_str}")
            else:
                logger.info(f"Dedup: {deduped} clusters (no cross-source duplicates found yet)")
        except Exception:
            pass  # dedup log is non-critical

        # ── Step 4: Rule-based scoring ──
        scored = score_all_jobs(profile)

        # ── Step 5: AI re-scores top jobs + C1: Structured analysis ──
        ai_scored = 0
        try:
            from app.services.ai_agent import analyze_jobs_batch, is_ai_enabled
            if is_ai_enabled():
                top_jobs = execute_query(
                    """SELECT id, title, company, location, description_snippet, match_score
                       FROM jobs WHERE status = 'new'
                       ORDER BY match_score DESC LIMIT 25""",
                    fetch_all=True
                )
                if top_jobs:
                    # C1: Get structured analysis with reasoning
                    # TPM fix: reduce batch size from 25 to 10 to stay under Groq's 6000 TPM limit
                    analyses = analyze_jobs_batch(top_jobs, profile, batch_size=10)
                    if analyses:
                        with get_connection() as conn:
                            for analysis in analyses:
                                job_id = analysis["job_id"]
                                ai_score = analysis["score"]

                                # Get base rule-based score
                                base = conn.execute(
                                    "SELECT match_score FROM jobs WHERE id = ?", (job_id,)
                                ).fetchone()
                                if base:
                                    blended = int(base[0] * 0.6 + ai_score * 0.4)

                                    # Update jobs table with blended score
                                    conn.execute(
                                        """UPDATE jobs SET adjusted_score = ?, ai_score = ?, ai_reason = ?
                                           WHERE id = ?""",
                                        (blended, ai_score, analysis["fit_summary"], job_id)
                                    )

                                    # C1: Store structured analysis
                                    try:
                                        conn.execute(
                                            """INSERT INTO job_ai_analysis
                                               (job_id, ai_score, apply_reasons, skip_reasons, fit_summary, red_flags, model_used)
                                               VALUES (?, ?, ?, ?, ?, ?, ?)
                                               ON CONFLICT(job_id) DO UPDATE SET
                                               ai_score = excluded.ai_score,
                                               apply_reasons = excluded.apply_reasons,
                                               skip_reasons = excluded.skip_reasons,
                                               fit_summary = excluded.fit_summary,
                                               red_flags = excluded.red_flags,
                                               analyzed_at = datetime('now')""",
                                            (job_id, ai_score,
                                             json.dumps(analysis.get("apply_reasons", [])),
                                             json.dumps(analysis.get("skip_reasons", [])),
                                             analysis["fit_summary"],
                                             json.dumps(analysis.get("red_flags", [])),
                                             "llama-3.1-8b-instant")
                                        )
                                    except Exception as e:
                                        logger.debug(f"C1: Failed to store analysis for job {job_id}: {e}")

                            conn.commit()
                        ai_scored = len(analyses)
                        logger.info(f"C1: Analyzed {ai_scored} jobs with structured reasoning")
        except Exception as e:
            logger.info(f"AI analysis skipped: {e}")

        # ── Retention: purge stale jobs to keep the table fresh ──
        try:
            from app.services.job_fetcher import purge_old_jobs
            purge_old_jobs()
        except Exception as e:
            logger.warning(f"Retention purge failed: {e}")

        return jsonify({
            "message": f"Found {new_count} new jobs",
            "new_jobs": new_count, "filtered": filtered,
            "deduplicated": deduped, "scored": scored,
            "ai_queries": ai_query_count, "ai_scored": ai_scored,
        })
    except Exception as e:
        return jsonify({"error": f"Refresh failed: {str(e)}"}), 500


# ============================================================
# Phase 2: Async Refresh Endpoints (Background Jobs + Polling)
# ============================================================

@jobs_bp.route("/jobs/refresh-async", methods=["POST"])
def refresh_jobs_async():
    """
    Kick off an async refresh job.
    Returns immediately with job_id for polling.

    Response (202 Accepted):
    {
      "job_id": "uuid",
      "status": "started",
      "poll_url": "/api/jobs/refresh-async/uuid"
    }
    """
    profile = execute_query("SELECT * FROM profiles ORDER BY id DESC LIMIT 1", fetch_one=True)
    if not profile:
        return jsonify({"error": "No profile found. Upload a resume first."}), 400

    from flask import current_app
    from app.services.job_fetcher import trigger_async_refresh

    try:
        # C1 429 fix: legacy ai_generate_queries() Groq call removed here too.
        # The async pipeline generates A2 source-aware queries inside fetch_all_jobs.

        # Trigger background job
        job_id = trigger_async_refresh(profile, current_app.config)

        return jsonify({
            "job_id": job_id,
            "status": "started",
            "poll_url": f"/api/jobs/refresh-async/{job_id}"
        }), 202

    except Exception as e:
        logger.exception(f"Failed to start async refresh: {e}")
        return jsonify({"error": f"Failed to start refresh: {str(e)}"}), 500


@jobs_bp.route("/jobs/refresh-async/<job_id>", methods=["GET"])
def get_refresh_status(job_id):
    """
    Poll endpoint: Get refresh job progress.

    Response while running:
    {
      "job_id": "uuid",
      "status": "running",
      "elapsed_sec": 12,
      "sources_done": 6,
      "sources_total": 14,
      "jobs_fetched": 312,
      "per_source": {...}
    }

    Response when complete:
    {
      "job_id": "uuid",
      "status": "completed",
      "duration_sec": 48,
      "jobs_fetched": 643,
      "jobs_new": 10,
      "jobs_ai_scored": 16
    }
    """
    from app.services.job_fetcher import get_refresh_job
    from datetime import datetime as dt

    job = get_refresh_job(job_id)
    if not job:
        return jsonify({"error": "Refresh job not found"}), 404

    started_dt = dt.fromisoformat(job["started_at"])
    elapsed = int((dt.utcnow() - started_dt).total_seconds())

    response = {
        "job_id": job_id,
        "status": job["status"],
        "started_at": job["started_at"],
        "elapsed_sec": elapsed,
        "sources_total": job["sources_total"],
        "sources_done": job["sources_done"],
        "sources_failed": job["sources_failed"],
        "jobs_fetched": job["jobs_fetched"],
        "jobs_new": job["jobs_new"],
    }

    # Include per-source breakdown if available
    if job["per_source_json"]:
        try:
            import json as _json
            response["per_source"] = _json.loads(job["per_source_json"])
        except Exception:
            response["per_source"] = {}

    # Include completion details if done
    if job["status"] in ("completed", "failed"):
        response["duration_sec"] = job["duration_sec"]
        response["jobs_ai_scored"] = job["jobs_ai_scored"]
        if job["error_message"]:
            response["error_message"] = job["error_message"]

    return jsonify(response), 200


@jobs_bp.route("/jobs/refresh-async/latest", methods=["GET"])
def get_latest_refresh():
    """
    Convenience endpoint: Get the most recent refresh job.
    Useful if frontend reconnects mid-refresh.
    """
    from app.database import get_latest_refresh_job
    from datetime import datetime as dt

    job = get_latest_refresh_job()
    if not job:
        return jsonify({"error": "No refresh jobs found"}), 404

    started_dt = dt.fromisoformat(job["started_at"])
    elapsed = int((dt.utcnow() - started_dt).total_seconds())

    response = {
        "job_id": job["id"],
        "status": job["status"],
        "started_at": job["started_at"],
        "elapsed_sec": elapsed,
        "sources_total": job["sources_total"],
        "sources_done": job["sources_done"],
        "jobs_fetched": job["jobs_fetched"],
    }

    if job["status"] in ("completed", "failed"):
        response["duration_sec"] = job["duration_sec"]
        response["jobs_ai_scored"] = job["jobs_ai_scored"]

    return jsonify(response), 200
