"""Settings API routes — quota usage, company registry, and preferences."""
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app.database import execute_query, get_connection, get_quota_usage

settings_bp = Blueprint("settings", __name__)


# ============================================================
# Quota Management
# ============================================================

@settings_bp.route("/settings/quota", methods=["GET"])
def get_quota():
    """Get current API quota usage across all sources."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    quotas = {
        "google_cse": {
            "used": get_quota_usage("google_cse", today),
            "daily_limit": 100,
            "source": "Google Custom Search API"
        },
        "bing": {
            "used": get_quota_usage("bing", today),
            "daily_limit": 33,  # ~1000/month
            "source": "Bing Web Search API"
        },
        "duckduckgo": {
            "used": get_quota_usage("duckduckgo", today),
            "daily_limit": -1,  # unlimited
            "source": "DuckDuckGo API"
        },
        "rss": {
            "used": get_quota_usage("rss", today),
            "daily_limit": -1,  # unlimited
            "source": "RSS Feeds (Indeed)"
        },
        "direct_scrape": {
            "used": get_quota_usage("direct_scrape", today),
            "daily_limit": -1,  # unlimited
            "source": "Direct Career Page Scraping"
        },
        "google_scrape": {
            "used": get_quota_usage("google_scrape", today),
            "daily_limit": 60,  # approximate safe limit
            "source": "Google Scrape Fallback"
        }
    }
    
    return jsonify({
        "date": today,
        "quotas": quotas
    })


# ============================================================
# Company Career Page Registry
# ============================================================

@settings_bp.route("/settings/companies", methods=["GET"])
def get_companies():
    """Get the company career page registry."""
    companies = execute_query(
        "SELECT * FROM company_sources ORDER BY company_name",
        fetch_all=True
    )
    return jsonify({"companies": companies})


@settings_bp.route("/settings/companies", methods=["POST"])
def add_company():
    """Add a new company career page to the registry."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    name = data.get("company_name", "").strip()
    url = data.get("careers_url", "").strip()
    pattern = data.get("search_pattern", "").strip()
    
    if not name or not url:
        return jsonify({"error": "company_name and careers_url are required"}), 400
    
    try:
        company_id = execute_query(
            "INSERT INTO company_sources (company_name, careers_url, search_pattern) VALUES (?, ?, ?)",
            (name, url, pattern)
        )
        return jsonify({"message": f"Added {name}", "id": company_id}), 201
    except Exception:
        return jsonify({"error": f"Career page URL already exists in registry"}), 409


@settings_bp.route("/settings/companies/<int:company_id>", methods=["DELETE"])
def remove_company(company_id):
    """Remove a company from the career page registry."""
    company = execute_query(
        "SELECT * FROM company_sources WHERE id = ?",
        (company_id,),
        fetch_one=True
    )
    if not company:
        return jsonify({"error": "Company not found"}), 404
    
    execute_query("DELETE FROM company_sources WHERE id = ?", (company_id,))
    return jsonify({
        "message": f"Removed {company['company_name']}",
        "id": company_id
    })


@settings_bp.route("/settings/companies/<int:company_id>/toggle", methods=["PATCH"])
def toggle_company(company_id):
    """Enable or disable a company in the registry."""
    company = execute_query(
        "SELECT * FROM company_sources WHERE id = ?",
        (company_id,),
        fetch_one=True
    )
    if not company:
        return jsonify({"error": "Company not found"}), 404
    
    new_enabled = 0 if company["enabled"] else 1
    execute_query(
        "UPDATE company_sources SET enabled = ? WHERE id = ?",
        (new_enabled, company_id)
    )
    status = "enabled" if new_enabled else "disabled"
    return jsonify({
        "message": f"{company['company_name']} {status}",
        "enabled": bool(new_enabled)
    })


# ============================================================
# Preference Management
# ============================================================

@settings_bp.route("/preferences/reset", methods=["POST"])
def reset_preferences():
    """Reset all learned preference weights to zero."""
    with get_connection() as conn:
        conn.execute("DELETE FROM preference_weights")
        conn.execute("DELETE FROM user_signals")
        conn.commit()
    
    return jsonify({"message": "All preference weights and signals have been reset."})


@settings_bp.route("/preferences", methods=["GET"])
def get_preferences():
    """Get current preference weights."""
    weights = execute_query(
        "SELECT * FROM preference_weights ORDER BY category, weight DESC",
        fetch_all=True
    )
    
    grouped = {"skill": [], "company_type": [], "source": []}
    for w in weights:
        if w["category"] in grouped:
            grouped[w["category"]].append(w)
    
    return jsonify({
        "weights": weights,
        "grouped": grouped
    })
