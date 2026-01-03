
import os
import sys
import json
import traceback
from dotenv import load_dotenv
from supabase import create_client

# Setup path
sys.path.append(os.getcwd())
load_dotenv()

# Setup Supabase
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

PROJECT_ID = "2ab31fac-ce8e-4f8d-8681-e95ea3059fea"

try:
    print(f"Fetching project {PROJECT_ID}...")
    result = supabase.table('projects').select('*').eq('id', PROJECT_ID).execute()
    
    if not result.data:
        print("Project not found!")
        sys.exit(1)
        
    project = result.data[0]
    full_data = project.get('full_audit_data', {}) or {}
    
    if isinstance(full_data, str):
        full_data = json.loads(full_data)
        
    audit_data = full_data
    audit_data['domain'] = project.get('domain')
    
    # Parse nested fields logic (same as index.py)
    for field in ['domain_rank', 'summary', 'backlinks_summary', 'organic_keywords', 'pages', 'referring_domains']:
        if isinstance(audit_data.get(field), str):
            try:
                audit_data[field] = json.loads(audit_data[field])
            except:
                pass

    print("Data loaded. Simulating slide generation...")
    from api.deep_audit_slides import create_deep_audit_slides
    
    # Simulate empty screenshots (backend should handle this)
    # or simulate basic ones
    screenshots = {
        # "homepage": "data:image/png;base64,..." # We can omit to trigger fallback or just pass None
    }
    
    # Note: creating slides requires Google Creds. 
    # If this crashes due to creds, it's a different error than the one strictly in logic.
    # But often the logic crash happens before API calls.
    
    create_deep_audit_slides(
        data=audit_data,
        domain=audit_data.get('domain'),
        creds=None, # It will try to load from env
        screenshots=screenshots
    )
    
    print("SUCCESS: Slides generated without crash.")

except Exception as e:
    print("\nCRASH DETECTED:")
    traceback.print_exc()
