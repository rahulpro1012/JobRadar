"""
JobRadar AI Agent v2
Intelligent resume analysis, location-aware query generation, and career-advisor scoring.
Uses Groq API with smart quota management.
"""
import json
import time
import logging
import re
import os
from datetime import datetime

from app.database import get_quota_usage, increment_quota

logger = logging.getLogger(__name__)

SMART_MODEL = "llama-3.3-70b-versatile"
FAST_MODEL = "llama-3.1-8b-instant"
QUOTA_GROQ_SMART = "groq_smart"
QUOTA_GROQ_FAST = "groq_fast"
DAILY_LIMIT_SMART = 50
DAILY_LIMIT_FAST = 200


# ============================================================
# Groq API Client
# ============================================================

def _call_groq(prompt, system_prompt, model=FAST_MODEL, max_tokens=2000, temperature=0.3,
               response_format=None):
    """Call Groq API with quota tracking and 429 retry/backoff.

    On HTTP 429 (TPM rate limit), retries up to 3 times honoring the
    Retry-After header when present, else backing off 5 → 10 → 20s.
    Quota is only counted on a successful (200) response.

    response_format: optional dict, e.g. {"type": "json_object"}, to force
    structured output (prevents weak models from emitting prose/code).
    """
    import requests

    quota_key = QUOTA_GROQ_SMART if model == SMART_MODEL else QUOTA_GROQ_FAST
    daily_limit = DAILY_LIMIT_SMART if model == SMART_MODEL else DAILY_LIMIT_FAST
    today = datetime.now().strftime("%Y-%m-%d")
    used = get_quota_usage(quota_key, today)

    if used >= daily_limit:
        logger.warning(f"Groq {model} quota exhausted ({used}/{daily_limit})")
        return None

    api_key = _get_groq_key()
    if not api_key:
        return None

    backoffs = [5, 10, 20]  # seconds between attempts on 429
    max_attempts = len(backoffs) + 1

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format

    for attempt in range(max_attempts):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                verify=False,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )

            if resp.status_code == 429:
                if attempt < max_attempts - 1:
                    # Honor Retry-After if Groq sends it, else use backoff schedule
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        wait = float(retry_after) if retry_after else backoffs[attempt]
                    except (TypeError, ValueError):
                        wait = backoffs[attempt]
                    logger.warning(
                        f"Groq 429 (TPM limit), retry {attempt + 1}/{max_attempts - 1} in {wait:.0f}s"
                    )
                    time.sleep(wait)
                    continue
                logger.warning("Groq 429 (TPM limit) — retries exhausted, giving up")
                return None

            if resp.status_code != 200:
                logger.warning(f"Groq API error: {resp.status_code} {resp.text[:200]}")
                return None

            # Success — count quota once
            increment_quota(quota_key, today)
            return resp.json()["choices"][0]["message"]["content"].strip()

        except Exception as e:
            logger.warning(f"Groq API call failed: {e}")
            return None

    return None


_groq_api_key = None

def _get_groq_key():
    global _groq_api_key
    if _groq_api_key:
        return _groq_api_key
    _groq_api_key = os.environ.get("GROQ_API_KEY", "")
    if not _groq_api_key:
        logger.info("GROQ_API_KEY not set — AI features disabled")
    return _groq_api_key


def is_ai_enabled():
    return bool(_get_groq_key())


# ============================================================
# Feature 1: Intelligent Resume Parsing
# ============================================================

