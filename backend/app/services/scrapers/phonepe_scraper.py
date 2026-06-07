"""
JobRadar PhonePe Direct Scraper (Tier 3b)
Scrapes jobs directly from https://phonepe.com/careers

PhonePe careers page structure:
- Job cards: .job-card, [data-job], .job-item, .opening
- Job title: .job-title, h3, h4
- Location: .location, .job-location
- Experience: .experience, .job-level, span
- Description: .job-description, p
"""

import logging
from typing import List, Dict
from bs4 import BeautifulSoup
from app.services.scrapers._base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class PhonePeScraper(BaseScraper):
    """PhonePe careers page scraper."""

    company_name = "PhonePe"
    source_domain = "phonepe.com"

    def get_listing_url(self) -> str:
        """PhonePe careers page URL."""
        return "https://phonepe.com/careers/"

    def parse_jobs(self, html: str) -> List[Dict]:
        """
        Parse PhonePe careers page HTML.

        PhonePe is a large fintech, may have 30-50+ openings across multiple locations.
        Locations: Bangalore, Mumbai, Pune, etc.
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Try multiple selector strategies
        job_containers = (
            soup.find_all(class_="job-card") or
            soup.find_all(attrs={"data-job": True}) or
            soup.find_all(class_="job-item") or
            soup.find_all(class_="opening") or
            soup.find_all(class_=lambda x: x and "job" in x.lower())
        )

        if not job_containers:
            logger.warning("[phonepe] Could not find job containers, trying fallback")
            # Fallback: look for divs that might contain job info
            all_divs = soup.find_all("div", limit=200)
            for div in all_divs:
                text = div.get_text().lower()
                if any(k in text for k in ["engineer", "developer", "designer", "position", "hiring", "opening"]):
                    if div not in job_containers:
                        job_containers.append(div)

        for container in job_containers[:60]:  # Limit to prevent noise
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

                # Extract location
                location_elem = container.find(class_="location") or container.find(class_="job-location")
                if location_elem:
                    location = location_elem.get_text(strip=True)
                else:
                    location = "India"  # PhonePe operates across India

                # Extract experience/level if available
                exp_elem = container.find(class_="experience") or container.find(class_="job-level")
                experience = exp_elem.get_text(strip=True) if exp_elem else ""

                # Extract description
                desc_elem = container.find(class_="job-description") or container.find("p")
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                # Append experience to description if available
                if experience:
                    description = f"{experience}. {description}"

                # Extract URL
                job_url = ""
                link = container.find("a", href=True)
                if link:
                    href = link.get("href", "")
                    if href.startswith("/"):
                        job_url = f"https://phonepe.com{href}"
                    elif href.startswith("http"):
                        job_url = href
                    else:
                        job_url = f"https://phonepe.com/careers/{href}"

                if not job_url:
                    job_url = self.get_listing_url()

                jobs.append(self._normalize_job(
                    title=title,
                    location=location,
                    url=job_url,
                    description=description,
                ))

            except Exception as e:
                logger.debug(f"[phonepe] Failed to parse job card: {e}")
                continue

        logger.info(f"[phonepe] Parsed {len(jobs)} jobs")
        return jobs


def fetch_phonepe(profile: dict) -> List[Dict]:
    """Fetch PhonePe jobs. Compatible with job_fetcher.py layer interface."""
    scraper = PhonePeScraper(profile)
    jobs = scraper.fetch_and_parse()
    logger.info(f"[phonepe] {len(jobs)} jobs kept")
    return jobs
