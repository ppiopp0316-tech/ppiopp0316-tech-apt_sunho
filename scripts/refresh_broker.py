
import os
from urllib.parse import unquote

import requests

API_URL = "https://api.data.go.kr/openapi/tn_pubr_public_med_office_api"


def main():
    key = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GitHub API 인증키가 없습니다.")

    params = {
        "serviceKey": unquote(key),
        "pageNo": 1,
        "numOfRows": 10,
        "type": "json",
    }

    response = requests.get(API_URL, params=params, timeout=60)
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            "JSON 응답이 아닙니다: " + response.text[:300]
        )

    if not isinstance(data, dict):
        raise RuntimeError("예상하지 못한 API 응답입니다.")

    print("API 응답 최상위 항목:", list(data.keys()))

    body = data.get("body", {})
    if not body:
        body = data.get("response", {}).get("body", {})

    print("API 전체 건수:", body.get("totalCount", "미확인"))

    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", [])

    if isinstance(items, list) and items:
        print("첫 번째 데이터의 항목명:", list(items[0].keys()))
        print("조회된 샘플 건수:", len(items))
    else:
        print("데이터 목록 구조:", type(items).__name__)

    print("진단 완료: 기존 DB 파일은 변경하지 않았습니다.")


if __name__ == "__main__":
    main()
