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

    conditions, params = [], []

    if status and status != "all":
        conditions.append("status = ?"); params.append(status)
    if min_score is not None:
        conditions.append("adjusted_score >= ?"); params.append(min_score)
    if source:
        conditions.append("source_domain LIKE ?"); params.append(f"%{source}%")
    if days:
        conditions.append("fetched_date >= datetime('now', ?)"); params.append(f"-{days} days")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * per_page

    count_result = execute_query(f"SELECT COUNT(*) as total FROM jobs {where}", params, fetch_one=True)
    total = count_result["total"] if count_result else 0

    jobs = execute_query(
        f"""SELECT * FROM jobs {where}
            ORDER BY adjusted_score DESC, fetched_date DESC
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
    job = execute_query("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch_one=True)
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
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        status_counts = {}
        for row in conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status"):
            status_counts[row[0]] = row[1]
        excellent = conn.execute("SELECT COUNT(*) FROM jobs WHERE adjusted_score >= 80").fetchone()[0]
        good = conn.execute("SELECT COUNT(*) FROM jobs WHERE adjusted_score >= 60 AND adjusted_score < 80").fetchone()[0]
        partial = conn.execute("SELECT COUNT(*) FROM jobs WHERE adjusted_score >= 40 AND adjusted_score < 60").fetchone()[0]
        low = conn.execute("SELECT COUNT(*) FROM jobs WHERE adjusted_score < 40").fetchone()[0]
        source_counts = {}
        for row in conn.execute("SELECT source_domain, COUNT(*) FROM jobs GROUP BY source_domain"):
            source_counts[row[0]] = row[1]

    return jsonify({
        "total": total, "by_status": status_counts,
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
        # ── Step 0: AI generates location-aware queries ──
        ai_query_count = 0
        try:
            from app.services.ai_agent import ai_generate_queries, is_ai_enabled
            if is_ai_enabled():
                # Get search locations from profile
                search_locations = []
                loc = profile.get("location", "")
                if loc:
                    search_locations.append(loc)

                extra_locs = profile.get("search_locations", "")
                if extra_locs:
                    import json as _json
                    if isinstance(extra_locs, str):
                        try:
                            extra_locs = _json.loads(extra_locs)
                        except (ValueError, TypeError):
                            extra_locs = [x.strip() for x in extra_locs.split(",") if x.strip()]
                    if isinstance(extra_locs, list):
                        search_locations.extend(extra_locs)

                if "India" not in search_locations:
                    search_locations.append("India")
                if "Remote" not in search_locations:
                    search_locations.append("Remote")

                ai_queries = ai_generate_queries(profile, search_locations=search_locations)
                if ai_queries:
                    ai_query_count = len(ai_queries)
                    current_app.config["_ai_queries"] = ai_queries
        except Exception as e:
            logger.info(f"AI query generation skipped: {e}")

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
        # Generate AI queries if available
        try:
            from app.services.ai_agent import ai_generate_queries, is_ai_enabled
            if is_ai_enabled():
                search_locations = []
                loc = profile.get("location", "")
                if loc:
                    search_locations.append(loc)

                extra_locs = profile.get("search_locations", "")
                if extra_locs:
                    import json as _json
                    if isinstance(extra_locs, str):
                        try:
                            extra_locs = _json.loads(extra_locs)
                        except (ValueError, TypeError):
                            extra_locs = [x.strip() for x in extra_locs.split(",") if x.strip()]
                    if isinstance(extra_locs, list):
                        search_locations.extend(extra_locs)

                if "India" not in search_locations:
                    search_locations.append("India")
                if "Remote" not in search_locations:
                    search_locations.append("Remote")

                ai_queries = ai_generate_queries(profile, search_locations=search_locations)
                if ai_queries:
                    current_app.config["_ai_queries"] = ai_queries
        except Exception as e:
            logger.info(f"AI query generation skipped: {e}")

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
