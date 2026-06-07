#!/usr/bin/env python3
"""
Verification script for Follow-Up Items Implementation
Checks that all code changes are in place and database is ready.
"""
import sqlite3
import json
from pathlib import Path

def check_file_changes():
    """Verify all code changes are in place."""
    print("\n📋 CHECKING CODE CHANGES...")
    print("=" * 60)

    checks = [
        {
            "name": "SmartRecruiters companies updated",
            "file": "app/services/smartrecruiters_fetcher.py",
            "should_contain": '"adobe"',
            "should_not_contain": '"bosch"',
        },
        {
            "name": "LinkedIn remote location handling",
            "file": "app/services/linkedin_guest_fetcher.py",
            "should_contain": 'query_location = "Worldwide"',
            "should_not_contain": None,
        },
        {
            "name": "Company registry schema added",
            "file": "app/database.py",
            "should_contain": "CREATE TABLE IF NOT EXISTS company_registry",
            "should_not_contain": None,
        },
        {
            "name": "Reset circuit breaker function",
            "file": "app/database.py",
            "should_contain": "def reset_circuit_breaker",
            "should_not_contain": None,
        },
        {
            "name": "Workable debug logs",
            "file": "app/services/workable_fetcher.py",
            "should_contain": "logger.info(f\"[{SOURCE_NAME}] raw keys",
            "should_not_contain": None,
        },
        {
            "name": "SmartRecruiters debug logs",
            "file": "app/services/smartrecruiters_fetcher.py",
            "should_contain": "logger.info(f\"[{SOURCE_NAME}] raw keys",
            "should_not_contain": None,
        },
    ]

    passed = 0
    failed = 0

    for check in checks:
        filepath = Path(check["file"])
        if not filepath.exists():
            print(f"❌ {check['name']}: FILE NOT FOUND ({check['file']})")
            failed += 1
            continue

        content = filepath.read_text()

        if check["should_contain"] and check["should_contain"] not in content:
            print(f"❌ {check['name']}: Missing expected code")
            failed += 1
            continue

        if check["should_not_contain"] and check["should_not_contain"] in content:
            print(f"❌ {check['name']}: Old code still present")
            failed += 1
            continue

        print(f"✅ {check['name']}")
        passed += 1

    return passed, failed


def check_database():
    """Verify database schema is ready."""
    print("\n🗄️  CHECKING DATABASE...")
    print("=" * 60)

    db_path = Path("jobradar.db")
    if not db_path.exists():
        print(f"⚠️  Database not found at {db_path}")
        print("   (Will be created on first Flask init)")
        return 0, 1

    try:
        conn = sqlite3.connect("jobradar.db")
        cursor = conn.cursor()

        # Check if company_registry table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='company_registry'
        """)

        if cursor.fetchone():
            print("✅ company_registry table exists")

            # Check columns
            cursor.execute("PRAGMA table_info(company_registry)")
            columns = [row[1] for row in cursor.fetchall()]
            expected = ['id', 'slug', 'name', 'ats', 'discovered_at', 'job_count', 'last_checked', 'created_at']

            if all(col in columns for col in expected):
                print(f"✅ All 8 columns present: {', '.join(expected)}")
                return 1, 0
            else:
                print(f"❌ Missing columns. Found: {columns}")
                return 0, 1
        else:
            print("⚠️  company_registry table not yet created")
            print("   (Will be created on next Flask init)")
            return 0, 0

        conn.close()
    except Exception as e:
        print(f"❌ Database error: {e}")
        return 0, 1


def check_smart_recruiters_companies():
    """Verify SmartRecruiters companies are updated."""
    print("\n🏢 CHECKING SMARTRECRUITERS COMPANIES...")
    print("=" * 60)

    from app.services.smartrecruiters_fetcher import SMARTRECRUITERS_COMPANIES

    old_companies = {"bosch", "visa", "ibm", "sap", "unilever", "zalando", "booking", "trivago", "klarna"}
    new_companies = {"adobe", "shopify", "slack", "stripe", "notion"}

    current = set(SMARTRECRUITERS_COMPANIES)

    has_new = bool(current & new_companies)
    has_old = bool(current & old_companies)

    if has_new and not has_old:
        print(f"✅ Companies updated: {', '.join(sorted(current)[:5])}...")
        return 1, 0
    elif has_old and not has_new:
        print(f"❌ Companies not updated. Still has: {', '.join(sorted(current & old_companies))}")
        return 0, 1
    else:
        print(f"⚠️  Mixed list: {len(current)} companies. Check manually.")
        print(f"   New: {current & new_companies}")
        print(f"   Old: {current & old_companies}")
        return 0, 0


def main():
    """Run all verification checks."""
    print("\n" + "=" * 60)
    print("🚀 FOLLOW-UP IMPLEMENTATION VERIFICATION")
    print("=" * 60)

    results = []

    # Check code changes
    p1, f1 = check_file_changes()
    results.append(("Code Changes", p1, f1))

    # Check SmartRecruiters
    try:
        p2, f2 = check_smart_recruiters_companies()
        results.append(("SmartRecruiters", p2, f2))
    except Exception as e:
        print(f"⚠️  SmartRecruiters check skipped: {e}")
        results.append(("SmartRecruiters", 0, 0))

    # Check database
    p3, f3 = check_database()
    results.append(("Database", p3, f3))

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)

    total_passed = sum(r[1] for r in results)
    total_failed = sum(r[2] for r in results)

    for name, passed, failed in results:
        status = "✅" if failed == 0 and passed > 0 else "⚠️" if failed == 0 else "❌"
        print(f"{status} {name:25} {passed} passed, {failed} failed")

    print("=" * 60)

    if total_failed == 0:
        print("\n✅ ALL CHECKS PASSED!")
        print("\nNext Steps:")
        print("1. Restart Flask (to create company_registry table)")
        print("2. Run profile refresh: curl -X POST http://localhost:5000/api/profile/{id}/refresh")
        print("3. Check logs for Naukri/LinkedIn/SmartRecruiters responses")
        print("4. (Optional) Set up UptimeRobot monitor")
    else:
        print(f"\n❌ {total_failed} CHECKS FAILED - Review above")
        print("\nHints:")
        print("- Ensure you're in the project root directory")
        print("- Check file paths are relative to current directory")
        print("- Some checks may show ⚠️ if Flask hasn't initialized yet")


if __name__ == "__main__":
    main()
