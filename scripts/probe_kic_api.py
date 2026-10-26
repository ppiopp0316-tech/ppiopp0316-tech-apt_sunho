"""Probe the approved BuildingHUB permit API without publishing unverified data."""
import os
import sys
import requests

URL = "https://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo"

def main():
    key = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_API_KEY is missing", file=sys.stderr)
        return 2
    params = {
        "serviceKey": key,
        "sigunguCd": "11545",
        "bjdongCd": "10300",
        "numOfRows": "1",
        "pageNo": "1",
        "_type": "json",
    }
    try:
        response = requests.get(URL, params=params, timeout=35)
        response.raise_for_status()
        body = response.text
        if any(s in body for s in ("SERVICE_KEY_IS_NOT_REGISTERED", "SERVICE_ACCESS_DENIED", "SERVICE_KEY_IS_NULL", "PERMISSION_DENIED", "NO_OPENAPI_SERVICE_ERROR")):
            print("API returned an authorization or service error", file=sys.stderr)
            return 1
        if not any(s in body for s in ('"response"', "<response", '"header"', "<header")):
            print("Unexpected API response (not printing raw body to protect secrets)", file=sys.stderr)
            return 1
        print("BuildingHUB permit API responded with a recognized envelope.")
        print("No records published: nationwide classification and occupancy verification pending.")
        return 0
    except requests.RequestException as exc:
        print(f"API connection failed: {type(exc).__name__}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
