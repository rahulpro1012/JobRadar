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

        # ── Step 4: Rule-based scoring ──
        scored = score_all_jobs(profile)

        # ── Step 5: AI re-scores top jobs ──
        ai_scored = 0
        try:
            from app.services.ai_agent import ai_score_jobs, is_ai_enabled
            if is_ai_enabled():
                top_jobs = execute_query(
                    """SELECT id, title, company, location, description_snippet, match_score
                       FROM jobs WHERE status = 'new'
                       ORDER BY match_score DESC LIMIT 16""",
                    fetch_all=True
                )
                if top_jobs:
                    ai_results = ai_score_jobs(top_jobs, profile)
                    if ai_results:
                        with get_connection() as conn:
                            for job_id, ai_data in ai_results.items():
                                base = conn.execute(
                                    "SELECT match_score FROM jobs WHERE id = ?", (job_id,)
                                ).fetchone()
                                if base:
                                    blended = int(base[0] * 0.6 + ai_data["ai_score"] * 0.4)
                                    conn.execute(
                                        """UPDATE jobs SET adjusted_score = ?, ai_score = ?, ai_reason = ?
                                           WHERE id = ?""",
                                        (blended, ai_data["ai_score"], ai_data["ai_reason"], job_id)
                                    )
                            conn.commit()
                        ai_scored = len(ai_results)
        except Exception as e:
            logger.info(f"AI scoring skipped: {e}")

        return jsonify({
            "message": f"Found {new_count} new jobs",
            "new_jobs": new_count, "filtered": filtered,
            "deduplicated": deduped, "scored": scored,
            "ai_queries": ai_query_count, "ai_scored": ai_scored,
        })
    except Exception as e:
        return jsonify({"error": f"Refresh failed: {str(e)}"}), 500
