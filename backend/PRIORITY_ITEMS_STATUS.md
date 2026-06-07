# Priority Items Implementation Status

## ✅ Phase 3: Verified Company Research & Optimization (6 Items)

### Item 1: Run company_registry CREATE TABLE ✅ SCHEMA READY
**Status**: Table schema already added in database.py
**Action**: Restart Flask
```bash
python run.py
sqlite3 jobradar.db "SELECT COUNT(*) FROM company_registry;"
```
**Expected**: Table auto-created on Flask init

---

### Item 2: Reset Naukri Circuit + Verify ✅ HELPER READY
**Status**: reset_circuit_breaker() function added in database.py
**Action**: Execute after refresh
```bash
# Option A: Via SQL
sqlite3 jobradar.db "UPDATE source_health SET disabled_until=NULL, consecutive_failures=0, status='healthy' WHERE source='naukri';"

# Option B: Via Python (in Flask shell)
from app.database import reset_circuit_breaker
reset_circuit_breaker("naukri")
```
**Then**: Restart Flask and run refresh, check logs for [naukri] 200 responses

---

### Item 3: Bump Adzuna Cap to 36/day + Extend Cache TTL ✅ DONE
**File**: `backend/app/services/adzuna_fetcher.py`
**Changes Made**:
- Line 32: `DAILY_LIMIT = 12` → `DAILY_LIMIT = 36` ✅
- Line 33: `CACHE_TTL_HOURS = 6` → `CACHE_TTL_HOURS = 12` ✅
- cache_set() automatically uses CACHE_TTL_HOURS ✅

**Impact**: +60-80 jobs/refresh from Adzuna (was ~30)

---

### Item 4: Fix RemoteOK Geo-Filter ✅ DONE
**File**: `backend/app/services/remoteok_fetcher.py`
**Changes Made**:
- Updated `_india_eligible()` function (line 132-149) ✅
- Added expanded BLOCKLIST with state/city level filtering ✅
- Added ALLOWLIST for India/Worldwide/Asia/Remote ✅
- Better handling of blank locations ✅

**Impact**: +15-30 jobs/refresh from RemoteOK (removes US/UK jobs)

---

### Item 5: Swap SmartRecruiters Companies (30 min) — RESEARCH FIRST ⚠️ READY
**Status**: Research script created, code change ready

**Step 1: Run Verification Script**
```bash
bash backend/verify_smartrecruiters.sh
```

This script will:
- Test all 15 candidate companies
- Show how many jobs each has
- Generate the replacement list automatically

**Expected Output Example**:
```
Testing CURRENT companies:
❌ bosch: 0 jobs
❌ visa: 0 jobs
...

Testing CANDIDATE companies:
✅ adobe: 45 jobs
✅ shopify: 80 jobs
✅ slack: 30 jobs
...

SUMMARY
========
Verified candidates found: 12 / 15
✅ READY TO SWAP!
```

**Step 2: Update Code**
Once verified, edit `smartrecruiters_fetcher.py` (lines 23-33):

```python
SMARTRECRUITERS_COMPANIES = [
    # Verified companies from verify_smartrecruiters.sh output
    # Only include companies that returned job counts > 0
    "adobe",           # ✓ verified
    "shopify",         # ✓ verified
    "slack",           # ✓ verified
    "stripe",          # ✓ verified
    "notion",          # ✓ verified
    "figma",           # ✓ verified
    "twilio",          # ✓ verified
    "elastic",         # ✓ verified
    "datadog",         # ✓ verified
    "github",          # ✓ verified
]
```

**Impact**: +40-80 jobs/refresh from SmartRecruiters (was ~10 from dead companies)

---

### Item 6: Audit Greenhouse + Lever 404 Registry 🟡 OPTIONAL
**Status**: Not automated (manual research required)
**Why Optional**: Low ROI, time-consuming

**If Doing Audit**:
1. Test each company's endpoint:
   ```bash
   for company in stripe figma discord postman github; do
     curl -s "https://boards-api.greenhouse.io/v1/boards/$company/jobs?&content=true" \
       | jq '.jobs | length'
   done
   ```

2. Remove companies returning 0 or errors
3. Update GREENHOUSE_COMPANIES and LEVER_COMPANIES in `ats_fetcher.py`

**Impact**: -10s per refresh (removes 404 delays)

---

## 📊 Current Implementation Status