def ai_parse_resume(resume_text):
    """Parse resume with career trajectory analysis."""
    if not is_ai_enabled():
        return None

    system_prompt = """You are an expert technical recruiter analyzing a developer's resume. 
Extract structured data AND provide career intelligence. Return ONLY valid JSON:

{
  "name": "Full Name",
  "primary_role": "Best job title this person should target",
  "role_variants": ["8-12 alternative job titles they'd be competitive for"],
  "experience_years": 2.0,
  "experience_level": "Junior|Junior-Mid|Mid|Senior|Lead",
  "core_skills": ["Top 10-15 skills RANKED by evidence — skills used across multiple roles first, then single-role skills, then skills-section-only mentions"],
  "secondary_skills": ["Next 10-15 less prominent skills"],
  "tools": ["IDEs, build tools, platforms, project management"],
  "domain_keywords": ["Industry domains and architecture patterns from their actual work"],
  "education": "Degree and field",
  "location": "Current city from HEADER/contact section only, not from past jobs",
  "career_narrative": "2-3 sentence summary of their career trajectory, strengths, and what makes them unique",
  "competitive_advantages": ["3-5 specific things that make this candidate stand out at their level"],
  "target_companies": ["Types of companies they'd be a good fit for: startup, mid-size, enterprise, product, consulting"]
}

Critical rules:
- primary_role: Infer from most recent role + dominant skill mix
- role_variants: Be creative — include titles recruiters actually search for. For a Java+React person: "Java Full Stack Developer", "Spring Boot Developer", "Backend Engineer", "Microservices Developer", "Java Backend Developer", "React Java Developer" etc.
- core_skills: RANK by evidence. Skills used in 3 jobs > 2 jobs > 1 job > just listed. Name them properly (e.g., "Spring Boot" not "spring boot").
- location: ONLY from the header/contact area, never from employer locations
- career_narrative: What's their story? Where are they heading?
- competitive_advantages: What's rare about their profile at their experience level?
- Today's date is """ + datetime.now().strftime("%B %Y")

    prompt = f"Analyze this resume:\n\n{resume_text[:4000]}"

    result = _call_groq(prompt, system_prompt, model=SMART_MODEL, max_tokens=1800, temperature=0.1)
    if not result:
        return None

    try:
        json_match = re.search(r"\{[\s\S]*\}", result)
        if not json_match:
            return None

        profile = json.loads(json_match.group())

        required = ["name", "primary_role", "core_skills"]
        for field in required:
            if field not in profile:
                return None

        for field in ["role_variants", "core_skills", "secondary_skills", "tools",
                      "domain_keywords", "competitive_advantages", "target_companies"]:
            if field in profile and not isinstance(profile[field], list):
                profile[field] = []

        if "experience_years" in profile:
            try:
                profile["experience_years"] = float(profile["experience_years"])
            except (ValueError, TypeError):
                profile["experience_years"] = 0.0

        logger.info(f"AI resume parse successful: {profile.get('primary_role')}, {len(profile.get('core_skills', []))} skills")
        return profile

    except json.JSONDecodeError as e:
        logger.warning(f"AI resume parse JSON error: {e}")
        return None


