"""
JobRadar Resume Parser
Extracts text from PDF/DOCX files and builds a structured profile.
Uses section detection, skill matching, and experience calculation.
"""
import re
import json
from pathlib import Path
from collections import Counter

from app.services.skills_dictionary import (
    ALL_SKILLS,
    SKILL_TO_CATEGORY,
    SKILL_CATEGORIES,
    ROLE_TITLES,
    EXPERIENCE_LEVELS,
)


# ============================================================
# Text Extraction
# ============================================================

def extract_text_from_pdf(filepath):
    """Extract text from a PDF file using pdfminer."""
    from pdfminer.high_level import extract_text
    try:
        text = extract_text(filepath)
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")


def extract_text_from_docx(filepath):
    """Extract text from a DOCX file."""
    try:
        from docx import Document
        doc = Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except ImportError:
        try:
            import docx2txt
            return docx2txt.process(filepath)
        except ImportError:
            raise ValueError("No DOCX parser available. Install python-docx or docx2txt.")


def extract_text(filepath):
    """Extract text from a resume file (PDF or DOCX)."""
    filepath = str(filepath)
    ext = filepath.rsplit(".", 1)[-1].lower()
    
    if ext == "pdf":
        return extract_text_from_pdf(filepath)
    elif ext in ("docx", "doc"):
        return extract_text_from_docx(filepath)
    else:
        raise ValueError(f"Unsupported file type: .{ext}")


# ============================================================
# Section Detection
# ============================================================

SECTION_PATTERNS = {
    "summary": r"(?i)(?:summary|objective|profile|about\s*me|career\s*objective|professional\s*summary)",
    "experience": r"(?i)(?:experience|work\s*experience|employment|professional\s*experience|work\s*history|career\s*history)",
    "education": r"(?i)(?:education|academic|qualification|degree|university|college)",
    "skills": r"(?i)(?:skills|technical\s*skills|technologies|tech\s*stack|competencies|proficiencies|expertise|tools\s*(?:and|&)\s*technologies)",
    "projects": r"(?i)(?:projects|personal\s*projects|key\s*projects|notable\s*projects)",
    "certifications": r"(?i)(?:certifications?|certificates?|licenses?|credentials)",
}


def detect_sections(text):
    """
    Split resume text into sections based on common headings.
    Returns a dict of section_name -> section_text.
    """
    lines = text.split("\n")
    sections = {}
    current_section = "header"
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_lines.append("")
            continue

        matched_section = None
        for section_name, pattern in SECTION_PATTERNS.items():
            # Match if the line is primarily a section header
            # (short line that matches the pattern)
            if len(stripped) < 60 and re.search(pattern, stripped):
                matched_section = section_name
                break

        if matched_section:
            # Save previous section
            if current_lines:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = matched_section
            current_lines = []
        else:
            current_lines.append(line)

    # Save last section
    if current_lines:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


# ============================================================
# Skill Extraction
# ============================================================

