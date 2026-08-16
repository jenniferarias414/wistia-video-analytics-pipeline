import json
import os
import sys
from pathlib import Path

import requests


API_VERSION = "2026-07"
url = "https://api.wistia.com/modern/stats/visitors"

api_token = os.getenv("WISTIA_API_TOKEN")

if not api_token:
    print("ERROR: WISTIA_API_TOKEN environment variable is not set.")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {api_token}",
    "X-Wistia-API-Version": API_VERSION,
}

params = {
    "page": 1,
    "per_page": 5,
}

try:
    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30,
    )
except requests.RequestException as exc:
    print(f"Request failed: {exc}")
    sys.exit(1)

print(f"HTTP status: {response.status_code}")

if response.status_code != 200:
    print("Wistia request was not successful.")
    print(response.text[:500])
    sys.exit(1)

payload = response.json()

output_dir = Path("data/exploration")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "visitors_page_1.json"

with output_file.open("w", encoding="utf-8") as file:
    json.dump(payload, file, indent=2)

print(f"Saved raw response to: {output_file}")

print("\n----- RESPONSE STRUCTURE -----")
print(f"Top-level type: {type(payload).__name__}")

if isinstance(payload, list):
    print(f"Records returned: {len(payload)}")

    if payload and isinstance(payload[0], dict):
        print("Visitor fields:")
        for key in payload[0].keys():
            print(f"  - {key}")

elif isinstance(payload, dict):
    print("Top-level fields:")

    for key, value in payload.items():
        print(f"  - {key}: {type(value).__name__}")

        if isinstance(value, list):
            print(f"    records: {len(value)}")

            if value and isinstance(value[0], dict):
                print("    first record fields:")
                for item_key in value[0].keys():
                    print(f"      - {item_key}")
