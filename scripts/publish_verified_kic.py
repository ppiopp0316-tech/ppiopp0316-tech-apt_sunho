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
    end = today + dt.timedelta(days=366)
    for n, row in enumerate(rows, 2):
        if row["검증상태"].strip() != "공식확인":
            errors.append(f"{n}행: 공식확인만 공개할 수 있습니다.")
        move_raw = row["입주시작일"].strip()
        completion_raw = row["준공예정일"].strip()
        move_in = None
        completion = None
        try:
            if move_raw and move_raw not in {"미확인", "미정", "-"}:
                move_in = dt.date.fromisoformat(move_raw)
            if completion_raw and completion_raw not in {"미확인", "미정", "-"}:
                completion = dt.date.fromisoformat(completion_raw)
        except ValueError:
            errors.append(f"{n}행: 날짜 형식이 잘못되었습니다.")
        target_date = move_in or completion
        if target_date is None or not today <= target_date <= end:
            errors.append(f"{n}행: 입주시작일 또는 준공예정일이 향후 12개월 범위여야 합니다.")
        if not row["공식출처"].strip() or not row["최근확인"].strip():
            errors.append(f"{n}행: 공식출처와 최근확인이 필요합니다.")
    if errors:
        for error in errors:
            print("REJECTED:", error)
        return 1
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