def extract_skills(text):
    """
    Extract skills from text by matching against the skills dictionary.
    Returns (core_skills, secondary_skills, tools) based on frequency.
    """
    text_lower = text.lower()
    skill_counts = Counter()

    # Multi-word skills first (longer matches take priority)
    sorted_skills = sorted(ALL_SKILLS, key=len, reverse=True)

    # Skills that commonly produce false positives from substrings
    # e.g., "ember" in "September", "scala" in "scalable", "go" in "going"
    substring_false_positives = {
        "ember": ["september", "november", "december", "remember", "member"],
        "scala": ["scalable", "scalability", "scaling"],
        "go": ["going", "good", "google", "goal", "gone", "got"],
        "r": ["for", "or", "are", "your", "our"],
        "c": ["css", "ci/cd"],
        "dart": ["standard", "darting"],
        "ion": ["action", "function", "application", "session"],
        "ant": ["want", "relevant", "significant"],
        "gin": ["engineering", "login", "staging"],
        "echo": ["technology"],
        "flux": ["influx"],
    }

    for skill in sorted_skills:
        # Use word boundary matching for short skills to avoid false positives
        if len(skill) <= 2:
            # Very short skills (C, R) need exact word boundary
            pattern = r"(?<![a-zA-Z])" + re.escape(skill) + r"(?![a-zA-Z])"
        elif len(skill) <= 3:
            pattern = r"\b" + re.escape(skill) + r"\b"
        else:
            # For longer skills, use word boundaries too
            pattern = r"\b" + re.escape(skill) + r"\b"

        matches = re.findall(pattern, text_lower)
        if matches:
            # Check for substring false positives
            if skill in substring_false_positives:
                false_containers = substring_false_positives[skill]
                # Count real matches (not inside a false positive word)
                real_count = len(matches)
                for fp_word in false_containers:
                    fp_matches = len(re.findall(re.escape(fp_word), text_lower))
                    real_count -= fp_matches
                if real_count <= 0:
                    continue
                skill_counts[skill] = real_count
            else:
                skill_counts[skill] = len(matches)

    # Categorize by frequency
    # Core skills: mentioned 2+ times or in title/header section
    # Secondary skills: mentioned once
    # Tools: from the tools category
    
    # Filter out noisy/generic matches
    noise_skills = {"rest", "mock", "web", "app", "api", "test", "code",
                    "build", "design", "security", "cloud", "data",
                    "mobile", "desktop", "server", "client", "service",
                    "system", "network", "database", "framework",
                    "library", "platform", "environment", "language",
                    "authentication", "authorization", "encryption",
                    "hashing", "logging", "monitoring", "alerting",
                    "ember", "backbone", "caching", "apache"}
    
    core = []
    secondary = []
    tools = []

    for skill, count in skill_counts.most_common():
        category = SKILL_TO_CATEGORY.get(skill, "")
        canonical = _canonical_skill_name(skill)

        # Skip noise words
        if skill.lower() in noise_skills:
            continue

        # Skip if we already have a variant of this skill
        if canonical in core or canonical in secondary or canonical in tools:
            continue

        if category == "tools":
            tools.append(canonical)
        elif count >= 2:
            core.append(canonical)
        else:
            secondary.append(canonical)

    return core[:15], secondary[:15], tools[:10]


def _canonical_skill_name(skill):
    """Convert a skill to its canonical display form."""
    # Map common variations to canonical names
    canonical_map = {
        "reactjs": "React",
        "react.js": "React",
        "vuejs": "Vue",
        "vue.js": "Vue",
        "angularjs": "Angular",
        "nodejs": "Node.js",
        "node.js": "Node.js",
        "express.js": "Express",
        "nextjs": "Next.js",
        "next.js": "Next.js",
        "nuxtjs": "Nuxt",
        "golang": "Go",
        "k8s": "Kubernetes",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mongodb": "MongoDB",
        "mysql": "MySQL",
        "nosql": "NoSQL",
        "graphql": "GraphQL",
        "typescript": "TypeScript",
        "javascript": "JavaScript",
        "tailwindcss": "Tailwind CSS",
        "spring boot": "Spring Boot",
        "spring mvc": "Spring MVC",
        "spring data": "Spring Data",
        "spring security": "Spring Security",
        "spring cloud": "Spring Cloud",
        "spring framework": "Spring Framework",
        "intellij idea": "IntelliJ IDEA",
        "intellij": "IntelliJ IDEA",
        "vs code": "VS Code",
        "visual studio code": "VS Code",
        "ci/cd": "CI/CD",
        "ci cd": "CI/CD",
        "amazon web services": "AWS",
        "google cloud": "GCP",
        "azure devops": "Azure DevOps",
        "github actions": "GitHub Actions",
        "gitlab ci": "GitLab CI",
        "junit5": "JUnit 5",
        "mockmvc": "MockMvc",
        "rest api": "REST API",
        "restful": "REST API",
        "jdbctemplate": "JdbcTemplate",
    }

    lower = skill.lower()
    if lower in canonical_map:
        return canonical_map[lower]

    # Default: title case with special handling
    if len(skill) <= 3 and skill.upper() in ("CSS", "SQL", "JSP", "JPA", "XML",
                                                "API", "AWS", "GCP", "SRE", "TDD",
                                                "BDD", "OOP", "DDD", "SQS", "SNS",
                                                "CDN", "DNS", "SSL", "TLS", "SSO",
                                                "HTML", "SASS", "SCSS", "LESS", "JSX",
                                                "TSX", "DOM", "SPA", "SSR", "SSG",
                                                "JWT", "MVC", "MVVM", "ETL", "NLP",
                                                "GIT", "SVN", "PHP", "LLM", "GPT"):
        return skill.upper()

    # Title case but keep known casing
    return skill.title()


# ============================================================
# Experience Extraction
# ============================================================

DATE_PATTERN = re.compile(
    r"(?:"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,./\-]*\d{4}"
    r"|"
    r"\d{1,2}[\s,./\-]+\d{4}"
    r"|"
    r"\d{4}"
    r")",
    re.IGNORECASE,
)

