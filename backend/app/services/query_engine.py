"""
JobRadar Query Engine (AI-Enhanced)
Generates tiered search queries + merges AI-generated queries.
"""


def generate_queries(profile, ai_queries=None):
    """
    Generate query matrix from profile + optional AI queries.
    AI queries are added as Tier 2 (medium priority).
    """
    role = profile.get("primary_role", "Software Developer")
    core_skills = profile.get("core_skills", [])
    variants = profile.get("role_variants", [])
    location = profile.get("location", "")
    exp_years = profile.get("experience_years", 0)

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
        normalized = query_text.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            queries.append({"query": query_text, "tier": tier})

    # ── Tier 1: Exact match ──
    if loc:
        _add(f'"{role}" {exp_range} years {loc}', 1)
        _add(f'"{role}" {loc}', 1)
    else:
        _add(f'"{role}" {exp_range} years', 1)

    if core_skills:
        top_skill = core_skills[0]
        if loc:
            _add(f'"{top_skill} {_role_word(role)}" {loc}', 1)
        else:
            _add(f'"{top_skill} {_role_word(role)}"', 1)

    # ── Tier 2: Skill combinations ──
    if len(core_skills) >= 2:
        for i in range(min(3, len(core_skills))):
            for j in range(i + 1, min(4, len(core_skills))):
                s1, s2 = core_skills[i], core_skills[j]
                q = f'"{s1}" "{s2}" developer'
                if loc:
                    q += f" {loc}"
                _add(q, 2)

    for skill in core_skills[:3]:
        q = f"{skill} developer jobs"
        if loc:
            q += f" {loc}"
        _add(q, 2)

    # ── AI-generated queries (Tier 2, merged in) ──
    if ai_queries:
        for aq in ai_queries[:6]:
            _add(aq, 2)

    # ── Tier 3: Role variants ──
    for variant in variants[:4]:
        q = variant
        if loc:
            q += f" {loc}"
        if core_skills:
            q += f" {core_skills[0]}"
        _add(q, 3)

    if loc and core_skills:
        _add(f"software developer {core_skills[0]} jobs {loc}", 3)

    return queries[:15]  # Increased cap to accommodate AI queries


def generate_site_queries(queries, sites=None):
    """Expand queries with site: prefixes for Google/Bing."""
    if sites is None:
        sites = ["naukri.com", "linkedin.com/jobs", "indeed.co.in"]

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
    """Generate Indeed RSS feed URLs."""
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

    q = role.replace(" ", "+")
    loc = location.replace(" ", "+") if location else ""
    urls.append(f"{base}?q={q}&l={loc}&sort=date")

    for skill in core_skills[:3]:
        sq = f"{skill}+developer".replace(" ", "+")
        urls.append(f"{base}?q={sq}&l={loc}&sort=date")

    return urls[:5]


def _role_word(role):
    if "engineer" in role.lower():
        return "Engineer"
    return "Developer"


def _experience_range_str(years):
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
