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
            # Launch headless browser with sandbox disabled (critical for Railway/Docker)
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
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
        print("ERROR: Playwright not installed. Check requirements.txt.")
        return None
    except Exception as e:
        error_msg = str(e)
        if "Executable doesn't exist" in error_msg:
            print(f"ERROR: Chromium not found. Playwright installation might be incomplete on this environment. Details: {error_msg}")
        else:
            print(f"ERROR capturing screenshot with Playwright: {e}")
        return None


def capture_screenshot_with_fallback(url: str) -> Optional[str]:
    """
    Capture screenshot with fallback chain:
    1. Try Playwright (best quality)
    2. Try PageSpeed API (fallback)
    3. Return None (graceful skip)
    
    Args:
        url: The URL to screenshot
        
    Returns:
        Base64 encoded image string, or None if all methods fail
    """
    # Method 1: Playwright (best quality)
    print(f"DEBUG: Attempting HIGH-QUALITY Playwright screenshot for {url}")
    result = capture_website_screenshot(url)
    if result:
        print(f"SUCCESS: Playwright capture successful for {url}")
        return result
    
    # Method 2: DataForSEO API Fallback (High Quality)
    print(f"WARNING: Playwright failed for {url}, attempting DataForSEO fallback")
    try:
        from api.dataforseo_client import capture_screenshot_via_dataforseo
        import requests
        
        image_url = capture_screenshot_via_dataforseo(url)
        if image_url:
            # Fetch the image content to convert to base64
            # DataForSEO returns a URL to the image file
            print(f"DEBUG: Fetching image from {image_url}")
            img_resp = requests.get(image_url, timeout=30)
            if img_resp.status_code == 200:
                img_b64 = base64.b64encode(img_resp.content).decode()
                # DataForSEO usually returns PNG or JPG, we can default to jpg/png
                # The browser preset 'desktop_chrome' usually implies standard format.
                return f"data:image/png;base64,{img_b64}"
            else:
                print(f"ERROR: Failed to download DataForSEO image: {img_resp.status_code}")
    except Exception as e:
        print(f"ERROR DataForSEO fallback failed for {url}: {e}")
    
    # Method 3: All failed - return None (slide will be skipped)
    print(f"CRITICAL: All screenshot methods failed for {url}")
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
