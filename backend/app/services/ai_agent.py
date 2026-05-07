"""
JobRadar AI Agent
Wraps Groq LLM API to provide intelligent:
  1. Resume parsing (understands context, ranks skills by proficiency)
  2. Query generation (creative, market-aware search queries)
  3. Job scoring (reads full JD, explains fit, spots red flags)

Uses llama-3.1-8b-instant for batched scoring (14,400 req/day limit)
Uses llama-3.3-70b-versatile for parsing and query gen (1,000 req/day limit)

Quota budget per day:
  - Parse: 1 call (on upload only)
  - Queries: 1 call per refresh × 5 refreshes = 5 calls
  - Scoring: 2 calls per refresh × 5 refreshes = 10 calls
  - Total: ~16 calls/day (1.6% of daily limit)
"""
import json
import time
import logging
import re
from datetime import datetime

from app.database import get_quota_usage, increment_quota

logger = logging.getLogger(__name__)

# Models
SMART_MODEL = "llama-3.3-70b-versatile"   # Better reasoning, 1000 RPD
FAST_MODEL = "llama-3.1-8b-instant"       # Fast + cheap, 14400 RPD

# Quota keys
QUOTA_GROQ_SMART = "groq_smart"
QUOTA_GROQ_FAST = "groq_fast"

# Daily limits (conservative — well under Groq's actual limits)
DAILY_LIMIT_SMART = 50   # We'll use ~6/day, cap at 50 for safety
DAILY_LIMIT_FAST = 200   # We'll use ~10/day, cap at 200 for safety


# ============================================================
# Groq API Client
# ============================================================

def _call_groq(prompt, system_prompt, model=FAST_MODEL, max_tokens=2000, temperature=0.3):
    """
    Call Groq API with rate limit awareness.
    Returns the response text, or None if quota exceeded or error.
    """
    import requests

    # Determine quota key and limit
    quota_key = QUOTA_GROQ_SMART if model == SMART_MODEL else QUOTA_GROQ_FAST
    daily_limit = DAILY_LIMIT_SMART if model == SMART_MODEL else DAILY_LIMIT_FAST

    # Check daily quota
    today = datetime.now().strftime("%Y-%m-%d")
    used = get_quota_usage(quota_key, today)
    if used >= daily_limit:
        logger.warning(f"Groq {model} daily quota exhausted ({used}/{daily_limit})")
        return None

    api_key = _get_groq_key()
    if not api_key:
        return None

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            verify=False,  # SSL fix for Windows — remove in production if certs are fixed
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=30,
        )

        increment_quota(quota_key, today)

        if resp.status_code == 429:
            logger.warning("Groq rate limited — backing off")
            time.sleep(5)
            return None

        if resp.status_code != 200:
            logger.warning(f"Groq API error: {resp.status_code} {resp.text[:200]}")
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content.strip()

    except Exception as e:
        logger.warning(f"Groq API call failed: {e}")
        return None


_groq_api_key = None

def _get_groq_key():
    """Get Groq API key from environment."""
    global _groq_api_key
    if _groq_api_key:
        return _groq_api_key
    import os
    _groq_api_key = os.environ.get("GROQ_API_KEY", "")
    if not _groq_api_key:
        logger.info("GROQ_API_KEY not set — AI features disabled")
    return _groq_api_key


def is_ai_enabled():
    """Check if AI features are available."""
    return bool(_get_groq_key())


# ============================================================
# Feature 1: AI Resume Parser
# ============================================================

