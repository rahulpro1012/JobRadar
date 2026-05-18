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

def _call_groq(prompt, system_prompt, model=FAST_MODEL, max_tokens=2000, temperature=0.3):
    """Call Groq API with quota tracking."""
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

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            verify=False,
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
            time.sleep(5)
            return None
        if resp.status_code != 200:
            logger.warning(f"Groq API error: {resp.status_code} {resp.text[:200]}")
            return None

        return resp.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.warning(f"Groq API call failed: {e}")
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
