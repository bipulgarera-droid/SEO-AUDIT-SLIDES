
import requests
import json
import base64

# URL of the local server
url = "http://localhost:3001/api/deep-audit/generate-slides"

# Payload mimicking the Frontend "Array" issue
# screenshots is a list, not a dict
payload = {
    "project_id": "2ab31fac-ce8e-4f8d-8681-e95ea3059fea",
    "screenshots": [
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    ],
    "issue_counts": {
        "titleTooLong": 0, "noDesc": 0
    }
}

try:
    print(f"Sending POST to {url} with LIST type screenshots...")
    resp = requests.post(url, json=payload, timeout=60)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")
    
except Exception as e:
    print(f"Request failed: {e}")