def ai_parse_resume(resume_text):
    """
    Use AI to parse a resume into a structured profile.
    Returns a dict matching our profile schema, or None if AI unavailable.
    Falls back to regex parser if AI fails.
    """
    if not is_ai_enabled():
        return None

    system_prompt = """You are a resume parsing expert. Extract structured data from resumes.
Return ONLY valid JSON, no markdown, no explanation. Follow this exact schema:
{
  "name": "Full Name",
  "primary_role": "The single best job title this person should apply for",
  "role_variants": ["list", "of", "6-10", "alternative", "job", "titles"],
  "experience_years": 2.0,
  "experience_level": "Junior|Junior-Mid|Mid|Senior|Lead",
  "core_skills": ["top 10-15 skills ranked by proficiency, most proficient first"],
  "secondary_skills": ["next 10-15 skills, less prominent"],
  "tools": ["IDEs, build tools, project management tools"],
  "domain_keywords": ["industry terms, architecture patterns, methodologies"],
  "education": "Degree and field",
  "location": "Current city (from address/header, NOT from past jobs)"
}

Rules:
- primary_role: Infer from their most recent role + skill mix. If they have both frontend and backend, say "Full Stack Developer".
- role_variants: Include creative titles recruiters might use. E.g., for a Java+React person: "Java Full Stack Developer", "Spring Boot Developer", "Backend Engineer", "Java Developer", "React Developer", "Software Engineer", "Web Developer", "Microservices Developer".
- core_skills: Rank by how much evidence exists (used in multiple roles > used in one role > mentioned in skills section only). Name them properly (e.g., "Spring Boot" not "spring boot").
- location: Extract from the HEADER/contact section only (their current city), not from past employer locations.
- experience_years: Calculate from work history dates. If "Present" appears, calculate to today (May 2026)."""

    prompt = f"Parse this resume into the JSON schema:\n\n{resume_text[:4000]}"

    result = _call_groq(prompt, system_prompt, model=SMART_MODEL, max_tokens=1500, temperature=0.1)
    if not result:
        return None

    try:
        # Extract JSON from response (AI might wrap it in markdown code blocks)
        json_match = re.search(r"\{[\s\S]*\}", result)
        if not json_match:
            logger.warning("AI resume parse: no JSON found in response")
            return None

        profile = json.loads(json_match.group())

        # Validate required fields exist
        required = ["name", "primary_role", "core_skills"]
        for field in required:
            if field not in profile:
                logger.warning(f"AI resume parse: missing field '{field}'")
                return None

        # Ensure lists are lists
        for field in ["role_variants", "core_skills", "secondary_skills", "tools", "domain_keywords"]:
            if field in profile and not isinstance(profile[field], list):
                profile[field] = []

        # Ensure numbers are numbers
        if "experience_years" in profile:
            try:
                profile["experience_years"] = float(profile["experience_years"])
            except (ValueError, TypeError):
                profile["experience_years"] = 0.0

        logger.info(f"AI resume parse successful: {profile.get('primary_role')}, {len(profile.get('core_skills', []))} skills")
        return profile

    except json.JSONDecodeError as e:
        logger.warning(f"AI resume parse: JSON decode error: {e}")
        return None


# ============================================================
# Feature 2: AI Query Generation
# ============================================================

def ai_generate_queries(profile):
    """
    Use AI to generate creative, market-aware search queries.
    Returns a list of query strings, or empty list if AI unavailable.
    These supplement (not replace) our template-based queries.
    """
    if not is_ai_enabled():
        return []

    system_prompt = """You are a job search expert for the Indian tech market.
Given a developer's profile, generate 8-10 creative job search queries that would find relevant openings.

Rules:
- Mix specific queries ("Spring Boot microservices developer Pune") with broader ones ("Java backend engineer India")
- Include queries using trending job titles and industry terminology
- Consider the person's skill combinations, not just individual skills
- Include queries that match their experience from past roles (e.g., if they worked on payment systems, try "payment backend developer")
- Some queries should target Naukri/Indeed style searches, others should be more natural
- Return ONLY a JSON array of strings, no explanation

Example output:
["Spring Boot microservices developer Pune", "Java React full stack 2 years India", ...]"""

    skills = profile.get("core_skills", [])
    if isinstance(skills, str):
        try:
            skills = json.loads(skills)
        except (json.JSONDecodeError, TypeError):
            skills = []

    role = profile.get("primary_role", "Software Developer")
    location = profile.get("location", "India")
    exp = profile.get("experience_years", 0)
    variants = profile.get("role_variants", [])
    if isinstance(variants, str):
        try:
            variants = json.loads(variants)
        except (json.JSONDecodeError, TypeError):
            variants = []

    prompt = f"""Generate search queries for this developer:
Role: {role}
Skills: {', '.join(skills[:10]) if isinstance(skills, list) else skills}
Experience: {exp} years
Location: {location}
Alternative titles: {', '.join(variants[:5]) if isinstance(variants, list) else variants}"""

    result = _call_groq(prompt, system_prompt, model=FAST_MODEL, max_tokens=600, temperature=0.5)
    if not result:
        return []

    try:
        json_match = re.search(r"\[[\s\S]*\]", result)
        if not json_match:
            return []

        queries = json.loads(json_match.group())
        if not isinstance(queries, list):
            return []

        # Clean and validate
        clean_queries = []
        for q in queries:
            if isinstance(q, str) and 5 < len(q) < 100:
                clean_queries.append(q.strip())

        logger.info(f"AI generated {len(clean_queries)} additional queries")
        return clean_queries[:10]

    except json.JSONDecodeError:
        return []


