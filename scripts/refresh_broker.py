
import gzip
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "broker_offices.csv.gz"
META = ROOT / "broker_source_meta.json"

API_URL = (
    "https://api.odcloud.kr/api/15063946/v1/"
    "uddi:fec486df-cac3-4f90-8a0d-f87a694112f9"
)

PAGE_SIZE = 1000
MAX_PAGES = 1000
MIN_ROWS = 1000

def main():
    key = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GitHub API 인증키가 없습니다.")

    key = unquote(key)
    session = requests.Session()
    rows = []
    total_count = None

    for page in range(1, MAX_PAGES + 1):
        response = session.get(
            API_URL,
            params={
                "serviceKey": key,
                "page": page,
                "perPage": PAGE_SIZE,
                "returnType": "JSON",
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise RuntimeError("예상하지 못한 API 응답입니다.")

        if payload.get("currentCount") is None:
            raise RuntimeError("API 응답의 건수를 확인할 수 없습니다.")

        batch = payload.get("data")
        if not isinstance(batch, list):
            raise RuntimeError("API 데이터 목록이 없습니다.")


if total_count is None:
    total_count = int(payload.get("totalCount", 0))
    print(f"API 전체 건수: {total_count:,}건")
    if total_count < MIN_ROWS:
        raise RuntimeError("전체 데이터 건수가 너무 적습니다.")


        rows.extend(batch)
        print(f"페이지 {page}: {len(batch)}건 수집")

        if len(rows) >= total_count:
            break

        if not batch:
            raise RuntimeError("전체 수집 완료 전 빈 페이지가 나왔습니다.")
    else:
        raise RuntimeError("최대 페이지 수를 초과했습니다.")

    if len(rows) != total_count:
        raise RuntimeError(
            f"수집 건수 불일치: {len(rows)} / {total_count}"
        )

    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError("수집된 데이터가 없습니다.")

    # 사이트가 사용하는 필수 컬럼이 있는지 확인합니다.
    office_columns = [
        "중개사무소명", "상호명", "사무소명",
        "office_name",
    ]
    if not any(col in df.columns for col in office_columns):
        raise RuntimeError(
            "중개사무소명 컬럼을 찾지 못했습니다. "
            f"실제 컬럼: {list(df.columns)}"
        )

    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)

    compressed = gzip.compress(
        csv_buffer.getvalue().encode("utf-8-sig")
    )

    # 모든 검증을 통과한 경우에만 파일을 교체합니다.
    temp_output = OUTPUT.with_name(OUTPUT.name + ".tmp")
    temp_output.write_bytes(compressed)
    temp_output.replace(OUTPUT)

    metadata = {
        "source": "국토교통부_중개사무소 등록현황",
        "url": API_URL,
        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "raw_rows": len(df),
        "complete_nationwide": True,
        "api_total_count": total_count,
        "columns": list(df.columns),
    }

    temp_meta = META.with_name(META.name + ".tmp")
    temp_meta.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_meta.replace(META)

    print(f"수집 및 검증 완료: {len(df):,}건")

if __name__ == "__main__":
    main()
