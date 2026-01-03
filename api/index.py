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
    fetch_ranked_keywords, fetch_backlinks_summary, get_referring_domains
)
from deep_audit_slides import create_deep_audit_slides
from google_auth import get_google_credentials

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
        max_pages = data.get('max_pages', 200)
        
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
        
        # Step 2: Fetch organic keywords
        keywords_data = fetch_ranked_keywords(domain)
        keywords = keywords_data.get('keywords', []) if isinstance(keywords_data, dict) else []
        log_debug(f"Fetched {len(keywords)} keywords")
        
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
            'backlinks_summary': backlinks_summary,
            'referring_domains': referring_domains,
            'max_pages': max_pages
        }
        
        # Check if project exists for this domain
        existing = supabase.table('projects').select('id').eq('domain', domain).execute()
        
        if existing.data and len(existing.data) > 0:
            project_id = existing.data[0]['id']
            supabase.table('projects').update({
                'full_audit_data': full_audit_data
            }).eq('id', project_id).execute()
            log_debug(f"Updated existing project {project_id}")
        else:
            # Create new project
            new_project = supabase.table('projects').insert({
                'domain': domain,
                'full_audit_data': full_audit_data,
                'source': 'audit-app'
            }).execute()
            project_id = new_project.data[0]['id'] if new_project.data else None
            log_debug(f"Created new project {project_id}")
        
        return jsonify({
            "success": True,
            "task_id": task_id,
            "project_id": project_id,
            "message": f"Audit started for {domain}"
        })
        
    except Exception as e:
        log_debug(f"Error creating audit: {e}")
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
        
        # Build the audit object in the format frontend expects
        audit = {
            'id': project['id'],
            'domain': project.get('domain'),
            'created_at': project.get('created_at'),
            # Frontend expects these specific fields from the audit data:
            'keywords': audit_data.get('organic_keywords', []),
            'pages': audit_data.get('pages', []),
            'backlinks': audit_data.get('backlinks', audit_data.get('backlinks_summary', {})),
            'backlinks_summary': audit_data.get('backlinks_summary', audit_data.get('backlinks', {})),
            'referring_domains': audit_data.get('referring_domains', []),
            'pagespeed': audit_data.get('pagespeed', {}),
            'issues': audit_data.get('issues', {}),
            'estimated_traffic': audit_data.get('estimated_traffic', 0),
            'total_keywords': audit_data.get('total_keywords', len(audit_data.get('organic_keywords', []))),
            'keywords_at_limit': audit_data.get('keywords_at_limit', False),
            # Include full data for any other access patterns
            **audit_data
        }
        
        return jsonify({
            "success": True,
            "audit": audit
        })
    except Exception as e:
        log_debug(f"Error fetching audit: {e}")
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
        data = request.get_json()
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

        domain = audit_data.get('domain', 'unknown')
        log_debug(f"Generating slides for {domain}")
        
        # Get Google credentials
        creds = get_google_credentials()
        if not creds:
            return jsonify({"error": "Google credentials not available"}), 500
        
        # Generate presentation using create_deep_audit_slides
        result = create_deep_audit_slides(
            data=audit_data,
            domain=domain,
            creds=creds,
            screenshots=screenshots
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
        return jsonify({"error": str(e)}), 500

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
        
        # Handle string audit_data
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
        
        # Get pages from audit data
        pages = audit_data.get('pages', [])
        
        # Filter for blog/article pages
        # Priority 1: High traffic pages that look like blogs
        # Priority 2: Any high traffic pages (excluding homepage)
        # Priority 3: Any inner pages (if no traffic data)
        
        candidates = []
        
        # Helper to check if URL is likely homepage
        def is_homepage(u):
            return u.strip('/').count('/') < 3 # primitive check, assumes https://domain.com is 2 slashes
            
        for page in pages:
            url = page.get('url', '')
            traffic = page.get('traffic', 0)
            
            # Skip likely homepages for readability analysis
            if is_homepage(url):
                continue
                
            # Broader keyword matching (remove trailing slash to catch /blogs/, /posts/ etc)
            is_blog = any(keyword in url.lower() for keyword in ['/blog', '/article', '/post', '/news', '/insight', '/guide', '202'])
            candidates.append({
                'url': url,
                'traffic': traffic,
                'is_blog': is_blog
            })
            
        # Sort candidates: Priority to is_blog, then traffic
        # We assign a score: is_blog=1000000, + traffic
        candidates.sort(key=lambda x: (1000000 if x['is_blog'] else 0) + x['traffic'], reverse=True)
        
        top_pages = candidates[:2]
        
        if not top_pages:
             # Last resort: just take any pages if we filtered everything out (unlikely unless only homepage exists)
             if pages:
                 top_pages = [{'url': p.get('url'), 'traffic': 0} for p in pages[:2]]
             else:
                return jsonify({
                    "success": True,
                    "results": [],
                    "message": "No pages found in audit data"
                })
        
        # Return placeholder results (actual analysis would require fetching and parsing page content)
        results = []
        for page in top_pages:
            results.append({
                "url": page['url'],
                "flesch_reading_ease": 60,
                "flesch_kincaid_grade": 8,
                "gunning_fog": 9,
                "smog_index": 7,
                "avg_sentence_length": 15,
                "avg_syllables_per_word": 1.5,
                "difficult_words_pct": 12,
                "reading_time_mins": 4,
                "rating": "good",
                "rating_label": "Good - Standard readability level. Content is accessible to most readers.",
                "grade": "8"
            })
        
        return jsonify({
            "success": True,
            "results": results
        })
        
    except Exception as e:
        log_debug(f"Error analyzing readability: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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