def ai_parse_resume_tiered(resume_text):
    """A1: Parse resume into tiered skills (primary/familiar/learning) + explicit preferences.

    Returns v2 profile with:
    - schema_version: 2
    - skills: {primary: [{name, years, evidence}], familiar: [...], learning: [...]}
    - preferences: {preferred_locations, avoid_locations, company_types, deal_breakers}
    - plus all existing v1 fields for backward compatibility
    """
    if not is_ai_enabled():
        return None

    system_prompt = """You are an expert technical recruiter analyzing a developer's resume.
Extract TIERED skills, explicit preferences, and career intelligence.

CRITICAL skill distinctions:
1. PRIMARY skills = used in MULTIPLE projects OR current role >6 months
   Include "years" estimate and specific evidence from resume
2. FAMILIAR skills = mentioned once, side project only, or <6 months exposure
3. LEARNING skills = explicit "learning", "in progress", "goal" statements ONLY

For preferences — extract from free-text sections (summary, cover letter references), location history, company type patterns:
- preferred_locations: Where do they live/want to work?
- avoid_locations: Any explicit location rejections?
- preferred_company_types: Startup, SaaS, consulting, fintech, etc. (infer from job history)
- deal_breakers: ONLY explicit statements like "Not interested in consulting body-shops", "Will not work for ...", "Avoid government contracts"

Conservative rule: If uncertain whether a skill is primary or familiar, classify as familiar. False primaries hurt scoring more than false familiars.

Return ONLY valid JSON:

{
  "schema_version": 2,
  "name": "Full Name",
  "primary_role": "Best job title",
  "role_variants": ["alt titles"],
  "experience_years": 2.0,
  "experience_level": "Junior|Junior-Mid|Mid|Senior|Lead",
  "skills": {
    "primary": [
      {"name": "Java", "years": 2, "evidence": "3 projects, current role (2yr)"},
      {"name": "Spring Boot", "evidence": "2yr current project + 1yr prior", "years": 2}
    ],
    "familiar": [
      {"name": "React", "years": 0.5, "evidence": "1 side project (2024)"},
      {"name": "Angular", "years": 0.5, "evidence": "mentioned, no projects listed"}
    ],
    "learning": ["GraphQL", "Kubernetes"]
  },
  "secondary_skills": ["...legacy field for compat..."],
  "tools": ["IDEs, build tools"],
  "domain_keywords": ["Industry domains"],
  "education": "Degree",
  "location": "Current city",
  "career_narrative": "2-3 sentence summary",
  "competitive_advantages": ["..."],
  "target_companies": ["startup", "SaaS", ...],
  "preferences": {
    "preferred_locations": ["Pune", "Bengaluru", "Remote"],
    "avoid_locations": ["US-only remote"],
    "preferred_company_types": ["product startup", "SaaS", "fintech"],
    "deal_breakers": ["no body-shop consulting"]
  }
}

Today's date is """ + datetime.now().strftime("%B %Y")

    prompt = f"Analyze this resume and extract tiered skills + preferences:\n\n{resume_text[:4000]}"

    result = _call_groq(prompt, system_prompt, model=SMART_MODEL, max_tokens=2200, temperature=0.1)
    if not result:
        return None

    try:
        json_match = re.search(r"\{[\s\S]*\}", result)
        if not json_match:
            return None

        profile = json.loads(json_match.group())

        # Validate schema_version
        if profile.get("schema_version") != 2:
            logger.warning("A1: Resume parse didn't return v2 schema, rejecting")
            return None

        required = ["name", "primary_role", "skills"]
        for field in required:
            if field not in profile:
                return None

        # Validate skills structure
        if not isinstance(profile.get("skills"), dict):
            return None

        # Ensure skills has all three tiers
        for tier in ["primary", "familiar", "learning"]:
            if tier not in profile["skills"]:
                profile["skills"][tier] = []

        # Parse legacy fields for backward compatibility
        for field in ["role_variants", "secondary_skills", "tools", "domain_keywords", "competitive_advantages", "target_companies"]:
            if field in profile and not isinstance(profile[field], list):
                profile[field] = []

        # Ensure preferences structure
        if not isinstance(profile.get("preferences"), dict):
            profile["preferences"] = {}
        for pref_field in ["preferred_locations", "avoid_locations", "preferred_company_types", "deal_breakers"]:
            if pref_field not in profile.get("preferences", {}):
                profile["preferences"][pref_field] = []

        if "experience_years" in profile:
            try:
                profile["experience_years"] = float(profile["experience_years"])
            except (ValueError, TypeError):
                profile["experience_years"] = 0.0

        logger.info(f"A1: Resume parse v2 successful: {profile.get('primary_role')}, " +
                   f"{len(profile.get('skills', {}).get('primary', []))} primary skills, " +
                   f"{len(profile.get('skills', {}).get('familiar', []))} familiar")
        return profile

    except json.JSONDecodeError as e:
        logger.warning(f"A1: Resume parse v2 JSON error: {e}")
        return None


# ============================================================
# Feature 2: Location-Aware Intelligent Query Generation
# ============================================================

