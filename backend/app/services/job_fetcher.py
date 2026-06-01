"""
JobRadar Job Fetcher v3
Layer 1:   Greenhouse API (free, no key)
Layer 2:   Lever API (free, no key)
Layer 2b:  Ashby API (free, no key)
Layer 3:   Jooble API (free, key required)
Layer 4:   Indeed RSS (disabled — consistent failures)
Layer 5:   SerpApi Google Jobs (100/month)
Layer 6:   Career page search URLs
Layer 7:   SearxNG (disabled until self-hosted — set SEARXNG_URL in .env)
Layer 8:   Yahoo Search fallback
Layer 9:   Bing API (when key available)
Layer 10:  DuckDuckGo (disabled, kept for future)
── Phase 1 additions ──
Layer 11:  RemoteOK (free, no key — worldwide remote jobs)
Layer 12:  HackerNews "Who is Hiring" (free, Algolia API — YC/startup remote jobs)
Layer 13:  Arbeitnow (free, no key — global remote job board)
Layer 14:  Adzuna India (free key required — India aggregator with salary data)
── Phase 2 additions ──
Layer 15:  Workable ATS (free, no key — remote-first startups)
Layer 16:  SmartRecruiters ATS (free, no key — enterprise companies)
"""
import re
import time
import json
import logging
from datetime import datetime
from urllib.parse import quote_plus, urlparse

from app.database import (
    get_connection, execute_query,
    get_quota_usage, increment_quota,
)
from app.services.query_engine import (
    generate_queries, generate_site_queries, generate_rss_urls,
)
from app.services.search_cache import purge_expired as _purge_cache

logger = logging.getLogger(__name__)

QUOTA_LIMITS = {
    "bing": 33,
}


import time as _time_module  # For phase 1 parallelization
import threading
import uuid
from datetime import datetime


