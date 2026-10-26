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
        if response.status_code >= 400:
            print(f"API HTTP status: {response.status_code}", file=sys.stderr)
            print("API returned an HTTP error; credentials and response body are hidden.", file=sys.stderr)
            return 1
        body = response.text
        if any(s in body for s in ("SERVICE_KEY_IS_NOT_REGISTERED", "SERVICE_ACCESS_DENIED", "SERVICE_KEY_IS_NULL", "PERMISSION_DENIED", "NO_OPENAPI_SERVICE_ERROR")):
            print("API returned an authorization or service error", file=sys.stderr)
            return 1
        if not any(s in body for s in ('"response"', "<response", '"header"', "<header")):
            print("Unexpected API response (not printing raw body to protect secrets)", file=sys.stderr)
            return 1
        import xml.etree.ElementTree as ET
        if body.lstrip().startswith("<"):
            root = ET.fromstring(body)
            code = root.findtext(".//resultCode")
            if code and code not in {"00", "000", "NORMAL_SERVICE"}:
                print(f"API returned error code: {code}", file=sys.stderr)
                return 1
        else:
            data = response.json()
            code = str(data.get("response", {}).get("header", {}).get("resultCode", ""))
            if code and code not in {"00", "000", "NORMAL_SERVICE"}:
                print(f"API returned error code: {code}", file=sys.stderr)
                return 1
        print("BuildingHUB permit API responded with a successful envelope.")
        print("No records published: nationwide classification and occupancy verification pending.")
        return 0
    except requests.RequestException as exc:
        print(f"API connection failed: {type(exc).__name__}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
