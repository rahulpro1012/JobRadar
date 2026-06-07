#!/bin/bash
# SmartRecruiters Company Verification Script
# Tests which companies actually have jobs on SmartRecruiters API
# Run this BEFORE editing smartrecruiters_fetcher.py

echo "🔍 SmartRecruiters Company Verification"
echo "=========================================="
echo ""

# Companies to test (candidates for replacement)
CANDIDATES=(
    "adobe"
    "shopify"
    "slack"
    "stripe"
    "notion"
    "figma"
    "twilio"
    "elastic"
    "datadog"
    "github"
    "segment"
    "mux"
    "supabase"
    "vercel"
    "railway"
)

# Current companies (to compare)
CURRENT=(
    "bosch"
    "visa"
    "ibm"
    "sap"
    "unilever"
    "zalando"
    "booking"
    "trivago"
    "klarna"
)

echo "Testing CURRENT companies:"
echo "=========================="
current_count=0
for company in "${CURRENT[@]}"; do
    # Test if company has jobs on SmartRecruiters
    count=$(curl -s "https://api.smartrecruiters.com/v1/companies/$company/postings?limit=1" \
        | jq -r '.content | length' 2>/dev/null || echo "0")

    if [ "$count" = "0" ] || [ "$count" = "" ]; then
        echo "❌ $company: 0 jobs (404 or empty)"
    else
        echo "✓ $company: $count jobs"
        ((current_count++))
    fi
done

echo ""
echo "Testing CANDIDATE companies:"
echo "============================"
verified=()
verified_count=0
for company in "${CANDIDATES[@]}"; do
    count=$(curl -s "https://api.smartrecruiters.com/v1/companies/$company/postings?limit=1" \
        | jq -r '.content | length' 2>/dev/null || echo "0")

    if [ "$count" = "0" ] || [ "$count" = "" ]; then
        echo "❌ $company: 0 jobs (404 or empty)"
    else
        echo "✅ $company: $count jobs"
        verified+=("$company")
        ((verified_count++))
    fi
done

echo ""
echo "=========================================="
echo "📊 SUMMARY"
echo "=========================================="
echo "Current companies with jobs: $current_count / ${#CURRENT[@]}"
echo "Verified candidates found: $verified_count / ${#CANDIDATES[@]}"
echo ""

if [ ${#verified[@]} -ge 10 ]; then
    echo "✅ READY TO SWAP!"
    echo "Use these verified companies:"
    echo "SMARTRECRUITERS_COMPANIES = ["
    for i in "${!verified[@]}"; do
        if [ $i -lt 10 ]; then
            echo "    \"${verified[$i]}\","
        fi
    done
    echo "]"
else
    echo "⚠️  NOT ENOUGH VERIFIED COMPANIES (need 10, found $verified_count)"
    echo "Try searching Google:"
    echo "  site:smartrecruiters.com \"engineer\" \"remote\""
    echo "  OR manually check careers pages:"
    echo "  https://company.com/careers (look for SmartRecruiters branding)"
fi

echo ""
echo "Next steps:"
echo "1. Review the verified list above"
echo "2. Edit backend/app/services/smartrecruiters_fetcher.py"
echo "3. Replace SMARTRECRUITERS_COMPANIES with the verified list"
echo "4. Restart Flask and test"
