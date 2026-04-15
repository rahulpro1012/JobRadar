"""
JobRadar Relevance Scorer
Computes a 0-100 match score for each job based on:
  - Skill Match (40%)
  - Role Match (25%)
  - Experience Fit (20%)
  - Recency (15%)
Then applies preference adjustments from user signals.
"""
import re
import json
import logging
from datetime import datetime, timedelta

from app.database import execute_query, get_connection

logger = logging.getLogger(__name__)


# ============================================================
# Main Scoring Entry Point
# ============================================================

def score_all_jobs(profile):
    """
    Score all unscored (or re-score all new) jobs against the profile.
    Returns the number of jobs scored.
    """
    # Get all jobs that need scoring (new or score=0)
    jobs = execute_query(
        "SELECT * FROM jobs WHERE status = 'new' OR match_score = 0",
        fetch_all=True,
    )
    if not jobs:
        return 0

    # Parse profile fields
    core_skills = _parse_json_field(profile.get("core_skills", "[]"))
    secondary_skills = _parse_json_field(profile.get("secondary_skills", "[]"))
    tools = _parse_json_field(profile.get("tools", "[]"))
    role = profile.get("primary_role", "")
    role_variants = _parse_json_field(profile.get("role_variants", "[]"))
    exp_years = profile.get("experience_years", 0)

    # Load preference weights
    pref_weights = _load_preference_weights()

    scored_count = 0

    with get_connection() as conn:
        for job in jobs:
            # Compute base score
            base_score = compute_score(
                job=job,
                core_skills=core_skills,
                secondary_skills=secondary_skills,
                tools=tools,
                role=role,
                role_variants=role_variants,
                exp_years=exp_years,
            )

            # Apply preference adjustments (±10 max)
            adjustment = compute_preference_adjustment(job, pref_weights)
            adjusted = max(0, min(100, base_score + adjustment))

            # Extract skills found in this job for display
            skills_found = _find_matching_skills(
                job.get("title", "") + " " + job.get("description_snippet", ""),
                core_skills + secondary_skills,
            )

            conn.execute(
                """UPDATE jobs 
                   SET match_score = ?, adjusted_score = ?, skills_found = ?
                   WHERE id = ?""",
                (base_score, adjusted, json.dumps(skills_found), job["id"]),
            )
            scored_count += 1

        conn.commit()

    logger.info(f"Scored {scored_count} jobs")
    return scored_count


# ============================================================
# Core Scoring Algorithm
# ============================================================

def compute_score(job, core_skills, secondary_skills, tools, role, role_variants, exp_years):
    """
    Compute a 0-100 relevance score for a single job.

    Weights:
      - Skill Match:    40%
      - Role Match:     25%
      - Experience Fit: 20%
      - Recency:        15%
    """
    skill_score = _score_skills(job, core_skills, secondary_skills, tools)
    role_score = _score_role(job, role, role_variants)
    exp_score = _score_experience(job, exp_years)
    recency_score = _score_recency(job)

    total = (
        skill_score * 0.40
        + role_score * 0.25
        + exp_score * 0.20
        + recency_score * 0.15
    )

    return max(0, min(100, round(total)))


def _score_skills(job, core_skills, secondary_skills, tools):
    """
    Score 0-100 based on skill matches in job title + description.
    Core skills: +12 each (max 60)
    Secondary skills: +6 each (max 30)
    Tools: +3 each (max 10)
    """
    text = (
        job.get("title", "") + " " + job.get("description_snippet", "")
    ).lower()

    score = 0

    # Core skills (highest value)
    core_matches = 0
    for skill in core_skills:
        if skill.lower() in text:
            core_matches += 1
            score += 12
    score = min(score, 60)  # Cap core contribution

    # Secondary skills
    sec_score = 0
    for skill in secondary_skills:
        if skill.lower() in text:
            sec_score += 6
    score += min(sec_score, 30)

    # Tools
    tool_score = 0
    for tool in tools:
        if tool.lower() in text:
            tool_score += 3
    score += min(tool_score, 10)

    return min(100, score)


