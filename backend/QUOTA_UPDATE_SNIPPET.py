    # PASTE THIS into backend/app/routes/settings.py
    # Replace the existing get_quota() function body with this:
    
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
        "jooble": {
            "used": get_quota_usage("jooble", today),
            "daily_limit": -1,
            "source": "Jooble API (free tier)"
        },
        "rss": {
            "used": get_quota_usage("rss", today),
            "daily_limit": -1,
            "source": "Indeed RSS (free, no limit)"
        },
        "serpapi": {
            "used": get_quota_usage("serpapi", today),
            "daily_limit": 3,  # ~100/month = ~3/day
            "source": "SerpApi Google Jobs (100/month)"
        },
        "direct_scrape": {
            "used": get_quota_usage("direct_scrape", today),
            "daily_limit": -1,
            "source": "Career Page Search URLs"
        },
        "google_cse": {
            "used": get_quota_usage("google_cse", today),
            "daily_limit": 100,
            "source": "Google Custom Search API"
        },
        "bing": {
            "used": get_quota_usage("bing", today),
            "daily_limit": 33,
            "source": "Bing Web Search API"
        },
        "duckduckgo": {
            "used": get_quota_usage("duckduckgo", today),
            "daily_limit": -1,
            "source": "DuckDuckGo (free, no limit)"
        },
    }
