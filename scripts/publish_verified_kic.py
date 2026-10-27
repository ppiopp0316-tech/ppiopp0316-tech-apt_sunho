"""Publish reviewed, officially evidenced future knowledge-industry-center move-ins only.

Building permits alone do not verify knowledge-industry-center identity or move-in dates.
Missing/empty/unverified input NEVER replaces the published database.
"""
import argparse
import csv
import datetime as dt
import os
import tempfile
from pathlib import Path
from validate_kic import COLUMNS, check
from db_common import date_bounds, classify_kic

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewed", type=Path, default=Path("reviewed_kic.csv"))
    parser.add_argument("--target", type=Path, default=Path("knowledge_industry_centers.csv"))
    args = parser.parse_args()
    if not args.reviewed.is_file():
        print("No reviewed evidence CSV: keeping existing database.")
        return 0
    today = dt.date.today()
    rows, errors = check(args.reviewed, today)

    for n, row in enumerate(rows, 2):
        if row["검증상태"].strip() not in {"공식확인", "준공예정 공식 확인 · 입주시작일 미확인"}:
            errors.append(f"{n}행: 공식 근거 검토가 완료된 자료만 게시할 수 있습니다.")
        if classify_kic(row, today) not in {'입주 예정', '준공 예정 · 입주일 미확인'}:
            errors.append(f"{n}행: 향후 12개월에 해당하는 입주·준공 일정이 필요합니다.")
        if not row["공식출처"].strip() or not row["최근확인"].strip():
            errors.append(f"{n}행: 공식출처와 최근확인이 필요합니다.")
    if errors:
        for error in errors:
            print("REJECTED:", error)
        return 1
    # Upsert reviewed identities; never discard older records absent from this batch.
    existing = []
    if args.target.exists():
        with args.target.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != COLUMNS:
                print('REJECTED: target schema mismatch; original kept.')
                return 1
            existing = list(reader)
    merged = {(r['센터명'].strip(), r['주소'].strip()): r for r in existing}
    for row in rows:
        merged[(row['센터명'].strip(), row['주소'].strip())] = row
    rows = list(merged.values())
    args.target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".kic-", suffix=".csv", dir=args.target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, args.target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"Published {len(rows)} verified records.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
