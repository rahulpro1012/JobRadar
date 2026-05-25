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
        "greenhouse": {
            "used": get_quota_usage("greenhouse", today),
            "daily_limit": -1,
            "source": "Greenhouse API (free, no limit)"
        },
        "lever": {
            "used": get_quota_usage("lever", today),
            "daily_limit": -1,
            "source": "Lever API (free, no limit)"
        },
        "ashby": {
            "used": get_quota_usage("ashby", today),
            "daily_limit": -1,
            "source": "Ashby API (free, no limit)"
        },
        "jooble": {
            "used": get_quota_usage("jooble", today),
            "daily_limit": -1,
            "source": "Jooble API (free tier)"
        },
        "serpapi": {
            "used": get_quota_usage("serpapi", today),
            "daily_limit": 3,
            "source": "SerpApi Google Jobs (100/month)"
        },
        "rss": {
            "used": get_quota_usage("rss", today),
            "daily_limit": -1,
            "source": "Indeed RSS (free)"
        },
        "searxng": {
            "used": get_quota_usage("searxng", today),
            "daily_limit": -1,
            "source": "SearxNG Metasearch (free)"
        },
        "yahoo": {
            "used": get_quota_usage("yahoo", today),
            "daily_limit": -1,
            "source": "Yahoo Search (free)"
        },
        "direct_scrape": {
            "used": get_quota_usage("direct_scrape", today),
            "daily_limit": -1,
            "source": "Career Page URLs (free)"
        },
        "bing": {
            "used": get_quota_usage("bing", today),
            "daily_limit": 33,
            "source": "Bing Web Search API"
        },
        "groq_smart": {
            "used": get_quota_usage("groq_smart", today),
            "daily_limit": 50,
            "source": "Groq AI — Smart (llama-3.3-70b)"
        },
        "groq_fast": {
            "used": get_quota_usage("groq_fast", today),
            "daily_limit": 200,
            "source": "Groq AI — Fast (llama-3.1-8b)"
        },
        # ── Phase 1 additions ──
        "remoteok": {
            "used": get_quota_usage("remoteok", today),
            "daily_limit": -1,
            "source": "RemoteOK (free, no key — worldwide remote)"
        },
        "hn_whoishiring": {
            "used": get_quota_usage("hn_whoishiring", today),
            "daily_limit": -1,
            "source": "HN Who is Hiring (free, Algolia API)"
        },
        "arbeitnow": {
            "used": get_quota_usage("arbeitnow", today),
            "daily_limit": -1,
            "source": "Arbeitnow (free, no key — global remote)"
        },
        "adzuna": {
            "used": get_quota_usage("adzuna", today),
            "daily_limit": 8,
            "source": "Adzuna India (free key, ~250-1000/month)"
        },
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
