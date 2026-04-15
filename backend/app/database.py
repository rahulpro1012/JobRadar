"""
JobRadar Database Layer
Handles both local SQLite (development) and Turso (production).
Provides schema creation, connection management, and query helpers.
"""
import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

# Will be set by init_db()
_db_path = None
_use_turso = False
_turso_url = None
_turso_token = None


# ============================================================
# Schema Definition
# ============================================================

SCHEMA_SQL = """
-- User's parsed resume profile
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT DEFAULT '',
    primary_role TEXT DEFAULT '',
    role_variants TEXT DEFAULT '[]',
    experience_years REAL DEFAULT 0,
    experience_level TEXT DEFAULT '',
    core_skills TEXT DEFAULT '[]',
    secondary_skills TEXT DEFAULT '[]',
    tools TEXT DEFAULT '[]',
    domain_keywords TEXT DEFAULT '[]',
    education TEXT DEFAULT '',
    location TEXT DEFAULT '',
    resume_text TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Fetched job listings
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    location TEXT DEFAULT '',
    source_url TEXT NOT NULL,
    source_domain TEXT DEFAULT '',
    description_snippet TEXT DEFAULT '',
    skills_found TEXT DEFAULT '[]',
    experience_required TEXT DEFAULT '',
    posted_date TEXT DEFAULT '',
    fetched_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    match_score INTEGER DEFAULT 0,
    adjusted_score INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new' CHECK(status IN ('new', 'saved', 'applied', 'skipped', 'archived')),
    duplicate_cluster_id INTEGER DEFAULT NULL,
    also_on TEXT DEFAULT '[]'
);

-- Multi-level blacklist
CREATE TABLE IF NOT EXISTS blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('domain', 'company', 'keyword')),
    value TEXT NOT NULL,
    added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(type, value)
);

-- User action signals for preference learning
CREATE TABLE IF NOT EXISTS user_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('applied', 'saved', 'skipped')),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- Company career page registry
CREATE TABLE IF NOT EXISTS company_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    careers_url TEXT NOT NULL,
    search_pattern TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    last_scraped DATETIME DEFAULT NULL,
    UNIQUE(careers_url)
);

-- Preference weights for scoring adjustments
CREATE TABLE IF NOT EXISTS preference_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK(category IN ('skill', 'company_type', 'source')),
    key TEXT NOT NULL,
    weight REAL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);

-- API quota tracking
CREATE TABLE IF NOT EXISTS quota_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    date TEXT NOT NULL,
    calls_used INTEGER DEFAULT 0,
    UNIQUE(source, date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched_date ON jobs(fetched_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_source_domain ON jobs(source_domain);
CREATE INDEX IF NOT EXISTS idx_blacklist_type ON blacklist(type);
CREATE INDEX IF NOT EXISTS idx_quota_date ON quota_usage(date);
"""

# Default company career page registry (Indian IT + product companies)
DEFAULT_COMPANIES = [
    ("TCS", "https://ibegin.tcs.com/iBegin/jobs/search", ""),
    ("Infosys", "https://career.infosys.com/joblist", ""),
    ("Wipro", "https://careers.wipro.com/search-jobs", ""),
    ("HCLTech", "https://www.hcltech.com/careers", ""),
    ("Persistent Systems", "https://careers.persistent.com/job-search", ""),
    ("Publicis Sapient", "https://careers.publicissapient.com/job-search", ""),
    ("Accenture India", "https://www.accenture.com/in-en/careers/jobsearch", ""),
    ("Thoughtworks", "https://www.thoughtworks.com/careers/jobs", ""),
    ("Razorpay", "https://razorpay.com/jobs", ""),
    ("Atlassian", "https://www.atlassian.com/company/careers/all-jobs", ""),
    ("Microsoft India", "https://careers.microsoft.com/v2/global/en/search", ""),
    ("Google India", "https://www.google.com/about/careers/applications/jobs/results", ""),
    ("Amazon India", "https://www.amazon.jobs/en/locations/india", ""),
    ("Flipkart", "https://www.flipkartcareers.com/#!/joblist", ""),
    ("Swiggy", "https://careers.swiggy.com", ""),
]


# ============================================================
# Connection Management
# ============================================================

def init_db(app_config):
    """Initialize database configuration from app config."""
    global _db_path, _use_turso, _turso_url, _turso_token
    
    _use_turso = app_config.get("USE_TURSO", False)
    _turso_url = app_config.get("TURSO_DATABASE_URL", "")
    _turso_token = app_config.get("TURSO_AUTH_TOKEN", "")
    _db_path = app_config.get("SQLITE_DB_PATH", "jobradar.db")
    
    # Create tables
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        _seed_default_companies(conn)
        conn.commit()


def _seed_default_companies(conn):
    """Insert default company career pages if table is empty."""
    cursor = conn.execute("SELECT COUNT(*) FROM company_sources")
    count = cursor.fetchone()[0]
    if count == 0:
        for name, url, pattern in DEFAULT_COMPANIES:
            conn.execute(
                "INSERT OR IGNORE INTO company_sources (company_name, careers_url, search_pattern) VALUES (?, ?, ?)",
                (name, url, pattern)
            )


@contextmanager
def get_connection():
    """
    Get a database connection.
    Uses local SQLite for development, Turso for production.
    """
    if _use_turso:
        conn = _get_turso_connection()
    else:
        conn = sqlite3.connect(_db_path)
    
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _get_turso_connection():
    """
    Get a Turso connection via libsql.
    Falls back to local SQLite if libsql is not installed.
    """
    try:
        import libsql_experimental as libsql
        return libsql.connect(
            _turso_url,
            auth_token=_turso_token
        )
    except ImportError:
        # Fallback: if libsql not installed, use local SQLite
        print("WARNING: libsql not installed, falling back to local SQLite")
        return sqlite3.connect(_db_path)


# ============================================================
# Query Helpers
# ============================================================

def dict_from_row(row):
    """Convert a sqlite3.Row to a regular dict, parsing JSON fields."""
    if row is None:
        return None
    d = dict(row)
    json_fields = [
        "role_variants", "core_skills", "secondary_skills",
        "tools", "domain_keywords", "skills_found", "also_on"
    ]
    for field in json_fields:
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
    return d


def execute_query(sql, params=(), fetch_one=False, fetch_all=False):
    """Execute a query and optionally fetch results."""
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        if fetch_one:
            row = cursor.fetchone()
            return dict_from_row(row) if row else None
        elif fetch_all:
            return [dict_from_row(row) for row in cursor.fetchall()]
        else:
            conn.commit()
            return cursor.lastrowid


def execute_many(sql, params_list):
    """Execute a query with multiple parameter sets."""
    with get_connection() as conn:
        conn.executemany(sql, params_list)
        conn.commit()


# ============================================================
# Quota Tracking Helpers
# ============================================================

def get_quota_usage(source, date=None):
    """Get today's API usage for a source."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    result = execute_query(
        "SELECT calls_used FROM quota_usage WHERE source = ? AND date = ?",
        (source, date),
        fetch_one=True
    )
    return result["calls_used"] if result else 0


def increment_quota(source, date=None):
    """Increment API usage count for a source."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO quota_usage (source, date, calls_used)
            VALUES (?, ?, 1)
            ON CONFLICT(source, date)
            DO UPDATE SET calls_used = calls_used + 1
        """, (source, date))
        conn.commit()