def fetch_all_jobs(profile, config):
    """
    ── PHASE 1: PARALLEL LAYER EXECUTION ──
    Fetch from ALL 16 layers in parallel using ThreadPoolExecutor.
    Expected time: ~45-60 sec (bounded by slowest layer, typically ATS at ~50s).

    Previously: ~3 min 10 sec (sequential execution)
    """
    # Get AI-generated queries if available
    ai_queries = config.get("_ai_queries", [])
    queries = generate_queries(profile, ai_queries=ai_queries)

    # Build location list for search layers
    search_locations = _get_search_locations(profile)
    scrape_delay = config.get("SCRAPE_DELAY", 1.0)

    # Import parallel execution tooling
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Define all 16 layers as (name, callable, kwargs_dict)
    layers = []
    layer_timings = {}

    # ── ATS Sources (parallel internally, now part of parallel pool) ──
    def _get_ats_jobs():
        """Fetch from Greenhouse, Lever, Ashby, Workable, SmartRecruiters in parallel."""
        from app.services.ats_fetcher import fetch_greenhouse_jobs, fetch_lever_jobs, fetch_ashby_jobs
        from app.services.workable_fetcher import fetch_workable_jobs
        from app.services.smartrecruiters_fetcher import fetch_smartrecruiters_jobs

        ats_jobs = []
        with ThreadPoolExecutor(max_workers=5) as ats_executor:
            ats_futures = {
                ats_executor.submit(fetch_greenhouse_jobs, profile, 0.15): "Greenhouse",
                ats_executor.submit(fetch_lever_jobs, profile, 0.15): "Lever",
                ats_executor.submit(fetch_ashby_jobs, profile, 0.15): "Ashby",
                ats_executor.submit(fetch_workable_jobs, profile, 0.3): "Workable",
                ats_executor.submit(fetch_smartrecruiters_jobs, profile, 0.3): "SmartRecruiters",
            }
            for future in as_completed(ats_futures):
                try:
                    jobs = future.result(timeout=120)
                    ats_jobs.extend(jobs)
                except Exception as e:
                    logger.warning(f"{ats_futures[future]} failed: {e}")
        return ats_jobs

    layers.append(("ATS (Greenhouse/Lever/Ashby/Workable/SmartRecruiters)", _get_ats_jobs, {}))

    # ── Layer 3: Jooble ──
    jooble_key = config.get("JOOBLE_API_KEY", "")
    if jooble_key:
        from app.services.job_api_fetcher import fetch_jooble_jobs
        layers.append(("Jooble", fetch_jooble_jobs, {"profile": profile, "api_key": jooble_key, "delay": scrape_delay}))

    # ── Layer 5: SerpApi ──
    serpapi_key = config.get("SERPAPI_API_KEY", "")
    if serpapi_key:
        from app.services.job_api_fetcher import fetch_serpapi_jobs
        layers.append(("SerpApi", fetch_serpapi_jobs, {"profile": profile, "api_key": serpapi_key, "delay": scrape_delay}))

    # ── Layer 6: Career Pages ──
    layers.append(("Career Pages", _fetch_from_career_pages, {"profile": profile}))

    # ── Layer 7: SearxNG (RE-ENABLED - uses self-hosted instance from SEARXNG_URL) ──
    searxng_url = config.get("SEARXNG_URL", "")
    if searxng_url:
        from app.services.search_fetcher import fetch_from_searxng
        portal_queries = _build_portal_queries(profile, queries, search_locations)
        layers.append(("SearxNG (Naukri + LinkedIn)", fetch_from_searxng, {"queries": portal_queries, "delay": 1.5}))
    else:
        logger.debug("Layer 7: SearxNG disabled (set SEARXNG_URL in .env to enable)")

    # ── Layer 8: Yahoo ──
    from app.services.search_fetcher import fetch_from_yahoo
    yahoo_q = _build_portal_queries(profile, queries, search_locations)[:4]
    layers.append(("Yahoo", fetch_from_yahoo, {"queries": yahoo_q, "delay": 1.5}))

    # ── Layer 9: Bing ──
    bing_key = config.get("BING_API_KEY", "")
    if bing_key:
        today_usage = get_quota_usage("bing")
        remaining = QUOTA_LIMITS["bing"] - today_usage
        if remaining > 0:
            def _fetch_bing_safe():
                jobs = []
                try:
                    top_queries = [q for q in queries if q["tier"] <= 2][:3]
                    site_queries = generate_site_queries(top_queries, ["naukri.com", "indeed.co.in"])
                    max_calls = min(6, remaining, len(site_queries))
                    for sq in site_queries[:max_calls]:
                        jobs.extend(_fetch_from_bing(sq["site_query"], bing_key, scrape_delay))
                except Exception as e:
                    logger.warning(f"Bing failed: {e}")
                return jobs
            layers.append(("Bing", _fetch_bing_safe, {}))

    # ── Layer 11: RemoteOK ──
    from app.services.remoteok_fetcher import fetch_remoteok_jobs
    layers.append(("RemoteOK", fetch_remoteok_jobs, {"profile": profile, "delay": scrape_delay}))

    # ── Layer 12: HackerNews Who is Hiring ──
    from app.services.hn_fetcher import fetch_hn_jobs
    layers.append(("HN Who's Hiring", fetch_hn_jobs, {"profile": profile, "delay": 0.5}))

    # ── Layer 13: Arbeitnow ──
    from app.services.arbeitnow_fetcher import fetch_arbeitnow_jobs
    layers.append(("Arbeitnow", fetch_arbeitnow_jobs, {"profile": profile, "delay": scrape_delay}))

    # ── Layer 14: Adzuna ──
    adzuna_id = config.get("ADZUNA_APP_ID", "")
    if adzuna_id:
        from app.services.adzuna_fetcher import fetch_adzuna_jobs
        layers.append(("Adzuna", fetch_adzuna_jobs, {"profile": profile, "queries": queries, "config": config, "delay": scrape_delay}))

    # ═══════════════════════════════════════════════════════════════
    # RUN ALL LAYERS IN PARALLEL
    # ═══════════════════════════════════════════════════════════════
    logger.info(f"Phase 1: Parallel fetch from {len(layers)} layers (max_workers=12, timeout=90s per layer)...")

    all_jobs = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {
            executor.submit(_safe_run_layer, name, fn, kwargs): name
            for name, fn, kwargs in layers
        }

        for future in as_completed(futures, timeout=120):
            name = futures[future]
            try:
                jobs, elapsed = future.result(timeout=95)  # Hard cap
                all_jobs.extend(jobs)
                layer_timings[name] = (len(jobs), round(elapsed, 1))
                logger.info(f"  [{name}] {len(jobs)} jobs ({elapsed:.1f}s)")
            except Exception as e:
                logger.warning(f"  [{name}] failed: {e}")
                layer_timings[name] = (0, -1)

    logger.info(f"Phase 1 complete: {len(all_jobs)} total jobs from {len(layers)} layers")
    logger.debug(f"Per-layer timing: {layer_timings}")

    # ── Maintenance: purge stale cache entries ──
    try:
        _purge_cache()
    except Exception:
        pass

    # Store new jobs
    new_count = _store_jobs(all_jobs)
    logger.info(f"Fetched {len(all_jobs)} total, {new_count} new jobs stored.")
    return new_count