# ============================================================
# Feature 3: AI Job Scoring (Batched)
# ============================================================

def ai_score_jobs(jobs, profile, batch_size=8):
    """
    Use AI to score and explain job matches in batches.
    Returns a dict of {job_id: {"ai_score": int, "ai_reason": str}}.
    Only processes jobs that haven't been AI-scored yet.
    """
    if not is_ai_enabled():
        return {}

    if not jobs:
        return {}

    skills = profile.get("core_skills", [])
    if isinstance(skills, str):
        try:
            skills = json.loads(skills)
        except (json.JSONDecodeError, TypeError):
            skills = []

    role = profile.get("primary_role", "Software Developer")
    exp = profile.get("experience_years", 0)
    location = profile.get("location", "")

    profile_summary = f"Role: {role} | Skills: {', '.join(skills[:10])} | Exp: {exp}yr | Location: {location}"

    system_prompt = f"""You are a job matching expert. Score how well each job fits this candidate:

{profile_summary}

For each job, return:
- score (0-100): How good a fit is this job for this candidate?
- reason (1-2 sentences): Why this score? Mention skill matches, experience fit, red flags.

Scoring guide:
- 80-100: Strong match — skills align, experience fits, worth applying immediately
- 60-79: Good match — most skills align, minor gaps acceptable  
- 40-59: Partial match — some skills match but significant gaps or overqualification
- 0-39: Weak match — different stack, wrong level, or unrelated role

Return ONLY valid JSON array, no explanation:
[{{"id": 1, "score": 85, "reason": "Strong match: needs Spring Boot + React which are your core skills. 2yr experience fits."}}, ...]"""

    results = {}

    # Process in batches
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]

        # Build job descriptions for the prompt
        job_descriptions = []
        for j, job in enumerate(batch):
            job_desc = f"ID {job['id']}: {job['title']}"
            if job.get('company'):
                job_desc += f" at {job['company']}"
            if job.get('location'):
                job_desc += f" ({job['location']})"
            if job.get('description_snippet'):
                job_desc += f"\n  Description: {job['description_snippet'][:200]}"
            job_descriptions.append(job_desc)

        prompt = f"Score these {len(batch)} jobs for the candidate:\n\n" + "\n\n".join(job_descriptions)

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

            for score_entry in scores:
                if not isinstance(score_entry, dict):
                    continue
                job_id = score_entry.get("id")
                ai_score = score_entry.get("score", 0)
                ai_reason = score_entry.get("reason", "")

                if job_id is not None:
                    # Clamp score
                    ai_score = max(0, min(100, int(ai_score)))
                    results[int(job_id)] = {
                        "ai_score": ai_score,
                        "ai_reason": str(ai_reason)[:300],
                    }

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"AI scoring batch parse error: {e}")
            continue

        # Respect rate limits — wait between batches
        time.sleep(2)

    logger.info(f"AI scored {len(results)} jobs")
    return results


# ============================================================
# Integration Functions (called from routes/services)
# ============================================================

def ai_enhance_refresh(profile, new_jobs):
    """
    Run AI enhancements after a job refresh:
    1. Generate additional queries (for next refresh)
    2. Score top new jobs with AI explanations
    
    Returns dict with ai_queries and ai_scores.
    """
    result = {"ai_queries": [], "ai_scores": {}}

    if not is_ai_enabled():
        return result

    # Generate additional queries for next time
    result["ai_queries"] = ai_generate_queries(profile)

    # Score top jobs (by base score, limit to 16 to use 2 batched calls)
    if new_jobs:
        top_jobs = sorted(new_jobs, key=lambda j: j.get("match_score", 0), reverse=True)[:16]
        result["ai_scores"] = ai_score_jobs(top_jobs, profile)

    return result
