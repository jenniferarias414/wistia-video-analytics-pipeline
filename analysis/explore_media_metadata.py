import json
import os
import sys
from pathlib import Path

import requests


API_VERSION = "2026-07"
MEDIA_IDS = [
    "8hunphufxp",
    "9k4tbcdfg0",
]
URL = "https://api.wistia.com/modern/medias"

api_token = os.getenv("WISTIA_API_TOKEN")

if not api_token:
    print("ERROR: WISTIA_API_TOKEN environment variable is not set.")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {api_token}",
    "X-Wistia-API-Version": API_VERSION,
}

params = [
    ("hashed_ids[]", media_id)
    for media_id in MEDIA_IDS
]

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

output_file = output_dir / "media_metadata.json"
output_file.write_text(json.dumps(payload, indent=2))

print(f"Saved raw response to: {output_file}")

print("\n----- MEDIA METADATA STRUCTURE -----")
print(f"Top-level type: {type(payload).__name__}")

if isinstance(payload, list):
    print(f"Records returned: {len(payload)}")

    if payload and isinstance(payload[0], dict):
        print("Media fields:")
        for key, value in payload[0].items():
            print(f"  - {key}: {type(value).__name__}")

elif isinstance(payload, dict):
    print("Top-level fields:")
    for key, value in payload.items():
        print(f"  - {key}: {type(value).__name__}")
