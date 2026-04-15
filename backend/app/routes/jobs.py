"""Jobs API routes — listing, filtering, status updates, and refresh trigger."""
import json
from flask import Blueprint, request, jsonify
from app.database import execute_query, get_connection

jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("/jobs", methods=["GET"])
def get_jobs():
    """
    Get all jobs with optional filters.
    Query params: status, min_score, source, days, page, per_page
    """
    status = request.args.get("status")
    min_score = request.args.get("min_score", type=int)
    source = request.args.get("source")
    days = request.args.get("days", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    
    conditions = []
    params = []
    
    if status and status != "all":
        conditions.append("status = ?")
        params.append(status)
    
    if min_score is not None:
        conditions.append("adjusted_score >= ?")
        params.append(min_score)
    
    if source:
        conditions.append("source_domain LIKE ?")
        params.append(f"%{source}%")
    
    if days:
        conditions.append("fetched_date >= datetime('now', ?)")
        params.append(f"-{days} days")
    
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * per_page
    
    # Get total count
    count_result = execute_query(
        f"SELECT COUNT(*) as total FROM jobs {where}",
        params,
        fetch_one=True
    )
    total = count_result["total"] if count_result else 0
    
    # Get paginated jobs
    jobs = execute_query(
        f"""SELECT * FROM jobs {where}
            ORDER BY adjusted_score DESC, fetched_date DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
        fetch_all=True
    )
    
    return jsonify({
        "jobs": jobs,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        }
    })


@jobs_bp.route("/jobs/<int:job_id>", methods=["GET"])
def get_job(job_id):
    """Get a single job by ID."""
    job = execute_query("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch_one=True)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@jobs_bp.route("/jobs/<int:job_id>/status", methods=["PATCH"])
def update_job_status(job_id):
    """Update a job's status (save, apply, skip) and record the signal."""
    data = request.get_json()
    new_status = data.get("status") if data else None
    
    valid_statuses = {"new", "saved", "applied", "skipped", "archived"}
    if new_status not in valid_statuses:
        return jsonify({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400
    
    # Check job exists
    job = execute_query("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch_one=True)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    with get_connection() as conn:
        # Update status
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
        
        # Record user signal for preference learning (only for actionable statuses)
        if new_status in {"applied", "saved", "skipped"}:
            conn.execute(
                "INSERT INTO user_signals (job_id, action) VALUES (?, ?)",
                (job_id, new_status)
            )
        
        conn.commit()
    
    return jsonify({"message": f"Job status updated to '{new_status}'", "job_id": job_id})


@jobs_bp.route("/jobs/stats", methods=["GET"])
def get_job_stats():
    """Get summary statistics about current jobs."""
    with get_connection() as conn:
        # Total jobs
        total = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()[0]
        
        # By status
        status_counts = {}
        for row in conn.execute("SELECT status, COUNT(*) as c FROM jobs GROUP BY status"):
            status_counts[row[0]] = row[1]
        
        # By score range
        excellent = conn.execute("SELECT COUNT(*) FROM jobs WHERE adjusted_score >= 80").fetchone()[0]
        good = conn.execute("SELECT COUNT(*) FROM jobs WHERE adjusted_score >= 60 AND adjusted_score < 80").fetchone()[0]
        partial = conn.execute("SELECT COUNT(*) FROM jobs WHERE adjusted_score >= 40 AND adjusted_score < 60").fetchone()[0]
        low = conn.execute("SELECT COUNT(*) FROM jobs WHERE adjusted_score < 40").fetchone()[0]
        
        # By source
        source_counts = {}
        for row in conn.execute("SELECT source_domain, COUNT(*) as c FROM jobs GROUP BY source_domain"):
            source_counts[row[0]] = row[1]
    
    return jsonify({
        "total": total,
        "by_status": status_counts,
        "by_score": {
            "excellent": excellent,
            "good": good,
            "partial": partial,
            "low": low
        },
        "by_source": source_counts
    })


@jobs_bp.route("/jobs/refresh", methods=["POST"])
def refresh_jobs():
    """
    Trigger a new job search across all sources.
    Phase 3 will implement the actual fetching logic.
    Returns status of the refresh operation.
    """
    # Check if profile exists
    profile = execute_query(
        "SELECT * FROM profiles ORDER BY id DESC LIMIT 1",
        fetch_one=True
    )
    if not profile:
        return jsonify({"error": "No profile found. Upload a resume first."}), 400
    
    # Phase 3 will call:
    # from app.services.job_fetcher import fetch_all_jobs
    # new_jobs_count = fetch_all_jobs(profile)
    
    return jsonify({
        "message": "Job refresh will be implemented in Phase 3",
        "profile_used": profile.get("primary_role", ""),
        "status": "pending_implementation"
    })
