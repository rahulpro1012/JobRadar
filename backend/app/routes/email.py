"""Email scanner API routes (Feature 1) — on-demand Gmail job-alert scan."""
import logging
from flask import Blueprint, request, jsonify, current_app
from app.database import (
    execute_query, get_setting, set_setting,
    list_email_senders, add_email_sender, remove_email_sender, toggle_email_sender,
)

email_bp = Blueprint("email", __name__)
logger = logging.getLogger(__name__)


def _mask(addr):
    if not addr or "@" not in addr:
        return ""
    name, domain = addr.split("@", 1)
    head = name[:2] if len(name) > 2 else name[:1]
    return f"{head}***@{domain}"


@email_bp.route("/email/status", methods=["GET"])
def email_status():
    """Config/status for the email scanner (no secrets)."""
    from app.services.email_fetcher import is_email_enabled
    try:
        scan_days = int(get_setting("email_scan_days", 7))
    except (TypeError, ValueError):
        scan_days = 7
    senders = list_email_senders()
    return jsonify({
        "enabled": is_email_enabled(),
        "address": _mask(current_app.config.get("GMAIL_ADDRESS", "")),
        "label": current_app.config.get("GMAIL_LABEL", "") or None,
        "scan_days": scan_days,
        "senders_count": len([s for s in senders if s["enabled"]]),
        "last_scan": get_setting("email_last_scan", None),
        "last_imported": get_setting("email_last_imported", None),
    })


@email_bp.route("/email/test", methods=["POST"])
def email_test():
    """Validate IMAP login without scanning."""
    from app.services.email_fetcher import test_connection
    ok, err = test_connection()
    return jsonify({"ok": ok, "error": err})


@email_bp.route("/email/scan-async", methods=["POST"])
def email_scan_async():
    """Kick off an async Gmail scan; poll via /api/jobs/refresh-async/<id>."""
    from app.services.email_fetcher import is_email_enabled
    if not is_email_enabled():
        return jsonify({"error": "Email not configured. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD."}), 400

    profile = execute_query("SELECT * FROM profiles ORDER BY id DESC LIMIT 1", fetch_one=True)
    if not profile:
        return jsonify({"error": "No profile found. Upload a resume first."}), 400

    from app.services.job_fetcher import trigger_email_scan
    try:
        job_id = trigger_email_scan(profile, current_app.config)
        return jsonify({
            "job_id": job_id,
            "status": "started",
            "poll_url": f"/api/jobs/refresh-async/{job_id}",
        }), 202
    except Exception as e:
        logger.exception(f"Failed to start email scan: {e}")
        return jsonify({"error": f"Failed to start scan: {str(e)}"}), 500


# ── Sender allowlist CRUD ──

@email_bp.route("/email/senders", methods=["GET"])
def get_senders():
    return jsonify({"senders": list_email_senders()})


@email_bp.route("/email/senders", methods=["POST"])
def add_sender():
    data = request.get_json() or {}
    value = (data.get("value") or "").strip().lower()
    if not value:
        return jsonify({"error": "value is required"}), 400
    add_email_sender(value)
    return jsonify({"message": f"Added {value}", "senders": list_email_senders()}), 201


@email_bp.route("/email/senders/<int:sender_id>", methods=["DELETE"])
def delete_sender(sender_id):
    removed = remove_email_sender(sender_id)
    if not removed:
        return jsonify({"error": "Sender not found"}), 404
    return jsonify({"message": "Removed", "senders": list_email_senders()})


@email_bp.route("/email/senders/<int:sender_id>/toggle", methods=["PATCH"])
def toggle_sender(sender_id):
    result = toggle_email_sender(sender_id)
    if result is None:
        return jsonify({"error": "Sender not found"}), 404
    return jsonify({"enabled": result, "senders": list_email_senders()})


@email_bp.route("/email/scan-days", methods=["PUT"])
def set_scan_days():
    data = request.get_json() or {}
    try:
        days = int(data.get("scan_days"))
    except (TypeError, ValueError):
        return jsonify({"error": "scan_days must be an integer"}), 400
    if days < 1 or days > 90:
        return jsonify({"error": "scan_days must be between 1 and 90"}), 400
    set_setting("email_scan_days", days)
    return jsonify({"scan_days": days})
