"""
JobRadar Swiggy Direct Scraper (Tier 3b)
Scrapes jobs directly from https://careers.swiggy.com/

Swiggy careers page structure (example selectors):
- Job cards: .job-card, [data-job-id], .job-item
- Job title: .job-title, h2, h3
- Location: .location, .job-location
- Department: .department, .job-category
- Description: .job-description, p
"""

import logging
from typing import List, Dict
from bs4 import BeautifulSoup
from app.services.scrapers._base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class SwiggyScraper(BaseScraper):
    """Swiggy careers page scraper."""

    company_name = "Swiggy"
    source_domain = "swiggy.com"

    def get_listing_url(self) -> str:
        """Swiggy careers page URL."""
        return "https://careers.swiggy.com/"

    def parse_jobs(self, html: str) -> List[Dict]:
        """
        Parse Swiggy careers page HTML.

        Swiggy's careers page may use JavaScript rendering, but we'll try to parse
        server-side rendered content or fallback to finding job-like elements.
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Try multiple selector strategies
        job_containers = (
            soup.find_all(class_="job-card") or
            soup.find_all(attrs={"data-job-id": True}) or
            soup.find_all(class_="job-item") or
            soup.find_all(class_=lambda x: x and "job" in x.lower()) or
            soup.find_all("div", class_=lambda x: x and any(k in (x or "").lower() for k in ["opening", "posting", "vacancy"]))
        )

        if not job_containers:
            logger.warning("[swiggy] Could not find job containers with standard selectors")
            # Fallback: look for divs with job-like text patterns
            for div in soup.find_all("div", limit=100):
                text = div.get_text().lower()
                if any(k in text for k in ["engineer", "developer", "designer", "position", "role"]):
                    job_containers.append(div)

        for container in job_containers[:50]:  # Limit to first 50 to avoid noise
            try:
                # Extract title
                title_elem = (
                    container.find(class_="job-title") or
                    container.find("h2") or
                    container.find("h3") or
                    container.find("h4")
                )
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title or len(title) < 5:
                    continue

                # Extract location (Swiggy is multi-city: Bangalore, Pune, Mumbai, Gurgaon, Hyderabad)
                location_elem = container.find(class_="location") or container.find(class_="job-location")
                if location_elem:
                    location = location_elem.get_text(strip=True)
                else:
                    location = "India"  # Swiggy operates across India

                # Extract department/category
                dept_elem = container.find(class_="department") or container.find(class_="job-category")
                department = dept_elem.get_text(strip=True) if dept_elem else ""

                # Extract description
                desc_elem = container.find(class_="job-description") or container.find("p")
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                # Combine department into description for better filtering
                if department:
                    description = f"{department}. {description}"

                # Extract URL
                job_url = ""
                link = container.find("a", href=True)
                if link:
                    href = link.get("href", "")
                    if href.startswith("/"):
                        job_url = f"https://careers.swiggy.com{href}"
                    elif href.startswith("http"):
                        job_url = href
                    else:
                        job_url = f"https://careers.swiggy.com/{href}"

                if not job_url:
                    job_url = self.get_listing_url()

                jobs.append(self._normalize_job(
                    title=title,
                    location=location,
                    url=job_url,
                    description=description,
                ))

            except Exception as e:
                logger.debug(f"[swiggy] Failed to parse job card: {e}")
                continue

        logger.info(f"[swiggy] Parsed {len(jobs)} jobs")
        return jobs


def fetch_swiggy(profile: dict) -> List[Dict]:
    """Fetch Swiggy jobs. Compatible with job_fetcher.py layer interface."""
    scraper = SwiggyScraper(profile)
    jobs = scraper.fetch_and_parse()
    logger.info(f"[swiggy] {len(jobs)} jobs kept")
    return jobs
