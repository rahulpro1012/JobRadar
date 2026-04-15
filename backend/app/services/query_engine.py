"""
JobRadar Query Engine
Generates tiered search queries from a parsed resume profile.
Produces 8-12 targeted queries across 3 tiers of specificity.
"""


def generate_queries(profile):
    """
    Generate a query matrix from a parsed profile.

    Args:
        profile: dict with keys like primary_role, core_skills,
                 role_variants, location, experience_years, etc.

    Returns:
        list of dicts, each with:
            - query: str (the search string)
            - tier: int (1=exact, 2=skill combo, 3=variant)
            - site: str or None (for site-scoped queries)
    """
    role = profile.get("primary_role", "Software Developer")
    core_skills = profile.get("core_skills", [])
    variants = profile.get("role_variants", [])
    location = profile.get("location", "")
    exp_years = profile.get("experience_years", 0)

    # Parse skills from JSON if needed
    if isinstance(core_skills, str):
        import json
        try:
            core_skills = json.loads(core_skills)
        except (json.JSONDecodeError, TypeError):
            core_skills = []
    if isinstance(variants, str):
        import json
        try:
            variants = json.loads(variants)
        except (json.JSONDecodeError, TypeError):
            variants = []

    exp_range = _experience_range_str(exp_years)
    loc = location.strip() if location else ""

    queries = []
    seen = set()

    def _add(query_text, tier):
        """Add query if not duplicate."""
        normalized = query_text.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            queries.append({"query": query_text, "tier": tier})

    # ── Tier 1: Exact match (role + location + experience) ──
    if loc:
        _add(f'"{role}" {exp_range} years {loc}', 1)
        _add(f'"{role}" {loc}', 1)
    else:
        _add(f'"{role}" {exp_range} years', 1)

    # Add top skill with role
    if core_skills:
        top_skill = core_skills[0]
        if loc:
            _add(f'"{top_skill} {_role_word(role)}" {loc}', 1)
        else:
            _add(f'"{top_skill} {_role_word(role)}"', 1)

    # ── Tier 2: Skill combination queries ──
    if len(core_skills) >= 2:
        # Pair top skills
        for i in range(min(3, len(core_skills))):
            for j in range(i + 1, min(4, len(core_skills))):
                s1, s2 = core_skills[i], core_skills[j]
                q = f'"{s1}" "{s2}" developer'
                if loc:
                    q += f" {loc}"
                _add(q, 2)

    # Single strong skill + developer
    for skill in core_skills[:3]:
        q = f"{skill} developer jobs"
        if loc:
            q += f" {loc}"
        _add(q, 2)

    # ── Tier 3: Role variants (broader net) ──
    for variant in variants[:4]:
        q = variant
        if loc:
            q += f" {loc}"
        if core_skills:
            q += f" {core_skills[0]}"
        _add(q, 3)

    # Generic fallback
    if loc and core_skills:
        _add(f"software developer {core_skills[0]} jobs {loc}", 3)

    return queries[:12]  # Cap at 12 queries


def generate_site_queries(queries, sites=None):
    """
    Expand queries with site: prefixes for Google/Bing search.

    Args:
        queries: list from generate_queries()
        sites: list of domains to scope, e.g. ["naukri.com", "linkedin.com/jobs"]

    Returns:
        list of dicts with added 'site_query' and 'site' fields
    """
    if sites is None:
        sites = [
            "naukri.com",
            "linkedin.com/jobs",
            "indeed.co.in",
        ]

    site_queries = []
    for q in queries:
        for site in sites:
            site_queries.append({
                "query": q["query"],
                "site_query": f"site:{site} {q['query']}",
                "site": site,
                "tier": q["tier"],
            })

    return site_queries


def generate_rss_urls(profile):
    """
    Generate Indeed RSS feed URLs from profile.
    Indeed RSS format: https://www.indeed.co.in/rss?q=QUERY&l=LOCATION

    Returns:
        list of RSS URL strings
    """
    role = profile.get("primary_role", "Software Developer")
    core_skills = profile.get("core_skills", [])
    location = profile.get("location", "")

    if isinstance(core_skills, str):
        import json
        try:
            core_skills = json.loads(core_skills)
        except (json.JSONDecodeError, TypeError):
            core_skills = []

    urls = []
    base = "https://www.indeed.co.in/rss"

    # Role-based RSS
    q = role.replace(" ", "+")
    loc = location.replace(" ", "+") if location else ""
    urls.append(f"{base}?q={q}&l={loc}&sort=date")

    # Top skills RSS
    for skill in core_skills[:3]:
        sq = f"{skill}+developer".replace(" ", "+")
        urls.append(f"{base}?q={sq}&l={loc}&sort=date")

    return urls[:5]


def _role_word(role):
    """Extract the role noun (Developer/Engineer) from a role title."""
    if "engineer" in role.lower():
        return "Engineer"
    return "Developer"


def _experience_range_str(years):
    """Convert years to a search-friendly range string."""
    if years < 1:
        return "0-1"
    elif years < 3:
        return "1-3"
    elif years < 6:
        return "3-5"
    elif years < 10:
        return "5-10"
    else:
        return "10+"