def ai_generate_queries(profile, search_locations=None):
    """Generate recruiter-style queries with multi-location awareness."""
    if not is_ai_enabled():
        return []

    system_prompt = """You are a senior technical recruiter in India searching for candidates.
Given a developer's profile and their target locations, generate 12-15 highly targeted job search queries.

Rules:
- Mix SPECIFIC queries ("Spring Boot Kafka backend engineer Pune") with DISCOVERY queries ("event-driven microservices developer India")
- Use the candidate's UNIQUE skill combinations, not just individual skills
- Reference their domain experience (payments, e-commerce, task management, etc.)
- Generate queries for EACH location provided (spread across locations)
- Include "remote" queries if remote is in the locations
- Use terminology that appears in real job postings on Naukri, LinkedIn, Indeed
- Include some queries targeting the candidate's competitive advantages
- Vary query styles: some with quotes for exact match, some natural language
- Think about what a hiring manager would type when looking for this person

Return ONLY a JSON array of strings, no explanation."""

    skills = _parse_field(profile.get("core_skills", []))
    role = profile.get("primary_role", "Software Developer")
    exp = profile.get("experience_years", 0)
    variants = _parse_field(profile.get("role_variants", []))
    domain = _parse_field(profile.get("domain_keywords", []))
    narrative = profile.get("career_narrative", "")
    advantages = _parse_field(profile.get("competitive_advantages", []))

    # Build location list
    locations = search_locations or []
    if not locations:
        loc = profile.get("location", "")
        if loc:
            locations = [loc, "India", "Remote"]
        else:
            locations = ["India", "Remote"]

    prompt = f"""Developer Profile:
Role: {role}
Experience: {exp} years
Core Skills: {', '.join(skills[:12])}
Role Variants: {', '.join(variants[:6])}
Domain Experience: {', '.join(domain[:5])}
Career Story: {narrative}
Competitive Advantages: {', '.join(advantages[:4])}

Target Locations: {', '.join(locations)}

Generate 12-15 search queries optimized for Indian job portals (Naukri, LinkedIn, Indeed)."""

    result = _call_groq(prompt, system_prompt, model=FAST_MODEL, max_tokens=800, temperature=0.5)
    if not result:
        return []

    try:
        json_match = re.search(r"\[[\s\S]*\]", result)
        if not json_match:
            return []

        queries = json.loads(json_match.group())
        if not isinstance(queries, list):
            return []

        clean = [q.strip() for q in queries if isinstance(q, str) and 5 < len(q) < 120]
        logger.info(f"AI generated {len(clean)} additional queries")
        return clean[:15]

    except json.JSONDecodeError:
        return []