DURATION_PATTERN = re.compile(
    r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:(?:and|&)\s*)?(?:(\d+)\s*(?:months?|mos?))?",
    re.IGNORECASE,
)

EXPERIENCE_RANGE_PATTERN = re.compile(
    r"(\d+)\s*[\-–to]+\s*(\d+)\s*(?:years?|yrs?)",
    re.IGNORECASE,
)


def extract_experience_years(text, sections=None):
    """
    Calculate total years of experience from resume text.
    Tries multiple strategies:
    1. Look for explicit "X years of experience" statements
    2. Parse date ranges from experience section
    3. Estimate from graduation year
    """
    # Strategy 1: Explicit mention
    explicit = re.findall(
        r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)",
        text,
        re.IGNORECASE,
    )
    if explicit:
        return float(max(int(x) for x in explicit))

    # Strategy 2: Duration mentions like "3 years and 6 months"
    durations = DURATION_PATTERN.findall(text)
    if durations:
        max_years = 0
        for years_str, months_str in durations:
            years = int(years_str)
            months = int(months_str) if months_str else 0
            total = years + months / 12
            max_years = max(max_years, total)
        if max_years > 0:
            return round(max_years, 1)

    # Strategy 3: Parse date ranges from experience section
    exp_text = sections.get("experience", "") if sections else text
    if exp_text:
        years_found = re.findall(r"\b(20\d{2}|19\d{2})\b", exp_text)
        if len(years_found) >= 2:
            years_int = [int(y) for y in years_found]
            span = max(years_int) - min(years_int)
            if 0 < span <= 40:
                return float(span)

    # Strategy 4: Check for "present" or "current" to calculate from earliest year
    if re.search(r"\b(?:present|current|till\s*date|ongoing)\b", text, re.IGNORECASE):
        all_years = re.findall(r"\b(20\d{2})\b", text)
        if all_years:
            from datetime import datetime
            earliest = min(int(y) for y in all_years)
            current_year = datetime.now().year
            span = current_year - earliest
            if 0 < span <= 40:
                return float(span)

    return 0.0


def get_experience_level(years):
    """Map years of experience to a level string."""
    for (low, high), level in EXPERIENCE_LEVELS.items():
        if low <= years < high:
            return level
    return "Junior"


def get_experience_range(years):
    """Get a search-friendly experience range string."""
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


# ============================================================
# Role Detection
# ============================================================

def detect_role(text, core_skills, sections=None):
    """
    Detect the primary role and generate variant titles.
    Uses the header/summary section and skill combinations.
    """
    text_lower = text.lower()
    header_text = (sections.get("header", "") + " " + sections.get("summary", "")).lower() if sections else text_lower

    # Check for explicit role mentions in header/summary
    primary_role = None
    for role, variants in ROLE_TITLES.items():
        for variant in variants:
            if variant in header_text:
                primary_role = role.title()
                break
        if primary_role:
            break

    # If not found in header, check full text
    if not primary_role:
        for role, variants in ROLE_TITLES.items():
            for variant in variants:
                if variant in text_lower:
                    primary_role = role.title()
                    break
            if primary_role:
                break

    # Infer from skills if still not found
    if not primary_role:
        core_lower = [s.lower() for s in core_skills]
        has_frontend = any(s in core_lower for s in ["react", "angular", "vue", "html", "css"])
        has_backend = any(s in core_lower for s in ["spring boot", "spring", "node.js", "django", "flask", "java"])
        has_mobile = any(s in core_lower for s in ["android", "ios", "react native", "flutter"])

        if has_frontend and has_backend:
            primary_role = "Full Stack Developer"
        elif has_frontend:
            primary_role = "Frontend Developer"
        elif has_backend:
            primary_role = "Backend Developer"
        elif has_mobile:
            primary_role = "Mobile Developer"
        else:
            primary_role = "Software Developer"

    # Generate role variants for broader search
    role_variants = _generate_role_variants(primary_role, core_skills)

    return primary_role, role_variants


def _generate_role_variants(primary_role, core_skills):
    """Generate alternative job title variants for search queries."""
    variants = set()
    core_lower = [s.lower() for s in core_skills]

    # Base variants
    role_base = primary_role.lower()
    if "developer" in role_base:
        variants.add(primary_role.replace("Developer", "Engineer"))
    elif "engineer" in role_base:
        variants.add(primary_role.replace("Engineer", "Developer"))

    # Skill-specific variants
    if "java" in core_lower:
        variants.add("Java Developer")
        if any(s in core_lower for s in ["react", "angular", "vue"]):
            variants.add("Java Full Stack Developer")
    if "spring boot" in core_lower or "spring" in core_lower:
        variants.add("Spring Boot Developer")
    if "react" in core_lower:
        variants.add("React Developer")
    if "node.js" in core_lower:
        variants.add("Node.js Developer")
    if "python" in core_lower:
        variants.add("Python Developer")

    # Generic variants
    variants.add("Software Engineer")
    variants.add("Software Developer")
    variants.add("Web Developer")

    # Remove the primary role from variants
    variants.discard(primary_role)

    return list(variants)[:8]


