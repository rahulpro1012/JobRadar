"""
One-time ATS slug audit script.
Run from the backend directory:
    python audit_ats.py

Pings every slug in GREENHOUSE_COMPANIES, LEVER_COMPANIES, ASHBY_COMPANIES
and prints HTTP status + job count so you can spot dead slugs easily.
"""
import sys
import time
import requests
import urllib3

urllib3.disable_warnings()

sys.path.insert(0, ".")
from app.services.ats_fetcher import GREENHOUSE_COMPANIES, LEVER_COMPANIES, ASHBY_COMPANIES

TIMEOUT = 10
DELAY = 0.3  # polite delay between pings

def _ping_greenhouse(slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false"
    try:
        r = requests.get(url, timeout=TIMEOUT, verify=False)
        if r.status_code == 200:
            count = len(r.json().get("jobs", []))
            return r.status_code, count
        return r.status_code, 0
    except Exception as e:
        return f"ERR:{e}", 0

def _ping_lever(slug):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, timeout=TIMEOUT, verify=False)
        if r.status_code == 200:
            data = r.json()
            count = len(data) if isinstance(data, list) else 0
            return r.status_code, count
        return r.status_code, 0
    except Exception as e:
        return f"ERR:{e}", 0

def _ping_ashby(slug):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(url, timeout=TIMEOUT, verify=False)
        if r.status_code == 200:
            count = len(r.json().get("jobs", []))
            return r.status_code, count
        return r.status_code, 0
    except Exception as e:
        return f"ERR:{e}", 0

def audit(ats_name, companies, ping_fn):
    print(f"\n{'='*60}")
    print(f"  {ats_name}  ({len(companies)} companies)")
    print(f"{'='*60}")
    print(f"{'Status':<10} {'Jobs':<8} {'Company':<30} {'Slug'}")
    print(f"{'-'*10} {'-'*8} {'-'*30} {'-'*20}")
    dead = []
    for name, slug in companies.items():
        status, count = ping_fn(slug)
        flag = "" if str(status) == "200" else "  ← DEAD"
        print(f"{str(status):<10} {count:<8} {name:<30} {slug}{flag}")
        if str(status) != "200":
            dead.append((name, slug, status))
        time.sleep(DELAY)
    if dead:
        print(f"\n  ⚠️  Dead slugs in {ats_name}: {len(dead)}")
        for name, slug, status in dead:
            print(f"     • {name!r}: {slug!r}  ({status})")
    else:
        print(f"\n  ✅ All {ats_name} slugs are live.")

if __name__ == "__main__":
    print("JobRadar ATS Slug Audit")
    print("Checking all registered company slugs against live ATS APIs...")
    audit("Greenhouse", GREENHOUSE_COMPANIES, _ping_greenhouse)
    audit("Lever", LEVER_COMPANIES, _ping_lever)
    audit("Ashby", ASHBY_COMPANIES, _ping_ashby)
    print("\nDone. Remove or fix any slugs marked ← DEAD in ats_fetcher.py.")
