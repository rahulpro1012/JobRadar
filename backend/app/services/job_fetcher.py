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
Layer 9:   Bing API (disabled — not using)
Layer 10:  DuckDuckGo (disabled, kept for future)
── Phase 1 additions ──
Layer 11:  RemoteOK (free, no key — worldwide remote jobs)
Layer 12:  HackerNews "Who is Hiring" (free, Algolia API — YC/startup remote jobs)
Layer 13:  Arbeitnow (free, no key — global remote job board)
Layer 14:  Adzuna India (free key required — India aggregator with salary data)
── Phase 2 additions ──
Layer 15:  Workable ATS (free, no key — remote-first startups)
Layer 16:  SmartRecruiters ATS (free, no key — enterprise companies)
Layer 17:  Recruitee ATS (free, no key — European startups)
── Phase 3 additions ──
Layer 18:  LinkedIn jobs-guest (free, no auth — India + Remote jobs)
Layer 19:  Naukri JSON API (undocumented, India-specific)
── Tier 3a addition ──
Layer 20:  Indian Unicorn Fetcher (SearxNG site: search on 35+ Indian unicorn careers pages)
── Tier 3b addition ──
Layer 21:  Razorpay Direct (direct career page scraping)
Layer 22:  Swiggy Direct (direct career page scraping)
Layer 23:  CRED Direct (direct career page scraping)
Layer 24:  PhonePe Direct (direct career page scraping)
Layer 25:  Zomato Direct (direct career page scraping)

── DISABLED (damage control) ──
Brave Search: Not using (no key configured)
Bing API: Not using (no key configured)
Indian Unicorns: 117s for 0 jobs
Career Pages: 0 jobs
Direct Scrapers (5): 0 jobs, placeholder selectors
Naukri (4 locations): HTTP 406 blocks, perma-open circuit breaker
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


