"""Admin API routes — source health dashboard, cache stats, circuit resets."""
from datetime import datetime
from flask import Blueprint, jsonify, request
from app.services.source_health import get_all_health, reset_circuit
from app.services.search_cache import get_cache_stats, purge_expired

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/source-health", methods=["GET"])
def source_health_endpoint():
    """
    GET /api/admin/source-health
    Returns health status for every source that has been used at least once.
    Frontend: shows in SettingsPanel → Source Health tab.
    """
    sources = get_all_health()
    return jsonify({
        "sources": sources,
        "total": len(sources),
        "checked_at": datetime.utcnow().isoformat() + "Z",
    })


@admin_bp.route("/admin/source-health/<source>/reset", methods=["POST"])
def reset_source_circuit(source):
    """
    POST /api/admin/source-health/<source>/reset
    Manually re-enable a source whose circuit was opened by failures.
    """
    reset_circuit(source)
    return jsonify({
        "message": f"Circuit reset for '{source}' — it will be retried on next refresh.",
        "source": source,
    })


@admin_bp.route("/admin/cache-stats", methods=["GET"])
def cache_stats_endpoint():
    """
    GET /api/admin/cache-stats
    Returns search cache statistics (total entries, active, by source).
    """
    stats = get_cache_stats()
    return jsonify(stats)


@admin_bp.route("/admin/cache-purge", methods=["POST"])
def cache_purge_endpoint():
    """
    POST /api/admin/cache-purge
    Purge all expired cache entries. Safe to call anytime.
    """
    purge_expired()
    return jsonify({"message": "Expired cache entries purged."})