def _safe_run_layer(name, fn, kwargs):
    """
    Execute a fetcher with timing + exception isolation.
    Returns (jobs_list, elapsed_seconds).
    """
    start = _time_module.time()
    try:
        jobs = fn(**kwargs) or []
    except Exception as e:
        logger.exception(f"[{name}] crashed: {e}")
        jobs = []
    elapsed = _time_module.time() - start
    return jobs, elapsed


# ============================================================
# Location Helpers
# ============================================================

def _get_search_locations(profile):
    """Extract search locations from profile."""
    locations = []

    # Primary location
    loc = profile.get("location", "")
    if loc:
        locations.append(loc)

    # Additional locations from search_locations field
    extra = profile.get("search_locations", "")
    if extra:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (json.JSONDecodeError, TypeError):
                extra = [x.strip() for x in extra.split(",") if x.strip()]
        if isinstance(extra, list):
            locations.extend(extra)

    # Always include India and Remote
    if "India" not in locations:
        locations.append("India")
    if "Remote" not in locations:
        locations.append("Remote")

    return locations


def _build_portal_queries(profile, queries, locations):
    """Build site-scoped queries for SearxNG/Yahoo targeting job portals."""
    role = profile.get("primary_role", "Developer")
    core_skills = profile.get("core_skills", [])
    if isinstance(core_skills, str):
        try:
            core_skills = json.loads(core_skills)
        except (json.JSONDecodeError, TypeError):
            core_skills = []

    sites = ["naukri.com", "linkedin.com/jobs"]
    portal_queries = []
    seen = set()

    # Use top tier queries with site: prefix
    for q in queries[:3]:
        query_text = q["query"] if isinstance(q, dict) else q
        for site in sites:
            full = f"site:{site} {query_text}"
            if full.lower() not in seen:
                seen.add(full.lower())
                portal_queries.append(full)

    # Add location-specific queries
    for loc in locations[:3]:
        if loc.lower() in ("india", "remote"):
            query = f"site:naukri.com {role} {loc}"
        else:
            query = f"site:naukri.com {role} {loc}"
        if query.lower() not in seen:
            seen.add(query.lower())
            portal_queries.append(query)

    return portal_queries[:8]


# ============================================================
# Layer 4: Indeed RSS
# ============================================================

def _fetch_from_indeed_rss(profile, delay=1.0):
    import requests

    rss_urls = generate_rss_urls(profile)
    jobs = []

    for url in rss_urls:
        try:
            resp = requests.get(url, timeout=15, verify=False, headers={
                "User-Agent": "Mozilla/5.0 (compatible; JobRadar/1.0)"
            })
            if resp.status_code != 200:
                continue
            parsed_jobs = _parse_rss_feed(resp.text)
            jobs.extend(parsed_jobs)
            increment_quota("rss")
            time.sleep(delay)
        except Exception as e:
            logger.warning(f"RSS fetch failed: {e}")
            continue
    return jobs


