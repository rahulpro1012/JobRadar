"""
JobRadar Tier 2: Auto-Import Probe Results to company_registry
Reads the latest probe_results_*.csv file and bulk-inserts verified companies into the company_registry table.

Usage:
    python scripts/import_probe_to_registry.py

This script:
1. Finds the most recent probe_results_*.csv file
2. Reads all entries with jobs_count > 0
3. Bulk-inserts into company_registry table (upserts on slug conflict)
4. Reports statistics
"""

import csv
import glob
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get connection to jobradar.db"""
    # Assume script runs from backend directory
    db_path = Path(__file__).parent.parent / "jobradar.db"

    if not db_path.exists():
        logger.error(f"❌ Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def find_latest_probe_file():
    """Find the most recent probe_results_*.csv file in the backend directory."""
    backend_dir = Path(__file__).parent.parent
    probe_files = sorted(glob.glob(str(backend_dir / "probe_results_*.csv")))

    if not probe_files:
        logger.error("❌ No probe_results_*.csv files found. Run probe_indian_companies.py first.")
        sys.exit(1)

    latest_file = probe_files[-1]
    logger.info(f"📂 Using probe results: {Path(latest_file).name}")
    return latest_file


def import_probe_results(csv_file: str):
    """Import probe results into company_registry table."""

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify company_registry table exists
    try:
        cursor.execute("SELECT COUNT(*) FROM company_registry;")
    except sqlite3.OperationalError:
        logger.error("❌ company_registry table does not exist. Ensure database.py schema is initialized.")
        sys.exit(1)

    # Read CSV and insert rows
    inserted = 0
    updated = 0
    skipped = 0

    with open(csv_file, "r") as f:
        reader = csv.DictReader(f)

        for row in reader:
            company_name = row["company_name"]
            slug = row["slug"]
            ats = row["ats"]
            jobs_count = int(row["jobs_count"]) if row["jobs_count"] else 0

            # Only import if company has jobs on this ATS
            if jobs_count == 0:
                skipped += 1
                continue

            try:
                cursor.execute(
                    """
                    INSERT INTO company_registry
                    (slug, name, ats, discovered_at, job_count)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        slug,
                        company_name,
                        ats,
                        datetime.utcnow().isoformat(),
                        jobs_count,
                    ),
                )
                inserted += 1
                logger.debug(f"✅ Inserted: {company_name:20s} ({ats:15s}) | {jobs_count} jobs")

            except sqlite3.IntegrityError:
                # Slug already exists — update instead
                cursor.execute(
                    """
                    UPDATE company_registry
                    SET job_count = ?, last_checked = ?, ats = ?
                    WHERE slug = ?
                    """,
                    (
                        jobs_count,
                        datetime.utcnow().isoformat(),
                        ats,
                        slug,
                    ),
                )
                updated += 1
                logger.debug(f"🔄 Updated: {company_name:20s} ({ats:15s}) | {jobs_count} jobs")

    conn.commit()
    conn.close()

    logger.info(f"\n{'='*80}")
    logger.info(f"📊 IMPORT COMPLETE")
    logger.info(f"{'='*80}")
    logger.info(f"Inserted: {inserted} new companies")
    logger.info(f"Updated:  {updated} existing companies")
    logger.info(f"Skipped:  {skipped} entries (no jobs or errors)")
    logger.info(f"Total:    {inserted + updated} companies in registry")

    # Show distribution by ATS
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ats, COUNT(*) as count FROM company_registry GROUP BY ats ORDER BY count DESC;"
    )
    logger.info(f"\n📈 Distribution by ATS:")
    for row in cursor.fetchall():
        logger.info(f"  {row['ats']:20s}: {row['count']:3d} companies")

    conn.close()

    logger.info(f"\n✅ Next step: Update ats_fetcher.py to load companies from database")


def main():
    """Main entry point."""
    logger.info("🚀 Starting import of probe results...")

    csv_file = find_latest_probe_file()
    import_probe_results(csv_file)


if __name__ == "__main__":
    main()
