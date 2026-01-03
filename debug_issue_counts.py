#!/usr/bin/env python3
"""Diagnostic script to analyze issue count sources"""
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

pages = audit_data.get('pages', [])
if isinstance(pages, str):
    pages = json.loads(pages)

print(f"=== DATA ANALYSIS ===")
print(f"Domain: {project.get('domain')}")
print(f"Total pages in data: {len(pages)}")

# Filter crawled pages (same as frontend)
crawled = [p for p in pages if p.get('meta', {}).get('title') and p.get('meta', {}).get('title') != 'Pending Audit']
print(f"Crawled pages (with valid title): {len(crawled)}")

# Count meta issues (same as frontend)
title_too_long = 0
no_desc = 0
for p in crawled:
    meta = p.get('meta', {})
    title = meta.get('title', '')
    desc = meta.get('description', '')
    if len(title) > 60:
        title_too_long += 1
    if not desc:
        no_desc += 1

print(f"\n=== META ISSUES (from crawled pages) ===")
print(f"Title too long: {title_too_long}")
print(f"No description: {no_desc}")

# Count heading duplicates (same as frontend)
h1_map = {}
h2_map = {}
h3_map = {}

for p in crawled:
    meta = p.get('meta', {})
    h1_list = meta.get('h1') or p.get('h1') or []
    h2_list = meta.get('h2') or p.get('h2') or []
    h3_list = meta.get('h3') or p.get('h3') or []
    
    if isinstance(h1_list, list):
        for h in h1_list:
            key = str(h).lower().strip()
            if len(key) > 3:
                if key not in h1_map:
                    h1_map[key] = []
                h1_map[key].append(p.get('url'))
    
    if isinstance(h2_list, list):
        for h in h2_list:
            key = str(h).lower().strip()
            if len(key) > 3:
                if key not in h2_map:
                    h2_map[key] = []
                h2_map[key].append(p.get('url'))
    
    if isinstance(h3_list, list):
        for h in h3_list:
            key = str(h).lower().strip()
            if len(key) > 3:
                if key not in h3_map:
                    h3_map[key] = []
                h3_map[key].append(p.get('url'))

dup_h1 = len([k for k, v in h1_map.items() if len(v) > 1])
dup_h2 = len([k for k, v in h2_map.items() if len(v) > 1])
dup_h3 = len([k for k, v in h3_map.items() if len(v) > 1])

print(f"\n=== HEADING DUPLICATES (from crawled pages) ===")
print(f"Duplicate H1 headings: {dup_h1}")
print(f"Duplicate H2 headings: {dup_h2}")
print(f"Duplicate H3 headings: {dup_h3}")

print(f"\n=== RAW DATA SAMPLES ===")
for i, p in enumerate(crawled[:3]):
    print(f"\nPage {i+1}: {p.get('url')}")
    meta = p.get('meta', {})
    h3_list = meta.get('h3') or p.get('h3') or []
    print(f"  H3 count: {len(h3_list) if isinstance(h3_list, list) else 'N/A'}")
    if isinstance(h3_list, list):
        print(f"  H3 samples: {h3_list[:5]}")
