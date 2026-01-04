"""
SEO Audit Dashboard - Standalone API Server
Extracted from AgencyOS for independent deployment
"""
import os
import sys
import time
import traceback
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import local modules
from dataforseo_client import (
    start_onpage_audit, get_audit_status, get_audit_summary,
    fetch_ranked_keywords, fetch_backlinks_summary, get_referring_domains,
    get_lighthouse_audit
)
from deep_audit_slides import create_deep_audit_slides
from google_auth import get_google_credentials
from execution.screenshot_capture import capture_screenshot_with_fallback

# Load environment variables
load_dotenv()

# Setup paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
template_dir = os.path.join(BASE_DIR, 'public')
static_dir = os.path.join(BASE_DIR, 'public')

# Flask app
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'audit-app-secret-key')
CORS(app, supports_credentials=True)

# Add no-cache headers to prevent browser caching
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')
supabase: Client = None
if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)
    print(f"✓ Supabase connected")
else:
    print("⚠ Supabase not configured")

# Logging
def log_debug(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# =============================================================================
# STATIC FILE ROUTES
# =============================================================================

@app.route('/')
def home():
    """Serve the audit dashboard"""
    return send_from_directory(template_dir, 'audit-dashboard.html')

@app.route('/audit-dashboard.html')
def audit_dashboard():
    return send_from_directory(template_dir, 'audit-dashboard.html')

@app.route('/ping')
def ping():
    return "pong", 200

@app.route('/favicon.ico')
def favicon():
    return "", 204

# =============================================================================
# PROJECT ENDPOINTS
# =============================================================================

@app.route('/api/get-projects', methods=['GET'])
def get_projects():
    """List all projects (for dropdown)"""
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        # Fetch all projects that have audit data
        projects_res = supabase.table('projects').select('id, domain, created_at, full_audit_data').order('created_at', desc=True).execute()
        projects = projects_res.data if projects_res.data else []
        
        # Format for dropdown
        result = []
        for p in projects:
            has_audit = p.get('full_audit_data') is not None
            result.append({
                'id': p['id'],
                'domain': p.get('domain', 'Unknown'),
                'created_at': p.get('created_at'),
                'has_audit': has_audit
            })
        
        return jsonify({"projects": result})
    except Exception as e:
        log_debug(f"Error fetching projects: {e}")
        return jsonify({"error": str(e)}), 500

# =============================================================================
# AUDIT ENDPOINTS
# =============================================================================

@app.route('/api/create-audit', methods=['POST'])
def create_new_audit():
    """Create a new SEO audit for a domain"""
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        data = request.get_json()
        domain = data.get('domain', '').strip()
        # Accept both 'limit' (frontend) and 'max_pages' (legacy) - default to 5 not 200
        max_pages = data.get('limit') or data.get('max_pages') or 5
        
        if not domain:
            return jsonify({"error": "Domain is required"}), 400
        
        # Clean domain
        domain = domain.replace('https://', '').replace('http://', '').rstrip('/')
        
        log_debug(f"Creating audit for {domain} with {max_pages} pages")
        
        # Step 1: Start on-page audit
        audit_result = start_onpage_audit(f"https://{domain}", max_pages)
        if not audit_result.get('success'):
            return jsonify({"error": audit_result.get('error', 'Failed to start audit')}), 500
        
        task_id = audit_result.get('task_id')
        log_debug(f"On-page audit started: task_id={task_id}")
        
        # Step 2: Fetch organic keywords (up to 1000 for display)
        keywords_data = fetch_ranked_keywords(domain)
        keywords = keywords_data.get('keywords', []) if isinstance(keywords_data, dict) else []
        log_debug(f"Fetched {len(keywords)} keywords")
        
        # Get totals from keywords response - these are ACCURATE
        # The ranked_keywords endpoint returns total_count (real total) and estimated_traffic (sum of visible)
        keywords_total_count = keywords_data.get('total_count', len(keywords))
        keywords_estimated_traffic = keywords_data.get('estimated_traffic', 0)
        keywords_at_limit = keywords_data.get('keywords_at_limit', len(keywords) >= 1000)
        
        log_debug(f"Keywords API totals: {keywords_total_count} keywords, {keywords_estimated_traffic} traffic")
        
        # Step 3: Fetch backlinks summary
        backlinks_summary = fetch_backlinks_summary(domain)
        log_debug(f"Fetched backlinks summary")
        
        # Step 4: Fetch referring domains
        referring_domains = get_referring_domains(domain)
        log_debug(f"Fetched {len(referring_domains)} referring domains")
        
        # Create initial audit data
        full_audit_data = {
            'task_id': task_id,
            'domain': domain,
            'status': 'pending',
            'created_at': time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            'organic_keywords': keywords,
            # Use totals from keywords API (reliable)
            'total_keywords': keywords_total_count,
            'total_traffic': keywords_estimated_traffic,
            'keywords_at_limit': keywords_at_limit,
            'backlinks_summary': backlinks_summary,
            'referring_domains': referring_domains,
            'max_pages': max_pages
        }
        
        # Always create a NEW project for each audit (allows audit history for same domain)
        new_project = supabase.table('projects').insert({
            'domain': domain,
            'full_audit_data': full_audit_data,
            'source': 'audit-app'
        }).execute()
        project_id = new_project.data[0]['id'] if new_project.data else None
        
        print(f"DEBUG CREATE: Initial total_traffic: {full_audit_data.get('total_traffic')}")
        log_debug(f"Created new project {project_id}")
        
        return jsonify({
            "success": True,
            "audit_id": project_id,       # Frontend expects 'audit_id'
            "onpage_task_id": task_id,    # Frontend expects 'onpage_task_id'
            "task_id": task_id,           # Keep for backward compatibility
            "project_id": project_id,     # Keep for backward compatibility
            "message": f"Audit started for {domain}"
        })
        
    except Exception as e:
        log_debug(f"Error creating audit: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/save-audit-results', methods=['POST'])
def save_audit_results():
    """Fetch and save on-page audit results when crawl completes"""
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        data = request.get_json()
        audit_id = data.get('audit_id')
        task_id = data.get('task_id')
        
        if not audit_id or not task_id:
            return jsonify({"error": "audit_id and task_id required"}), 400
        
        log_debug(f"Saving audit results for {audit_id} with task {task_id}")
        
        # Fetch the on-page audit results from DataForSEO
        from api.dataforseo_client import get_page_issues
        pages_data = get_page_issues(task_id, limit=200)  # Get up to 200 pages
        pages = pages_data.get('pages', []) if pages_data.get('success') else []
        
        log_debug(f"Fetched {len(pages)} pages from on-page audit")
        
        # Get existing project data
        result = supabase.table('projects').select('*').eq('id', audit_id).execute()
        if not result.data:
            return jsonify({"error": "Audit not found"}), 404
        
        project = result.data[0]
        audit_data = project.get('full_audit_data', {}) or {}
        if isinstance(audit_data, str):
            try:
                audit_data = json.loads(audit_data)
            except:
                audit_data = {}
        
        # Get domain from audit data
        domain = audit_data.get('domain', project.get('domain', '')).replace('https://', '').replace('http://', '').rstrip('/')
        print(f"DEBUG save-audit: domain='{domain}', audit_data_keys={list(audit_data.keys())}", flush=True)
        
        # Fetch PageSpeed data using Google's PageSpeed Insights API - BOTH mobile and desktop
        pagespeed = {}
        if domain:
            print(f"DEBUG save-audit: Fetching PageSpeed for {domain}...", flush=True)
            try:
                from execution.pagespeed_insights import fetch_pagespeed_scores
                
                # Fetch MOBILE
                mobile_result = fetch_pagespeed_scores(f"https://{domain}", strategy="mobile")
                if mobile_result:
                    pagespeed['mobile'] = {
                        'scores': mobile_result.get('scores', {}),
                        'metrics': mobile_result.get('metrics', {})
                    }
                    print(f"DEBUG save-audit: Mobile PageSpeed performance={mobile_result.get('scores', {}).get('performance')}", flush=True)
                
                # Fetch DESKTOP
                desktop_result = fetch_pagespeed_scores(f"https://{domain}", strategy="desktop")
                if desktop_result:
                    pagespeed['desktop'] = {
                        'scores': desktop_result.get('scores', {}),
                        'metrics': desktop_result.get('metrics', {})
                    }
                    print(f"DEBUG save-audit: Desktop PageSpeed performance={desktop_result.get('scores', {}).get('performance')}", flush=True)
                
                # Also store combined scores for backward compatibility
                if mobile_result:
                    pagespeed['scores'] = mobile_result.get('scores', {})
                    pagespeed['metrics'] = mobile_result.get('metrics', {})
                    
            except Exception as e:
                print(f"DEBUG save-audit: PageSpeed error: {e}", flush=True)
        else:
            print(f"DEBUG save-audit: Domain is empty, skipping PageSpeed", flush=True)
        
        # Update with pages, pagespeed, and mark as completed
        audit_data['pages'] = pages
        audit_data['pagespeed'] = pagespeed
        audit_data['status'] = 'completed'
        
        print(f"DEBUG SAVE: Writing total_traffic: {audit_data.get('total_traffic')}")
        
        print(f"DEBUG save-audit: Saving to Supabase - pages count={len(audit_data.get('pages', []))}, pagespeed={pagespeed.get('performance', 'N/A')}", flush=True)
        
        # Save back to Supabase
        supabase.table('projects').update({
            'full_audit_data': audit_data
        }).eq('id', audit_id).execute()
        
        print(f"DEBUG save-audit: Saved successfully for {audit_id}", flush=True)
        
        return jsonify({"success": True, "message": "Results saved"})
        
    except Exception as e:
        log_debug(f"Error saving audit results: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/deep-audit/status/<task_id>', methods=['GET'])
def deep_audit_status(task_id):
    """Check the status of an on-page audit"""
    try:
        status = get_audit_status(task_id)
        return jsonify(status)
    except Exception as e:
        log_debug(f"Error checking audit status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/audits', methods=['GET'])
@app.route('/api/audits/list', methods=['GET'])
def list_audits_endpoint():
    """List all audits"""
    log_debug("list_audits_endpoint called")
    
    if not supabase:
        log_debug("Supabase not configured")
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        # Optimized query - only fetch ID, domain, date and status
        # We avoid fetching 'full_audit_data' which is heavy (megabytes)
        log_debug("Fetching projects list from Supabase...")
        
        # Try to filter by full_audit_data not being null on server side
        # Note: syntax for JSONB null check can be tricky, if this fails we might need to fetch all and accept empty ones
        try:
            result = supabase.table('projects').select('id, domain, created_at').neq('full_audit_data', 'null').order('created_at', desc=True).execute()
        except:
            # Fallback if filtered query fails
            log_debug("Filtered query failed, fetching all projects (lightweight)")
            result = supabase.table('projects').select('id, domain, created_at').order('created_at', desc=True).execute()
            
        log_debug(f"Got {len(result.data) if result.data else 0} projects")
        
        audits = []
        for p in result.data or []:
            # Since we filtered on server (or just fetching lightweight list), we assume these are valid or display them anyway
            # The frontend allows deleting empty ones if needed
            audits.append({
                'id': p['id'],
                'domain': p.get('domain'),
                'created_at': p.get('created_at'),
                'status': 'completed', # Assumed completed if in this list
                'task_id': None,       # Not needed for list view
                # 'full_audit_data': ... # Omitted for performance
            })
            
        log_debug(f"Returning {len(audits)} audits")
        return jsonify({"success": True, "audits": audits})
    except Exception as e:
        log_debug(f"Error listing audits: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/audits/<audit_id>', methods=['GET'])
def get_audit_detail_endpoint(audit_id):
    """Get full audit details by project ID"""
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        result = supabase.table('projects').select('*').eq('id', audit_id).execute()
        
        if not result.data:
            return jsonify({"error": "Audit not found"}), 404
        
        project = result.data[0]
        audit_data = project.get('full_audit_data', {}) or {}
        
        # Handle case where audit_data is stored as a JSON string
        if isinstance(audit_data, str):
            try:
                audit_data = json.loads(audit_data)
            except:
                audit_data = {}
        
        # Ensure audit_data is a dict
        if not isinstance(audit_data, dict):
            audit_data = {}
        
        # Get stored values
        stored_traffic = audit_data.get('total_traffic', 0)
        stored_keywords_count = audit_data.get('total_keywords', 0)
        keywords = audit_data.get('organic_keywords', [])
        domain = project.get('domain')
        
        # If stored values are 0/missing, re-fetch REAL data from DataForSEO
        if (not stored_traffic or stored_traffic == 0) and domain:
            try:
                from api.dataforseo_client import fetch_ranked_keywords
                fresh_data = fetch_ranked_keywords(domain, limit=1)  # Just get metrics, not all keywords
                if fresh_data.get('success'):
                    stored_traffic = fresh_data.get('estimated_traffic', 0)
                    stored_keywords_count = fresh_data.get('total_count', len(keywords))
                    print(f"DEBUG GET: Re-fetched from DataForSEO: traffic={stored_traffic}, keywords={stored_keywords_count}")
            except Exception as e:
                print(f"DEBUG GET: Failed to re-fetch: {e}")
                # Fall back to stored keywords length
                stored_keywords_count = len(keywords)
        
        if not stored_keywords_count or stored_keywords_count == 0:
            stored_keywords_count = len(keywords)
        
        print(f"DEBUG GET: Returning total_traffic: {stored_traffic}, total_keywords: {stored_keywords_count}")
        
        # Build the audit object in the format frontend expects
        # NOTE: **audit_data is first so our explicit values override stored values
        audit = {
            **audit_data,
            'id': project['id'],
            'domain': project.get('domain'),
            'created_at': project.get('created_at'),
            'keywords': keywords,
            'pages': audit_data.get('pages', []),
            'backlinks': audit_data.get('backlinks', audit_data.get('backlinks_summary', {})),
            'backlinks_summary': audit_data.get('backlinks_summary', audit_data.get('backlinks', {})),
            'referring_domains': audit_data.get('referring_domains', []),
            'pagespeed': audit_data.get('pagespeed', {}),
            'issues': audit_data.get('issues', {}),
            'estimated_traffic': audit_data.get('estimated_traffic', 0),
            'total_traffic': stored_traffic,
            'total_keywords': stored_keywords_count,
            'keywords_at_limit': audit_data.get('keywords_at_limit', len(keywords) >= 1000),
        }
        
        return jsonify({
            "success": True,
            "audit": audit
        })
    except Exception as e:
        log_debug(f"Error fetching audit: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/audits/<audit_id>', methods=['DELETE'])
def delete_audit_endpoint(audit_id):
    """Delete an audit by project ID"""
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        # Delete from projects table
        result = supabase.table('projects').delete().eq('id', audit_id).execute()
        log_debug(f"Deleted audit {audit_id}")
        return jsonify({"success": True, "message": "Audit deleted"})
    except Exception as e:
        log_debug(f"Error deleting audit: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/deep-audit/results/<task_id>', methods=['GET'])
def get_deep_audit_results(task_id):
    """Fetch and store complete audit results"""
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        # Get audit results from DataForSEO
        results = get_audit_summary(task_id)
        
        if not results.get('success'):
            return jsonify({"error": results.get('error', 'Failed to fetch results')}), 500
        
        # Find the project with this task_id
        projects = supabase.table('projects').select('id, full_audit_data').execute()
        target_project = None
        
        for p in projects.data or []:
            audit_data = p.get('full_audit_data', {}) or {}
            if audit_data.get('task_id') == task_id:
                target_project = p
                break
        
        if target_project:
            # Merge results into existing audit data
            existing = target_project.get('full_audit_data', {}) or {}
            existing['status'] = 'completed'
            existing['pages'] = results.get('pages', [])
            existing['summary'] = results.get('summary', {})
            existing['completed_at'] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            supabase.table('projects').update({
                'full_audit_data': existing
            }).eq('id', target_project['id']).execute()
            
            log_debug(f"Stored audit results for project {target_project['id']}")
        
        return jsonify({
            "success": True,
            "results": results
        })
        
    except Exception as e:
        log_debug(f"Error fetching audit results: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# =============================================================================
# SLIDES GENERATION
# =============================================================================

@app.route('/api/deep-audit/slides', methods=['POST'])
@app.route('/api/deep-audit/generate-slides', methods=['POST'])
def generate_deep_audit_slides():
    """Generate Google Slides presentation from audit data"""
    try:
        # Robust JSON parsing - handle both JSON and raw bytes
        data = request.get_json(silent=True)
        if data is None:
            # Fallback: try to parse raw request data
            raw_data = request.data
            if isinstance(raw_data, bytes):
                try:
                    data = json.loads(raw_data.decode('utf-8'))
                except:
                    data = {}
            else:
                data = {}
        
        if not isinstance(data, dict):
            data = {}
            
        screenshots = data.get('screenshots', {})
        audit_data = data.get('audit_data')
        project_id = data.get('project_id')
        
        # If audit_data not provided but project_id is, fetch it
        if not audit_data and project_id:
            try:
                result = supabase.table('projects').select('*').eq('id', project_id).execute()
                if result.data:
                    project = result.data[0]
                    # Get full audit data
                    full_data = project.get('full_audit_data', {}) or {}
                    
                    # Store logic for potential string JSON
                    if isinstance(full_data, str):
                        try:
                            full_data = json.loads(full_data)
                        except:
                            full_data = {}
                            
                    # Construct audit_data expected by slides generator
                    audit_data = full_data
                    audit_data['domain'] = project.get('domain')
            except Exception as e:
                log_debug(f"Error fetching project for slides: {e}")

        if not audit_data:
            return jsonify({"error": "No audit data provided and could not fetch from project_id"}), 400

        # Ensure critical nested fields are parsed if they are strings
        # This fixes "str object has no attribute get" errors
        for field in ['domain_rank', 'summary', 'backlinks_summary', 'organic_keywords', 'pages', 'referring_domains']:
            if isinstance(audit_data.get(field), str):
                try:
                    audit_data[field] = json.loads(audit_data[field])
                except:
                    pass # Keep as is if parse fails

        # Ensure we have a valid domain for screenshot capture
        domain = audit_data.get('domain')
        if not domain or domain in ['unknown', 'Pending Audit']:
            if project_id:
                try:
                    # Fetch fresh domain from project table
                    p_res = supabase.table('projects').select('domain').eq('id', project_id).execute()
                    if p_res.data:
                        domain = p_res.data[0].get('domain')
                        audit_data['domain'] = domain
                except Exception as e:
                    log_debug(f"Error resolving domain from project: {e}")
        
        if not domain:
            domain = 'unknown'
            
        log_debug(f"Generating slides for {domain}")
        
        # Get Google credentials
        creds = get_google_credentials()
        if not creds:
            return jsonify({"error": "Google credentials not available"}), 500
        
        # Upload screenshots to Supabase Storage if present
        processed_screenshots = {}
        try:
            if not screenshots:
                screenshots = {}
            if not isinstance(screenshots, dict):
                log_debug(f"Warning: screenshots is not a dict, it is {type(screenshots)}. resetting to empty.")
                screenshots = {}

            # Fallback for Homepage
            try:
                # Basic validation for homepage key existence
                hp = screenshots.get('homepage')
                is_homepage_missing = not hp or len(str(hp)) < 100
                
                if is_homepage_missing and domain and domain != 'unknown':
                    log_debug(f"Homepage screenshot missing, attempting backend capture for {domain}...")
                    homepage_b64 = capture_screenshot_with_fallback(domain)
                    if homepage_b64:
                        screenshots['homepage'] = homepage_b64
            except Exception as e:
                log_debug(f"Homepage fallback error: {e}")

            if screenshots:
                log_debug(f"Processing {len(screenshots)} screenshots...")
                import base64
                import uuid
                
                bucket_name = 'audit-screenshots'
                # Ensure bucket exists
                try:
                    buckets = supabase.storage.list_buckets()
                    existing_buckets = [b.name for b in buckets]
                    if bucket_name not in existing_buckets:
                        supabase.storage.create_bucket(bucket_name, options={"public": True})
                except Exception as e:
                    log_debug(f"Bucket check warning: {e}")

                for key, data_uri in screenshots.items():
                    try:
                        if not data_uri or not isinstance(data_uri, str):
                            continue
                        # Skip if already a URL
                        if data_uri.startswith('http'):
                            processed_screenshots[key] = data_uri
                            continue
                            
                        # Parse Base64
                        if ',' in data_uri:
                            _, encoded = data_uri.split(',', 1)
                        else:
                            encoded = data_uri
                            
                        img_data = base64.b64decode(encoded)
                        filename = f"{uuid.uuid4()}.png"
                        
                        # Upload
                        supabase.storage.from_(bucket_name).upload(
                            file=img_data,
                            path=filename,
                            file_options={"content-type": "image/png", "x-upsert": "true"}
                        )
                        
                        # Get Public URL
                        public_url = supabase.storage.from_(bucket_name).get_public_url(filename)
                        processed_screenshots[key] = public_url
                        
                    except Exception as e:
                        log_debug(f"Failed to upload screenshot {key}: {e}")
                        continue
                        
        except Exception as e:
            log_debug(f"CRITICAL SCREENSHOT ERROR (Skipping all): {e}")
            processed_screenshots = {} # Fallback to no screenshots

        log_debug(f"Final screenshots count: {len(processed_screenshots)}")
        
        # Ensure audit_data is a dict
        if isinstance(audit_data, str):
            try:
                audit_data = json.loads(audit_data)
            except:
                pass

        # Get issue counts from frontend if provided
        issue_counts = data.get('issue_counts', None)

        # Generate presentation using create_deep_audit_slides
        result = create_deep_audit_slides(
            data=audit_data,
            domain=domain,
            creds=creds,
            screenshots=processed_screenshots,
            issue_counts=issue_counts
        )
        
        if result and result.get('presentation_id'):
            return jsonify({
                "success": True,
                "presentation_id": result.get('presentation_id'),
                "presentation_url": result.get('presentation_url')
            })
        else:
            return jsonify({"error": result.get('error', 'Failed to generate slides')}), 500
        
    except Exception as e:
        log_debug(f"Error generating slides: {e}")
        traceback.print_exc()
        
        # WRITE ERROR TO TMP FILE
        try:
            with open("/tmp/audit_error.log", "w") as f:
                f.write(f"Error: {str(e)}\n")
                f.write(traceback.format_exc())
        except:
            pass
            
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500

# =============================================================================
# READABILITY ANALYSIS
# =============================================================================

@app.route('/api/audit/<audit_id>/readability', methods=['GET'])
def analyze_readability(audit_id):
    """Analyze content readability for audit pages"""
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        # Get the audit data
        result = supabase.table('projects').select('*').eq('id', audit_id).execute()
        
        if not result.data:
            return jsonify({"success": False, "error": "Audit not found"}), 404
        
        project = result.data[0]
        audit_data = project.get('full_audit_data', {}) or {}
        
        # Handle stringified JSON
        if isinstance(audit_data, str):
            try:
                audit_data = json.loads(audit_data)
            except:
                audit_data = {}

        # Check if we have cached readability results
        if audit_data.get('readability_results') and not request.args.get('refresh'):
            return jsonify({
                "success": True,
                "results": audit_data.get('readability_results')
            })
        
        # Ensure critical fields are parsed if they are strings
        for field in ['pages', 'organic_keywords']:
            if isinstance(audit_data.get(field), str):
                try:
                    audit_data[field] = json.loads(audit_data[field])
                except:
                    audit_data[field] = []

        # Extract pages and keywords
        pages = audit_data.get('pages', [])
        
        # Filter for blog/article pages
        # Priority 1: High traffic pages that look like blogs
        # Priority 2: Any high traffic pages (excluding homepage)
        # Priority 3: Any inner pages (if no traffic data)
        
        candidates = []
        
        # Helper to check if URL is likely homepage (more accurate version)
        def is_homepage(u):
            from urllib.parse import urlparse
            parsed = urlparse(u)
            path = parsed.path.strip('/')
            return path == '' or path in ['index.html', 'index.php', 'home']
            
        log_debug(f"Readability: Starting candidate selection. Pages: {len(pages)}, Keywords: {len(audit_data.get('organic_keywords', []))}")
        
        # Define filters outside loop so they're accessible everywhere
        blacklist = ['/collections', '/products', '/cart', '/checkout', '/account', '/search', '/policies/', '/pages/']
        blog_keywords = ['/blog', '/blogs', '/article', '/post', '/news', '/insight', '/guide', '202']
            
        for page in pages:
            url = page.get('url', '')
            traffic = page.get('traffic', 0)
            
            # 1. Skip homepages (must be inner page)
            if is_homepage(url):
                continue
            
            # 2. Skip blacklisted shop/system pages
            if any(item in url.lower() for item in blacklist):
                continue
                
            # 3. Identify blog pages
            is_blog = any(keyword in url.lower() for keyword in blog_keywords)
            
            candidates.append({
                'url': url,
                'traffic': traffic,
                'is_blog': is_blog
            })
            
        log_debug(f"Readability: After crawled pages filter: {len(candidates)} candidates")
            
        # 4. Supplemental: Add top ranking pages from Organic Keywords
        organic_keywords = audit_data.get('organic_keywords', [])
        existing_urls = {c['url'] for c in candidates}
        
        added_from_kw = 0
        for kw in organic_keywords:
            if not isinstance(kw, dict): continue
            
            # Extract URL and traffic from DataForSEO structure
            serp_item = kw.get('ranked_serp_element', {}).get('serp_item', {})
            url_kw = kw.get('url') or serp_item.get('url', '')
            traffic_kw = kw.get('traffic_cost') or serp_item.get('etv', 0) or 0
            
            if not url_kw or url_kw in existing_urls:
                continue
                
            # Skip homepage
            if is_homepage(url_kw): continue
            
            # Skip blacklisted pages
            if any(item in url_kw.lower() for item in blacklist):
                continue
                
            is_blog_kw = any(keyword in url_kw.lower() for keyword in blog_keywords)
            
            # Add if it looks like a blog OR has significant traffic
            if is_blog_kw or traffic_kw > 50:  # Lowered threshold from 100 to 50
                candidates.append({
                    'url': url_kw,
                    'traffic': traffic_kw,
                    'is_blog': is_blog_kw
                })
                existing_urls.add(url_kw)
                added_from_kw += 1
                
        log_debug(f"Readability: Added {added_from_kw} URLs from organic_keywords. Total candidates: {len(candidates)}")
            
        # Sort candidates: Priority to is_blog=True, then by traffic
        candidates.sort(key=lambda x: (1 if x['is_blog'] else 0, x['traffic']), reverse=True)
        
        top_pages = candidates[:2]
        
        # FALLBACK: If no candidates, try ANY inner page (including products/collections)
        if not top_pages:
            log_debug("No blog pages found, attempting fallback to any inner pages...")
            fallback_candidates = []
            for page in pages:
                url = page.get('url', '')
                traffic = page.get('traffic', 0)
                # Only skip homepage
                if is_homepage(url):
                    continue
                fallback_candidates.append({'url': url, 'traffic': traffic, 'is_blog': False})
                
            # Also add from organic keywords without strict blog filter
            for kw in organic_keywords:
                if not isinstance(kw, dict): continue
                serp_item = kw.get('ranked_serp_element', {}).get('serp_item', {})
                url_kw = kw.get('url') or serp_item.get('url', '')
                traffic_kw = kw.get('traffic_cost') or serp_item.get('etv', 0) or 0
                if not url_kw or is_homepage(url_kw): continue
                if url_kw in {c['url'] for c in fallback_candidates}: continue
                fallback_candidates.append({'url': url_kw, 'traffic': traffic_kw, 'is_blog': False})
                
            # Sort by traffic and take top 2
            fallback_candidates.sort(key=lambda x: x['traffic'], reverse=True)
            top_pages = fallback_candidates[:2]
            log_debug(f"Fallback found {len(top_pages)} pages for readability.")
        
        if not top_pages:
            return jsonify({
                "success": True,
                "results": [],
                "message": "No suitable blog or content pages found for readability analysis. Please ensure your site has been fully crawled."
            })
        
        # Return placeholder results (actual analysis would require fetching and parsing page content)
        results = []
        # Real Analysis
        import requests
        from bs4 import BeautifulSoup
        import textstat
        
        results = []
        for page in top_pages:
            url = page['url']
            try:
                # Fetch page content
                print(f"DEBUG: Fetching content for readability analysis: {url}")
                # Use a standard user agent to avoid bot blocks
                resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
                
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    
                    # Clean boilerplate
                    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe']):
                        tag.decompose()
                        
                    # Get main text
                    text = soup.get_text(separator=' ', strip=True)
                    
                    # Calculate metrics if we have enough content
                    if len(text) > 200:
                        # Helper for difficult words percentage
                        def get_difficult_words_pct(t):
                            try:
                                words = t.split()
                                if not words: return 0
                                return (textstat.difficult_words(t) / len(words)) * 100
                            except: return 12 # Default fallback
                            
                        # Grade logic
                        grade_score = textstat.flesch_kincaid_grade(text)
                        
                        # Rating logic
                        flesch = textstat.flesch_reading_ease(text)
                        # Use grade score for rating (user preference)
                        if grade_score <= 9:
                            rating = "good"
                            rating_label = "Content readability is apt."
                        else:
                            rating = "poor"
                            rating_label = "Page readability is poor. Needs improvement."
                            
                        results.append({
                            "url": url,
                            "flesch_reading_ease": int(flesch),
                            "flesch_kincaid_grade": round(grade_score, 1),
                            "gunning_fog": round(textstat.gunning_fog(text), 1),
                            "smog_index": round(textstat.smog_index(text), 1),
                            "avg_sentence_length": int(textstat.avg_sentence_length(text)),
                            "avg_syllables_per_word": round(textstat.avg_syllables_per_word(text), 1),
                            "difficult_words_pct": int(get_difficult_words_pct(text)),
                            "reading_time_mins": max(1, int(len(text.split()) / 200)), # Approx 200 wpm
                            "rating": rating,
                            "rating_label": rating_label,
                            "grade": str(int(grade_score))
                        })
                    else:
                        print(f"DEBUG: Not enough text content found on {url} (Length: {len(text)})")
                else:
                    print(f"DEBUG: API fetch failed for {url}: {resp.status_code}")
                    
            except Exception as e:
                print(f"DEBUG: Readability analysis error for {url}: {e}")
                continue

        if not results:
             return jsonify({
                "success": False, 
                "message": "Could not analyze content. Pages may be blocking crawlers or have insufficient text."
            })
        
        # Save results to Supabase for slides to use later
        try:
            audit_data['readability_results'] = results
            supabase.table('projects').update({
                'full_audit_data': audit_data
            }).eq('id', audit_id).execute()
            log_debug(f"Saved readability results for {audit_id}")
        except Exception as e:
            log_debug(f"Failed to save readability results: {e}")
        
        return jsonify({
            "success": True,
            "results": results
        })
        
    except Exception as e:
        log_debug(f"Error analyzing readability: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/audit/<audit_id>/refresh-speed', methods=['POST'])
def refresh_speed(audit_id):
    """Refresh PageSpeed metrics for a specific audit"""
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 500
    
    try:
        # Get project
        project_res = supabase.table('projects').select('*').eq('id', audit_id).execute()
        
        project = project_res.data[0] if project_res.data else None
        if not project:
             return jsonify({"error": "Audit not found"}), 404

        full_audit_data = project.get('full_audit_data', {})
        if isinstance(full_audit_data, str):
             try:
                 full_audit_data = json.loads(full_audit_data)
             except:
                 full_audit_data = {}

        domain = project.get('domain')
        if not domain:
             return jsonify({"error": "No domain found"}), 400
        
        # Ensure URL has protocol
        if not domain.startswith('http'):
            domain = 'https://' + domain
            
        print(f"Refreshing PageSpeed for: {domain} (Audit: {audit_id})...")
        
        pagespeed_data = {'url': domain}
        
        # Mobile
        print(f"  Fetching Mobile scores (Google PageSpeed)...")
        from execution.pagespeed_insights import fetch_pagespeed_scores
        
        # Helper for valid checks
        def mobile_result_valid(res):
            return res and res.get('success') and res.get('scores')
            
        mobile_res = fetch_pagespeed_scores(domain, strategy='mobile')
        
        if mobile_result_valid(mobile_res):
            pagespeed_data['mobile'] = mobile_res
            print(f"  Mobile Success: {mobile_res.get('scores', {})}")
        else:
            print(f"  Mobile Failed: {mobile_res.get('error') if mobile_res else 'No result'}")
            
        # Desktop
        print(f"  Fetching Desktop scores (Google PageSpeed)...")
        desktop_res = fetch_pagespeed_scores(domain, strategy='desktop')
        
        if mobile_result_valid(desktop_res):
            pagespeed_data['desktop'] = desktop_res
            print(f"  Desktop Success: {desktop_res.get('scores', {})}")
        else:
            print(f"  Desktop Failed: {desktop_res.get('error') if desktop_res else 'No result'}")
            
        if 'mobile' not in pagespeed_data and 'desktop' not in pagespeed_data:
             return jsonify({"success": False, "error": "Failed to fetch any PageSpeed data. Check API keys and URL."}), 500

        # Update full_data
        full_audit_data['pagespeed'] = pagespeed_data
        
        supabase.table('projects').update({
             'full_audit_data': full_audit_data
        }).eq('id', project['id']).execute()
        
        return jsonify({
            "success": True, 
            "pagespeed": pagespeed_data
        })

    except Exception as e:
        log_debug(f"Error refreshing speed: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(Exception)
def handle_exception(e):
    log_debug(f"Unhandled exception: {e}")
    traceback.print_exc()
    return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 3000))
    print(f"\n🚀 SEO Audit Dashboard starting on port {port}")
    print(f"   Open http://localhost:{port} in your browser\n")
    app.run(host='0.0.0.0', port=port, debug=False)
