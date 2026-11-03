
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

API_URL = "https://api.data.go.kr/openapi/tn_pubr_public_med_office_api"
PAGE_SIZE = 1000
MIN_ROWS = 50000

COLUMN_MAP = {
    "medOfficeNm": "중개사무소명",
    "estblRegNo": "개설등록번호",
    "rprsvNm": "대표자명",
    "telno": "전화번호",
    "estblRegYmd": "개설등록일자",
    "lctnRoadNmAddr": "소재지도로명주소",
    "lctnLotnoAddr": "소재지지번주소",
    "opbizLreaClscSe": "개업공인중개사종별구분",
    "latitude": "위도",
    "longitude": "경도",
    "crtrYmd": "데이터기준일자",
}

def main():
    key = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
    if not key:
        raise RuntimeError("API 인증키가 없습니다.")

    session = requests.Session()
    rows = []
    total = None

    for page in range(1, 1001):
        response = session.get(
            API_URL,
            params={
                "serviceKey": unquote(key),
                "pageNo": page,
                "numOfRows": PAGE_SIZE,
                "type": "json",
            },
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()

        body = data.get("body")
        if body is None:
            body = data.get("response", {}).get("body")

        if not isinstance(body, dict):
            raise RuntimeError("API 응답 구조가 올바르지 않습니다.")

        if total is None:
            total = int(body.get("totalCount", 0))
            print(f"API 전체 건수: {total:,}건")
            if total < MIN_ROWS:
                raise RuntimeError("전체 건수가 안전 기준보다 적습니다.")

        batch = body.get("items", [])
        if isinstance(batch, dict):
            batch = batch.get("item", [])

        if not isinstance(batch, list) or not batch:
            raise RuntimeError(f"{page}페이지 데이터가 비어 있습니다.")

        rows.extend(batch)
        print(f"{page}페이지 완료 / 누적 {len(rows):,}건")

        if len(rows) >= total:
            break
    else:
        raise RuntimeError("최대 페이지 수를 초과했습니다.")

    if len(rows) != total:
        raise RuntimeError(
            f"전체 건수 불일치: {len(rows):,} / {total:,}"
        )

    df = pd.DataFrame(rows)

    required = [
        "medOfficeNm",
        "estblRegNo",
        "estblRegYmd",
        "lctnRoadNmAddr",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"필수 항목 누락: {missing}")

    df = df.rename(columns=COLUMN_MAP)

    for column in COLUMN_MAP.values():
        if column not in df.columns:
            df[column] = ""

    df = df.fillna("")

    names = df["중개사무소명"].astype(str).str.strip()
    if (names == "").any():
        raise RuntimeError("사무소명이 없는 데이터가 있습니다.")

    reg = df["개설등록번호"].astype(str).str.strip()
    if (reg == "").any():
        raise RuntimeError("등록번호가 없는 데이터가 있습니다.")

    duplicates = df[reg.duplicated(keep=False)].copy()

    if not duplicates.empty:
        print(f"중복 등록번호 관련 행: {len(duplicates):,}건")
        print(f"중복된 등록번호 종류: {reg[reg.duplicated(keep=False)].nunique():,}개")

        same_office = duplicates.groupby("개설등록번호").agg(
            사무소명수=("중개사무소명", "nunique"),
            주소수=("소재지도로명주소", "nunique"),
        )
        conflicts = same_office[
            (same_office["사무소명수"] > 1)
            | (same_office["주소수"] > 1)
        ]

        print(f"사무소명 또는 주소가 다른 등록번호: {len(conflicts):,}개")
        raise RuntimeError("중복 진단 완료. 기존 DB는 변경하지 않았습니다.")

    if OUTPUT.exists():
        with gzip.open(OUTPUT, "rt", encoding="utf-8-sig") as f:
            previous_count = sum(1 for _ in f) - 1

        if previous_count > 0 and len(df) < previous_count * 0.9:
            raise RuntimeError(
                "기존 DB 대비 데이터가 10% 넘게 감소했습니다."
            )

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)

    compressed = gzip.compress(
        buffer.getvalue().encode("utf-8-sig"),
        mtime=0,
    )

    metadata = {
        "source": "전국공인중개사사무소표준데이터",
        "url": API_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "raw_rows": len(df),
        "api_total_count": total,
        "columns": list(df.columns),
    }

    temp_output = OUTPUT.with_name(OUTPUT.name + ".tmp")
    temp_meta = META.with_name(META.name + ".tmp")

    temp_output.write_bytes(compressed)
    temp_meta.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    temp_output.replace(OUTPUT)
    temp_meta.replace(META)

    print(f"전체 수집 및 저장 완료: {len(df):,}건")


if __name__ == "__main__":
    main()