def fetch_all_jobs(profile, config, job_id=None):
    """
    ── PHASE 1: PARALLEL LAYER EXECUTION ──
    Fetch from ALL 16 layers in parallel using ThreadPoolExecutor.
    Expected time: ~45-60 sec (bounded by slowest layer, typically ATS at ~50s).

    If job_id is provided (async refresh), per-layer progress is written to the
    refresh_jobs row so the frontend loader can show live source counts.

    Previously: ~3 min 10 sec (sequential execution)

    A2: Uses source-aware queries if AI enabled, falls back to legacy query_engine
    """
    # A2: Try source-aware query generation first
    queries_by_source = None
    try:
        from app.services.ai_agent import ai_generate_source_aware_queries, is_ai_enabled
        if is_ai_enabled():
            queries_by_source = ai_generate_source_aware_queries(profile, search_locations=_get_search_locations(profile))
            logger.info(f"A2: Generated source-aware queries: {sum(len(q) for q in queries_by_source.values())} total")
    except Exception as e:
        logger.debug(f"A2: Failed to generate source-aware queries: {e}")

    # Fallback: legacy query engine if A2 not available
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

    # ❌ DISABLED 2026-06-08: Has returned 0 jobs in every log analyzed.
    # Career Pages layer was a search-URL generator but never produced fetchable jobs.
    #
    # layers.append(("Career Pages", _fetch_from_career_pages, {"profile": profile}))

    # ── Layer 7: SearxNG (RE-ENABLED - uses self-hosted instance from SEARXNG_URL) ──
    searxng_url = config.get("SEARXNG_URL", "")
    if searxng_url:
        from app.services.search_fetcher import fetch_from_searxng
        # A2: Use ATS-specific queries for SearxNG
        ats_search_queries = queries_by_source.get("ats_search", []) if queries_by_source else []
        if not ats_search_queries:
            ats_search_queries = _build_portal_queries(profile, queries, search_locations)
        layers.append(("SearxNG (Naukri + LinkedIn)", fetch_from_searxng, {"queries": ats_search_queries, "delay": 1.5}))
    else:
        logger.debug("Layer 7: SearxNG disabled (set SEARXNG_URL in .env to enable)")

    # ── Layer 8: Yahoo ──
    from app.services.search_fetcher import fetch_from_yahoo
    # A2: Use ATS-specific queries for Yahoo
    yahoo_qs = queries_by_source.get("ats_search", []) if queries_by_source else []
    if not yahoo_qs:
        yahoo_qs = _build_portal_queries(profile, queries, search_locations)
    yahoo_q = yahoo_qs[:4]
    layers.append(("Yahoo", fetch_from_yahoo, {"queries": yahoo_q, "delay": 1.5}))

    # ❌ DISABLED 2026-06-08: Not using Bing API (no key configured, low priority)
    # bing_key = config.get("BING_API_KEY", "")
    # if bing_key:
    #     today_usage = get_quota_usage("bing")
    #     remaining = QUOTA_LIMITS["bing"] - today_usage
    #     if remaining > 0:
    #         def _fetch_bing_safe():
    #             jobs = []
    #             try:
    #                 top_queries = [q for q in queries if q["tier"] <= 2][:3]
    #                 site_queries = generate_site_queries(top_queries, ["naukri.com", "indeed.co.in"])
    #                 max_calls = min(6, remaining, len(site_queries))
    #                 for sq in site_queries[:max_calls]:
    #                     jobs.extend(_fetch_from_bing(sq["site_query"], bing_key, scrape_delay))
    #             except Exception as e:
    #                 logger.warning(f"Bing failed: {e}")
    #             return jobs
    #         layers.append(("Bing", _fetch_bing_safe, {}))

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
        # A2: Use Adzuna-specific queries (no city names, no quotes)
        adzuna_qs = queries_by_source.get("adzuna", []) if queries_by_source else []
        if not adzuna_qs:
            adzuna_qs = queries
        layers.append(("Adzuna", fetch_adzuna_jobs, {"profile": profile, "queries": adzuna_qs, "config": config, "delay": scrape_delay}))

    # ── Layer 18: LinkedIn jobs-guest ──
    from app.services.linkedin_guest_fetcher import fetch_linkedin_guest_jobs
    # A2: Use LinkedIn-specific queries (short, max 4 words, no quotes)
    linkedin_qs = queries_by_source.get("linkedin", []) if queries_by_source else []
    if not linkedin_qs:
        linkedin_qs = [q["query"] if isinstance(q, dict) else q for q in queries]
    layers.append(("LinkedIn Guest", fetch_linkedin_guest_jobs, {"profile": profile, "queries": linkedin_qs, "location": "Pune", "max_pages": 2}))

    # ❌ DISABLED 2026-06-08: Naukri direct API blocks our requests (HTTP 406).
    # Circuit breaker has been perma-open for 4 sessions. Header variations tried: none work.
    # Naukri likely requires browser session cookies or JS challenge.
    # Note: We still get ~45 Naukri jobs per refresh via Jooble/Yahoo/SearxNG aggregation.
    # To re-enable: Build Playwright-based scraper with real browser session (4-6 hours, separate project).
    #
    # from app.services.naukri_fetcher import fetch_naukri_jobs
    # naukri_queries = [q["query"] if isinstance(q, dict) else q for q in queries]
    # for naukri_loc in ["pune", "delhi", "bangalore", "mumbai"]:
    #     layers.append((f"Naukri ({naukri_loc.title()})", fetch_naukri_jobs, {"profile": profile, "queries": naukri_queries, "location": naukri_loc, "max_pages": 1}))

    # ❌ DISABLED 2026-06-08: 117s for 0 jobs across multiple sessions.
    # Queries with exact-match quotes (e.g., "engineer") rarely match SearxNG index.
    # site:domain.com doesn't deep-index careers subpages. Sequential calls (100 SearxNG calls back-to-back).
    # To re-enable: Drop quotes from queries, use site:domain.com/jobs scoping, parallelize with ThreadPoolExecutor, cap to 5 companies.
    #
    # from app.services.indian_unicorn_fetcher import fetch_indian_unicorns
    # layers.append(("Indian Unicorns", fetch_indian_unicorns, {"profile": profile, "max_companies": 20}))

    # ❌ DISABLED 2026-06-08: All 5 scrapers shipped with placeholder CSS selectors.
    # Razorpay/Swiggy/PhonePe/Zomato: returned 0 jobs, results cached as empty for 6h.
    # CRED: URL outdated (cred.club/careers → 404, real URL is careers.cred.club).
    # To re-enable: Visit careers page, get real selectors via DevTools, update parse_jobs(), test locally, then uncomment.
    #
    # from app.services.scrapers.razorpay_scraper import fetch_razorpay
    # from app.services.scrapers.swiggy_scraper import fetch_swiggy
    # from app.services.scrapers.cred_scraper import fetch_cred
    # from app.services.scrapers.phonepe_scraper import fetch_phonepe
    # from app.services.scrapers.zomato_scraper import fetch_zomato
    #
    # layers.append(("Razorpay Direct", fetch_razorpay, {"profile": profile}))
    # layers.append(("Swiggy Direct", fetch_swiggy, {"profile": profile}))
    # layers.append(("CRED Direct", fetch_cred, {"profile": profile}))
    # layers.append(("PhonePe Direct", fetch_phonepe, {"profile": profile}))
    # layers.append(("Zomato Direct", fetch_zomato, {"profile": profile}))

    # ❌ DISABLED 2026-06-08: Not using Brave Search API (no key configured, low priority)
    # brave_key = config.get("BRAVE_SEARCH_API_KEY", "")
    # if brave_key:
    #     from app.services.brave_search_fetcher import fetch_brave_search_jobs
    #     brave_queries = [q["query"] if isinstance(q, dict) else q for q in queries]
    #     layers.append(("Brave Search", fetch_brave_search_jobs, {"profile": profile, "queries": brave_queries, "api_key": brave_key, "max_results": 20}))

    # ═══════════════════════════════════════════════════════════════
    # RUN ALL LAYERS IN PARALLEL
    # ═══════════════════════════════════════════════════════════════
    logger.info(f"Phase 1: Parallel fetch from {len(layers)} layers (max_workers=12, timeout=90s per layer)...")

    # Async progress: seed the real layer count so the loader can show N/total
    if job_id:
        from app.database import update_refresh_job
        update_refresh_job(job_id, sources_total=len(layers), sources_done=0, jobs_fetched=0)

    all_jobs = []
    done = 0
    failed = 0
    per_source = {}
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
                per_source[name] = len(jobs)
                logger.info(f"  [{name}] {len(jobs)} jobs ({elapsed:.1f}s)")
            except Exception as e:
                logger.warning(f"  [{name}] failed: {e}")
                layer_timings[name] = (0, -1)
                per_source[name] = 0
                failed += 1
            finally:
                done += 1
                # Async progress: push live source/jobs counts to the refresh_jobs row
                if job_id:
                    update_refresh_job(
                        job_id,
                        sources_done=done,
                        sources_failed=failed,
                        jobs_fetched=len(all_jobs),
                        per_source_json=json.dumps(per_source),
                    )

    logger.info(f"Phase 1 complete: {len(all_jobs)} total jobs from {len(layers)} layers")
    logger.debug(f"Per-layer timing: {layer_timings}")

    # ── Phase 2: Persistent Company Discovery (Patch 2: Parallel) ──
    # Auto-grow ATS registry by probing companies found in search results
    try:
        from app.services.company_discovery import discover_companies_batch_parallel
        search_source_jobs = [
            j for j in all_jobs
            if j.get("source_domain") in (
                "linkedin.com",
                "naukri.com",
                "brave.com",
                "searxng",
                "yahoo.com",
            )
        ]
        if search_source_jobs:
            # Extract company names (parallel function expects list of strings, not job dicts)
            candidate_names = [j.get("company", "").strip() for j in search_source_jobs if j.get("company")]
            # Remove duplicates while preserving order
            candidate_names = list(dict.fromkeys(candidate_names))

            if candidate_names:
                result = discover_companies_batch_parallel(candidate_names, max_workers=8)
                if result["discovered"] > 0:
                    logger.info(f"Phase 2: Company discovery found {result['discovered']} new companies "
                               f"(rejected {result['rejected']} garbage names)")
    except Exception as e:
        logger.warning(f"Phase 2 (company discovery) error: {e}")

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
# Retention / cleanup
# ============================================================

