import io, re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote, quote
import pandas as pd
import requests
import streamlit as st

BASE_DIR = Path(__file__).parent
SUPPLEMENT_PATH = BASE_DIR / 'supplemental_verified.csv'
BROKER_LOCAL_PATH = BASE_DIR / 'broker_offices.csv'
APPLYHOME_API = 'https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail'
LH_URL = 'https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?mi=1042&sUppAisTpCd=06'

st.set_page_config(page_title='전국입주 DB', page_icon='🏢', layout='wide')
st.markdown('''
<style>
.block-container{padding-top:1rem}.apt-card,.broker-card{border:1px solid rgba(128,128,128,.25);border-radius:14px;padding:14px;margin-bottom:12px}.movein{font-size:1.08rem;font-weight:800}.apt-name,.broker-name{font-size:1.05rem;font-weight:700;margin:4px 0 8px}.meta{font-size:.92rem;line-height:1.65}.hot{font-weight:800}.source-box{padding:.7rem 1rem;border-radius:12px;border:1px solid rgba(128,128,128,.25);margin:.3rem 0 1rem}
@media(max-width:768px){.block-container{padding-left:.7rem;padding-right:.7rem}h1{font-size:1.5rem!important}}
</style>''', unsafe_allow_html=True)


def normalize_key(k):
    k = (k or '').strip()
    for _ in range(2):
        d = unquote(k)
        if d == k:
            break
        k = d
    return k


def get_secret(name, default=''):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def get_api_key():
    return normalize_key(get_secret('APPLYHOME_SERVICE_KEY', ''))


def clean_int(v):
    d = re.sub(r'[^\d]', '', str(v))
    return int(d) if d else 0


def normalize_movein(v):
    if v is None:
        return None
    s = str(v).strip()
    m = re.search(r'(\d{4})\s*년?\s*0?(\d{1,2})', s)
    if m:
        return f'{m.group(1)}-{int(m.group(2)):02d}'
    d = re.sub(r'[^\d]', '', s)
    return f'{d[:4]}-{d[4:6]}' if len(d) >= 6 else None


def guess_sigungu(a):
    for w in str(a or '').split():
        if w.endswith(('시', '군', '구')) and not w.endswith(('특별시', '광역시')):
            return w
    return ''


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_applyhome(key):
    if not key:
        return pd.DataFrame()
    start = '2025-01-01'
    end = date.today().strftime('%Y-%m-%d')
    rows = []
    for page in range(1, 51):
        params = {
            'page': page, 'perPage': 500, 'returnType': 'JSON', 'serviceKey': normalize_key(key),
            'cond[RCRIT_PBLANC_DE::GTE]': start, 'cond[RCRIT_PBLANC_DE::LTE]': end
        }
        r = requests.get(APPLYHOME_API, params=params, timeout=30)
        if r.status_code == 401:
            raise RuntimeError('청약홈 인증키 오류(401)')
        r.raise_for_status()
        data = r.json()
        batch = data.get('data', [])
        rows.extend(batch)
        total = int(data.get('totalCount', len(rows)) or len(rows))
        if len(rows) >= total or len(batch) < 500:
            break
    out = []
    for x in rows:
        mv = normalize_movein(x.get('MVN_PREARNGE_YM'))
        if not mv:
            continue
        out.append({
            '입주예정월': mv, '시도': x.get('SUBSCRPT_AREA_CODE_NM') or '',
            '시군구': guess_sigungu(x.get('HSSPLY_ADRES')), '단지명': x.get('HOUSE_NM') or '',
