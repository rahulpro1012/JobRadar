"""Settings API routes — quota usage and preferences."""
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
    
    # Only sources that are actually active in the fetch pipeline.
    # daily_limit -1 = free/unlimited (these don't increment quota, shown for visibility).
    quotas = {
        # ── Rate-limited / metered sources ──
        "adzuna": {
            "used": get_quota_usage("adzuna", today),
            "daily_limit": 36,
            "source": "Adzuna India (free key, capped at 36/day)"
        },
        "serpapi": {
            "used": get_quota_usage("serpapi", today),
            "daily_limit": 3,
            "source": "SerpApi Google Jobs (100/month)"
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
        # ── Free / unlimited sources ──
        "jooble": {
            "used": get_quota_usage("jooble", today),
            "daily_limit": -1,
            "source": "Jooble API (free tier)"
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
        "linkedin_guest": {
            "used": get_quota_usage("linkedin_guest", today),
            "daily_limit": -1,
            "source": "LinkedIn Guest (free, no key)"
        },
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
        # ── ATS APIs (free, no key) ──
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
        "workable": {
            "used": get_quota_usage("workable", today),
            "daily_limit": -1,
            "source": "Workable ATS (free, no key — remote-first startups)"
        },
        "smartrecruiters": {
            "used": get_quota_usage("smartrecruiters", today),
            "daily_limit": -1,
            "source": "SmartRecruiters ATS (free, no key — enterprise)"
        },
    }
    
    return jsonify({
        "date": today,
        "quotas": quotas
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
