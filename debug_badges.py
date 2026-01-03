#!/usr/bin/env python3
"""Check actual backlinks and readability data for badge debugging"""
import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

PROJECT_ID = "2ab31fac-ce8e-4f8d-8681-e95ea3059fea"

result = supabase.table('projects').select('*').eq('id', PROJECT_ID).execute()
project = result.data[0]
audit_data = project.get('full_audit_data', {}) or {}

if isinstance(audit_data, str):
    audit_data = json.loads(audit_data)

print("=== BACKLINKS DATA ===")
backlinks = audit_data.get('backlinks', {})
if isinstance(backlinks, str):
    backlinks = json.loads(backlinks)
print(f"backlinks keys: {list(backlinks.keys()) if backlinks else 'EMPTY'}")
print(f"referring_domains: {backlinks.get('referring_domains')}")
print(f"total_count: {backlinks.get('total_count')}")
print(f"total_backlinks: {backlinks.get('total_backlinks')}")

# Check threshold
ref_domains = backlinks.get('referring_domains', 0) or 0
print(f"\nThreshold check: referring_domains ({ref_domains}) < 100? {ref_domains < 100}")
if ref_domains < 100:
    print("=> Should show: Needs Link Building")
else:
    print("=> Will show: Building Authority (or Strong Link Profile if >= 500)")

print("\n=== READABILITY DATA ===")
readability = audit_data.get('readability_results', [])
if isinstance(readability, str):
    try:
        readability = json.loads(readability)
    except:
        readability = []

print(f"readability_results type: {type(readability)}")
print(f"readability_results length: {len(readability) if isinstance(readability, list) else 'N/A'}")

if readability:
    for i, r in enumerate(readability[:3]):
        if isinstance(r, dict):
            print(f"\nResult {i+1}:")
            print(f"  URL: {r.get('url', 'N/A')}")
            print(f"  flesch_kincaid_grade: {r.get('flesch_kincaid_grade')}")
            print(f"  grade: {r.get('grade')}")

    # Calculate average grade
    grades = [r.get('flesch_kincaid_grade', 0) for r in readability if isinstance(r, dict)]
    avg_grade = sum(grades) / len(grades) if grades else 0
    print(f"\nAverage grade: {avg_grade}")
    print(f"Threshold check: avg_grade ({avg_grade}) > 9? {avg_grade > 9}")
    if avg_grade > 9:
        print("=> Should show: Poor Page Readability")
    else:
        print("=> Will show: Content Readability is Apt")
else:
    print("NO READABILITY RESULTS FOUND!")
