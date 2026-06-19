"""
JobRadar Configuration
Environment-based config for development and production.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Local SQLite database
    SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", str(BASE_DIR / "jobradar.db"))

    # API Keys (free tiers)
    GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
    GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")
    BING_API_KEY = os.environ.get("BING_API_KEY", "")
    JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY", "")
    SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

    # Phase 1 additions
    # Adzuna India API (free, ~250-1000 calls/month — sign up at developer.adzuna.com)
    ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

    # Phase 2 additions
    # Self-hosted SearxNG URL (deploy searxng-jobradar repo to Render free tier)
    # When set, this is used as the primary SearxNG instance (replaces flaky public ones)
    SEARXNG_URL = os.environ.get("SEARXNG_URL", "")

    # Feature 1: Gmail job-alert scanner (IMAP app password — never stored in DB)
    GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
    GMAIL_LABEL = os.environ.get("GMAIL_LABEL", "")  # optional; empty = search all mail
    # CORS
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

    # Upload settings (override UPLOAD_FOLDER to point at a persistent volume in prod)
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB max resume size
    ALLOWED_EXTENSIONS = {"pdf", "docx"}
    
    # Scraping settings
    SCRAPE_DELAY = float(os.environ.get("SCRAPE_DELAY", "1.0"))  # seconds between requests
    MAX_JOBS_PER_REFRESH = int(os.environ.get("MAX_JOBS_PER_REFRESH", "100"))
    
    # Scoring thresholds
    SCORE_EXCELLENT = 80
    SCORE_GOOD = 60
    SCORE_PARTIAL = 40
    
    # Job expiry
    JOB_ARCHIVE_DAYS = 30


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    FLASK_ENV = "development"


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    FLASK_ENV = "production"


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLITE_DB_PATH = ":memory:"


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    """Get configuration based on FLASK_ENV environment variable."""
    env = os.environ.get("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)


def log_config_status():
    """Log which integrations are configured. Non-fatal — a missing key just
    disables that source, so this is a heads-up, not a gate. Helps a fresh
    deploy see at a glance what's on."""
    import logging
    log = logging.getLogger("jobradar.config")
    c = Config
    status = {
        "Groq AI": bool(c.GROQ_API_KEY),
        "Jooble": bool(c.JOOBLE_API_KEY),
        "Adzuna": bool(c.ADZUNA_APP_ID and c.ADZUNA_APP_KEY),
        "SerpApi": bool(c.SERPAPI_API_KEY),
        "SearxNG": bool(c.SEARXNG_URL),
        "Gmail scan": bool(c.GMAIL_ADDRESS and c.GMAIL_APP_PASSWORD),
    }
    on = [k for k, v in status.items() if v]
    off = [k for k, v in status.items() if not v]
    log.info("Integrations enabled: %s", ", ".join(on) or "(none)")
    if off:
        log.info("Integrations disabled (no key): %s", ", ".join(off))
    if not c.GROQ_API_KEY:
        log.warning(
            "GROQ_API_KEY is not set — resume parsing, scoring, and AI reasoning "
            "will be disabled. Get a free key at https://console.groq.com/keys"
        )
