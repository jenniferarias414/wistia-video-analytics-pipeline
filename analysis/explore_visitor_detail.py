import json
import os
import sys
from pathlib import Path

import requests


API_VERSION = "2026-05"
VISITORS_FILE = Path("data/exploration/visitors_page_1.json")

api_token = os.getenv("WISTIA_API_TOKEN")

if not api_token:
    print("ERROR: WISTIA_API_TOKEN environment variable is not set.")
    sys.exit(1)

if not VISITORS_FILE.exists():
    print(f"ERROR: Expected file not found: {VISITORS_FILE}")
    sys.exit(1)

visitors = json.loads(VISITORS_FILE.read_text())

if not visitors:
    print("ERROR: Visitor list is empty.")
    sys.exit(1)

visitor_key = visitors[0].get("visitor_key")

if not visitor_key:
    print("ERROR: First visitor record does not contain visitor_key.")
    sys.exit(1)

url = f"https://api.wistia.com/modern/stats/visitors/{visitor_key}"

headers = {
    "Authorization": f"Bearer {api_token}",
    "X-Wistia-API-Version": API_VERSION,
}

try:
    response = requests.get(url, headers=headers, timeout=30)
except requests.RequestException as exc:
    print(f"Request failed: {exc}")
    sys.exit(1)

print(f"HTTP status: {response.status_code}")

if response.status_code != 200:
    print("Wistia request was not successful.")
    print(response.text[:500])
    sys.exit(1)

payload = response.json()

output_file = Path("data/exploration/visitor_detail_sample.json")
output_file.write_text(json.dumps(payload, indent=2))

print(f"Saved detailed response to: {output_file}")

print("\n----- VISITOR DETAIL STRUCTURE -----")
print(f"Top-level type: {type(payload).__name__}")

if isinstance(payload, dict):
    for key, value in payload.items():
        if isinstance(value, list):
            print(f"{key}: list with {len(value)} items")
            if value and isinstance(value[0], dict):
                print("  first item fields:")
                for item_key in value[0].keys():
                    print(f"    - {item_key}")

        elif isinstance(value, dict):
            print(f"{key}: dict with fields:")
            for item_key in value.keys():
                print(f"  - {item_key}")

        else:
            print(f"{key}: {type(value).__name__}")