def ai_generate_source_aware_queries(profile, search_locations=None):
    """A2: Generate source-specific queries optimized for each platform's syntax.

    Returns dict with per-source query lists:
    {
        "linkedin": ["query1", "query2", ...],
        "naukri": ["query1", "query2", ...],
        "adzuna": ["query1", "query2", ...],
        "ats_search": ["query1", "query2"],
        "generic": ["query1", "query2"]
    }
    """
    if not is_ai_enabled():
        return {
            "linkedin": [],
            "naukri": [],
            "adzuna": [],
            "ats_search": [],
            "generic": []
        }

    # Get top-performing queries from history to feed into generation
    top_performers = {}
    for source in ["linkedin", "naukri", "adzuna", "ats_search", "generic"]:
        top_performers[source] = get_top_performing_queries(source, limit=3)

    system_prompt = """You generate job search queries optimized for specific platforms.
Each source has different syntax rules and expectations.
Your queries must be MEANINGFULLY different (different skills, roles, locations), not near-duplicates.

IMPORTANT: Return ONLY valid JSON in the exact format specified. No explanation, no markdown."""

    skills = _parse_field(profile.get("core_skills", []))
    role = profile.get("primary_role", "Software Developer")
    exp = profile.get("experience_years", 0)
    variants = _parse_field(profile.get("role_variants", []))
    domain = _parse_field(profile.get("domain_keywords", []))

    locations = search_locations or []
    if not locations:
        loc = profile.get("location", "")
        locations = [loc] if loc else ["Pune"]

    prompt = f"""Developer Profile:
- Role: {role}
- Experience: {exp} years
- Core Skills: {', '.join(skills[:8])}
- Role Variants: {', '.join(variants[:4])}
- Domain: {', '.join(domain[:3])}
- Target Locations: {', '.join(locations)}

Last Week's Best Performers (try variants of these):
- LinkedIn: {', '.join(top_performers.get('linkedin', []))}
- Naukri: {', '.join(top_performers.get('naukri', []))}
- Adzuna: {', '.join(top_performers.get('adzuna', []))}

Generate source-specific queries following these rules:

LINKEDIN (3 queries, MAX 4 words each, NO quotes, prefer job titles):
Examples: "Java Developer", "Backend Engineer", "Spring Boot Developer"
BAD: "Java Developer with Spring Boot in Pune" (too long)

NAUKRI (3 queries, location keyword pairs, NO quotes, lowercase):
Examples: "java spring boot pune", "backend engineer bangalore", "full stack developer remote"
BAD: '"Java" "Spring Boot"' (Naukri hates quotes)

ADZUNA (3 queries, 2-3 keywords only, NO city names, NO quotes):
Examples: "java spring boot", "backend microservices", "full stack developer"
BAD: "java spring boot developer pune" (Adzuna filters city separately)

ATS_SEARCH (2 queries for SearxNG/Yahoo, can use site: operators):
Examples: "site:naukri.com {role.lower()} {skills[0].lower()}", "site:linkedin.com/jobs {role.lower()}"

GENERIC (2 queries for Jooble/SerpApi, balanced specificity):
Examples: "java spring boot developer pune", "backend engineer bangalore"

Return ONLY this JSON (no explanation):
{{
  "linkedin": ["query1", "query2", "query3"],
  "naukri": ["query1", "query2", "query3"],
  "adzuna": ["query1", "query2", "query3"],
  "ats_search": ["query1", "query2"],
  "generic": ["query1", "query2"]
}}"""

    result = _call_groq(prompt, system_prompt, model=FAST_MODEL, max_tokens=1000, temperature=0.4)
    if not result:
        return {
            "linkedin": [],
            "naukri": [],
            "adzuna": [],
            "ats_search": [],
            "generic": []
        }

    try:
        json_match = re.search(r"\{[\s\S]*\}", result)
        if not json_match:
            return {
                "linkedin": [],
                "naukri": [],
                "adzuna": [],
                "ats_search": [],
                "generic": []
            }

        queries_by_source = json.loads(json_match.group())

        # Validate and clean each source's queries
        cleaned = {}
        for source, queries_list in queries_by_source.items():
            if not isinstance(queries_list, list):
                queries_list = []
            cleaned[source] = [q.strip() for q in queries_list if isinstance(q, str) and 3 < len(q) < 150]

        logger.info(f"A2: Generated source-aware queries: {sum(len(q) for q in cleaned.values())} total queries")
        return cleaned

    except json.JSONDecodeError as e:
        logger.warning(f"A2: Failed to parse source-aware queries: {e}")
        return {
            "linkedin": [],
            "naukri": [],
            "adzuna": [],
            "ats_search": [],
            "generic": []
        }


def get_top_performing_queries(source: str, limit: int = 5) -> list:
    """Get queries that returned >5 jobs in last 7 days for feedback loop."""
    try:
        from app.database import get_connection

        with get_connection() as db:
            rows = db.execute("""
                SELECT query, AVG(jobs_returned) as avg_yield
                FROM query_yield_history
                WHERE source = ? AND refreshed_at > datetime('now', '-7 days')
                GROUP BY query
                HAVING avg_yield > 5
                ORDER BY avg_yield DESC
                LIMIT ?
            """, (source, limit)).fetchall()

            return [row["query"] for row in rows] if rows else []
    except Exception as e:
        logger.debug(f"Failed to get top queries for {source}: {e}")
        return []


# ============================================================
# Feature 3: Career-Advisor Job Scoring
# ============================================================

