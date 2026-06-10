"""
JobRadar ATS Fetcher (with Dynamic Filtering)
Fetches jobs from Greenhouse, Lever, and Ashby public APIs.
Filters based on the user's profile: seniority level, tech stack, and skill overlap.

All free, no API key required.

Patch 1: Parallelized company probing within each ATS platform.
"""
import re
import json
import time
import html
import logging
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)



# ============================================================
# Company → ATS Mapping
# ============================================================

GREENHOUSE_COMPANIES = {
    "Stripe": "stripe",
    "Cloudflare": "cloudflare",
    "Coinbase": "coinbase",
    "Figma": "figma",
    "Discord": "discord",
    "Brex": "brex",
    "Airtable": "airtable",
    "Webflow": "webflow",
    "HashiCorp": "hashicorp",
    "GitLab": "gitlab",
    "Grafana Labs": "grafanalabs",
    "Postman": "postman",
    "Snyk": "snyk",
    "LaunchDarkly": "launchdarkly",
    "Kong": "kong",
    "PlanetScale": "planetscale",
    "Sourcegraph": "sourcegraph",
    "Vercel": "vercel",
    "Railway": "railway",
    "Retool": "retool",
    "Dbt Labs": "dbtlabs",
    "Supabase": "supabase",
    "Render": "render",
    "Fly.io": "fly-io",
    "Neon": "neon-inc",
    "Turso": "turso",
    "CRED": "cred",
    "Razorpay": "razorpay",
    "Swiggy": "swiggy",
    "Meesho": "meesho",
    "Dream11": "dream11",
    "MPL": "mobilepremierleague",
    "Chargebee": "chargebee",
    "BrowserStack": "browserstack",
    "Setu": "setu",
}

LEVER_COMPANIES = {
    # Issue 4: Removed 12 perma-404 companies (consistently 404 across 6+ sessions):
    # Removed: twilio, shopify, workato, hasura, postman, browserstack, druva,
    #          phonepe, groww, upstox, sliceit, licious
    # Reasoning: Most use different ATSes or in-house portals. Postman moved to Greenhouse.
    "Netflix": "netflix",
    "Atlassian": "atlassian",
    "Spotify": "spotify",
    "Cloudinary": "cloudinary",
    "Freshworks": "freshworks",
}

ASHBY_COMPANIES = {
    "Notion": "notion",      # canonical — removed from Greenhouse
    "Plaid": "plaid",        # canonical — removed from Greenhouse
    "Ramp": "ramp",          # canonical — removed from Greenhouse
    "Linear": "linear",      # canonical — removed from Greenhouse
    "Deel": "deel",
    "Vanta": "vanta",
    "Sardine": "sardine",
    "Assembled": "assembled",
    "Hightouch": "hightouch",
    "Airbyte": "airbyte",
}


# ============================================================
# Dynamic Company Loading from Database (UNION Pattern)
# ============================================================

def _load_companies_for_ats(ats_name: str) -> dict:
    """
    Load companies for an ATS as UNION of:
      1. Hardcoded baseline (always present, known-good, source of truth)
      2. DB-discovered companies from company_registry (probe results, auto-discovery)

    This guarantees we never regress from removing known-working companies,
    while still letting the registry grow organically.

    Args:
        ats_name: One of "greenhouse", "lever", "ashby", "workable", "smartrecruiters"

    Returns:
        Dict of {company_name: slug, ...} combining hardcoded + DB discoveries
    """
    # Move these imports inside the function to break the circular dependency.
    # workable_fetcher and smartrecruiters_fetcher import ProfileFilter from here at top-level.
    from app.services.workable_fetcher import WORKABLE_COMPANIES
    from app.services.smartrecruiters_fetcher import SMARTRECRUITERS_COMPANIES

    # Convert list constants to dicts for UNION consistency {Title: slug}
    workable_dict = {slug.title(): slug for slug in WORKABLE_COMPANIES}
    smartrecruiters_dict = {slug.title(): slug for slug in SMARTRECRUITERS_COMPANIES}

    # Hardcoded baseline from each fetcher file
    HARDCODED_COMPANIES = {
        "greenhouse": GREENHOUSE_COMPANIES,
        "lever": LEVER_COMPANIES,
        "ashby": ASHBY_COMPANIES,
        "workable": workable_dict,
        "smartrecruiters": smartrecruiters_dict,
    }

    hardcoded = HARDCODED_COMPANIES.get(ats_name, {})
    if not hardcoded:
        return {}

    # Load DB discoveries (only companies with job_count > 0)
    db_companies = {}
    try:
        from app.database import get_connection
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT name, slug FROM company_registry WHERE ats = ? AND job_count > 0",
                (ats_name,)
            ).fetchall()
            if rows:
                db_companies = {row["name"]: row["slug"] for row in rows}
    except Exception as e:
        logger.debug(f"[ats_fetcher] DB lookup failed for {ats_name}: {e}")

    # UNION: hardcoded takes precedence, DB adds new discoveries
    combined = {**db_companies, **hardcoded}  # hardcoded overwrites DB if slug collision

    logger.debug(
        f"[ats_fetcher] {ats_name}: {len(hardcoded)} hardcoded + "
        f"{len(db_companies)} from DB = {len(combined)} total companies"
    )
    return combined