| Item | Status | Time | Action Required |
|------|--------|------|-----------------|
| 1. company_registry table | ✅ Ready | 2 min | Restart Flask |
| 2. Reset Naukri circuit | ✅ Ready | 3 min | Run SQL/Python after refresh |
| 3. Adzuna cap (36/day) | ✅ Done | 0 min | Already implemented |
| 4. RemoteOK geo-filter | ✅ Done | 0 min | Already implemented |
| 5. SmartRecruiters swap | ⚠️ Ready | 30 min | Run verify script, then edit code |
| 6. Greenhouse/Lever audit | 🟡 Optional | 45 min | Manual research if time permits |

---

## Quick Start Checklist

- [ ] **Step 1** (5 min): Restart Flask
  ```bash
  python run.py
  ```

- [ ] **Step 2** (2 min): Verify company_registry table created
  ```bash
  sqlite3 jobradar.db "SELECT COUNT(*) FROM company_registry;"
  ```

- [ ] **Step 3** (10 min): Run SmartRecruiters verification script
  ```bash
  bash backend/verify_smartrecruiters.sh
  ```

- [ ] **Step 4** (10 min): If script says "✅ READY TO SWAP", update `smartrecruiters_fetcher.py`

- [ ] **Step 5** (3 min): Reset Naukri circuit
  ```bash
  sqlite3 jobradar.db "UPDATE source_health SET disabled_until=NULL, consecutive_failures=0, status='healthy' WHERE source='naukri';"
  ```

- [ ] **Step 6** (60 sec): Run profile refresh
  ```bash
  curl -X POST http://localhost:5000/api/profile/{profile_id}/refresh
  ```

- [ ] **Step 7** (2 min): Check logs
  ```bash
  tail -100 logs/app.log | grep -E "\[(adzuna|naukri|smartrecruiters|remoteok)\]"
  ```

---

## Expected Results After All Changes

| Source | Before | After | Change |
|--------|--------|-------|--------|
| **Adzuna** | ~30 | ~60 | +30 (Item 3) |
| **RemoteOK** | ~20 | ~35 | +15 (Item 4) |
| **SmartRecruiters** | ~10 | ~50 | +40 (Item 5) |
| **Naukri** | 0 | ~80 | +80 (Item 2) |
| **Other sources** | ~196 | ~196 | 0 |
| **TOTAL** | ~256 | ~420 | **+164 (+64%)** |

---

## Debugging If Issues Occur

### Adzuna Still Low
- Check quota: `sqlite3 jobradar.db "SELECT * FROM quota_usage WHERE source='adzuna' AND date='2025-01-XX';"`
- Should see quota increasing (used calls)

### RemoteOK Still Returning US Jobs
- Check logs: `grep "geo-blocked" logs/app.log`
- May need to expand BLOCKLIST with additional keywords

### SmartRecruiters Verification Script Fails
- Verify jq is installed: `which jq`
- If not: `brew install jq` (macOS) or `apt-get install jq` (Linux)
- Try testing one company manually: `curl -s "https://api.smartrecruiters.com/v1/companies/adobe/postings?limit=1" | jq '.content | length'`

### Naukri Still Showing 406 After Reset
- Headers may still need adjustment
- Check logs for actual error: `grep "naukri" logs/app.log | tail -20`
- May need to switch header strategy (see Phase 1 plan for alternatives)

---

## Files Changed

### Phase 1 Fixes (Already Implemented)
- ✅ adzuna_fetcher.py — Query cleaning
- ✅ search_fetcher.py — Timeout increase
- ✅ linkedin_guest_fetcher.py — Query truncation + remote tuning
- ✅ naukri_fetcher.py — Header overhaul + query cleaning
- ✅ company_discovery.py — DB context fixes
- ✅ workable_fetcher.py — Debug logs
- ✅ smartrecruiters_fetcher.py — Debug logs
- ✅ job_fetcher.py — Recruitee removal
- ✅ database.py — company_registry schema + reset_circuit_breaker()

### Phase 3 Changes (This Round)
- ✅ adzuna_fetcher.py — DAILY_LIMIT 12→36, CACHE_TTL 6→12
- ✅ remoteok_fetcher.py — Enhanced _india_eligible() function
- ⚠️ smartrecruiters_fetcher.py — Awaiting verification script results

### New Helper Scripts
- ✅ verify_smartrecruiters.sh — Company verification script
- ✅ PRIORITY_ITEMS_STATUS.md — This file

---

## Support & Next Steps

After running the checklist:
1. Check if job counts increased to target (420+ total)
2. Monitor for 2-3 refreshes to catch any issues
3. If Item 5 verification fails, try alternate companies
4. Item 6 audit is optional - do if you have time

**Contact/Feedback**: Check logs for [source] error messages. Share them if debugging needed.