def ai_score_jobs(jobs, profile, batch_size=8):
    """Score jobs as a career advisor with actionable insights."""
    if not is_ai_enabled() or not jobs:
        return {}

    skills = _parse_field(profile.get("core_skills", []))
    role = profile.get("primary_role", "Software Developer")
    exp = profile.get("experience_years", 0)
    location = profile.get("location", "")
    narrative = profile.get("career_narrative", "")
    advantages = _parse_field(profile.get("competitive_advantages", []))

    profile_summary = f"""Candidate: {role} | {exp}yr exp | {location}
Skills: {', '.join(skills[:10])}
Story: {narrative}
Strengths: {', '.join(advantages[:3])}"""

    system_prompt = f"""You are a career advisor evaluating job opportunities for this developer:

{profile_summary}

For each job, provide:
- score (0-100): How strong a match AND how good an opportunity is this?
- reason (2 sentences max): Be specific and actionable. Mention exact skill matches, red flags, career growth potential, or why to skip.

Scoring guide:
- 85-100: "Apply immediately" — skills align perfectly, right level, good company
- 70-84: "Strong apply" — most skills match, minor gaps they can learn
- 50-69: "Worth considering" — partial match, some relevant experience transfers
- 30-49: "Stretch application" — significant gaps but some overlap
- 0-29: "Skip" — wrong stack, wrong level, or unrelated role

Be honest and direct. Mention specific skills from their profile that match or don't match.

Return ONLY valid JSON array:
[{{"id": 1, "score": 82, "reason": "Your Spring Boot + Kafka stack matches perfectly. 1-3yr range is ideal. Apply emphasizing your Boardify project."}}, ...]"""

    results = {}

    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]

        job_descs = []
        for job in batch:
            desc = f"ID {job['id']}: {job['title']}"
            if job.get('company'):
                desc += f" at {job['company']}"
            if job.get('location'):
                desc += f" ({job['location']})"
            if job.get('description_snippet'):
                desc += f"\nDescription: {job['description_snippet'][:250]}"
            job_descs.append(desc)

        prompt = f"Evaluate these {len(batch)} jobs:\n\n" + "\n\n".join(job_descs)

        result = _call_groq(prompt, system_prompt, model=FAST_MODEL, max_tokens=1500, temperature=0.2)
        if not result:
            continue

        try:
            json_match = re.search(r"\[[\s\S]*\]", result)
            if not json_match:
                continue

            scores = json.loads(json_match.group())
            if not isinstance(scores, list):
                continue

            for entry in scores:
                if not isinstance(entry, dict):
                    continue
                job_id = entry.get("id")
                if job_id is not None:
                    results[int(job_id)] = {
                        "ai_score": max(0, min(100, int(entry.get("score", 0)))),
                        "ai_reason": str(entry.get("reason", ""))[:300],
                    }

        except (json.JSONDecodeError, ValueError):
            continue

        time.sleep(2)

    logger.info(f"AI scored {len(results)} jobs")
    return results


def _clean_groq_json(text: str) -> str:
    """Strip common Groq response wrappers (markdown, preamble, trailing text)."""
    text = text.strip()

    # Strip markdown fence if present
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].strip()
        elif "```" in text:
            text = text.rsplit("```", 1)[0].strip()

    # If response starts with non-JSON text, find first { or [
    if text and text[0] not in "{[":
        # Look for first occurrence of valid JSON start
        for i, ch in enumerate(text):
            if ch in "{[":
                text = text[i:]
                break

    # Find matching closing brace/bracket if response has trailing text
    if text.startswith("["):
        depth = 0
        for i, ch in enumerate(text):
            if ch == "[": depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    text = text[:i+1]
                    break
    elif text.startswith("{"):
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = text[:i+1]
                    break

    return text


