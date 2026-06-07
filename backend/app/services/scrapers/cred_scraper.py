"""
JobRadar CRED Direct Scraper (Tier 3b)
Scrapes jobs directly from https://cred.club/careers

CRED careers page structure:
- Job cards: .job-card, [data-role], .opening
- Job title: .job-title, h3, h4
- Location: .location, .job-location (usually Bangalore)
- Description: .job-description, p
"""

import logging
from typing import List, Dict
from bs4 import BeautifulSoup
from app.services.scrapers._base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class CredScraper(BaseScraper):
    """CRED careers page scraper."""

    company_name = "CRED"
    source_domain = "cred.club"

    def get_listing_url(self) -> str:
        """CRED careers page URL."""
        return "https://cred.club/careers/"

    def parse_jobs(self, html: str) -> List[Dict]:
        """
        Parse CRED careers page HTML.

        CRED is a smaller company, so fewer jobs expected (~10-20 per refresh).
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Try multiple selector strategies
        job_containers = (
            soup.find_all(class_="job-card") or
            soup.find_all(attrs={"data-role": True}) or
            soup.find_all(class_="opening") or
            soup.find_all(class_=lambda x: x and "job" in x.lower())
        )

        if not job_containers:
            logger.warning("[cred] Could not find job containers, trying fallback")
            # Fallback: look for sections with job-like content
            job_containers = soup.find_all("section") or soup.find_all("div", class_="role")

        for container in job_containers:
            try:
                # Extract title
                title_elem = (
                    container.find(class_="job-title") or
                    container.find("h3") or
                    container.find("h4") or
                    container.find("h2")
                )
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title or len(title) < 5:
                    continue

                # Extract location (CRED is primarily Bangalore-based)
                location_elem = container.find(class_="location") or container.find(class_="job-location")
                location = location_elem.get_text(strip=True) if location_elem else "Bangalore, India"

                # Extract description
                desc_elem = container.find(class_="job-description") or container.find("p")
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                # Extract URL
                job_url = ""
                link = container.find("a", href=True)
                if link:
                    href = link.get("href", "")
                    if href.startswith("/"):
                        job_url = f"https://cred.club{href}"
                    elif href.startswith("http"):
                        job_url = href
                    else:
                        job_url = f"https://cred.club/careers/{href}"

                if not job_url:
                    job_url = self.get_listing_url()

                jobs.append(self._normalize_job(
                    title=title,
                    location=location,
                    url=job_url,
                    description=description,
                ))

            except Exception as e:
                logger.debug(f"[cred] Failed to parse job card: {e}")
                continue

        logger.info(f"[cred] Parsed {len(jobs)} jobs")
        return jobs


def fetch_cred(profile: dict) -> List[Dict]:
    """Fetch CRED jobs. Compatible with job_fetcher.py layer interface."""
    scraper = CredScraper(profile)
    jobs = scraper.fetch_and_parse()
    logger.info(f"[cred] {len(jobs)} jobs kept")
    return jobs
