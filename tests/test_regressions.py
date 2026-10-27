import csv
import datetime as dt
import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from db_common import (KIC_COLUMNS, add_months, classify_kic, date_bounds,
                       filter_apartments, prepare_kic, naver_search_url)
from validate_kic import check


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.today = dt.date(2026, 10, 27)
        self.row = dict.fromkeys(KIC_COLUMNS, '미확인')
        self.row.update({'센터명': '센터A', '주소': '경기도 안양시 주소', '시도': '경기도',
                         '사업상태': '공사 중', '준공예정일': '2027-03',
                         '공식출처': '시행사 공시', '출처URL': 'https://example.gov.kr/source',
                         '최근확인': '2026-10-27', '검증상태': '준공예정 공식 확인 · 입주시작일 미확인'})

    def test_month_precision_is_not_a_fake_day(self):
        self.assertEqual(date_bounds('2026-10'), (dt.date(2026, 10, 1), dt.date(2026, 10, 31)))
        self.row['준공예정일'] = '2026-10'
        self.assertEqual(classify_kic(self.row, self.today), '준공 예정 · 입주일 미확인')

    def test_invalid_date(self):
        for value in ('2027-13', '2027-02-29', '2027.03', '2027-3'):
            with self.assertRaises(ValueError):
                date_bounds(value)

    def test_calendar_horizon(self):
        self.assertEqual(add_months(dt.date(2024, 2, 29), 12), dt.date(2025, 2, 28))
        self.assertEqual(add_months(self.today, 12), dt.date(2027, 10, 27))

    def test_occupancy_and_completion_are_distinct(self):
        self.assertEqual(classify_kic(self.row, self.today), '준공 예정 · 입주일 미확인')
        self.row['입주시작일'] = '2027-04-15'
        self.assertEqual(classify_kic(self.row, self.today), '입주 예정')

    def test_outside_horizon_not_unknown_candidate(self):
        self.row['준공예정일'] = '2028-01'
        self.assertEqual(classify_kic(self.row, self.today), '기간 외·완료')

    def test_unknown_and_past_completion(self):
        self.row['준공예정일'] = '미확인'
        self.assertEqual(classify_kic(self.row, self.today), '공사 중 · 일정 미확인')
        self.row['사용승인일'] = '2025-01-01'
        self.assertEqual(classify_kic(self.row, self.today), '기간 외·완료')

    def test_completed_with_official_future_movein(self):
        self.row.update({'사업상태': '준공완료', '사용승인일': '2026-09-30', '입주시작일': '2026-11-01'})
        self.assertEqual(classify_kic(self.row, self.today), '입주 예정')

    def test_real_csv_schema_and_month_validation(self):
        rows, errors = check(ROOT / 'knowledge_industry_centers.csv', self.today)
        self.assertFalse(errors, errors)
        self.assertEqual(list(rows[0]), KIC_COLUMNS)

    def test_mixed_date_precision(self):
        a, b = self.row.copy(), self.row.copy()
        b['센터명'], b['주소'], b['준공예정일'] = '센터B', '주소B', '2027-04-15'
        frame = prepare_kic(pd.DataFrame([a, b]), self.today)
        self.assertTrue(frame['준공예정일_dt'].notna().all())

    def test_apartment_filters_combine_and_literal_keywords(self):
        frame = pd.DataFrame([
            {'시도':'경기','입주예정월':'2027-03','세대수':1000,'단지명':'테스트[1]','주소':'안양','시공사':'DL'},
            {'시도':'서울특별시','입주예정월':'2027-03','세대수':500,'단지명':'테스트','주소':'서울','시공사':'DL'},
            {'시도':'경기도','입주예정월':'2027-04','세대수':100,'단지명':'소규모','주소':'경기','시공사':'DL'}])
        result = filter_apartments(frame, '경기도', '2027', '03', 900, '[1]')
        self.assertEqual(result['단지명'].tolist(), ['테스트[1]'])
        self.assertTrue(filter_apartments(frame, keyword='없는값').empty)

    def test_search_is_query_not_fragment(self):
        url = urlparse(naver_search_url('테스트 & 단지', '경기도', '안양시'))
        self.assertEqual(url.fragment, '')
        self.assertEqual(parse_qs(url.query)['query'], ['경기도 안양시 테스트 & 단지'])

    def test_publisher_merges_instead_of_deleting_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            target, reviewed = Path(directory) / 'target.csv', Path(directory) / 'reviewed.csv'
            old = self.row.copy()
            old['센터명'], old['주소'] = '보존할 과거 센터', '보존주소'
            fresh = self.row.copy()
            fresh['준공예정일'] = '2027-03'
            for path, rows in ((target, [old]), (reviewed, [fresh])):
                with path.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, KIC_COLUMNS)
                    writer.writeheader(); writer.writerows(rows)
            process = subprocess.run([sys.executable, str(ROOT / 'scripts/publish_verified_kic.py'), '--reviewed', str(reviewed), '--target', str(target)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            with target.open(encoding='utf-8-sig') as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 2)
            before = target.read_bytes()
            reviewed.write_text(','.join(KIC_COLUMNS) + '\n', encoding='utf-8-sig')
            process = subprocess.run([sys.executable, str(ROOT / 'scripts/publish_verified_kic.py'), '--reviewed', str(reviewed), '--target', str(target)], capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(before, target.read_bytes())

    def test_protected_source_data_unchanged(self):
        for name in ('managed_offices.csv', 'knowledge_industry_centers.csv', 'broker_offices.csv.gz', 'supplemental_verified.csv', 'naver_rankings.json', 'naver_rank_extension_20261015.json', 'naver_rank_extension_20261016.json'):
            original = subprocess.check_output(['git', 'show', '153a9b22ef4d4ef2178351437c0c09ff48f924fc:' + name], cwd=ROOT)
            self.assertEqual(hashlib.sha256(original).hexdigest(), hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), name)


if __name__ == '__main__':
    unittest.main()
