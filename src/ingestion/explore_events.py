import json
import os
import sys
from pathlib import Path

import requests


API_VERSION = "2026-07"
MEDIA_ID = "8hunphufxp"
URL = "https://api.wistia.com/modern/stats/events"

api_token = os.getenv("WISTIA_API_TOKEN")

if not api_token:
    print("ERROR: WISTIA_API_TOKEN environment variable is not set.")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {api_token}",
    "X-Wistia-API-Version": API_VERSION,
}

params = {
    "media_id": MEDIA_ID,
    "page": 1,
    "per_page": 5,
}

try:
    response = requests.get(
        URL,
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

output_file = output_dir / f"events_{MEDIA_ID}_page_1.json"
output_file.write_text(json.dumps(payload, indent=2))

print(f"Saved raw response to: {output_file}")

print("\n----- EVENT LIST STRUCTURE -----")
print(f"Top-level type: {type(payload).__name__}")

if isinstance(payload, list):
    print(f"Records returned: {len(payload)}")

    if payload and isinstance(payload[0], dict):
        print("Event fields:")
        for key, value in payload[0].items():
            print(f"  - {key}: {type(value).__name__}")

elif isinstance(payload, dict):
    print("Top-level fields:")
    for key, value in payload.items():
        print(f"  - {key}: {type(value).__name__}")
