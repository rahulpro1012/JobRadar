"""
JobRadar ATS Fetcher (with Dynamic Filtering)
Fetches jobs from Greenhouse, Lever, and Ashby public APIs.
Filters based on the user's profile: seniority level, tech stack, and skill overlap.

All free, no API key required.
"""
import re
import json
import time
import html
import logging
from urllib.parse import urlparse

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
    "Netflix": "netflix",
    "Atlassian": "atlassian",
    "Twilio": "twilio",
    "Spotify": "spotify",
    "Shopify": "shopify",
    "Cloudinary": "cloudinary",
    "Workato": "workato",
    "Hasura": "hasura",
    "Postman": "postman",
    "BrowserStack": "browserstack",
    "Druva": "druva",
    "Freshworks": "freshworks",
    "PhonePe": "phonepe",
    "Groww": "groww",
    "Upstox": "upstox",
    "Slice": "sliceit",
    "Licious": "licious",
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
# Dynamic Company Loading from Database
# ============================================================

def _load_companies_from_db(ats_name: str) -> dict:
    """
    Load companies for a specific ATS from the company_registry database table.
    Falls back to hardcoded company lists if database is empty or unavailable.

    Args:
        ats_name: One of "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"

    Returns:
        Dict of {company_name: slug, ...} or fallback hardcoded dict
    """
    try:
        from app.database import get_connection

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT name, slug FROM company_registry WHERE ats = ? ORDER BY job_count DESC",
                (ats_name,)
            ).fetchall()

            if rows:
                # Build company dict from database
                companies = {row["name"]: row["slug"] for row in rows}
                logger.debug(f"Loaded {len(companies)} companies for {ats_name} from database")
                return companies
    except Exception as e:
        logger.debug(f"Failed to load {ats_name} companies from database: {e}")

    # Fallback to hardcoded lists
    fallback_map = {
        "greenhouse": GREENHOUSE_COMPANIES,
        "lever": LEVER_COMPANIES,
        "ashby": ASHBY_COMPANIES,
    }

    fallback = fallback_map.get(ats_name, {})
    if fallback:
        logger.debug(f"Using hardcoded fallback: {len(fallback)} companies for {ats_name}")
    return fallback


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
        self.exp_years = float(profile.get("experience_years", 0))
        self.core_skills = self._parse_list(profile.get("core_skills", []))
        self.secondary_skills = self._parse_list(profile.get("secondary_skills", []))
        self.tools = self._parse_list(profile.get("tools", []))
        self.role = (profile.get("primary_role", "") or "").lower()
        self.location = (profile.get("location", "") or "").lower()

        # Build skill set for matching (lowercase)
        self.all_skills = set(s.lower() for s in self.core_skills + self.secondary_skills + self.tools)
        self.core_skills_lower = set(s.lower() for s in self.core_skills)

        # Detect user's primary stack domains
        self.user_domains = self._detect_user_domains()

        # Calculate max seniority the user qualifies for
        self.max_seniority_years = self.exp_years + 2  # Allow 2 years stretch

        logger.info(f"ProfileFilter: {self.exp_years}yr exp, domains={self.user_domains}, "
                     f"{len(self.all_skills)} skills tracked")

    def should_keep(self, title, description=""):
        """
        Decide whether to keep a job based on profile matching.
        Returns (keep: bool, reason: str)
        """
        title_lower = title.lower()
        desc_lower = description.lower() if description else ""
        searchable = title_lower + " " + desc_lower

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


# ============================================================
# Greenhouse Fetcher
# ============================================================

def fetch_greenhouse_jobs(profile, delay=0.2):
    """Fetch and filter jobs from Greenhouse companies."""
    import requests

    pf = ProfileFilter(profile)
    all_jobs = []
    kept = 0
    filtered = 0

    # Load companies from database (with fallback to hardcoded list)
    companies = _load_companies_from_db("greenhouse")

    for company_name, board_token in companies.items():
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
            resp = requests.get(url, verify=False, timeout=15, headers={
                "User-Agent": "JobRadar/1.0 (personal job search tool)"
            })

            if resp.status_code != 200:
                continue

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

                all_jobs.append({
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

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"Greenhouse {company_name} error: {e}")
            continue

    logger.info(f"Greenhouse: {kept} kept, {filtered} filtered out, from {len(companies)} companies")
    return all_jobs


# ============================================================
# Lever Fetcher
# ============================================================

def fetch_lever_jobs(profile, delay=0.5):
    """Fetch and filter jobs from Lever companies."""
    import requests

    pf = ProfileFilter(profile)
    all_jobs = []
    kept = 0
    filtered = 0

    # Load companies from database (with fallback to hardcoded list)
    companies = _load_companies_from_db("lever")

    for company_name, slug in companies.items():
        try:
            url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
            resp = requests.get(url, verify=False, timeout=15, headers={
                "User-Agent": "JobRadar/1.0 (personal job search tool)"
            })

            if resp.status_code != 200:
                continue

            postings = resp.json()
            if not isinstance(postings, list):
                continue

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

                all_jobs.append({
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

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"Lever {company_name} error: {e}")
            continue

    logger.info(f"Lever: {kept} kept, {filtered} filtered out, from {len(companies)} companies")
    return all_jobs


# ============================================================
# Ashby Fetcher
# ============================================================

def fetch_ashby_jobs(profile, delay=0.5):
    """Fetch and filter jobs from Ashby companies."""
    import requests

    pf = ProfileFilter(profile)
    all_jobs = []
    kept = 0
    filtered = 0

    # Load companies from database (with fallback to hardcoded list)
    companies = _load_companies_from_db("ashby")

    for company_name, slug in companies.items():
        try:
            url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
            resp = requests.get(url, verify=False, timeout=15, headers={
                "User-Agent": "JobRadar/1.0 (personal job search tool)"
            })

            if resp.status_code != 200:
                continue

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

                all_jobs.append({
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

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"Ashby {company_name} error: {e}")
            continue

    logger.info(f"Ashby: {kept} kept, {filtered} filtered out, from {len(companies)} companies")
    return all_jobs
