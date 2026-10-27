"""Validate a prospective knowledge-industry-center CSV without altering the live DB.

Usage: python scripts/validate_kic.py path/to/candidate.csv
Exit 0 only if the input schema is valid. This is a staging safety check,
not an API downloader or a claim that occupancy dates were verified.
"""
import argparse
import csv
import datetime as dt
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db_common import date_bounds, classify_kic

COLUMNS = [
    "센터명", "시도", "시군구", "주소", "사업상태", "허가일", "착공일",
    "준공예정일", "사용승인일", "입주시작일", "시행사", "시공사",
    "연락처", "공식출처", "출처URL", "최근확인", "검증상태",
]
DATE_COLUMNS = ("허가일", "착공일", "준공예정일", "사용승인일", "입주시작일", "최근확인")
EMPTY = {"", "미확인", "확인중", "미정", "-"}


def check(path: Path, today: dt.date) -> tuple[list[dict], list[str]]:
    errors = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            return [], ["CSV 헤더가 사이트 DB의 17개 필드와 일치하지 않습니다."]
        rows = list(reader)
    if not rows:
        return [], ["실제 센터 데이터가 0건입니다. 기존 DB를 덮어쓰지 않습니다."]
    seen = set()
    accepted = []
    for number, row in enumerate(rows, 2):
        prefix = f"{number}행"
        if None in row or any(v is None for v in row.values()):
            errors.append(f"{prefix}: 열 개수가 맞지 않습니다.")
            continue
        if not row["센터명"].strip() or not row["주소"].strip():
            errors.append(f"{prefix}: 센터명과 주소는 필수입니다.")
        identity = (row["센터명"].strip(), row["주소"].strip())
        if identity in seen:
            errors.append(f"{prefix}: 센터명+주소 중복입니다.")
        seen.add(identity)
        parsed = {}
        for field in DATE_COLUMNS:
            value = row[field].strip()
            if value in EMPTY:
                continue
            try:
                parsed[field] = date_bounds(value)
            except ValueError:
                errors.append(f"{prefix}: {field}은 YYYY-MM, YYYY-MM-DD 또는 미확인으로 입력하세요.")
        if not row["출처URL"].strip().startswith(("https://", "http://")):
            errors.append(f"{prefix}: 확인 가능한 출처URL이 필요합니다.")
        if row["검증상태"].strip() not in {"공식확인", "추가확인필요", "준공예정 공식 확인 · 입주시작일 미확인"}:
            errors.append(f"{prefix}: 검증상태가 허용된 검증 구분과 일치하지 않습니다.")
        if classify_kic(row, today) == '기간 외·완료':
            errors.append(f"{prefix}: 향후 입주·준공 대상 또는 일정 미확인 공사 후보가 아닙니다.")
        accepted.append(row)
    return accepted, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    rows, errors = check(args.csv_path, dt.date.today())
    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        return 1
    print(f"Schema and basic dates passed: {len(rows)} rows.")
    print("주의: 공식 출처의 진위와 실제 입주예정일은 별도 검증이 필요합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