def purge_old_jobs(days=None):
    """Delete jobs older than `days` (by fetched_date). Defaults to the
    retention_days app setting (15 if unset). FK ON DELETE CASCADE cleans up
    job_ai_analysis + user_signals rows. Returns the number deleted."""
    from app.database import get_setting
    if days is None:
        try:
            days = int(get_setting("retention_days", 15))
        except (TypeError, ValueError):
            days = 15
    if days <= 0:
        return 0
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE fetched_date < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        deleted = cur.rowcount
    if deleted:
        logger.info(f"Retention: purged {deleted} jobs older than {days} days")
    return deleted


def purge_jobs(criteria):
    """Manual purge. criteria is one of:
      {"older_than_days": N} | {"status": "..."} | {"source": "..."} | {"all": True}
    Returns the number of jobs deleted."""
    criteria = criteria or {}
    with get_connection() as conn:
        if criteria.get("all"):
            cur = conn.execute("DELETE FROM jobs")
        elif "older_than_days" in criteria:
            days = int(criteria["older_than_days"])
            cur = conn.execute(
                "DELETE FROM jobs WHERE fetched_date < datetime('now', ?)",
                (f"-{days} days",),
            )
        elif criteria.get("status"):
            cur = conn.execute(
                "DELETE FROM jobs WHERE status = ?", (criteria["status"],)
            )
        elif criteria.get("source"):
            cur = conn.execute(
                "DELETE FROM jobs WHERE source_domain LIKE ?",
                (f"%{criteria['source']}%",),
            )
        else:
            return 0
        conn.commit()
        deleted = cur.rowcount
    logger.info(f"Manual purge {criteria} → deleted {deleted} jobs")
    return deleted


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
    from app.database import update_refresh_job, get_connection, execute_query
    import json

    try:
        # === STAGE 1: Parallel fetch all layers ===
        # fetch_all_jobs stores jobs to the DB and returns the new-job COUNT (int),
        # so the rest of the pipeline operates on the DB (mirrors the sync path).
        logger.info(f"[RefreshJob {job_id}] Starting Phase 1: parallel fetch...")
        update_refresh_job(job_id, status='running')

        new_count = fetch_all_jobs(profile, config, job_id=job_id)

        # === STAGE 2: Apply filters + dedup + rule-based scoring (DB-based) ===
        logger.info(f"[RefreshJob {job_id}] Stage 2: applying filters...")
        from app.services.blacklist_engine import apply_blacklist
        from app.services.deduplicator import deduplicate_jobs
        from app.services.scorer import score_all_jobs

        filtered = apply_blacklist()
        deduped = deduplicate_jobs()
        scored = score_all_jobs(profile)
        logger.info(f"[RefreshJob {job_id}] Stage 2 done: {filtered} filtered, {deduped} deduped, {scored} scored")

        update_refresh_job(job_id, jobs_new=new_count)

        # === STAGE 3: C1 AI scoring + structured analysis (top 25 jobs) ===
        logger.info(f"[RefreshJob {job_id}] Stage 3: AI scoring top jobs...")
        update_refresh_job(job_id, status='ai_scoring')

        from app.services.ai_agent import analyze_jobs_batch, is_ai_enabled

        ai_count = 0
        if is_ai_enabled():
            top_jobs = execute_query(
                """SELECT id, title, company, location, description_snippet, match_score
                   FROM jobs WHERE status = 'new'
                   ORDER BY match_score DESC LIMIT 25""",
                fetch_all=True
            )
            if top_jobs:
                analyses = analyze_jobs_batch(top_jobs, profile, batch_size=10)
                if analyses:
                    with get_connection() as conn:
                        for analysis in analyses:
                            jid = analysis["job_id"]
                            ai_score = analysis["score"]
                            base = conn.execute(
                                "SELECT match_score FROM jobs WHERE id = ?", (jid,)
                            ).fetchone()
                            if base:
                                blended = int(base[0] * 0.6 + ai_score * 0.4)
                                conn.execute(
                                    """UPDATE jobs SET adjusted_score = ?, ai_score = ?, ai_reason = ?
                                       WHERE id = ?""",
                                    (blended, ai_score, analysis["fit_summary"], jid)
                                )
                                try:
                                    conn.execute(
                                        """INSERT INTO job_ai_analysis
                                           (job_id, ai_score, apply_reasons, skip_reasons, fit_summary, red_flags, model_used)
                                           VALUES (?, ?, ?, ?, ?, ?, ?)
                                           ON CONFLICT(job_id) DO UPDATE SET
                                           ai_score = excluded.ai_score,
                                           apply_reasons = excluded.apply_reasons,
                                           skip_reasons = excluded.skip_reasons,
                                           fit_summary = excluded.fit_summary,
                                           red_flags = excluded.red_flags,
                                           analyzed_at = datetime('now')""",
                                        (jid, ai_score,
                                         json.dumps(analysis.get("apply_reasons", [])),
                                         json.dumps(analysis.get("skip_reasons", [])),
                                         analysis["fit_summary"],
                                         json.dumps(analysis.get("red_flags", [])),
                                         "llama-3.1-8b-instant")
                                    )
                                except Exception as e:
                                    logger.debug(f"C1: Failed to store analysis for job {jid}: {e}")
                        conn.commit()
                    ai_count = len(analyses)
                    logger.info(f"[RefreshJob {job_id}] C1: Analyzed {ai_count} jobs with structured reasoning")
            update_refresh_job(job_id, jobs_ai_scored=ai_count)

        # === Retention: purge stale jobs to keep the table fresh ===
        try:
            purge_old_jobs()
        except Exception as e:
            logger.warning(f"[RefreshJob {job_id}] retention purge failed: {e}")

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
