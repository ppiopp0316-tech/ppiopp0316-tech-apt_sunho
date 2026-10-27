"""Shared, side-effect-free rules for Streamlit and the private Sites view."""
import calendar
import datetime as dt
import re
from urllib.parse import quote


SIDO_ALIASES = {
    '서울': '서울특별시', '부산': '부산광역시', '대구': '대구광역시',
    '인천': '인천광역시', '광주': '광주광역시', '대전': '대전광역시',
    '울산': '울산광역시', '세종': '세종특별자치시', '경기': '경기도',
    '강원': '강원특별자치도', '강원도': '강원특별자치도',
    '충북': '충청북도', '충남': '충청남도', '전북': '전북특별자치도',
    '전라북도': '전북특별자치도', '전남': '전라남도',
    '경북': '경상북도', '경남': '경상남도', '제주': '제주특별자치도',
    '제주도': '제주특별자치도',
}
SIDOS = ['서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시',
         '대전광역시', '울산광역시', '세종특별자치시', '경기도', '강원특별자치도',
         '충청북도', '충청남도', '전북특별자치도', '전라남도', '경상북도',
         '경상남도', '제주특별자치도']
UNKNOWN = {'', '미확인', '확인중', '미정', '-', 'nan', 'None', 'NaT'}
KIC_COLUMNS = ['센터명', '시도', '시군구', '주소', '사업상태', '허가일', '착공일',
               '준공예정일', '사용승인일', '입주시작일', '시행사', '시공사', '연락처',
               '공식출처', '출처URL', '최근확인', '검증상태']


def normalize_sido(value):
    value = str(value or '').strip()
    return SIDO_ALIASES.get(value, value)


def date_bounds(value):
    """Retain month precision; do not turn an unknown day into a claimed first day."""
    value = str(value or '').strip()
    if value in UNKNOWN:
        return None
    if re.fullmatch(r'\d{4}-\d{2}', value):
        year, month = map(int, value.split('-'))
        return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('YYYY-MM 또는 YYYY-MM-DD 형식이 필요합니다.')
    day = dt.date.fromisoformat(value)
    return day, day


def add_months(day, months):
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def classify_kic(row, today=None):
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    end = add_months(today, 12)
    def bounds(col):
        try:
            return date_bounds(row.get(col, ''))
        except ValueError:
            return None
    move, completion, approved = (bounds(c) for c in ('입주시작일', '준공예정일', '사용승인일'))
    def overlaps(pair):
        return pair is not None and pair[1] >= today and pair[0] <= end
    if move:
        return '입주 예정' if overlaps(move) else '기간 외·완료'
    if re.search('입주완료|준공완료|사용승인완료', str(row.get('사업상태', ''))):
        return '기간 외·완료'
    if approved and approved[1] < today:
        return '기간 외·완료'
    if completion:
        return '준공 예정 · 입주일 미확인' if overlaps(completion) else '기간 외·완료'
    if re.search('공사|착공|건설|허가', str(row.get('사업상태', ''))):
        return '공사 중 · 일정 미확인'
    return '기간 외·완료'


def prepare_kic(frame, today=None):
    import pandas as pd
    frame = frame.copy()
    for column in KIC_COLUMNS:
        if column not in frame:
            frame[column] = ''
    frame = frame[KIC_COLUMNS].fillna('')
    frame['시도'] = frame['시도'].map(normalize_sido)
    frame['구분'] = frame.apply(lambda row: classify_kic(row, today), axis=1) if len(frame) else pd.Series(dtype=str)
    for column in ('입주시작일', '준공예정일'):
        frame[column + '_dt'] = pd.to_datetime(frame[column], errors='coerce', format='mixed')
    frame['일정월'] = frame['입주시작일'].where(~frame['입주시작일'].isin(UNKNOWN), frame['준공예정일']).str[:7]
    return frame


def filter_apartments(frame, sido='전체', year='전체', month='전체', minimum=300, keyword=''):
    import pandas as pd
    out = frame[pd.to_numeric(frame['세대수'], errors='coerce').fillna(0) >= minimum].copy()
    if sido != '전체':
        out = out[out['시도'].map(normalize_sido).eq(normalize_sido(sido))]
    if year != '전체':
        out = out[out['입주예정월'].str[:4].eq(str(year))]
    if month != '전체':
        out = out[out['입주예정월'].str[5:7].eq(str(month).zfill(2))]
    if keyword.strip():
        out = out[out[['단지명', '주소', '시공사']].fillna('').astype(str).apply(
            lambda c: c.str.contains(keyword.strip(), case=False, regex=False)).any(axis=1)]
    return out


def naver_search_url(name, sido='', sigungu=''):
    query = ' '.join(x for x in (sido, sigungu, name) if str(x).strip())
    return 'https://land.naver.com/search/complex.nhn?query=' + quote(query, safe='')
