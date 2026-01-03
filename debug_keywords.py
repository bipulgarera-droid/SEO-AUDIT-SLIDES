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
project = result.data[0]
audit_data = project.get('full_audit_data', {}) or {}

if isinstance(audit_data, str):
    audit_data = json.loads(audit_data)

organic_keywords = audit_data.get('organic_keywords', [])
if isinstance(organic_keywords, str):
    organic_keywords = json.loads(organic_keywords)

print(f"Total organic_keywords: {len(organic_keywords)}")

# Extract unique URLs from organic_keywords
urls = set()
for kw in organic_keywords:
    if not isinstance(kw, dict): continue
    # Try both structures
    url_direct = kw.get('url', '')
    serp_item = kw.get('ranked_serp_element', {}).get('serp_item', {})
    url_serp = serp_item.get('url', '')
    
    if url_direct: urls.add(url_direct)
    if url_serp: urls.add(url_serp)

print(f"\nUnique URLs in organic_keywords: {len(urls)}")

# Check for blog URLs
blog_keywords = ['/blog', '/blogs', '/article', '/post', '/news']
blog_urls = [u for u in urls if any(kw in u.lower() for kw in blog_keywords)]
print(f"Blog URLs found: {len(blog_urls)}")
for u in blog_urls[:5]:
    print(f"  - {u}")

# Show sample of all URLs    
print(f"\nSample of all URLs:")
for u in list(urls)[:10]:
    print(f"  - {u}")
