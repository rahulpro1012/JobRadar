"""
JobRadar Base Scraper Class (Tier 3b)
Abstract base class for all direct career page scrapers.
Handles: caching, source health tracking, profile filtering, user-agent rotation.

Subclasses implement:
  - get_listing_url() → careers page URL
  - parse_jobs(html) → list of job dicts
"""

import re
import time
import logging
import requests
import json
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from app.services.search_cache import cache_get, cache_set
from app.services.source_health import is_healthy, record_success, record_failure
from app.services.ats_fetcher import ProfileFilter

logger = logging.getLogger(__name__)

# User-Agent rotation to avoid blocking
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
]

CACHE_TTL_HOURS = 6


class BaseScraper:
    """
    Abstract base scraper for direct career page scraping.

    Subclasses must implement:
      - company_name (str): Human-readable company name
      - source_domain (str): Domain for source tracking (e.g., "razorpay.com")
      - get_listing_url() → str: Returns the careers page URL
      - parse_jobs(html: str) → List[Dict]: Parses HTML and returns job list
    """

    company_name: str = "Unknown"
    source_domain: str = "unknown.com"

    def __init__(self, profile: dict):
        """Initialize scraper with user profile."""
        self.profile = profile
        self.pf = ProfileFilter(profile)
        self.session = requests.Session()
        self._setup_headers()

    def _setup_headers(self):
        """Setup headers with random user agent."""
        import random
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

    def fetch_and_parse(self) -> List[Dict]:
        """
        Main entry point: fetch careers page, parse jobs, filter by profile.
        Returns list of normalized job dicts ready for DB insertion.
        """
        # Check circuit breaker
        source_name = self._get_source_name()
        if not is_healthy(source_name):
            logger.info(f"[{source_name}] circuit open — skipping")
            return []

        try:
            # Check cache first
            cached = cache_get(source_name, self.company_name, ttl_hours=CACHE_TTL_HOURS)
            if cached:
                logger.debug(f"[{source_name}] Cache hit")
                jobs = json.loads(cached) if isinstance(cached, str) else cached
                record_success(source_name, jobs_returned=len(jobs))
                return jobs

            # Fetch careers page
            url = self.get_listing_url()
            logger.debug(f"[{source_name}] Fetching {url}")

            resp = self.session.get(url, timeout=20, verify=False)
            resp.raise_for_status()

            # Parse jobs from HTML
            jobs = self.parse_jobs(resp.text)
            logger.debug(f"[{source_name}] Parsed {len(jobs)} raw jobs")

            # Filter by profile
            filtered_jobs = []
            filtered_count = 0

            for job in jobs:
                title = job.get("title", "")
                description = job.get("description_snippet", "")

                keep, reason = self.pf.should_keep(title, description)
                if not keep:
                    filtered_count += 1
                    continue

                filtered_jobs.append(job)

            logger.debug(f"[{source_name}] Filtered: {filtered_count} rejected, {len(filtered_jobs)} kept")

            # Cache results
            cache_set(
                source_name,
                self.company_name,
                json.dumps(filtered_jobs),
                ttl_hours=CACHE_TTL_HOURS,
            )

            # Record success
            record_success(source_name, jobs_returned=len(filtered_jobs))

            return filtered_jobs

        except requests.Timeout:
            record_failure(source_name, "Timeout")
            logger.warning(f"[{source_name}] Timeout")
            return []
        except requests.HTTPError as e:
            record_failure(source_name, f"HTTP {e.response.status_code}")
            logger.warning(f"[{source_name}] HTTP {e.response.status_code}")
            return []
        except Exception as e:
            record_failure(source_name, str(e))
            logger.warning(f"[{source_name}] Error: {str(e)}")
            return []

    def get_listing_url(self) -> str:
        """Return the careers/jobs listing page URL. Override in subclass."""
        raise NotImplementedError()

    def parse_jobs(self, html: str) -> List[Dict]:
        """
        Parse HTML and return list of job dicts with keys:
          - title (str): Job title
          - location (str): Job location (default to company HQ)
          - description_snippet (str): Job description excerpt
          - source_url (str): Link to job posting

        Override in subclass with company-specific parsing logic.
        """
        raise NotImplementedError()

    def _get_source_name(self) -> str:
        """Get source name for logging/tracking (lowercase, no spaces)."""
        return self.company_name.lower().replace(" ", "_")

    def _normalize_job(self, title: str, location: str = "", url: str = "", description: str = "") -> Dict:
        """Create normalized job dict for DB insertion."""
        return {
            "title": title[:150],
            "company": self.company_name,
            "location": location[:100],
            "source_url": url,
            "source_domain": self.source_domain,
            "description_snippet": description[:300],
            "posted_date": "",
            "skills_found": json.dumps([]),
        }
