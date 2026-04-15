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
    
    # Database - supports both local SQLite and Turso
    # For local dev: sqlite:///jobradar.db
    # For production (Turso): set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN
    TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL", "")
    TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")
    SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", str(BASE_DIR / "jobradar.db"))
    
    # Use Turso if URL is provided, otherwise fall back to local SQLite
    USE_TURSO = bool(TURSO_DATABASE_URL)
    
    # API Keys (free tiers)
    GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
    GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")
    BING_API_KEY = os.environ.get("BING_API_KEY", "")
    
    # CORS
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    
    # Upload settings
    UPLOAD_FOLDER = str(BASE_DIR / "uploads")
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
    USE_TURSO = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    """Get configuration based on FLASK_ENV environment variable."""
    env = os.environ.get("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)