def _parse_rss_feed(xml_text):
    jobs = []
    items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)

    for item in items[:20]:
        title = _xml_tag(item, "title")
        link = _xml_tag(item, "link")
        desc = _xml_tag(item, "description")
        pub_date = _xml_tag(item, "pubDate")

        if not title or not link:
            continue

        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()[:300]

        parts = title.split(" - ")
        job_title = parts[0].strip()
        company = parts[1].strip() if len(parts) > 1 else ""
        location = parts[2].strip() if len(parts) > 2 else ""

        jobs.append({
            "title": job_title[:150],
            "company": company[:100],
            "location": location[:100],
            "source_url": link,
            "source_domain": "indeed.co.in",
            "description_snippet": desc,
            "posted_date": pub_date,
        })
    return jobs


def _xml_tag(text, tag):
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL)
    if match:
        content = match.group(1).strip()
        cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>", content, re.DOTALL)
        return cdata.group(1).strip() if cdata else content
    return ""


# ============================================================
# Layer 6: Career Page Search URLs
# ============================================================

def _fetch_from_career_pages(profile):
    companies = execute_query(
        "SELECT * FROM company_sources WHERE enabled = 1", fetch_all=True
    )
    if not companies:
        return []

    role = profile.get("primary_role", "developer")
    location = profile.get("location", "")
    core_skills = profile.get("core_skills", [])
    if isinstance(core_skills, str):
        try:
            core_skills = json.loads(core_skills)
        except (json.JSONDecodeError, TypeError):
            core_skills = []

    search_queries = [role]
    if core_skills:
        search_queries.append(f"{core_skills[0]} Developer")

    jobs = []
    for company in companies:
        search_pattern = company.get("search_pattern", "")
        if not search_pattern:
            continue

        for query_text in search_queries[:2]:
            encoded_query = quote_plus(query_text)
            encoded_location = quote_plus(location) if location else ""

            search_url = search_pattern.replace("{query}", encoded_query)
            search_url = search_url.replace("{location}", encoded_location)

            title = f"{query_text} at {company['company_name']}"
            if location:
                title += f" — {location}"

            domain = urlparse(company["careers_url"]).hostname or ""
            domain = domain.replace("www.", "")

            jobs.append({
                "title": title[:150],
                "company": company["company_name"],
                "location": location,
                "source_url": search_url,
                "source_domain": domain,
                "description_snippet": f"Search {company['company_name']} careers for {query_text} positions.",
                "posted_date": datetime.now().strftime("%Y-%m-%d"),
            })

    increment_quota("direct_scrape")
    return jobs


# ============================================================
# Layer 9: Bing API
# ============================================================

def _fetch_from_bing(query, api_key, delay=1.0):
    import requests

    try:
        resp = requests.get(
            "https://api.bing.microsoft.com/v7.0/search",
            headers={"Ocp-Apim-Subscription-Key": api_key},
            params={"q": query, "count": 10, "mkt": "en-IN"},
            timeout=15, verify=False,
        )
        increment_quota("bing")

        if resp.status_code != 200:
            return []

        data = resp.json()
        jobs = []
        for item in data.get("webPages", {}).get("value", []):
            from app.services.search_fetcher import _parse_search_result
            parsed = _parse_search_result(
                item.get("name", ""), item.get("url", ""), item.get("snippet", "")
            )
            if parsed:
                jobs.append(parsed)

        time.sleep(delay)
        return jobs
    except Exception as e:
        logger.warning(f"Bing error: {e}")
        return []


# ============================================================
# Database Storage
# ============================================================

def _store_jobs(jobs):
    if not jobs:
        return 0

    new_count = 0
    with get_connection() as conn:
        for job in jobs:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE source_url = ?", (job["source_url"],)
            ).fetchone()

            if existing:
                continue

            try:
                conn.execute("""
                    INSERT INTO jobs (
                        title, company, location, source_url, source_domain,
                        description_snippet, skills_found, posted_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')
                """, (
                    job["title"], job["company"], job["location"],
                    job["source_url"], job["source_domain"],
                    job["description_snippet"], job.get("skills_found", "[]"),
                    job.get("posted_date", ""),
                ))
                new_count += 1
            except Exception as e:
                logger.warning(f"Failed to insert job: {e}")
                continue

        conn.commit()
    return new_count


