"""Read BuildingHUB permit responses and extract *unverified* center candidates.

Building permits do not provide reliable occupancy start dates. Output is an
inspection report only, never a replacement for knowledge_industry_centers.csv.
"""
import argparse
import csv
import datetime as dt
import os
import sys
import xml.etree.ElementTree as ET

import requests

URL = "https://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo"
KEYWORDS = ("지식산업센터", "아파트형공장", "지식산업", "비즈밸리")
HEADERS = ("건축물명", "주소", "시군구코드", "법정동코드", "인허가일", "API출처", "조회일")


def fetch(sigungu: str, bjdong: str, key: str, pages: int):
    for page in range(1, pages + 1):
        response = requests.get(
            URL,
            params={"serviceKey": key, "sigunguCd": sigungu, "bjdongCd": bjdong,
                    "pageNo": page, "numOfRows": 100, "_type": "xml"},
            timeout=40,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        code = root.findtext(".//resultCode", "")
        if code not in ("", "00", "000", "NORMAL_SERVICE"):
            raise RuntimeError(f"BuildingHUB error code: {code}")
        items = root.findall(".//item")
        for item in items:
            yield {child.tag: (child.text or "").strip() for child in item}
        if len(items) < 100:
            break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region-file", required=True, help="CSV with sigunguCd,bjdongCd (official legal-dong codes)")
    parser.add_argument("--output", default="kic_api_candidates.csv")
    parser.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()
    key = os.getenv("DATA_GO_KR_API_KEY", "").strip()
    if not key:
        sys.exit("DATA_GO_KR_API_KEY is missing")
    if args.max_pages < 1 or args.max_pages > 100:
        sys.exit("--max-pages must be between 1 and 100")
    with open(args.region_file, encoding="utf-8-sig", newline="") as file:
        regions = list(csv.DictReader(file))
    if not regions or not all(row.get("sigunguCd") and row.get("bjdongCd") for row in regions):
        sys.exit("region-file must contain sigunguCd,bjdongCd for every row")
    rows = []
    seen = set()
    for region in regions:
        sigungu, bjdong = region["sigunguCd"].strip(), region["bjdongCd"].strip()
        if not (sigungu.isdigit() and len(sigungu) == 5 and bjdong.isdigit() and len(bjdong) == 5):
            sys.exit("Invalid official region code")
        for item in fetch(sigungu, bjdong, key, args.max_pages):
            name = item.get("bldNm") or item.get("bldgNm") or ""
            if not any(term in name for term in KEYWORDS):
                continue
            address = item.get("platPlc") or item.get("newPlatPlc") or ""
            identity = (sigungu, bjdong, name, address)
            if identity in seen:
                continue
            seen.add(identity)
            rows.append({
                "건축물명": name, "주소": address, "시군구코드": sigungu,
                "법정동코드": bjdong, "인허가일": item.get("pmsDay", ""),
                "API출처": URL, "조회일": dt.date.today().isoformat(),
            })
    with open(args.output, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Unverified permit candidates: {len(rows)}. Not published to live DB.")


if __name__ == "__main__":
    main()