def _score_role(job, role, role_variants):
    """
    Score 0-100 based on role title match.
    Exact match: 100
    Variant match: 70
    Partial keyword match: 40
    Developer/Engineer generic: 20
    """
    title = job.get("title", "").lower()

    if not title:
        return 0

    # Exact role match
    if role.lower() in title:
        return 100

    # Variant match
    for variant in role_variants:
        if variant.lower() in title:
            return 70

    # Partial keyword matches
    role_words = set(role.lower().split())
    title_words = set(title.split())
    overlap = role_words & title_words
    if len(overlap) >= 2:
        return 55

    # Generic developer/engineer match
    dev_keywords = {"developer", "engineer", "programmer", "architect", "sde"}
    if dev_keywords & title_words:
        return 30

    # Very generic tech role
    tech_keywords = {"software", "web", "full stack", "fullstack", "backend",
                     "frontend", "java", "react", "spring", "node"}
    if any(kw in title for kw in tech_keywords):
        return 20

    return 0


def _score_experience(job, user_years):
    """
    Score 0-100 based on experience fit.
    Checks job title and description for experience requirements.
    """
    text = (
        job.get("title", "") + " " + job.get("description_snippet", "")
        + " " + job.get("experience_required", "")
    ).lower()

    # Try to extract required years from the job
    required_range = _extract_experience_range(text)

    if required_range is None:
        # No experience mentioned — assume it's a match (benefit of doubt)
        return 70

    min_req, max_req = required_range

    # Perfect fit: user's experience falls within the range
    if min_req <= user_years <= max_req:
        return 100

    # Close fit: within 1 year of range
    if (min_req - 1) <= user_years <= (max_req + 1):
        return 75

    # Overlapping range
    if user_years < min_req:
        gap = min_req - user_years
        if gap <= 2:
            return 50
        elif gap <= 4:
            return 25
        return 10

    if user_years > max_req:
        gap = user_years - max_req
        if gap <= 2:
            return 60  # Slightly overqualified is OK
        return 30

    return 50


def _extract_experience_range(text):
    """Extract experience range (min, max) from text. Returns None if not found."""
    # Pattern: "2-5 years", "3 to 7 years", "5+ years"
    range_match = re.search(
        r"(\d+)\s*[\-–to]+\s*(\d+)\s*(?:\+?\s*)?(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)?",
        text,
        re.IGNORECASE,
    )
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    # Pattern: "5+ years"
    plus_match = re.search(
        r"(\d+)\+\s*(?:years?|yrs?)",
        text,
        re.IGNORECASE,
    )
    if plus_match:
        base = int(plus_match.group(1))
        return base, base + 5

    # Pattern: "minimum 3 years" or "at least 2 years"
    min_match = re.search(
        r"(?:minimum|min|at\s*least)\s*(\d+)\s*(?:years?|yrs?)",
        text,
        re.IGNORECASE,
    )
    if min_match:
        base = int(min_match.group(1))
        return base, base + 5

    # Pattern: just "X years experience"
    simple_match = re.search(
        r"(\d+)\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)",
        text,
        re.IGNORECASE,
    )
    if simple_match:
        yrs = int(simple_match.group(1))
        return max(0, yrs - 1), yrs + 2

    # Senior/Lead implies 5+ years
    if re.search(r"\b(?:senior|sr\.?|lead|principal|staff)\b", text, re.IGNORECASE):
        return 5, 15

    # Junior/Entry implies 0-2 years
    if re.search(r"\b(?:junior|jr\.?|entry|fresher|trainee|intern)\b", text, re.IGNORECASE):
        return 0, 3

    return None


