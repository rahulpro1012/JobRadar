"""
JobRadar Zomato Direct Scraper (Tier 3b)
Scrapes jobs directly from https://zomato.com/careers

Zomato careers page structure:
- Job cards: .job-card, [data-job-id], .job-opening, .role
- Job title: .job-title, h3, h4, a.job-link
- Location: .location, .job-location, span
- Department: .department, .team, .category
- Description: .job-description, .snippet, p
"""

import logging
from typing import List, Dict
from bs4 import BeautifulSoup
from app.services.scrapers._base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ZomatoScraper(BaseScraper):
    """Zomato careers page scraper."""

    company_name = "Zomato"
    source_domain = "zomato.com"

    def get_listing_url(self) -> str:
        """Zomato careers page URL."""
        return "https://www.zomato.com/careers/"

    def parse_jobs(self, html: str) -> List[Dict]:
        """
        Parse Zomato careers page HTML.

        Zomato is a large company with 25-40+ openings across:
        - Engineering (Backend, Frontend, Mobile)
        - Product, Design, Data
        - Multiple locations (Bangalore, Mumbai, Delhi, etc.)
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Try multiple selector strategies
        job_containers = (
            soup.find_all(class_="job-card") or
            soup.find_all(attrs={"data-job-id": True}) or
            soup.find_all(class_="job-opening") or
            soup.find_all(class_="role") or
            soup.find_all(class_=lambda x: x and "job" in x.lower())
        )

        if not job_containers:
            logger.warning("[zomato] Could not find job containers with standard selectors")
            # Fallback: look for article or section elements
            job_containers = soup.find_all("article") or soup.find_all("li", class_=lambda x: x and "job" in (x or "").lower())

        for container in job_containers[:70]:  # Limit to prevent noise
            try:
                # Extract title
                title_elem = (
                    container.find(class_="job-title") or
                    container.find("h3") or
                    container.find("h4") or
                    container.find("a", class_="job-link")
                )
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title or len(title) < 5:
                    continue

                # Extract location (Zomato multi-city: Bangalore, Mumbai, Delhi, Pune, etc.)
                location_elem = container.find(class_="location") or container.find(class_="job-location")
                if location_elem:
                    location = location_elem.get_text(strip=True)
                else:
                    location = "India"  # Default to India

                # Extract department/team
                dept_elem = container.find(class_="department") or container.find(class_="team") or container.find(class_="category")
                department = dept_elem.get_text(strip=True) if dept_elem else ""

                # Extract description/snippet
                desc_elem = container.find(class_="job-description") or container.find(class_="snippet") or container.find("p")
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                # Combine department into description
                if department:
                    description = f"{department}. {description}"

                # Extract URL
                job_url = ""
                link = container.find("a", href=True)
                if link:
                    href = link.get("href", "")
                    if href.startswith("/"):
                        job_url = f"https://www.zomato.com{href}"
                    elif href.startswith("http"):
                        job_url = href
                    else:
                        job_url = f"https://www.zomato.com/careers/{href}"

                if not job_url:
                    job_url = self.get_listing_url()

                jobs.append(self._normalize_job(
                    title=title,
                    location=location,
                    url=job_url,
                    description=description,
                ))

            except Exception as e:
                logger.debug(f"[zomato] Failed to parse job card: {e}")
                continue

        logger.info(f"[zomato] Parsed {len(jobs)} jobs")
        return jobs


def fetch_zomato(profile: dict) -> List[Dict]:
    """Fetch Zomato jobs. Compatible with job_fetcher.py layer interface."""
    scraper = ZomatoScraper(profile)
    jobs = scraper.fetch_and_parse()
    logger.info(f"[zomato] {len(jobs)} jobs kept")
    return jobs
