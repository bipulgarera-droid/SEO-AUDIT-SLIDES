#!/usr/bin/env python3
"""
Website Screenshot Capture using Playwright
High-quality, reliable screenshot capture for any website
"""
import os
import base64
from typing import Optional


def capture_website_screenshot(url: str, output_path: str = None, width: int = 1920, height: int = 1080) -> Optional[str]:
    """
    Capture a high-resolution screenshot of a website using Playwright.
    
    Args:
        url: The URL to screenshot (with or without protocol)
        output_path: Optional path to save the image file
        width: Viewport width (default 1920)
        height: Viewport height (default 1080)
    
    Returns:
        Base64 encoded image string, or None on error
    """
    try:
        from playwright.sync_api import sync_playwright
        
        # Ensure URL has protocol
        if not url.startswith('http'):
            url = f"https://{url}"
        
        print(f"DEBUG: Capturing screenshot for {url} at {width}x{height}")
        
        with sync_playwright() as p:
            # Launch headless browser
            browser = p.chromium.launch(headless=True)
            
            # Create context with viewport size
            context = browser.new_context(
                viewport={'width': width, 'height': height},
                device_scale_factor=2,  # 2x for high DPI/retina quality
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = context.new_page()
            
            # Navigate with timeout
            page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait a bit for any lazy-loaded content
            page.wait_for_timeout(2000)
            
            # Take screenshot
            screenshot_bytes = page.screenshot(
                type='png',
                full_page=False  # Just viewport, not full scroll
            )
            
            browser.close()
            
            # Save to file if path provided
            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(screenshot_bytes)
                print(f"DEBUG: Screenshot saved to {output_path}")
            
            # Return base64 encoded
            base64_image = base64.b64encode(screenshot_bytes).decode()
            print(f"DEBUG: Screenshot captured successfully ({len(screenshot_bytes)} bytes)")
            
            return f"data:image/png;base64,{base64_image}"
            
    except ImportError:
        print("ERROR: Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        print(f"ERROR capturing screenshot with Playwright: {e}")
        return None


def capture_screenshot_with_fallback(url: str) -> Optional[str]:
    """
    Capture screenshot with fallback chain:
    1. Try Playwright (best quality)
    2. Try DataForSEO On-Page API (reliable fallback)
    3. Return None (graceful skip)
    
    Args:
        url: The URL to screenshot
        
    Returns:
        Base64 encoded image string, or None if all methods fail
    """
    # Method 1: Playwright (best quality)
    print(f"DEBUG: Attempting Playwright screenshot for {url}")
    result = capture_website_screenshot(url)
    if result:
        return result
    
    # Method 2: PageSpeed Insights (Primary Fallback - Desktop Quality)
    print(f"DEBUG: Playwright failed, trying PageSpeed Insights (Desktop Strategy)")
    try:
        # Pinned API Key (from existing env/code)
        PAGESPEED_API_KEY = os.environ.get("PAGESPEED_API_KEY", "AIzaSyBSz0KCoCYy_9VSUaqVlWr-wF-BL2KdpPM")
        
        # Ensure URL has protocol
        ps_url = url if url.startswith('http') else f"https://{url}"
        
        params = {
            "url": ps_url,
            "key": PAGESPEED_API_KEY,
            "strategy": "desktop",  # Force Desktop Viewport
            "category": ["performance"],
            "screenshot": "true"
        }
        
        import requests
        response = requests.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", params=params, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            # Extract screenshot data
            lighthouse = data.get("lighthouseResult", {})
            audits = lighthouse.get("audits", {})
            screenshot_audit = audits.get("final-screenshot", {})
            details = screenshot_audit.get("details", {})
            base64_data = details.get("data", "")
            
            if base64_data:
                # PageSpeed returns "data:image/jpeg;base64,..." - perfect for us
                print(f"DEBUG: PageSpeed screenshot success ({len(base64_data)} chars)")
                return base64_data
            else:
                print("DEBUG: PageSpeed returned 200 but no screenshot data")
        else:
            print(f"DEBUG: PageSpeed API failed with status {response.status_code}: {response.text[:200]}")
            
    except Exception as e:
        print(f"ERROR PageSpeed fallback failed: {e}")

    # Method 3: DataForSEO API fallback
    print(f"DEBUG: Playwright failed, trying DataForSEO API fallback")
    try:
        from api.dataforseo_client import fetch_dataforseo_screenshot
        
        # Ensure URL has protocol for DataForSEO
        if not url.startswith('http'):
            url = f"https://{url}"
            
        screenshot_b64 = fetch_dataforseo_screenshot(url)
        
        if screenshot_b64:
            # DataForSEO returns plain base64, we need to add prefix
            # Check if prefix already exists (unlikely but safe)
            if screenshot_b64.startswith('data:image'):
                return screenshot_b64
            else:
                return f"data:image/jpeg;base64,{screenshot_b64}"
                
    except Exception as e:
        print(f"ERROR DataForSEO fallback failed: {e}")
    
    # Method 3: All failed - return None (slide will be skipped)
    print(f"WARNING: All screenshot methods failed for {url}")
    return None


if __name__ == "__main__":
    # Test the screenshot capture
    test_url = "https://example.com"
    print(f"\nTesting screenshot capture for: {test_url}")
    
    result = capture_screenshot_with_fallback(test_url)
    
    if result:
        print(f"SUCCESS: Screenshot captured ({len(result)} chars base64)")
    else:
        print("FAILED: Could not capture screenshot")
