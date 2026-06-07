"""
JobRadar Razorpay Direct Scraper (Tier 3b)
Scrapes jobs directly from https://razorpay.com/jobs/jobs-all/

Razorpay careers page structure (example selectors):
- Job cards: .job-card, [data-job-id], .job-listing
- Job title: .job-title, h3, a.job-link
- Location: .location, .job-location, span.location
- Description: .job-description, .job-snippet, p.description
"""

import logging
from typing import List, Dict
from bs4 import BeautifulSoup
from app.services.scrapers._base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class RazorpayScraper(BaseScraper):
    """Razorpay careers page scraper."""

    company_name = "Razorpay"
    source_domain = "razorpay.com"

    def get_listing_url(self) -> str:
        """Razorpay careers page URL."""
        return "https://razorpay.com/jobs/jobs-all/"

    def parse_jobs(self, html: str) -> List[Dict]:
        """
        Parse Razorpay careers page HTML.

        Note: Razorpay's careers page structure may vary. This parser tries multiple selectors.
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs = []

        # Try to find job containers (multiple selector strategies)
        job_containers = (
            soup.find_all(class_="job-card") or
            soup.find_all(attrs={"data-job-id": True}) or
            soup.find_all(class_="job-listing") or
            soup.find_all("div", class_=lambda x: x and "job" in x.lower())
        )

        if not job_containers:
            logger.warning("[razorpay] Could not find job containers, trying alternative selectors")
            # Fallback: look for links that look like job postings
            job_containers = soup.find_all("a", class_=lambda x: x and any(k in (x or "").lower() for k in ["job", "opening", "posting"]))

        for container in job_containers:
            try:
                # Extract title
                title_elem = (
                    container.find(class_="job-title") or
                    container.find("h3") or
                    container.find("h4") or
                    container.find("a")
                )
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title:
                    continue

                # Extract location
                location_elem = container.find(class_="job-location") or container.find(class_="location")
                location = location_elem.get_text(strip=True) if location_elem else "Bengaluru, India"

                # Extract description/snippet
                desc_elem = container.find(class_="job-description") or container.find(class_="job-snippet") or container.find("p")
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                # Extract job URL
                job_url = ""
                link = container.find("a", href=True)
                if link:
                    href = link.get("href", "")
                    # Convert relative URLs to absolute
                    if href.startswith("/"):
                        job_url = f"https://razorpay.com{href}"
                    elif href.startswith("http"):
                        job_url = href
                    else:
                        job_url = f"https://razorpay.com/jobs/{href}"

                if not job_url:
                    job_url = self.get_listing_url()  # Fallback to careers page

                jobs.append(self._normalize_job(
                    title=title,
                    location=location,
                    url=job_url,
                    description=description,
                ))

            except Exception as e:
                logger.debug(f"[razorpay] Failed to parse job card: {e}")
                continue

        logger.info(f"[razorpay] Parsed {len(jobs)} jobs")
        return jobs


def fetch_razorpay(profile: dict) -> List[Dict]:
    """Fetch Razorpay jobs. Compatible with job_fetcher.py layer interface."""
    scraper = RazorpayScraper(profile)
    jobs = scraper.fetch_and_parse()
    logger.info(f"[razorpay] {len(jobs)} jobs kept")
    return jobs