# ============================================================
# Name & Location Extraction
# ============================================================

def extract_name(text, sections=None):
    """
    Extract candidate name from the header section.
    Typically the first non-empty line that looks like a name.
    """
    header = sections.get("header", text) if sections else text
    lines = [l.strip() for l in header.split("\n") if l.strip()]

    for line in lines[:5]:  # Check first 5 lines only
        # Skip lines that look like contact info
        if re.search(r"[@|phone|email|http|www\.|linkedin|github|\d{10}]", line, re.IGNORECASE):
            # But the name might be the part BEFORE the separator
            parts = re.split(r"[|,]", line)
            first_part = parts[0].strip()
            if 2 < len(first_part) < 40 and re.match(r"^[A-Za-z\s.\-']+$", first_part):
                return first_part
            continue
        # Skip lines that are section headers
        if any(re.search(p, line) for p in SECTION_PATTERNS.values()):
            continue
        # Skip lines that are too long (probably description) or too short
        if 2 < len(line) < 40:
            # Check if it looks like a name (mostly letters and spaces)
            if re.match(r"^[A-Za-z\s.\-']+$", line):
                return line.strip()

    return ""


def extract_location(text, sections=None):
    """
    Extract location from resume text.
    Prioritizes the header/contact section (current location)
    over locations mentioned in experience or education.
    """
    # Common Indian cities
    indian_cities = [
        "Mumbai", "Delhi", "Bangalore", "Bengaluru", "Hyderabad",
        "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur",
        "Lucknow", "Kanpur", "Nagpur", "Indore", "Thane",
        "Bhopal", "Visakhapatnam", "Patna", "Vadodara", "Ghaziabad",
        "Ludhiana", "Agra", "Nashik", "Faridabad", "Meerut",
        "Rajkot", "Varanasi", "Srinagar", "Aurangabad", "Dhanbad",
        "Noida", "Gurgaon", "Gurugram", "Navi Mumbai",
        "Coimbatore", "Kochi", "Cochin", "Trivandrum",
        "Thiruvananthapuram", "Mysore", "Mysuru",
    ]

    # Strategy 1: Check header section first (most likely current location)
    header = sections.get("header", "") if sections else ""
    if header:
        for city in indian_cities:
            if re.search(r"\b" + re.escape(city) + r"\b", header, re.IGNORECASE):
                return city

    # Strategy 2: Check the first 3 lines of the entire text (contact info area)
    first_lines = "\n".join(text.split("\n")[:5])
    for city in indian_cities:
        if re.search(r"\b" + re.escape(city) + r"\b", first_lines, re.IGNORECASE):
            return city

    # Strategy 3: Check near "present" or current job (current work location)
    present_match = re.search(
        r"(?:present|current|ongoing).*?\n(.*?)(?:\n|$)",
        text, re.IGNORECASE
    )
    if not present_match:
        # Try the line BEFORE "present"
        present_match = re.search(
            r"([^\n]+)(?:\s+\w+\s+\d{4}\s*-\s*(?:present|current))",
            text, re.IGNORECASE
        )
    if present_match:
        context = present_match.group(0)
        for city in indian_cities:
            if re.search(r"\b" + re.escape(city) + r"\b", context, re.IGNORECASE):
                return city

    # Strategy 4: Fall back to first city mentioned anywhere
    for city in indian_cities:
        if re.search(r"\b" + re.escape(city) + r"\b", text, re.IGNORECASE):
            return city

    # Strategy 5: Try generic location patterns
    loc_match = re.search(
        r"(?:location|city|address|based\s*(?:in|at)|residing\s*(?:in|at))\s*[:\-]?\s*([A-Za-z\s]+?)(?:\n|,|\.|$)",
        text,
        re.IGNORECASE,
    )
    if loc_match:
        return loc_match.group(1).strip()

    return ""


# ============================================================
# Education Extraction
# ============================================================

