import io, re, json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote, quote
import pandas as pd
import requests
import streamlit as st
from apt_sections import render_charts, render_table

BASE_DIR = Path(__file__).parent
SUPPLEMENT_PATH = BASE_DIR / 'supplemental_verified.csv'
BROKER_LOCAL_PATH = BASE_DIR / 'broker_offices.csv.gz'
APPLYHOME_API = 'https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail'
LH_URL = 'https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?mi=1042&sUppAisTpCd=06'

st.set_page_config(page_title='전국입주 DB', page_icon='🏢', layout='wide')
st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

/* ── 글씨체: IBM Plex Sans KR (아이콘 글꼴은 건드리지 않음) ── */
.stApp, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li, .stApp label,
.stApp input, .stApp textarea, .stApp button, .stApp td, .stApp th,
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stMetricLabel"], .stApp [data-baseweb="select"] div,
.stApp [data-baseweb="tab"], .stApp [data-testid="stAlert"] {
  font-family: 'IBM Plex Sans KR', sans-serif;
}

/* ── 페이지 ── */
.block-container{padding-top:1.6rem; max-width:1280px}
.stApp h1{font-size:30px!important; font-weight:700!important; letter-spacing:-.6px; color:#141A22}
.stApp h2, .stApp h3{font-weight:700!important; letter-spacing:-.3px; color:#141A22}
.stApp [data-testid="stCaptionContainer"]{color:#5B6470}

/* ── 사이드바 ── */
[data-testid="stSidebar"]{background:#FFFFFF; border-right:1px solid #DDE0DA}
[data-testid="stSidebar"] h2{font-size:17px!important}

/* ── 숫자 요약(metric) → 흰 카드 ── */
[data-testid="stMetric"]{background:#FFFFFF; border:1px solid #DDE0DA; border-radius:14px; padding:18px 20px}
[data-testid="stMetricLabel"] p{font-size:14px!important; font-weight:500; color:#4A535E}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div{font-family:'IBM Plex Mono', monospace!important; font-weight:600; letter-spacing:-1px; color:#141A22}

/* ── 입력칸 ── */
.stApp [data-baseweb="select"] > div, .stApp [data-baseweb="input"], .stApp [data-baseweb="base-input"]{
  border-radius:10px!important; border-color:#C9CEC6!important; background:#FFFFFF}

/* ── 버튼 ── */
.stApp .stDownloadButton button, .stApp .stButton button, .stApp .stLinkButton a{
  border-radius:10px; border:1px solid #C9CEC6; background:#FFFFFF; color:#141A22; font-weight:600; min-height:44px}
.stApp .stDownloadButton button:hover, .stApp .stButton button:hover, .stApp .stLinkButton a:hover{
  border-color:#1E3A6E; color:#1E3A6E}

/* ── 탭 ── */
.stApp [data-baseweb="tab"]{font-weight:600}

/* ── 표(dataframe) 테두리 ── */
.stApp [data-testid="stDataFrame"]{border:1px solid #DDE0DA; border-radius:14px; overflow:hidden; background:#FFFFFF}

/* ── 모바일 보기 카드 ── */
.apt-card,.broker-card{background:#FFFFFF; border:1px solid #DDE0DA; border-radius:14px; padding:18px 20px; margin-bottom:12px}
.movein{font-family:'IBM Plex Mono', monospace; font-size:.95rem; font-weight:600; color:#1E3A6E}
.apt-name,.broker-name{font-size:1.1rem; font-weight:700; margin:6px 0 10px}
.apt-name a,.broker-name a{color:#141A22!important; text-decoration:none; border-bottom:1px solid #C9CEC6}
.apt-name a:hover,.broker-name a:hover{color:#1E3A6E!important; border-color:#1E3A6E}
.meta{font-size:.92rem; line-height:1.7; color:#4A535E}
.hot{font-weight:800}
.source-box{padding:.8rem 1rem; border-radius:14px; border:1px solid #DDE0DA; background:#FFFFFF; margin:.3rem 0 1rem}

@media(max-width:768px){
  .block-container{padding-left:.8rem; padding-right:.8rem}
  .stApp h1{font-size:1.5rem!important}
  [data-testid="stMetric"]{padding:14px 16px}
}
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
            '세대수': clean_int(x.get('TOT_SUPLY_HSHLDCO')), '시공사': x.get('CNSTRCT_ENTRPS_NM') or '',
            '주소': x.get('HSSPLY_ADRES') or '', '출처': '청약홈', '원문': x.get('PBLANC_URL') or '',
            '최근확인': date.today().isoformat(), '검증상태': '공식 API'
        })
    return pd.DataFrame(out)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_lh():
    r = requests.get(LH_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    r.raise_for_status()
    target = None
    for t in pd.read_html(io.StringIO(r.text)):
        cols = [str(c).replace('\n', ' ').strip() for c in t.columns]
        t.columns = cols
        if '지역' in cols and any('지구명' in c for c in cols) and any('입주예정' in c for c in cols):
            target = t
            break
    if target is None:
        return pd.DataFrame()
    def fc(k):
        return next((c for c in target.columns if k in str(c)), None)
    f = pd.DataFrame({
        '시도': target[fc('지역')].astype(str).str.strip(),
        '단지명': target[fc('지구명')].astype(str).str.strip(),
        '세대수': target[fc('공급호수')].map(clean_int),
        '입주예정월': target[fc('입주예정')].map(normalize_movein)
    })
    f = f[(f['단지명'] != '') & f['입주예정월'].notna()].groupby(
        ['시도', '단지명', '입주예정월'], as_index=False).agg(세대수=('세대수', 'sum'))
    f['시군구'] = ''
    f['시공사'] = 'LH'
    f['주소'] = ''
    f['출처'] = 'LH청약플러스'
    f['원문'] = LH_URL
    f['최근확인'] = date.today().isoformat()
    f['검증상태'] = '공식 공급계획'
    return f[['입주예정월', '시도', '시군구', '단지명', '세대수', '시공사', '주소', '출처', '원문', '최근확인', '검증상태']]


def load_supplement():
    if not SUPPLEMENT_PATH.exists():
        return pd.DataFrame()
    f = pd.read_csv(SUPPLEMENT_PATH, encoding='utf-8-sig')
    f['세대수'] = f['세대수'].map(clean_int)
    return f


def nname(v):
    return re.sub(r'[^가-힣A-Za-z0-9]', '', str(v or '')).lower()


def clean_apt_name(v):
    """청약 공고 제목에서 실제 단지명 검색에 방해되는 문구를 제거한다.

    예: '명지화전 우방아이유쉘 우선분양전환 후 잔여세대(2차)'
        -> '명지화전 우방아이유쉘'

    실제 단지명의 '2차', '3차' 등이 잘못 지워지지 않도록 공고성 문구를
    우선 제거하고, 그 뒤에 붙은 차수 표기만 정리한다.
    """
    s = re.sub(r'\s+', ' ', str(v or '')).strip()
    if not s:
        return ''

    original = s

    # 제목 앞뒤의 따옴표/공고 표시 정리
    s = s.strip(' \t\r\n"\'“”‘’')

    # 청약/재공급 공고에 자주 붙는 문구. 실제 단지명 뒤에 붙는 경우부터 잘라낸다.
    notice_patterns = [
        r'\s*우선분양전환\s*후\s*잔여세대.*$',
        r'\s*분양전환\s*후\s*잔여세대.*$',
        r'\s*우선분양전환.*$',
        r'\s*계약취소주택.*$',
        r'\s*취소주택\s*재공급.*$',
        r'\s*취소후\s*재공급.*$',
        r'\s*무순위(?:\s*\(사후\))?.*$',
        r'\s*임의공급.*$',
        r'\s*잔여세대.*$',
        r'\s*추가모집.*$',
        r'\s*추가입주자모집.*$',
        r'\s*추가\s*입주자모집.*$',
        r'\s*입주자모집공고.*$',
        r'\s*입주자\s*모집공고.*$',
        r'\s*예비입주자.*$',
        r'\s*특별공급.*$',
        r'\s*일반공급.*$',
        r'\s*선착순.*$',
        r'\s*재공급.*$',
    ]
    for pat in notice_patterns:
        cleaned = re.sub(pat, '', s, flags=re.IGNORECASE).strip()
        if cleaned != s:
            s = cleaned
            break

    # 공고성 문구가 제거된 경우에만 끝에 남은 '(2차)', '[3차]' 같은 차수 표기를 제거.
    if s != original.strip(' \t\r\n"\'“”‘’'):
        s = re.sub(r'\s*[\(\[]\s*\d+\s*차\s*[\)\]]\s*$', '', s).strip()
        s = re.sub(r'\s+\d+\s*차\s*$', '', s).strip()

    # 괄호 안에 공고 문구만 있는 경우도 제거한다.
    s = re.sub(
        r'\s*[\(\[]\s*(?:무순위(?:\s*사후)?|잔여세대|임의공급|계약취소주택|재공급|추가모집)'
        r'(?:\s*\d+\s*차)?\s*[\)\]]\s*$',
        '', s, flags=re.IGNORECASE
    ).strip()

    return re.sub(r'\s+', ' ', s).strip(' -_/') or original


def naver_apt_url(row):
    """네이버 부동산 지도에서 '중개'가 선택된 상태로 연다.

    네이버 지도 URL의 표시 옵션:
    - showRealtors=true   : 중개사 표시
    - showComplexes=false : 단지 표시 끔
    - showArticles=false  : 매물 표시 끔
    """
    sido = str(row.get('시도', '') or '').strip()
    sigungu = str(row.get('시군구', '') or '').strip()
    apt_name = clean_apt_name(row.get('단지명', ''))

    # 동명이인 단지를 줄이기 위해 지역 + 실제 단지명을 검색어로 사용한다.
    query = ' '.join(x for x in [sido, sigungu, apt_name] if x)
    encoded_query = quote(query, safe='')

    # 사용자가 네이버 부동산에서 '중개'를 눌렀을 때 생성되는 표시 옵션을 적용한다.
    return (
        'https://fin.land.naver.com/map'
        '?showRealtors=true'
        '&showComplexes=false'
        '&showArticles=false'
        f'#{encoded_query}'
    )


def dedup(f):
    x = f.copy()
    x['_k'] = x['시도'].fillna('') + '|' + x['단지명'].map(nname) + '|' + x['입주예정월'].fillna('')
    p = {'공식 보완DB': 0, '청약홈': 1, 'LH청약플러스': 2}
    x['_p'] = x['출처'].map(lambda s: p.get(str(s), 9))
    return x.sort_values(['_k', '_p']).drop_duplicates('_k').drop(columns=['_k', '_p'])


def excel_bytes(f, sheet_name='DB'):
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine='openpyxl') as w:
        f.to_excel(w, index=False, sheet_name=sheet_name[:31])
    return b.getvalue()


def render_apartment_db():
    st.title('🏢 전국 신규 아파트 입주 DB')
    st.caption('300세대 이상 · 입주예정월 중심 · 누락단지 공식 보완DB 포함')
    errs = []
    with st.spinner('최신 입주정보 확인 중...'):
        try:
            a = fetch_applyhome(get_api_key())
        except Exception as e:
            a = pd.DataFrame(); errs.append(f'청약홈: {e}')
        try:
            l = fetch_lh()
        except Exception as e:
            l = pd.DataFrame(); errs.append(f'LH: {e}')
        s = load_supplement()
    frames = [x for x in [a, l, s] if isinstance(x, pd.DataFrame) and not x.empty]
    if not frames:
        st.error('입주정보를 불러오지 못했습니다.')
        return
    df = dedup(pd.concat(frames, ignore_index=True))
    df = df[(df['세대수'] >= 300) & (df['입주예정월'] >= '2025-01')].copy()
    # 화면/검색용 실제 단지명. 원본 공고명은 '원공고단지명'으로 보존한다.
    df['원공고단지명'] = df['단지명']
    df['단지명'] = df['단지명'].map(clean_apt_name)
    df = df.sort_values(['입주예정월', '시도', '단지명'])
    this = pd.Timestamp.today().strftime('%Y-%m')
    m3 = (pd.Timestamp.today() + pd.DateOffset(months=3)).strftime('%Y-%m')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('등록 단지', f'{len(df):,}개')
    c2.metric('이번 달 입주', f"{(df['입주예정월'] == this).sum():,}개")
    c3.metric('3개월 내 입주', f"{((df['입주예정월'] >= this) & (df['입주예정월'] <= m3)).sum():,}개")
    c4.metric('공식 보완', f"{(df['출처'] == '공식 보완DB').sum():,}개")

    with st.sidebar:
        st.header('🔎 아파트 검색 조건')
        sido = st.selectbox('시도', ['전체'] + sorted(df['시도'].dropna().unique().tolist()), key='apt_sido')
        years = sorted(set(str(x)[:4] for x in df['입주예정월'].dropna()))
        year = st.selectbox('입주연도', ['전체'] + years, key='apt_year')
        month = st.selectbox('입주월', ['전체'] + [f'{i:02d}' for i in range(1, 13)], key='apt_month')
        minhh = st.number_input('최소 세대수', min_value=300, value=300, step=100, key='apt_minhh')
        kw = st.text_input('단지명/주소/시공사 검색', key='apt_kw')
    f = df[df['세대수'] >= minhh].copy()
    if sido != '전체': f = f[f['시도'] == sido]
    if year != '전체': f = f[f['입주예정월'].str.startswith(year)]
    if month != '전체': f = f[f['입주예정월'].str[5:7] == month]
    if kw.strip():
        k = kw.strip()
        f = f[f['단지명'].fillna('').str.contains(k, case=False, regex=False) |
              f['주소'].fillna('').str.contains(k, case=False, regex=False) |
              f['시공사'].fillna('').str.contains(k, case=False, regex=False)]
    st.subheader(f'검색 결과 · {len(f):,}개 단지')
    render_charts(f)
    mt, tt = st.tabs(['📱 모바일 보기', '📋 표 보기'])
    with mt:
        for _, r in f.head(200).iterrows():
            naver_url = naver_apt_url(r)
            st.markdown(
                f"<div class='apt-card'><div class='movein'>📅 {r['입주예정월']} 입주예정</div>"
                f"<div class='apt-name'><a href='{naver_url}' target='_blank' rel='noopener noreferrer'>{r['단지명']}</a></div>"
                f"<div class='meta'>📍 {r['시도']} {r['시군구']}<br>🏠 {int(r['세대수']):,}세대<br>🏗️ {r['시공사']}<br>🔎 {r['출처']} · {r['검증상태']}</div></div>",
                unsafe_allow_html=True
            )
            if r.get('원문'):
                with st.expander('상세정보'):
                    st.write('주소:', r.get('주소', ''))
                    original_name = str(r.get('원공고단지명', '') or '').strip()
                    if original_name and original_name != str(r.get('단지명', '') or '').strip():
                        st.write('원 공고명:', original_name)
                    st.link_button('공식 원문 보기', r['원문'], use_container_width=True)
    with tt:
        table_f = f.copy()
        if not table_f.empty:
            table_f['_naver_url'] = table_f.apply(naver_apt_url, axis=1)
        render_table(table_f)
    st.download_button('⬇️ 현재 검색결과 Excel 다운로드', excel_bytes(f, '입주DB'), file_name=f'전국_300세대이상_입주예정_{date.today()}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
    if errs:
        with st.expander('일부 출처 오류'):
            for e in errs: st.write('•', e)


# ------------------------- 신규 부동산중개사무소 DB -------------------------
BROKER_ALIASES = {
    '중개사무소명': ['중개사무소명', '상호명', '사무소명', 'office_name'],
    '개설등록번호': ['개설등록번호', '중개업등록번호', '등록번호', 'registration_number'],
    '대표자명': ['대표자명', '중개업자명', '대표자', 'representative_name'],
    '전화번호': ['전화번호', '연락처', 'phone'],
    '개설등록일자': ['개설등록일자', '등록일자', '개업일자', '개업일', 'registration_date'],
    '소재지도로명주소': ['소재지도로명주소', '도로명주소', 'road_address'],
    '소재지지번주소': ['소재지지번주소', '지번주소', 'jibun_address'],
    '개업공인중개사종별구분': ['개업공인중개사종별구분', '종별구분', 'office_type'],
    '위도': ['위도', 'latitude'], '경도': ['경도', 'longitude'],
    '데이터기준일자': ['데이터기준일자', '기준일자', 'data_date'],
    '영업상태': ['영업상태', '상태', 'business_status']
}


def _pick_col(df, aliases):
    norm = {str(c).strip().replace(' ', ''): c for c in df.columns}
    for a in aliases:
        k = a.strip().replace(' ', '')
        if k in norm:
            return norm[k]
    return None


def normalize_broker_df(raw):
    if raw is None or raw.empty:
        return pd.DataFrame()
    x = raw.copy()
    out = pd.DataFrame(index=x.index)
    for target, aliases in BROKER_ALIASES.items():
        c = _pick_col(x, aliases)
        out[target] = x[c] if c is not None else ''
    for c in out.columns:
        if c not in ('개설등록일자', '위도', '경도'):
            out[c] = out[c].fillna('').astype(str).str.strip()
    out['개설등록일자_dt'] = pd.to_datetime(out['개설등록일자'], errors='coerce', format='mixed')
    # 1900-01-01 등 지자체의 무효 기본값은 신규판정에서 제외
    out.loc[out['개설등록일자_dt'] < pd.Timestamp('1980-01-01'), '개설등록일자_dt'] = pd.NaT
    out['주소'] = out['소재지지번주소'].where(out['소재지지번주소'].str.strip() != '', out['소재지도로명주소'])
    parsed = out['주소'].map(parse_admin_area)
    out[['시도','시군구','읍면동']] = pd.DataFrame(parsed.tolist(), index=out.index)
    out['지역'] = (out['시도'] + ' ' + out['시군구'] + ' ' + out['읍면동']).str.replace(r'\s+', ' ', regex=True).str.strip()
    out.loc[out['읍면동'].eq(''), '지역'] = (out['시도'] + ' ' + out['시군구']).str.replace(r'\s+', ' ', regex=True).str.strip()
    out['개설등록일자'] = out['개설등록일자_dt'].dt.strftime('%Y-%m-%d').fillna('')
    out = out[out['중개사무소명'].str.strip() != ''].copy()
    if '개설등록번호' in out:
        key = out['개설등록번호'].str.strip()
        fallback = out['중개사무소명'].map(nname) + '|' + out['주소'].map(nname)
        out['_dedup'] = key.where(key != '', fallback)
        out = out.drop_duplicates('_dedup', keep='last').drop(columns='_dedup')
    return out


def parse_admin_area(address):
    s = re.sub(r'[,\s]+', ' ', str(address or '')).strip()
    if not s:
        return ('', '', '')
    tokens = s.split()
    sido = tokens[0] if tokens else ''
    sigungu_parts = []
    for t in tokens[1:4]:
        clean = re.sub(r'[()]', '', t)
        if clean.endswith(('시','군','구')):
            sigungu_parts.append(clean)
            if clean.endswith(('군','구')):
                break
        elif sigungu_parts:
            break
    sigungu = ' '.join(sigungu_parts)
    # 지번주소 또는 괄호 속 법정동/읍/면을 우선 탐색
    candidates = re.findall(r'([가-힣A-Za-z0-9·]+(?:동|읍|면))(?=[,\s\)])', s + ' ')
    town = ''
    for c in candidates:
        if c not in sigungu and not c.endswith(('자동','도로동')):
            town = c
    return (sido, sigungu, town)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_broker_url(url):
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
    r.raise_for_status()
    content = r.content
    ctype = (r.headers.get('content-type') or '').lower()
    if 'json' in ctype or str(url).lower().split('?')[0].endswith('.json'):
        obj = r.json()
        if isinstance(obj, list):
            return pd.DataFrame(obj)
        if isinstance(obj, dict):
            for k in ('data','items','records','result'):
                if isinstance(obj.get(k), list):
                    return pd.DataFrame(obj[k])
        raise ValueError('JSON에서 목록형 데이터를 찾지 못했습니다.')
    # CSV 인코딩 자동 시도
    for enc in ('utf-8-sig','cp949','euc-kr','utf-8'):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=enc)
        except Exception:
            pass
    raise ValueError('CSV/JSON 형식을 읽지 못했습니다.')


def read_uploaded_broker(uploaded):
    if uploaded is None:
        return pd.DataFrame()
    name = uploaded.name.lower()
    data = uploaded.getvalue()
    if name.endswith(('.xlsx','.xls')):
        return pd.read_excel(io.BytesIO(data))
    for enc in ('utf-8-sig','cp949','euc-kr','utf-8'):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()


def load_broker_source(uploaded=None):
    # 우선순위: 화면 업로드 > Secrets URL > 프로젝트 내 broker_offices.csv
    if uploaded is not None:
        raw = read_uploaded_broker(uploaded)
        return normalize_broker_df(raw), f'업로드 파일: {uploaded.name}'
    url = str(get_secret('BROKER_DATA_URL', '') or '').strip()
    if url:
        raw = fetch_broker_url(url)
        return normalize_broker_df(raw), 'BROKER_DATA_URL 자동연계'
    if BROKER_LOCAL_PATH.exists():
        raw = pd.read_csv(BROKER_LOCAL_PATH, encoding='utf-8-sig')
        return normalize_broker_df(raw), '공공데이터포털 공식 자료 · 2026-10-16 수집'
    return pd.DataFrame(), '연결 대기'


def broker_area_stats(df, days=30, min_count=3):
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    today = pd.Timestamp(date.today())
    start = today - pd.Timedelta(days=days - 1)
    recent = df[df['개설등록일자_dt'].between(start, today)].copy()
    recent = recent[recent['지역'].str.strip() != '']
    if recent.empty:
        return pd.DataFrame(), recent
    g = recent.groupby(['지역','시도','시군구','읍면동'], as_index=False).agg(
        신규수=('중개사무소명','count'),
        최근개업일=('개설등록일자_dt','max')
    )
    d7 = today - pd.Timedelta(days=6)
    today_counts = recent[recent['개설등록일자_dt'].eq(today)].groupby('지역').size()
    week_counts = recent[recent['개설등록일자_dt'].between(d7, today)].groupby('지역').size()
    g['오늘신규'] = g['지역'].map(today_counts).fillna(0).astype(int)
    g['7일신규'] = g['지역'].map(week_counts).fillna(0).astype(int)
    g['최근개업일'] = g['최근개업일'].dt.strftime('%Y-%m-%d')
    g = g[g['신규수'] >= min_count].copy()
    g['등급'] = g['신규수'].map(lambda n: '🔥 급증' if n >= 10 else ('⭐ 관심' if n >= 5 else '🆕 신규'))
    g = g.sort_values(['오늘신규','7일신규','신규수','최근개업일'], ascending=[False,False,False,False])
    return g, recent


def render_broker_db():
    st.title('🏠 신규 부동산중개사무소 DB')
    st.caption('공식 개설등록일 기준 · 지역별 최근 등록 현황과 업체 연락처 조회')

    with st.sidebar:
        st.header('🏠 신규 부동산 조건')
        days = st.slider('최근 등록 조회 기간', 1, 365, 30, key='broker_days')
        min_count = st.number_input('지역별 최소 신규 수', min_value=1, max_value=50, value=3, step=1, key='broker_min')
        uploaded = st.file_uploader('중개사무소 CSV/XLSX 임시 업로드', type=['csv','xlsx','xls'], key='broker_upload')

    try:
        with st.spinner('부동산중개업 데이터 확인 중...'):
            df, source_name = load_broker_source(uploaded)
    except Exception as e:
        st.error(f'중개사무소 데이터 연결 오류: {e}')
        df, source_name = pd.DataFrame(), '연결 오류'

    st.markdown(f"<div class='source-box'>📡 <b>데이터 연결:</b> {source_name}</div>", unsafe_allow_html=True)
    if df.empty:
        st.warning('아직 부동산중개업 원천데이터가 연결되지 않았습니다. Streamlit Secrets에 BROKER_DATA_URL을 등록하거나, 왼쪽에서 전국공인중개사사무소 CSV를 업로드하면 즉시 작동합니다.')
        st.info('필요 컬럼: 중개사무소명, 개설등록번호, 개설등록일자, 소재지도로명주소/지번주소. 대표자명·전화번호는 있으면 함께 표시됩니다.')
        return

    meta_path = BASE_DIR / 'broker_source_meta.json'
    if meta_path.exists() and uploaded is None:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        st.warning(f"공식 포털 다운로드 한도에 따라 {meta['raw_rows']:,}건을 수집한 자료입니다. 전국 전체를 포함하지 않으며, 등록·폐업 변동의 실시간 자료가 아닙니다.")
        st.caption('수집일: ' + meta['retrieved_at'] + ' · 출처: ' + meta['url'])
    st.caption('개설등록일은 행정상 등록일이며 실제 영업 시작일과 다를 수 있습니다. 전화번호 누락은 미확인으로 표시합니다.')

    valid_dates = df['개설등록일자_dt'].notna().sum()
    latest_data_date = ''
    if '데이터기준일자' in df and df['데이터기준일자'].astype(str).str.strip().ne('').any():
        latest_data_date = pd.to_datetime(df['데이터기준일자'], errors='coerce', format='mixed').max()
        latest_data_date = latest_data_date.strftime('%Y-%m-%d') if pd.notna(latest_data_date) else ''

    stats, recent = broker_area_stats(df, int(days), int(min_count))
    today_ts = pd.Timestamp(date.today())
    c1,c2,c3,c4 = st.columns(4)
    c1.metric('수집된 중개사무소', f'{len(df):,}개')
    c2.metric(f'최근 {days}일 신규', f'{len(recent):,}개')
    c3.metric(f'{min_count}개 이상 지역', f'{len(stats):,}곳')
    c4.metric('오늘 등록일인 업체', f"{(df['개설등록일자_dt'] == today_ts).sum():,}개")

    if latest_data_date:
        st.caption(f"지역별 원천자료 기준일: {df['데이터기준일자'].min()} ~ {latest_data_date} · 유효 등록일 {valid_dates:,}건")
    else:
        st.caption(f'유효한 개설등록일자 {valid_dates:,}건')

    st.subheader('중개사무소 목록 · 최근 등록일순')
    region_options = ['전체'] + sorted(df['시도'].dropna().unique().tolist())
    selected_sido = st.selectbox('조회 시도', region_options, key='broker_list_sido')
    keyword = st.text_input('업체명·주소 검색', key='broker_list_keyword')
    recent_only = st.checkbox(f'최근 {days}일 등록 업체만 보기', value=False, key='broker_list_recent')
    listing = (recent if recent_only else df).copy()
    if selected_sido != '전체':
        listing = listing[listing['시도'].eq(selected_sido)]
    if keyword.strip():
        listing = listing[listing['중개사무소명'].str.contains(keyword.strip(), regex=False) | listing['주소'].str.contains(keyword.strip(), regex=False)]
    listing = listing.sort_values('개설등록일자_dt', ascending=False)
    list_cols = ['개설등록일자', '중개사무소명', '대표자명', '전화번호', '소재지도로명주소', '개설등록번호', '데이터기준일자']
    table = listing[list_cols].replace('', '미확인')
    st.caption(f'조회 결과 {len(table):,}개 · 화면에는 최대 1,000개 표시, CSV는 조회 결과 전체 포함')
    st.dataframe(table.head(1000), hide_index=True, use_container_width=True, height=450)
    st.download_button('조회 업체 CSV 다운로드', table.to_csv(index=False).encode('utf-8-sig'), file_name='신규부동산_공식자료.csv', mime='text/csv')
    if recent.empty:
        st.info(f'수집 자료에서 최근 {days}일 등록 업체를 확인하지 못했습니다. 최근 등록 필터를 해제하면 기존 업체를 볼 수 있습니다.')
    if stats.empty:
        st.info(f'수집 자료에서 최근 {days}일 등록 {min_count}개 이상인 지역은 확인되지 않았습니다.')
        return

    st.subheader(f'🔥 최근 {days}일 신규 {min_count}개 이상 지역')
    show_stats = stats[['지역','오늘신규','7일신규','신규수','최근개업일','등급']].rename(columns={'신규수':f'{days}일신규'})
    st.dataframe(show_stats, use_container_width=True, hide_index=True, height=min(650, 80 + len(show_stats)*35))

    st.download_button('⬇️ 신규지역 요약 Excel', excel_bytes(show_stats, '신규지역'), file_name=f'신규부동산_{days}일_{min_count}개이상_지역_{date.today()}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)

    st.divider()
    region = st.selectbox('지역 상세보기', stats['지역'].tolist(), key='broker_region')
    detail = recent[recent['지역'] == region].sort_values('개설등록일자_dt', ascending=False).copy()
    row = stats[stats['지역'] == region].iloc[0]
    d1,d2,d3 = st.columns(3)
    d1.metric(f'{days}일 신규', f"{int(row['신규수'])}개")
    d2.metric('최근 7일', f"{int(row['7일신규'])}개")
    d3.metric('오늘', f"{int(row['오늘신규'])}개")

    cols = ['개설등록일자','중개사무소명','대표자명','전화번호','개설등록번호','소재지도로명주소','개업공인중개사종별구분']
    st.dataframe(detail[cols], use_container_width=True, hide_index=True, height=min(600, 80 + len(detail)*35))
    st.download_button('⬇️ 선택 지역 업체 Excel', excel_bytes(detail[cols], '중개사무소'), file_name=f"{re.sub(r'[^가-힣A-Za-z0-9_-]','_',region)}_신규중개사무소_{date.today()}.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)

    with st.expander('⚙️ 데이터 연결 안내'):
        st.markdown('''
**자동연계 방법**  
Streamlit 앱의 Secrets에 아래처럼 등록하면 앱이 1시간 캐시 후 원천데이터를 다시 읽습니다.

```toml
BROKER_DATA_URL = "CSV 또는 JSON 원천데이터 URL"
```

전국공인중개사사무소 표준 컬럼은 자동 인식합니다. 원천데이터의 `개설등록일자`를 이용하므로 별도의 전날 파일이 없어도 최근 7일/30일 신규 집계가 가능합니다.
        ''')



# ------------------------- 지식산업센터 입주예정 DB -------------------------
KIC_PATH = BASE_DIR / 'knowledge_industry_centers.csv'
KIC_COLUMNS = [
    '센터명', '시도', '시군구', '주소', '입주예정일', '준공예정일',
    '시공사', '시행사', '연락처', '확인출처', '원문URL', '최근확인일', '검증상태'
]


def render_knowledge_industry_db():
    st.title('🏭 전국 지식산업센터 입주예정 DB')
    st.caption('전국 · 오늘부터 12개월 이내 · 확인된 입주예정일 기준')

    if not KIC_PATH.exists():
        st.warning('knowledge_industry_centers.csv 파일이 없습니다. 앱과 같은 폴더에 업로드해 주세요.')
        return

    try:
        raw = pd.read_csv(KIC_PATH, encoding='utf-8-sig', dtype=str).fillna('')
    except Exception as e:
        st.error(f'지식산업센터 CSV를 읽지 못했습니다: {e}')
        return

    missing = [c for c in KIC_COLUMNS if c not in raw.columns]
    if missing:
        st.error('CSV 필수 컬럼 누락: ' + ', '.join(missing))
        return

    if raw.empty:
        st.info('현재 등록된 지식산업센터 입주예정 데이터가 없습니다.')
        st.download_button(
            '⬇️ DB 입력 양식 다운로드',
            raw[KIC_COLUMNS].to_csv(index=False).encode('utf-8-sig'),
            file_name='knowledge_industry_centers.csv',
            mime='text/csv',
            use_container_width=True
        )
        return

    f = raw.copy()
    f['_date'] = pd.to_datetime(f['입주예정일'].str.strip(), errors='coerce', format='mixed')
    today = pd.Timestamp(date.today())
    until = today + pd.DateOffset(months=12)
    f = f[f['_date'].between(today, until)].copy()
    f = f.sort_values(['_date', '시도', '센터명'])

    with st.sidebar:
        st.header('🏭 지식산업센터 검색')
        areas = sorted(f.loc[f['시도'].ne(''), '시도'].unique().tolist())
        area = st.selectbox('지역', ['전체'] + areas, key='kic_area')
        keyword = st.text_input('센터명 / 주소 / 시공사 / 시행사 검색', key='kic_keyword')

    if area != '전체':
        f = f[f['시도'] == area]

    if keyword.strip():
        k = keyword.strip()
        match = (
            f['센터명'].str.contains(k, case=False, regex=False) |
            f['주소'].str.contains(k, case=False, regex=False) |
            f['시공사'].str.contains(k, case=False, regex=False) |
            f['시행사'].str.contains(k, case=False, regex=False)
        )
        f = f[match]

    c1, c2, c3 = st.columns(3)
    c1.metric('향후 12개월 입주예정', f'{len(f):,}개')
    c2.metric('3개월 내 입주', f"{(f['_date'] <= today + pd.DateOffset(months=3)).sum():,}개")
    c3.metric('검증 완료', f"{f['검증상태'].str.contains('검증|확인|공식', case=False, regex=True).sum():,}개")

    if f.empty:
        st.info('선택한 조건에 해당하는 확인된 입주예정 센터가 없습니다.')
        return

    f['입주까지'] = f['_date'].map(lambda d: f"D-{(d - today).days}")
    display_cols = [
        '입주예정일', '입주까지', '센터명', '시도', '시군구', '주소',
        '시공사', '시행사', '연락처', '검증상태', '확인출처', '원문URL'
    ]
    st.dataframe(
        f[display_cols],
        use_container_width=True,
        hide_index=True,
        height=min(650, 80 + len(f) * 35),
        column_config={'원문URL': st.column_config.LinkColumn('확인 원문', display_text='원문 보기')}
    )

    st.download_button(
        '⬇️ 현재 검색결과 Excel 다운로드',
        excel_bytes(f[KIC_COLUMNS], '지식산업센터'),
        file_name=f'지식산업센터_입주예정_{date.today()}.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        use_container_width=True
    )


def render_managed_offices():
    st.title('📒 애드플래닝 관리업체 · 실제 네이버 노출순위')
    raw = pd.read_csv(BASE_DIR / 'managed_offices.csv', sep='|', encoding='utf-8-sig').fillna('')
    path = BASE_DIR / 'naver_rankings.json'
    if not path.exists():
        st.info('측정 자료를 불러오는 중입니다.')
        st.dataframe(raw, hide_index=True, use_container_width=True)
        return
    snap = json.loads(path.read_text(encoding='utf-8'))
    office_proof = {o['name']: o for o in snap['offices']}
    for extra_path in sorted(BASE_DIR.glob('naver_rank_extension_*.json')):
        extra = json.loads(extra_path.read_text(encoding='utf-8'))
        snap['queries'].update(extra.get('queries', {}))
        office_proof.update({o['name']: o for o in extra.get('offices', [])})
    snap['offices'] = list(office_proof.values())
    snap['measuredQueries'] = sum(bool(v.get('time')) for v in snap['queries'].values())
    snap['totalQueries'] = len(snap['queries'])
    proof = {o['name']: o for o in snap['offices']}
    def stamp(value):
        return pd.to_datetime(value, utc=True).tz_convert('Asia/Seoul').strftime('%Y-%m-%d %H:%M:%S') if value else ''
    rows = []
    for _, office in raw.iterrows():
        p = proof.get(office['업체명'], {'keywords': [], 'matches': []})
        matches = sorted([m for m in p['matches'] if m['rank'] <= 10], key=lambda m: m['rank'])
        measured = [q for q in p['keywords'] if snap['queries'].get(q, {}).get('time')]
        best = matches[0] if matches else {}
        keyword_ranks = {}
        for hit in matches:
            if len(keyword_ranks) < 5:
                keyword_ranks.setdefault(hit['keyword'], hit['rank'])
        exposed_keywords = ', '.join(f"{q} ({r}위)" for q, r in keyword_ranks.items())
        if matches:
            status = f'10위 이내 {len(keyword_ranks)}개 확인' + (' · 3개 미만' if len(keyword_ranks) < 3 else '')
        elif not p['keywords']:
            status = '주소 확인 필요'
        elif not measured:
            status = '미측정 · 조회 대기'
        else:
            status = '10위 이내 확인 키워드 없음'
        if measured and len(measured) < len(p['keywords']):
            status += ' · 일부 미측정'
        times = [snap['queries'][q]['time'] for q in measured]
        rows.append({'업체명': office['업체명'], '지역주소': office['지역주소'], '영업담당자': office['영업담당자'],
                     '측정상태': status, '실제 노출키워드': exposed_keywords, '확인키워드수': len(keyword_ranks), '최고순위': best.get('rank'), '확인검색어': best.get('keyword', ''),
                     '게시물': best.get('url', ''), '측정검색어수': f"{len(measured)}/{len(p['keywords'])}",
                     '측정시각(KST)': stamp(max(times)) if times else ''})
    summary = pd.DataFrame(rows)
    st.caption('네이버 블로그 · PC 비로그인 · 관련도순 · 광고 제외 · 2026-10-15~16 실측. 10위 이내 검색어만 업체별 최대 5개 표시합니다.')
    a, b, c, d = st.columns(4)
    a.metric('관리업체', len(raw))
    b.metric('실측 검색어', f"{snap['measuredQueries']}/{snap['totalQueries']}")
    c.metric('3~5개 확보 업체', int(summary['확인키워드수'].ge(3).sum()))
    d.metric('10위 이내 업체', int(summary['최고순위'].le(10).sum()))
    remaining = snap['totalQueries'] - snap['measuredQueries']
    if remaining:
        st.warning(f'확장한 검색어 중 {remaining}개는 아직 미측정입니다. 검색 환경의 연속 조회 제한으로 조회가 대기 중이며, 해당 업체나 블로그가 제재받았다는 뜻이 아닙니다.')
    with st.expander('미측정 · 조회 대기 표시의 의미'):
        st.write('여러 검색어를 연속 조회한 브라우저·네트워크에 네이버가 일시적으로 검색을 제한한 것입니다. 업체의 블로그 제재, 검색 누락 또는 광고 실패 판정이 아닙니다. 순위와 실제 노출키워드는 결과를 직접 확인한 경우만 표시합니다.')
    st.caption('측정 범위: 지역별 토지 매매 · 상가 임대 · 아파트 매매/전세/월세 · 확인 가능한 단지명+매매/전세/월세. 단지명은 업체명 자체가 아닌 부동산 단지 검색어입니다.')
    st.caption('작성자명과 업체명을 대조했습니다. 운영 블로그가 별칭을 쓰는 업체의 미식별은 10위 밖 확정이 아닙니다. 3개 미만은 확인된 개수만 표시합니다. 실제 유입수·문의수는 이 순위에 포함되지 않습니다.')
    search = st.text_input('업체명·지역·영업담당자 검색', key='rank_search')
    only_found = st.checkbox('노출 확인 업체만 보기', key='rank_only_found')
    show = summary.copy()
    if search.strip():
        show = show[show[['업체명', '지역주소', '영업담당자']].astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, regex=False)).any(axis=1)]
    if only_found:
        show = show[show['최고순위'].notna()]
    show = show.sort_values('최고순위', na_position='last', kind='stable')
    show = show[['업체명', '영업담당자', '실제 노출키워드', '확인키워드수', '측정상태', '최고순위', '지역주소', '게시물', '측정검색어수', '측정시각(KST)']]
    st.dataframe(show, hide_index=True, use_container_width=True, height=520,
                 column_config={'실제 노출키워드': st.column_config.TextColumn('10위 이내 노출키워드 (최대 5개)', width='large'),
                                '게시물': st.column_config.LinkColumn('근거 게시물', display_text='게시물 보기'),
                                '최고순위': st.column_config.NumberColumn('최고순위', format='%d위')})
    st.download_button('실측 결과 CSV 다운로드', summary.to_csv(index=False).encode('utf-8-sig'),
                       file_name='네이버_실측순위_2026-10-15.csv', mime='text/csv')
    st.subheader('업체별 검색어 측정 상세')
    selected = st.selectbox('업체 선택', summary.sort_values('최고순위', na_position='last', kind='stable')['업체명'].tolist(), key='rank_office')
    p = proof.get(selected, {'keywords': [], 'matches': []})
    detail = []
    for q in p['keywords']:
        measured = snap['queries'].get(q, {})
        hits = sorted([m for m in p['matches'] if m['keyword'] == q and m['rank'] <= 10], key=lambda m: m['rank'])
        hit = hits[0] if hits else {}
        if not measured.get('time'):
            result = '미측정 · 조회 대기'
        elif hits:
            result = f"{hit['rank']}위 · 해당 업체 {len(hits)}개 게시물 확인"
        else:
            result = '10위 이내 확인 게시물 없음'
        detail.append({'검색어': q, '측정결과': result, '블로그 작성자(검색결과)': hit.get('author', ''),
                       '게시물제목': hit.get('title', ''), '게시물': hit.get('url', ''),
                       '측정시각(KST)': stamp(measured.get('time'))})
    if detail:
        st.dataframe(pd.DataFrame(detail), hide_index=True, use_container_width=True,
                     column_config={'게시물': st.column_config.LinkColumn('근거 게시물', display_text='게시물 보기')})
        checked = [q for q in p['keywords'] if snap['queries'].get(q, {}).get('time')]
        if checked:
            with st.expander('실측 근거 게시물 보기'):
                query = st.selectbox('실측 검색어', checked, key='rank_audit_query')
                record = snap['queries'][query]
                if record.get('evidence_scope') == 'matched_posts_only':
                    st.caption(f"실제 조회한 게시물 {record.get('scanned_count', 0)}개 중 관리업체와 작성자가 일치한 근거 게시물입니다.")
                audit = pd.DataFrame([r for r in record['results'] if r['rank'] <= 10], columns=['rank', 'author', 'title', 'url']).rename(columns={'rank':'순위','author':'블로그 작성자(검색결과)','title':'게시물제목','url':'게시물'})
                st.dataframe(audit, hide_index=True, use_container_width=True, height=450,
                             column_config={'게시물': st.column_config.LinkColumn('게시물', display_text='게시물 보기')})
    else:
        st.info('주소가 확인되지 않아 지역 검색어를 측정하지 못했습니다.')
    with st.expander('관리업체 주소·영업담당자·검색어 후보'):
        st.dataframe(raw, hide_index=True, use_container_width=True)



with st.sidebar:
    st.header('📂 전국입주 DB')
    page = st.radio(
        '메뉴',
        ['🏢 아파트 입주 DB', '🏠 신규 부동산 DB', '🏭 지식산업센터 DB', '📒 애드플래닝 관리업체'],
        key='main_page'
    )
    st.divider()

if page == '🏢 아파트 입주 DB':
    render_apartment_db()
elif page == '🏠 신규 부동산 DB':
    render_broker_db()
elif page == '🏭 지식산업센터 DB':
    render_knowledge_industry_db()
else:
    render_managed_offices()

st.caption('전국입주 DB · 공식/공공 원천데이터 기반')