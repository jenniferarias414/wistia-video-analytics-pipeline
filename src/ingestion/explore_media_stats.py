import json
import os
import sys
from pathlib import Path

import requests


MEDIA_ID = "8hunphufxp"
API_VERSION = "2026-07"

url = f"https://api.wistia.com/modern/stats/medias/{MEDIA_ID}"

api_token = os.getenv("WISTIA_API_TOKEN")

if not api_token:
    print("ERROR: WISTIA_API_TOKEN environment variable is not set.")
    sys.exit(1)

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

output_dir = Path("data/exploration")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / f"media_stats_{MEDIA_ID}.json"

with output_file.open("w", encoding="utf-8") as file:
    json.dump(payload, file, indent=2)

print(f"Saved raw response to: {output_file}")

if isinstance(payload, dict):
    print("Top-level JSON keys:")
    for key in payload.keys():
        print(f"  - {key}")
elif isinstance(payload, list):
    print(f"Response is a list containing {len(payload)} records.")
else:
    print(f"Unexpected response type: {type(payload).__name__}")