# ============================================================
# Dynamic Profile Filter
# ============================================================

class ProfileFilter:
    """
    Dynamic filter based on the user's parsed resume profile.
    Determines what jobs to keep/reject based on seniority, stack, and skill overlap.
    """

    # Seniority keywords mapped to minimum years of experience typically required
    SENIORITY_MAP = {
        "intern": 0,
        "trainee": 0,
        "fresher": 0,
        "junior": 0,
        "jr": 0,
        "associate": 0,
        "entry": 0,
        # Mid-level (no prefix) = 2-5 years — always included
        "senior": 5,
        "sr": 5,
        "staff": 8,
        "principal": 10,
        "distinguished": 15,
        "fellow": 15,
        "lead": 5,
        "head": 8,
        "director": 10,
        "vp": 12,
        "vice president": 12,
        "cto": 12,
        "cio": 12,
        "manager": 5,
        "engineering manager": 6,
    }

    # Stack/domain keywords — used to detect what domain a job belongs to
    STACK_DOMAINS = {
        "frontend": {"react", "angular", "vue", "svelte", "next.js", "css", "html",
                      "tailwind", "redux", "frontend", "front-end", "ui", "ux"},
        "backend": {"spring", "spring boot", "django", "flask", "node.js", "express",
                     "fastapi", "rest api", "microservices", "kafka", "redis", "java",
                     "go", "golang", "python", "ruby", "backend", "back-end"},
        "fullstack": {"full stack", "fullstack", "full-stack"},
        "mobile": {"ios", "android", "swift", "kotlin", "react native", "flutter",
                    "swiftui", "jetpack compose", "mobile"},
        "devops": {"devops", "sre", "kubernetes", "k8s", "terraform", "ansible",
                    "aws", "azure", "gcp", "ci/cd", "infrastructure", "platform"},
        "data": {"data science", "data engineer", "machine learning", "ml ",
                  "deep learning", "tensorflow", "pytorch", "pandas", "spark",
                  "hadoop", "data analyst", "analytics", "nlp", "ai "},
        "security": {"security", "cybersecurity", "infosec", "penetration",
                      "vulnerability", "soc ", "security engineer"},
        "qa": {"qa", "quality", "test engineer", "sdet", "automation test",
                "selenium", "cypress", "testing"},
    }

    def __init__(self, profile):
        self.profile = profile
        self.schema_version = profile.get("schema_version", 1)
        self.exp_years = float(profile.get("experience_years", 0))
        self.role = (profile.get("primary_role", "") or "").lower()
        self.location = (profile.get("location", "") or "").lower()

        # A1: Support tiered skills (v2) or flat skills (v1)
        if self.schema_version >= 2:
            self._init_v2_skills(profile)
        else:
            self._init_v1_skills(profile)

        # Detect user's primary stack domains
        self.user_domains = self._detect_user_domains()

        # Calculate max seniority the user qualifies for
        self.max_seniority_years = self.exp_years + 2  # Allow 2 years stretch

        logger.info(f"ProfileFilter: schema_v{self.schema_version}, {self.exp_years}yr exp, "
                     f"domains={self.user_domains}, {len(self.all_skills)} skills tracked")

    def _init_v1_skills(self, profile):
        """Initialize flat skill lists for v1 profiles."""
        self.core_skills = self._parse_list(profile.get("core_skills", []))
        self.secondary_skills = self._parse_list(profile.get("secondary_skills", []))
        self.tools = self._parse_list(profile.get("tools", []))
        self.deal_breakers = []

        # Build skill set for matching (lowercase)
        self.all_skills = set(s.lower() for s in self.core_skills + self.secondary_skills + self.tools)
        self.core_skills_lower = set(s.lower() for s in self.core_skills)

    def _init_v2_skills(self, profile):
        """Initialize tiered skill lists for v2 profiles (A1)."""
        # Parse tiered skills
        skills_tiered = self._parse_json(profile.get("skills_tiered", "{}"))
        primary = skills_tiered.get("primary", []) if isinstance(skills_tiered, dict) else []
        familiar = skills_tiered.get("familiar", []) if isinstance(skills_tiered, dict) else []
        learning = skills_tiered.get("learning", []) if isinstance(skills_tiered, dict) else []

        # Extract skill names from tiered structure (may be dicts with metadata)
        self.core_skills = [s.get("name", s) if isinstance(s, dict) else s for s in primary]
        self.secondary_skills = [s.get("name", s) if isinstance(s, dict) else s for s in familiar]
        self.learning_skills = learning if isinstance(learning, list) else []
        self.tools = self._parse_list(profile.get("tools", []))

        # Build skill set (lowercase)
        all_skill_list = self.core_skills + self.secondary_skills + self.learning_skills + self.tools
        self.all_skills = set(s.lower() for s in all_skill_list)
        self.core_skills_lower = set(s.lower() for s in self.core_skills)

        # A1: Extract deal-breakers from preferences
        preferences = self._parse_json(profile.get("preferences_explicit", "{}"))
        self.deal_breakers = preferences.get("deal_breakers", []) if isinstance(preferences, dict) else []

    def should_keep(self, title, description=""):
        """
        Decide whether to keep a job based on profile matching.
        Returns (keep: bool, reason: str)

        A1: Checks deal-breakers first (hard rejects)
        """
        title_lower = title.lower()
        desc_lower = description.lower() if description else ""
        searchable = title_lower + " " + desc_lower

        # ── A1: Check 0: Deal-breaker hard filter ──
        for breaker in self.deal_breakers:
            if breaker and breaker.lower() in searchable:
                return False, f"deal_breaker:{breaker}"

        # ── Check 1: Seniority filter ──
        seniority_ok, seniority_reason = self._check_seniority(title_lower)
        if not seniority_ok:
            return False, seniority_reason

        # ── Check 2: Must be a tech/relevant role ──
        if not self._is_relevant_role(title_lower):
            return False, "not_tech_role"

        # ── Check 3: Stack/domain compatibility ──
        stack_ok, stack_reason = self._check_stack(title_lower, searchable)
        if not stack_ok:
            return False, stack_reason

        # ── Check 4: Minimum skill overlap ──
        # A1: For v2 profiles, require at least one primary skill match
        if self.schema_version >= 2:
            primary_matches = sum(1 for s in self.core_skills_lower if s in searchable)
            if primary_matches < 1:
                # Fall back to role matching if no primary skills match
                if not self._role_matches(title_lower):
                    return False, "no_primary_skill_match"
        else:
            matching_skills = self._count_skill_matches(searchable)
            if matching_skills < 1:
                # If no skills match at all, check if role title matches
                if not self._role_matches(title_lower):
                    return False, "no_skill_overlap"

        return True, "passed"

    def _check_seniority(self, title_lower):
        """Check if the job's seniority level matches the user's experience."""
        for keyword, min_years in self.SENIORITY_MAP.items():
            # Use word boundary to avoid false matches
            if re.search(r'\b' + re.escape(keyword) + r'\b', title_lower):
                if min_years > self.max_seniority_years:
                    return False, f"seniority_too_high:{keyword}({min_years}yr)"
        return True, "ok"

    def _is_relevant_role(self, title_lower):
        """Check if the title contains any tech/engineering role keyword."""
        role_keywords = {
            "developer", "engineer", "programmer", "architect",
            "sde", "swe", "devops", "sre", "qa", "tester",
            "full stack", "fullstack", "frontend", "front-end",
            "backend", "back-end", "software", "data", "cloud",
            "platform", "infrastructure", "security", "mobile",
            "web", "analyst", "consultant", "designer",
            "scientist", "ml ", "ai ", "intern", "trainee",
        }
        return any(kw in title_lower for kw in role_keywords)

    def _check_stack(self, title_lower, searchable):
        """
        Check if the job's tech stack/domain is compatible with the user's.
        
        Logic:
        - If user is "fullstack" → accept frontend, backend, and fullstack jobs
        - If user is "backend" → accept backend and fullstack, reject mobile/iOS
        - If user is "frontend" → accept frontend and fullstack, reject mobile
        - Always reject completely unrelated domains (mobile when you're backend, etc.)
        """
        # Detect what domain this job belongs to
        job_domains = set()
        for domain, keywords in self.STACK_DOMAINS.items():
            if any(kw in title_lower for kw in keywords):
                job_domains.add(domain)

        # If we can't detect the job's domain, let it through (benefit of doubt)
        if not job_domains:
            return True, "ok"

        # If we don't know the user's domain, let it through
        if not self.user_domains:
            return True, "ok"

        # Define compatibility rules
        compatibility = {
            "fullstack": {"fullstack", "frontend", "backend", "devops", "qa"},
            "backend": {"backend", "fullstack", "devops", "qa", "data"},
            "frontend": {"frontend", "fullstack", "qa"},
            "mobile": {"mobile", "fullstack", "frontend"},
            "devops": {"devops", "backend", "fullstack", "security"},
            "data": {"data", "backend", "fullstack"},
            "security": {"security", "devops", "backend"},
            "qa": {"qa", "fullstack", "frontend", "backend"},
        }

        # Get all compatible domains for the user
        user_compatible = set()
        for ud in self.user_domains:
            user_compatible.update(compatibility.get(ud, {ud}))

        # Check if any of the job's domains are compatible
        if job_domains & user_compatible:
            return True, "ok"

        return False, f"stack_mismatch:job={job_domains},user={self.user_domains}"

    def _count_skill_matches(self, searchable):
        """Count how many of the user's skills appear in the job text."""
        count = 0
        for skill in self.all_skills:
            if len(skill) <= 2:
                # Short skills need word boundary
                if re.search(r'\b' + re.escape(skill) + r'\b', searchable):
                    count += 1
            else:
                if skill in searchable:
                    count += 1
        return count

    def _role_matches(self, title_lower):
        """Check if the job title matches the user's role."""
        if not self.role:
            return False
        role_words = set(self.role.split())
        title_words = set(title_lower.split())
        return len(role_words & title_words) >= 2

    def _detect_user_domains(self):
        """Detect which stack domains the user belongs to based on skills and role."""
        domains = set()

        # Check role first
        for domain, keywords in self.STACK_DOMAINS.items():
            if any(kw in self.role for kw in keywords):
                domains.add(domain)

        # Check skills
        for domain, keywords in self.STACK_DOMAINS.items():
            matching = sum(1 for kw in keywords if kw in self.core_skills_lower)
            if matching >= 2:
                domains.add(domain)

        # If "full stack" detected, add it explicitly
        if "fullstack" in domains or ("frontend" in domains and "backend" in domains):
            domains.add("fullstack")

        return domains if domains else {"fullstack"}  # Default to fullstack if unclear

    @staticmethod
    def _parse_list(value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @staticmethod
    def _parse_json(value):
        """Parse JSON field (dict or string)."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}


# ============================================================
# Greenhouse Fetcher
# ============================================================

def fetch_greenhouse_jobs(profile, delay=0.2):
    """
    Fetch and filter jobs from Greenhouse companies.

    Patch 1: Probes companies IN PARALLEL (max 10 workers) instead of sequentially.
    """
    import requests

    pf = ProfileFilter(profile)
    companies = _load_companies_for_ats("greenhouse")

    if not companies:
        return []

    all_jobs = []
    kept_total = 0
    filtered_total = 0

    # Patch 1: Parallel company probing with ThreadPoolExecutor
    logger.info(f"Greenhouse: Probing {len(companies)} companies in parallel")
    with ThreadPoolExecutor(max_workers=10, thread_name_prefix="gh") as executor:
        futures = {
            executor.submit(_fetch_one_greenhouse_company, company_name, board_token, pf): company_name
            for company_name, board_token in companies.items()
        }

        for future in as_completed(futures):
            company_name = futures[future]
            try:
                jobs, kept, filtered = future.result(timeout=20)
                all_jobs.extend(jobs)
                kept_total += kept
                filtered_total += filtered
            except Exception as e:
                logger.warning(f"Greenhouse {company_name} error: {e}")

    logger.info(f"Greenhouse: {kept_total} kept, {filtered_total} filtered out, from {len(companies)} companies (parallel)")
    return all_jobs


def _fetch_one_greenhouse_company(company_name: str, board_token: str, pf) -> tuple:
    """
    Fetch jobs from one Greenhouse company and filter them.

    Patch 1: Helper for parallel company probing.

    Returns:
        Tuple of (jobs_list, kept_count, filtered_count)
    """
    import requests

    jobs = []
    kept = 0
    filtered = 0

    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        resp = requests.get(url, verify=False, timeout=15, headers={
            "User-Agent": "JobRadar/1.0 (personal job search tool)"
        })

        if resp.status_code != 200:
            return jobs, kept, filtered

        data = resp.json()
        jobs_list = data.get("jobs", [])

        for job in jobs_list:
            title = job.get("title", "")
            content = job.get("content", "")
            job_location = job.get("location", {}).get("name", "")

            # Clean HTML from content
            clean_content = html.unescape(content) if content else ""
            clean_content = re.sub(r"<[^>]+>", " ", clean_content)
            clean_content = re.sub(r"\s+", " ", clean_content).strip()

            # ── Dynamic filtering ──
            keep, reason = pf.should_keep(title, clean_content)
            if not keep:
                filtered += 1
                continue

            # Find matching skills for display
            searchable = (title + " " + clean_content).lower()
            matching_skills = [s for s in pf.core_skills if s.lower() in searchable]

            jobs.append({
                "title": title[:150],
                "company": company_name,
                "location": job_location[:100],
                "source_url": job.get("absolute_url", ""),
                "source_domain": "greenhouse.io",
                "description_snippet": clean_content[:300],
                "posted_date": job.get("updated_at", "")[:10],
                "skills_found": json.dumps(matching_skills[:8]),
            })
            kept += 1

    except Exception as e:
        logger.debug(f"[gh] {company_name}: {e}")

    return jobs, kept, filtered


# ============================================================
# Lever Fetcher
# ============================================================

def fetch_lever_jobs(profile, delay=0.5):
    """
    Fetch and filter jobs from Lever companies.

    Patch 1: Probes companies IN PARALLEL (max 5 workers) instead of sequentially.
    """
    import requests

    pf = ProfileFilter(profile)
    companies = _load_companies_for_ats("lever")

    if not companies:
        return []

    all_jobs = []
    kept_total = 0
    filtered_total = 0

    # Patch 1: Parallel company probing
    logger.info(f"Lever: Probing {len(companies)} companies in parallel")
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="lever") as executor:
        futures = {
            executor.submit(_fetch_one_lever_company, company_name, slug, pf): company_name
            for company_name, slug in companies.items()
        }

        for future in as_completed(futures):
            company_name = futures[future]
            try:
                jobs, kept, filtered = future.result(timeout=20)
                all_jobs.extend(jobs)
                kept_total += kept
                filtered_total += filtered
            except Exception as e:
                logger.warning(f"Lever {company_name} error: {e}")

    logger.info(f"Lever: {kept_total} kept, {filtered_total} filtered out, from {len(companies)} companies (parallel)")
    return all_jobs


def _fetch_one_lever_company(company_name: str, slug: str, pf) -> tuple:
    """
    Fetch jobs from one Lever company and filter them.

    Patch 1: Helper for parallel company probing.

    Returns:
        Tuple of (jobs_list, kept_count, filtered_count)
    """
    import requests

    jobs = []
    kept = 0
    filtered = 0

    try:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        resp = requests.get(url, verify=False, timeout=15, headers={
            "User-Agent": "JobRadar/1.0 (personal job search tool)"
        })

        if resp.status_code != 200:
            return jobs, kept, filtered

        postings = resp.json()
        if not isinstance(postings, list):
            return jobs, kept, filtered

        for posting in postings:
            title = posting.get("text", "")
            categories = posting.get("categories", {})
            department = categories.get("department", "")
            team = categories.get("team", "")
            job_location = categories.get("location", "")
            desc_text = posting.get("descriptionPlain", "")

            searchable = f"{title} {department} {team} {desc_text}"

            # ── Dynamic filtering ──
            keep, reason = pf.should_keep(title, searchable)
            if not keep:
                filtered += 1
                continue

            # Find matching skills
            searchable_lower = searchable.lower()
            matching_skills = [s for s in pf.core_skills if s.lower() in searchable_lower]

            apply_url = posting.get("hostedUrl", "") or posting.get("applyUrl", "")

            jobs.append({
                "title": title[:150],
                "company": company_name,
                "location": job_location[:100],
                "source_url": apply_url,
                "source_domain": "lever.co",
                "description_snippet": desc_text[:300],
                "posted_date": "",
                "skills_found": json.dumps(matching_skills[:8]),
            })
            kept += 1

    except Exception as e:
        logger.debug(f"[lever] {company_name}: {e}")

    return jobs, kept, filtered


# ============================================================
# Ashby Fetcher
# ============================================================

def fetch_ashby_jobs(profile, delay=0.5):
    """
    Fetch and filter jobs from Ashby companies.

    Patch 1: Probes companies IN PARALLEL (max 6 workers) instead of sequentially.
    """
    import requests

    pf = ProfileFilter(profile)
    companies = _load_companies_for_ats("ashby")

    if not companies:
        return []

    all_jobs = []
    kept_total = 0
    filtered_total = 0

    # Patch 1: Parallel company probing
    logger.info(f"Ashby: Probing {len(companies)} companies in parallel")
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="ashby") as executor:
        futures = {
            executor.submit(_fetch_one_ashby_company, company_name, slug, pf): company_name
            for company_name, slug in companies.items()
        }

        for future in as_completed(futures):
            company_name = futures[future]
            try:
                jobs, kept, filtered = future.result(timeout=20)
                all_jobs.extend(jobs)
                kept_total += kept
                filtered_total += filtered
            except Exception as e:
                logger.warning(f"Ashby {company_name} error: {e}")

    logger.info(f"Ashby: {kept_total} kept, {filtered_total} filtered out, from {len(companies)} companies (parallel)")
    return all_jobs


def _fetch_one_ashby_company(company_name: str, slug: str, pf) -> tuple:
    """
    Fetch jobs from one Ashby company and filter them.

    Patch 1: Helper for parallel company probing.

    Returns:
        Tuple of (jobs_list, kept_count, filtered_count)
    """
    import requests

    jobs = []
    kept = 0
    filtered = 0

    try:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
        resp = requests.get(url, verify=False, timeout=15, headers={
            "User-Agent": "JobRadar/1.0 (personal job search tool)"
        })

        if resp.status_code != 200:
            return jobs, kept, filtered

        data = resp.json()
        jobs_list = data.get("jobs", [])

        for job in jobs_list:
            title = job.get("title", "")
            job_location = job.get("location", "")
            desc_plain = job.get("descriptionPlain", "")
            desc_html = job.get("descriptionHtml", "")
            job_url = job.get("jobUrl", "")
            apply_url = job.get("applyUrl", "")
            department = job.get("department", "")
            compensation = job.get("compensation", {})

            # Clean description
            if desc_plain:
                clean_desc = desc_plain
            elif desc_html:
                clean_desc = html.unescape(desc_html)
                clean_desc = re.sub(r"<[^>]+>", " ", clean_desc)
                clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
            else:
                clean_desc = ""

            searchable = f"{title} {department} {clean_desc}"

            # ── Dynamic filtering ──
            keep, reason = pf.should_keep(title, searchable)
            if not keep:
                filtered += 1
                continue

            # Find matching skills
            searchable_lower = searchable.lower()
            matching_skills = [s for s in pf.core_skills if s.lower() in searchable_lower]

            # Extract salary info if available
            salary_info = ""
            if compensation:
                salary_summary = compensation.get("compensationTierSummary", "")
                if salary_summary:
                    salary_info = f" | Compensation: {salary_summary}"

            jobs.append({
                "title": title[:150],
                "company": company_name,
                "location": job_location[:100] if isinstance(job_location, str) else "",
                "source_url": job_url or apply_url,
                "source_domain": "ashbyhq.com",
                "description_snippet": (clean_desc[:280] + salary_info)[:300],
                "posted_date": job.get("publishedAt", "")[:10] if job.get("publishedAt") else "",
                "skills_found": json.dumps(matching_skills[:8]),
            })
            kept += 1

    except Exception as e:
        logger.debug(f"[ashby] {company_name}: {e}")

    return jobs, kept, filtered
