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
_turso_initial_sync = False  # one-time pull from the Turso primary per process


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
    schema_version INTEGER DEFAULT 1,
    skills_tiered TEXT DEFAULT '',
    deal_breakers TEXT DEFAULT '[]',
    preferences_explicit TEXT DEFAULT '{}',
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
    also_on TEXT DEFAULT '[]',
    ai_score INTEGER DEFAULT NULL,
    ai_reason TEXT DEFAULT '',
    dismissed_at TIMESTAMP DEFAULT NULL,
    via_email INTEGER DEFAULT 0
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

-- Search result cache (prevents redundant API calls within TTL window)
CREATE TABLE IF NOT EXISTS search_cache (
    cache_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    query TEXT NOT NULL,
    location TEXT DEFAULT '',
    results_json TEXT NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

-- Per-source health tracking and circuit-breaker state
CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'healthy',
    consecutive_failures INTEGER DEFAULT 0,
    last_success_at TIMESTAMP,
    last_failure_at TIMESTAMP,
    last_failure_reason TEXT,
    total_calls INTEGER DEFAULT 0,
    total_failures INTEGER DEFAULT 0,
    jobs_returned_last_run INTEGER DEFAULT 0,
    disabled_until TIMESTAMP
);

-- Append-only audit log for source health events
CREATE TABLE IF NOT EXISTS source_health_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT,
    jobs_returned INTEGER,
    timestamp TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);

-- Auto-discovered ATS company registry (populated by company_discovery.py)
CREATE TABLE IF NOT EXISTS company_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    ats TEXT NOT NULL,  -- "greenhouse", "lever", "ashby", "workable", "smartrecruiters"
    discovered_at TIMESTAMP,
    job_count INTEGER DEFAULT 0,
    last_checked TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Phase 2: Background refresh job tracking (async refresh + polling)
CREATE TABLE IF NOT EXISTS refresh_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_sec INTEGER,

    sources_total INTEGER DEFAULT 0,
    sources_done INTEGER DEFAULT 0,
    sources_failed INTEGER DEFAULT 0,

    jobs_fetched INTEGER DEFAULT 0,
    jobs_new INTEGER DEFAULT 0,
    jobs_ai_scored INTEGER DEFAULT 0,

    per_source_json TEXT,
    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- A2: Query yield tracking (which queries return jobs per source)
CREATE TABLE IF NOT EXISTS query_yield_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    source TEXT NOT NULL,
    location TEXT NOT NULL,
    jobs_returned INTEGER NOT NULL DEFAULT 0,
    refreshed_at TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    UNIQUE(query, source, location, refreshed_at)
);