def analyze_jobs_batch(jobs, profile, batch_size=15):
    """C1: Analyze jobs with structured reasoning (apply/skip reasons, red flags).

    Returns list of analysis dicts:
    [{
        "job_id": 123,
        "score": 87,
        "apply_reasons": ["reason1", "reason2"],
        "skip_reasons": ["caution1"],
        "fit_summary": "...",
        "red_flags": ["stale_posting", "seniority_mismatch"]
    }, ...]
    """
    if not is_ai_enabled() or not jobs:
        return []

    skills = _parse_field(profile.get("core_skills", []))
    role = profile.get("primary_role", "Software Developer")
    exp = profile.get("experience_years", 0)
    location = profile.get("location", "")
    narrative = profile.get("career_narrative", "")
    advantages = _parse_field(profile.get("competitive_advantages", []))

    profile_summary = f"""Candidate: {role} | {exp}yr exp | {location}
Skills: {', '.join(skills[:10])}
Strengths: {', '.join(advantages[:3])}"""

    system_prompt = f"""You are a career advisor analyzing job opportunities for this developer:

{profile_summary}

For each job, return ONLY valid JSON array with this exact structure. Never include explanatory text before or after the JSON. Never wrap in markdown code fences.

Return ONLY:
[
  {{
    "job_id": int,
    "score": 0-100 (overall fit),
    "apply_reasons": ["reason1 (max 12 words)", ...],
    "skip_reasons": ["caution1 (max 12 words)", ...],
    "fit_summary": "One sentence verdict (max 20 words)",
    "red_flags": ["seniority_mismatch", "stale_posting", ...]
  }},
  ...
]

Red flag types: seniority_mismatch, stale_posting, underpaid, generic_jd, experience_too_high, location_mismatch, stack_mismatch, body_shop"""

    results = []
    total_batches = (len(jobs) + batch_size - 1) // batch_size

    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        logger.info(f"C1: Analyzing batch {batch_num}/{total_batches} ({len(batch)} jobs)")

        job_jsons = []
        for job in batch:
            job_compact = {
                "id": job['id'],
                "title": job['title'],
                "company": job.get('company', ''),
                "location": job.get('location', ''),
                "description": job.get('description_snippet', '')[:250],
                "posted_date": job.get('posted_date', ''),
            }
            job_jsons.append(job_compact)

        prompt = f"Analyze these {len(batch)} jobs:\n\n{json.dumps(job_jsons, indent=2)}"

        result = _call_groq(prompt, system_prompt, model=FAST_MODEL, max_tokens=1500, temperature=0.1)
        if not result:
            logger.debug(f"C1: No response from Groq for batch of {len(batch)} jobs")
            continue

        try:
            # ===== DIAGNOSTIC LOGGING =====
            logger.debug(f"C1: Raw response length: {len(result)} chars")
            logger.debug(f"C1: Response first 300: {result[:300]}")
            logger.debug(f"C1: Response last 200: {result[-200:]}")

            # ===== ROBUST PARSING =====
            cleaned = _clean_groq_json(result)

            try:
                analyses = json.loads(cleaned)
            except json.JSONDecodeError as e:
                # Show EXACTLY where parse failed
                logger.error(f"C1: JSON parse failed at position {e.pos}: {e.msg}")
                logger.error(f"C1: Around error: ...{cleaned[max(0, e.pos-80):e.pos+80]}...")
                # Save full response for debugging
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                        f.write(result)
                        logger.error(f"C1: Full response saved to {f.name}")
                except Exception:
                    pass
                continue

            if not isinstance(analyses, list):
                logger.warning(f"C1: Response is not a list, got {type(analyses)}")
                continue

            for entry in analyses:
                if not isinstance(entry, dict):
                    logger.debug(f"C1: Skipping non-dict entry: {entry}")
                    continue
                job_id = entry.get("job_id")
                if job_id is not None:
                    analysis = {
                        "job_id": int(job_id),
                        "score": max(0, min(100, int(entry.get("score", 0)))),
                        "apply_reasons": entry.get("apply_reasons", []) if isinstance(entry.get("apply_reasons"), list) else [],
                        "skip_reasons": entry.get("skip_reasons", []) if isinstance(entry.get("skip_reasons"), list) else [],
                        "fit_summary": str(entry.get("fit_summary", ""))[:120],
                        "red_flags": entry.get("red_flags", []) if isinstance(entry.get("red_flags"), list) else [],
                    }
                    results.append(analysis)

            logger.info(f"C1: Successfully parsed {len([a for a in analyses if isinstance(a, dict) and 'job_id' in a])} job analyses from batch")

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"C1: Exception parsing batch of {len(batch)} jobs: {e}")
            continue

        # Pause between batches to stay under Groq's per-minute TPM limit
        # (skip after last batch). 8s keeps cumulative tokens/min well under 6000.
        if i + batch_size < len(jobs):
            time.sleep(8.0)

    logger.info(f"C1: Total {len(results)} jobs analyzed across {total_batches} batches")
    return results


# ============================================================
# Helpers
# ============================================================

def _parse_field(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return []