def _score_recency(job):
    """
    Score 0-100 based on how recently the job was posted/fetched.
    Today: 100
    Within 3 days: 80
    Within 7 days: 60
    Within 14 days: 40
    Within 30 days: 20
    Older: 10
    """
    # Try posted_date first, fall back to fetched_date
    date_str = job.get("posted_date", "") or job.get("fetched_date", "")

    if not date_str:
        return 50  # Unknown date — neutral score

    try:
        # Try various date formats
        for fmt in [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y",
            "%B %d, %Y",
        ]:
            try:
                date = datetime.strptime(date_str.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return 50  # Couldn't parse — neutral

        days_old = (datetime.now() - date).days

        if days_old <= 0:
            return 100
        elif days_old <= 3:
            return 80
        elif days_old <= 7:
            return 60
        elif days_old <= 14:
            return 40
        elif days_old <= 30:
            return 20
        else:
            return 10

    except Exception:
        return 50


# ============================================================
# Preference Adjustments
# ============================================================

def _load_preference_weights():
    """Load all preference weights from database."""
    weights = execute_query(
        "SELECT category, key, weight FROM preference_weights",
        fetch_all=True,
    )
    result = {}
    for w in weights:
        cat = w["category"]
        if cat not in result:
            result[cat] = {}
        result[cat][w["key"].lower()] = w["weight"]
    return result


def compute_preference_adjustment(job, pref_weights):
    """
    Compute a preference adjustment (-10 to +10) based on learned signals.
    Checks skill, company_type, and source preferences.
    """
    adjustment = 0.0

    # Skill preferences
    skill_prefs = pref_weights.get("skill", {})
    if skill_prefs:
        text = (job.get("title", "") + " " + job.get("description_snippet", "")).lower()
        for skill, weight in skill_prefs.items():
            if skill in text:
                adjustment += weight * 0.5  # Dampen individual skill impact

    # Source preferences
    source_prefs = pref_weights.get("source", {})
    source_domain = job.get("source_domain", "").lower()
    if source_domain in source_prefs:
        adjustment += source_prefs[source_domain]

    # Company preferences
    company_prefs = pref_weights.get("company_type", {})
    company = job.get("company", "").lower()
    for company_key, weight in company_prefs.items():
        if company_key in company:
            adjustment += weight

    # Clamp to ±10
    return max(-10, min(10, round(adjustment)))


def update_preference_weights(job_id, action):
    """
    Update preference weights based on a user action on a job.
    Called when user applies, saves, or skips a job.

    Weights:
      apply:  skill +3, company +2, source +1
      save:   skill +1, company +1
      skip:   skill -1, company -1
    """
    job = execute_query("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch_one=True)
    if not job:
        return

    if action == "applied":
        skill_delta, company_delta, source_delta = 3, 2, 1
    elif action == "saved":
        skill_delta, company_delta, source_delta = 1, 1, 0
    elif action == "skipped":
        skill_delta, company_delta, source_delta = -1, -1, 0
    else:
        return

    skills_found = _parse_json_field(job.get("skills_found", "[]"))
    company = job.get("company", "").lower().strip()
    source = job.get("source_domain", "").lower().strip()

    with get_connection() as conn:
        # Update skill weights
        for skill in skills_found:
            _upsert_weight(conn, "skill", skill.lower(), skill_delta)

        # Update company weight
        if company:
            _upsert_weight(conn, "company_type", company, company_delta)

        # Update source weight
        if source and source_delta != 0:
            _upsert_weight(conn, "source", source, source_delta)

        conn.commit()


def _upsert_weight(conn, category, key, delta):
    """Insert or update a preference weight, clamping to ±10."""
    conn.execute("""
        INSERT INTO preference_weights (category, key, weight, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(category, key)
        DO UPDATE SET 
            weight = MAX(-10, MIN(10, weight + ?)),
            updated_at = CURRENT_TIMESTAMP
    """, (category, key, max(-10, min(10, delta)), delta))


# ============================================================
# Helpers
# ============================================================

def _find_matching_skills(text, all_skills):
    """Find which skills from the profile appear in the job text."""
    text_lower = text.lower()
    found = []
    for skill in all_skills:
        if skill.lower() in text_lower:
            found.append(skill)
    return found[:10]  # Cap at 10 for display


def _parse_json_field(value):
    """Parse a JSON string or return list as-is."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return []
