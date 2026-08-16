import json
import os
import sys
from pathlib import Path

import requests


API_VERSION = "2026-07"
VISITOR_DETAIL_FILE = Path("data/exploration/visitor_detail_sample.json")

api_token = os.getenv("WISTIA_API_TOKEN")

if not api_token:
    print("ERROR: WISTIA_API_TOKEN environment variable is not set.")
    sys.exit(1)

if not VISITOR_DETAIL_FILE.exists():
    print(f"ERROR: Expected file not found: {VISITOR_DETAIL_FILE}")
    sys.exit(1)

visitor = json.loads(VISITOR_DETAIL_FILE.read_text())

event_key = visitor.get("last_event_key")

if not event_key:
    print("ERROR: Visitor record does not contain last_event_key.")
    sys.exit(1)

url = f"https://api.wistia.com/modern/stats/events/{event_key}"

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

output_file = Path("data/exploration/event_detail_sample.json")
output_file.write_text(json.dumps(payload, indent=2))

print(f"Saved detailed response to: {output_file}")

print("\n----- EVENT DETAIL STRUCTURE -----")
print(f"Top-level type: {type(payload).__name__}")

if isinstance(payload, dict):
    for key, value in payload.items():
        if isinstance(value, dict):
            print(f"{key}: dict with fields:")
            for nested_key, nested_value in value.items():
                print(f"  - {nested_key}: {type(nested_value).__name__}")

        elif isinstance(value, list):
            print(f"{key}: list with {len(value)} items")
            if value:
                print(f"  first item type: {type(value[0]).__name__}")
                if isinstance(value[0], dict):
                    print("  first item fields:")
                    for nested_key in value[0].keys():
                        print(f"    - {nested_key}")

        else:
            print(f"{key}: {type(value).__name__}")