-- Generic key-value app settings (retention_days, email scan_days, etc.)
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Feature 1: editable sender allowlist for the Gmail job-alert scanner
CREATE TABLE IF NOT EXISTS email_senders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    value TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Feature 1: processed email message-ids (avoid re-importing the same alert)
CREATE TABLE IF NOT EXISTS email_seen (
    message_id TEXT PRIMARY KEY,
    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- C1: Job AI analysis with structured reasoning (apply/skip reasons, red flags)
CREATE TABLE IF NOT EXISTS job_ai_analysis (
    job_id INTEGER PRIMARY KEY,
    ai_score INTEGER NOT NULL,
    apply_reasons TEXT DEFAULT '[]',
    skip_reasons TEXT DEFAULT '[]',
    fit_summary TEXT DEFAULT '',
    red_flags TEXT DEFAULT '[]',
    analyzed_at TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    model_used TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched_date ON jobs(fetched_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_source_domain ON jobs(source_domain);
CREATE INDEX IF NOT EXISTS idx_blacklist_type ON blacklist(type);
CREATE INDEX IF NOT EXISTS idx_quota_date ON quota_usage(date);
CREATE INDEX IF NOT EXISTS idx_search_cache_expires ON search_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_search_cache_source ON search_cache(source);
CREATE INDEX IF NOT EXISTS idx_health_log_source_time ON source_health_log(source, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_refresh_jobs_started ON refresh_jobs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_registry_ats ON company_registry(ats);
CREATE INDEX IF NOT EXISTS idx_company_registry_discovered ON company_registry(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_yield_query_source ON query_yield_history(query, source);
CREATE INDEX IF NOT EXISTS idx_yield_refreshed ON query_yield_history(refreshed_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_analyzed ON job_ai_analysis(analyzed_at DESC);
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
        _ensure_columns(conn)
        _seed_default_companies(conn)
        _seed_email_senders(conn)
        conn.commit()


DEFAULT_EMAIL_SENDERS = [
    "linkedin.com", "naukri.com", "indeed.com", "glassdoor.com",
    "instahyre.com", "hirist.com", "cutshort.io",
]


def _seed_email_senders(conn):
    """Seed the job-alert sender allowlist if empty (Feature 1)."""
    count = conn.execute("SELECT COUNT(*) FROM email_senders").fetchone()[0]
    if count == 0:
        for value in DEFAULT_EMAIL_SENDERS:
            conn.execute(
                "INSERT OR IGNORE INTO email_senders (value) VALUES (?)", (value,)
            )


def _ensure_columns(conn):
    """Idempotently add columns missing from pre-existing databases.

    CREATE TABLE IF NOT EXISTS won't alter an existing table, so columns
    added after a DB was first created must be backfilled here.
    """
    # jobs.dismissed_at (Dismiss feature) + jobs.via_email (Email scanner)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
    if "dismissed_at" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN dismissed_at TIMESTAMP DEFAULT NULL")
    if "via_email" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN via_email INTEGER DEFAULT 0")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_dismissed_at ON jobs(dismissed_at)"
    )


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


# ============================================================
# Turso / libsql compatibility shim
# ============================================================
# libsql (Turso's driver) is DBAPI-ish but lacks two things the codebase uses:
# sqlite3.Row (row_factory) and executescript(). These thin wrappers let every
# call site keep sqlite3.Row semantics — dict(row) AND row[0] — and
# conn.executescript() unchanged, whether the backend is SQLite or Turso.

class _Row(dict):
    """A dict that also supports positional indexing, like sqlite3.Row."""
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return dict.__getitem__(self, key)


class _LibsqlCursor:
    """Wraps a libsql cursor so fetches return _Row objects."""
    def __init__(self, cursor):
        self._cur = cursor

    def _columns(self):
        desc = self._cur.description
        return [d[0] for d in desc] if desc else []

    def fetchone(self):
        row = self._cur.fetchone()
        return _Row(self._columns(), row) if row is not None else None

    def fetchall(self):
        # libsql populates description only after a fetchone() (not after fetchall),
        # so drive iteration with fetchone(). Rows are buffered, so this stays local.
        first = self._cur.fetchone()
        if first is None:
            return []
        cols = self._columns()
        rows = [first]
        while True:
            r = self._cur.fetchone()
            if r is None:
                break
            rows.append(r)
        return [_Row(cols, r) for r in rows]

    def fetchmany(self, size=None):
        rows = self._cur.fetchmany(size) if size is not None else self._cur.fetchmany()
        cols = self._columns()
        return [_Row(cols, r) for r in rows]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description


def _split_sql_statements(script):
    """Split a multi-statement SQL script into individual statements.
    Safe for our schema (plain CREATE TABLE/INDEX; no triggers/embedded ';')."""
    statements = []
    for raw in script.split(";"):
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


class _LibsqlConn:
    """Wraps a libsql connection to mimic the sqlite3 API the app relies on:
    cursors that yield _Row, and executescript()."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        # libsql requires a tuple for parameters; callers (and sqlite3) also pass lists
        return _LibsqlCursor(self._conn.execute(sql, tuple(params)))

    def executemany(self, sql, seq_of_params):
        self._conn.executemany(sql, [tuple(p) for p in seq_of_params])

    def executescript(self, script):
        for stmt in _split_sql_statements(script):
            self._conn.execute(stmt)

    def cursor(self):
        return _LibsqlCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()
        # Embedded replica: push committed local writes to the remote Turso primary
        try:
            self._conn.sync()
        except Exception:
            pass

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


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
    
    # sqlite3.Row + PRAGMAs apply to the stdlib driver only. libsql has no
    # row_factory and remote PRAGMAs are no-ops/errors, so guard them.
    if isinstance(conn, sqlite3.Connection):
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
    global _turso_initial_sync
    try:
        import libsql_experimental as libsql
    except ImportError:
        print("WARNING: libsql_experimental not installed, falling back to local SQLite")
        return sqlite3.connect(_db_path)
    # Embedded-replica mode: a local SQLite file kept in sync with the Turso
    # primary. Remote-only mode is unreliable here (Hrana "stream not found" on
    # multi-statement writes -> writes silently lost). Embedded replica gives
    # correct local read-after-write; sync() pushes writes durably to Turso.
    conn = libsql.connect(_db_path, sync_url=_turso_url, auth_token=_turso_token)
    if not _turso_initial_sync:
        try:
            conn.sync()  # pull existing remote data into the fresh replica (once per boot)
        except Exception as e:
            print(f"WARNING: initial Turso sync failed: {e}")
        _turso_initial_sync = True
    return _LibsqlConn(conn)


# ============================================================
# Query Helpers
# ============================================================

def dict_from_row(row):
    """Convert a sqlite3.Row to a regular dict, parsing JSON fields."""
    if row is None:
        return None
    d = dict(row)
    # Fields stored as JSON arrays (default to [] on parse failure)
    json_array_fields = [
        "role_variants", "core_skills", "secondary_skills",
        "tools", "domain_keywords", "skills_found", "also_on",
        # C1 structured analysis (arrive via LEFT JOIN job_ai_analysis)
        "apply_reasons", "skip_reasons", "red_flags",
        # A1 tiered profile
        "deal_breakers",
    ]
    for field in json_array_fields:
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
    # Fields stored as JSON objects (default to {} on parse failure)
    json_object_fields = ["skills_tiered", "preferences_explicit"]
    for field in json_object_fields:
        if field in d and isinstance(d[field], str):
            if not d[field].strip():
                d[field] = {}
                continue
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = {}
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
# App Settings (generic key-value)
# ============================================================

def get_setting(key, default=None):
    """Get an app_settings value (string), or default if unset."""
    row = execute_query(
        "SELECT value FROM app_settings WHERE key = ?", (key,), fetch_one=True
    )
    return row["value"] if row else default


def set_setting(key, value):
    """Upsert an app_settings value."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, str(value)),
        )
        conn.commit()


# ============================================================
# Feature 1: email sender allowlist + seen-message tracking
# ============================================================

def list_email_senders(enabled_only=False):
    """Return sender allowlist rows. If enabled_only, only enabled ones."""
    sql = "SELECT id, value, enabled, added_at FROM email_senders"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY value"
    return execute_query(sql, fetch_all=True)


def add_email_sender(value):
    """Add a sender domain/address to the allowlist (idempotent)."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO email_senders (value) VALUES (?)",
            (value.strip().lower(),),
        )
        conn.commit()


def remove_email_sender(sender_id):
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM email_senders WHERE id = ?", (sender_id,))
        conn.commit()
        return cur.rowcount


def toggle_email_sender(sender_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT enabled FROM email_senders WHERE id = ?", (sender_id,)
        ).fetchone()
        if not row:
            return None
        new_val = 0 if row["enabled"] else 1
        conn.execute(
            "UPDATE email_senders SET enabled = ? WHERE id = ?", (new_val, sender_id)
        )
        conn.commit()
        return bool(new_val)


def is_email_seen(message_id):
    if not message_id:
        return False
    row = execute_query(
        "SELECT 1 FROM email_seen WHERE message_id = ?", (message_id,), fetch_one=True
    )
    return row is not None


def mark_email_seen(message_id):
    if not message_id:
        return
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO email_seen (message_id) VALUES (?)", (message_id,)
        )
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


# ============================================================
# Phase 2: Refresh Job Tracking (Async Background Jobs)
# ============================================================

def create_refresh_job(job_id, sources_total=0):
    """Create a new refresh job record with 'pending' status.

    sources_total defaults to 0 so the loader shows its indeterminate state
    until fetch_all_jobs sets the real layer count (avoids a 16->10 flash).
    """
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO refresh_jobs (id, status, started_at, sources_total)
            VALUES (?, 'pending', ?, ?)
        """, (job_id, datetime.utcnow().isoformat(), sources_total))
        conn.commit()


def get_refresh_job(job_id):
    """Fetch a refresh job record."""
    return execute_query(
        "SELECT * FROM refresh_jobs WHERE id = ?",
        (job_id,),
        fetch_one=True
    )


def update_refresh_job(job_id, **updates):
    """Update refresh job fields (status, jobs_fetched, per_source_json, etc.)."""
    allowed_fields = {
        'status', 'sources_total', 'sources_done', 'sources_failed', 'jobs_fetched',
        'jobs_new', 'jobs_ai_scored', 'per_source_json', 'error_message',
        'completed_at', 'duration_sec'
    }
    updates = {k: v for k, v in updates.items() if k in allowed_fields}
    if not updates:
        return

    with get_connection() as conn:
        cols = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [job_id]
        conn.execute(f"UPDATE refresh_jobs SET {cols} WHERE id = ?", values)
        conn.commit()


def get_latest_refresh_job():
    """Get the most recent refresh job."""
    return execute_query(
        "SELECT * FROM refresh_jobs ORDER BY started_at DESC LIMIT 1",
        fetch_one=True
    )


def reset_circuit_breaker(source: str):
    """
    Reset circuit breaker for a source (after fixing a previously-broken fetcher).

    Used by: Item 1 (Naukri header fix) to retry with new headers.

    Args:
        source: Source name (e.g., "naukri", "linkedin_guest")
    """
    try:
        with get_connection() as conn:
            conn.execute("""
                UPDATE source_health
                SET disabled_until = NULL,
                    consecutive_failures = 0,
                    status = 'healthy'
                WHERE source = ?
            """, (source,))
            conn.commit()
            return True
    except Exception as e:
        print(f"Failed to reset {source} circuit: {e}")
        return False
