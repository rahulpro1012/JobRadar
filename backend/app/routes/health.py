"""Health check endpoint — used by cron-job.org keep-alive pings and frontend wake-up."""
from flask import Blueprint, jsonify
from app.database import get_connection

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Return app status and basic DB connectivity check."""
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return jsonify({
        "status": "ok",
        "database": db_status,
        "app": "JobRadar v1.0"
    })