# ============================================================
# Phase 2: Async Background Refresh (Background Jobs + Polling)
# ============================================================

def trigger_async_refresh(profile, config):
    """
    Kick off an async refresh job.
    Returns job_id immediately for the frontend to poll.
    The actual fetching happens in a background thread.
    """
    from app.database import create_refresh_job

    job_id = str(uuid.uuid4())

    # Create DB record
    create_refresh_job(job_id)

    # Spawn background thread (daemon = doesn't block app shutdown)
    thread = threading.Thread(
        target=_run_refresh_background,
        args=(job_id, profile, config),
        daemon=True
    )
    thread.start()

    return job_id


def _run_refresh_background(job_id, profile, config):
    """
    Background thread: Execute Phase 1 (parallel fetch), apply filters,
    score, and store to DB. Updates refresh_jobs table with progress.
    """
    from app.database import update_refresh_job, get_connection
    import json

    try:
        # === STAGE 1: Parallel fetch all layers ===
        logger.info(f"[RefreshJob {job_id}] Starting Phase 1: parallel fetch...")
        update_refresh_job(job_id, status='running')

        all_jobs = fetch_all_jobs(profile, config)

        # === STAGE 2: Apply filters + rule-based scoring ===
        logger.info(f"[RefreshJob {job_id}] Stage 2: applying filters...")
        from app.services.blacklist_engine import apply_blacklist_filters
        from app.services.deduplicator import deduplicate_jobs
        from app.services.scorer import score_jobs

        all_jobs = apply_blacklist_filters(all_jobs)
        all_jobs = deduplicate_jobs(all_jobs)
        all_jobs = score_jobs(all_jobs)

        # Store jobs with rule-based scores (AI pending)
        new_count = _store_jobs(all_jobs)

        update_refresh_job(
            job_id,
            jobs_fetched=len(all_jobs),
            jobs_new=new_count
        )

        # === STAGE 3: AI scoring (top 16 jobs) ===
        logger.info(f"[RefreshJob {job_id}] Stage 3: AI scoring top jobs...")
        update_refresh_job(job_id, status='ai_scoring')

        from app.services.ai_agent import score_jobs_with_ai

        top_jobs = sorted(all_jobs, key=lambda j: j.get("match_score", 0), reverse=True)[:16]
        if top_jobs:
            ai_results = score_jobs_with_ai(top_jobs)
            ai_count = 0
            # Update jobs with AI scores in DB
            with get_connection() as conn:
                for job in ai_results:
                    if "ai_score" in job:
                        conn.execute("""
                            UPDATE jobs
                            SET ai_score = ?, ai_reason = ?
                            WHERE source_url = ?
                        """, (job.get("ai_score"), job.get("ai_reason", ""), job.get("source_url")))
                        ai_count += 1
                conn.commit()
            update_refresh_job(job_id, jobs_ai_scored=ai_count)

        # === Completion ===
        logger.info(f"[RefreshJob {job_id}] Refresh complete!")
        elapsed = int(_time_module.time() - datetime.fromisoformat(get_refresh_job(job_id)["started_at"]).timestamp())
        update_refresh_job(
            job_id,
            status='completed',
            duration_sec=elapsed,
            completed_at=datetime.utcnow().isoformat()
        )

    except Exception as e:
        logger.exception(f"[RefreshJob {job_id}] Background refresh failed: {e}")
        update_refresh_job(
            job_id,
            status='failed',
            error_message=str(e)[:500],
            completed_at=datetime.utcnow().isoformat()
        )


def get_refresh_job(job_id):
    """Fetch refresh job details (for polling endpoint)."""
    from app.database import get_refresh_job as db_get_refresh_job
    return db_get_refresh_job(job_id)