EDUCATION_PATTERNS = [
    (r"\b(?:b\.?\s*tech|bachelor\s*of\s*technology)\b", "B.Tech"),
    (r"\b(?:b\.?\s*e\.?\b|bachelor\s*of\s*engineering)", "B.E."),
    (r"\b(?:m\.?\s*tech|master\s*of\s*technology)\b", "M.Tech"),
    (r"\b(?:m\.?\s*e\.?\b|master\s*of\s*engineering)", "M.E."),
    (r"\b(?:b\.?\s*sc\b|bachelor\s*of\s*science)", "B.Sc"),
    (r"\b(?:m\.?\s*sc\b|master\s*of\s*science)", "M.Sc"),
    (r"\b(?:b\.?\s*c\.?\s*a\b|bachelor\s*of\s*computer\s*application)", "BCA"),
    (r"\b(?:m\.?\s*c\.?\s*a\b|master\s*of\s*computer\s*application)", "MCA"),
    (r"\b(?:mba\b|master\s*of\s*business\s*administration)", "MBA"),
    (r"\b(?:ph\.?\s*d\b|doctorate)", "Ph.D"),
    (r"\b(?:diploma)\b", "Diploma"),
]


def extract_education(text, sections=None):
    """Extract highest education qualification."""
    # Use education section if available, otherwise full text
    edu_text = sections.get("education", "") if sections else ""
    if len(edu_text.strip()) < 5:
        # Education section might be too short if the heading consumed the first line
        # Fall back to full text
        edu_text = text
    edu_lower = edu_text.lower()

    # Also check full text as fallback
    full_lower = text.lower()

    # Check from highest to lowest
    for pattern, label in reversed(EDUCATION_PATTERNS):
        # Try education section first, then full text
        for search_text in [edu_lower, full_lower]:
            if re.search(pattern, search_text):
                # Try to find the field of study
                field_match = re.search(
                    pattern + r"[.\s,\-in]*(?:in\s+)?([A-Za-z\s&]+?)(?:\n|,|\(|\d|$)",
                    search_text,
                )
                if field_match:
                    field = field_match.group(1).strip().title()
                    if len(field) > 3 and len(field) < 50:
                        return f"{label} {field}"
                return label

    return ""


# ============================================================
# Domain Keywords
# ============================================================

DOMAIN_KEYWORDS = [
    "web application", "mobile application", "desktop application",
    "microservices", "monolithic", "distributed system",
    "cloud native", "cloud computing", "serverless",
    "e-commerce", "ecommerce", "fintech", "healthcare",
    "edtech", "saas", "paas", "iaas",
    "real-time", "real time", "high availability",
    "scalability", "performance optimization",
    "ci/cd", "devops", "automation",
    "api development", "api integration",
    "data pipeline", "data processing",
    "machine learning", "artificial intelligence",
    "blockchain", "iot", "internet of things",
    "cybersecurity", "information security",
]


def extract_domain_keywords(text):
    """Extract domain/industry keywords from the resume."""
    text_lower = text.lower()
    found = []
    for kw in DOMAIN_KEYWORDS:
        if kw in text_lower:
            found.append(kw.title())
    return found[:10]


# ============================================================
# Main Parse Function
# ============================================================

def parse_resume(filepath):
    """
    Parse a resume file and return a structured profile dictionary.

    Returns:
        dict with keys: name, primary_role, role_variants, experience_years,
        experience_level, core_skills, secondary_skills, tools,
        domain_keywords, education, location, resume_text
    """
    # Extract raw text
    raw_text = extract_text(filepath)
    if not raw_text or len(raw_text.strip()) < 50:
        raise ValueError("Could not extract meaningful text from the resume file.")

    # Detect sections
    sections = detect_sections(raw_text)

    # Extract all components
    core_skills, secondary_skills, tools = extract_skills(raw_text)
    experience_years = extract_experience_years(raw_text, sections)
    experience_level = get_experience_level(experience_years)
    primary_role, role_variants = detect_role(raw_text, core_skills, sections)
    name = extract_name(raw_text, sections)
    location = extract_location(raw_text, sections)
    education = extract_education(raw_text, sections)
    domain_keywords = extract_domain_keywords(raw_text)

    return {
        "name": name,
        "primary_role": primary_role,
        "role_variants": role_variants,
        "experience_years": experience_years,
        "experience_level": experience_level,
        "core_skills": core_skills,
        "secondary_skills": secondary_skills,
        "tools": tools,
        "domain_keywords": domain_keywords,
        "education": education,
        "location": location,
        "resume_text": raw_text[:5000],  # Store first 5000 chars for reference
    }
