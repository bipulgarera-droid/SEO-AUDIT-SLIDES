#!/usr/bin/env python3
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
if not result.data:
    print("Project not found!")
    exit(1)

project = result.data[0]
audit_data = project.get('full_audit_data', {}) or {}

if isinstance(audit_data, str):
    audit_data = json.loads(audit_data)

pages = audit_data.get('pages', [])
if isinstance(pages, str):
    pages = json.loads(pages)

print(f"Domain: {project.get('domain')}")
print(f"Pages count: {len(pages)}")
print(f"Pages type: {type(pages)}")

if pages:
    print("\nFirst 3 pages:")
    for i, p in enumerate(pages[:3]):
        print(f"  {i+1}. {p.get('url', 'NO URL')}")
else:
    print("\nNO PAGES FOUND IN DATA!")
    print("Keys in audit_data:", list(audit_data.keys())[:20])
