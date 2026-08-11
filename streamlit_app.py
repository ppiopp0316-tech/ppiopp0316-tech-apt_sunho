import io, re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote
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
    start = (date.today() - timedelta(days=365 * 7)).strftime('%Y-%m-%d')
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
    df = df[df['세대수'] >= 300].sort_values(['입주예정월', '시도', '단지명'])
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
    mt, tt = st.tabs(['📱 모바일 보기', '📋 표 보기'])
    with mt:
        for _, r in f.head(200).iterrows():
            st.markdown(f"<div class='apt-card'><div class='movein'>📅 {r['입주예정월']} 입주예정</div><div class='apt-name'>{r['단지명']}</div><div class='meta'>📍 {r['시도']} {r['시군구']}<br>🏠 {int(r['세대수']):,}세대<br>🏗️ {r['시공사']}<br>🔎 {r['출처']} · {r['검증상태']}</div></div>", unsafe_allow_html=True)
            if r.get('원문'):
                with st.expander('상세정보'):
                    st.write('주소:', r.get('주소', ''))
                    st.link_button('공식 원문 보기', r['원문'], use_container_width=True)
    with tt:
        st.dataframe(f[['입주예정월','시도','시군구','단지명','세대수','시공사','출처','검증상태','최근확인','원문']], use_container_width=True, hide_index=True, height=600)
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
    out['개설등록일자_dt'] = pd.to_datetime(out['개설등록일자'], errors='coerce')
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
        return normalize_broker_df(raw), '프로젝트 broker_offices.csv'
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
    st.caption('개설등록일 기준 · 같은 지역에서 신규 중개사무소가 집중 발생하는 곳을 자동 탐지')

    with st.sidebar:
        st.header('🏠 신규 부동산 조건')
        days = st.slider('신규 판정 기간', 1, 90, 30, key='broker_days')
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

    valid_dates = df['개설등록일자_dt'].notna().sum()
    latest_data_date = ''
    if '데이터기준일자' in df and df['데이터기준일자'].astype(str).str.strip().ne('').any():
        latest_data_date = pd.to_datetime(df['데이터기준일자'], errors='coerce').max()
        latest_data_date = latest_data_date.strftime('%Y-%m-%d') if pd.notna(latest_data_date) else ''

    stats, recent = broker_area_stats(df, int(days), int(min_count))
    today_ts = pd.Timestamp(date.today())
    c1,c2,c3,c4 = st.columns(4)
    c1.metric('전체 중개사무소', f'{len(df):,}개')
    c2.metric(f'최근 {days}일 신규', f'{len(recent):,}개')
    c3.metric(f'{min_count}개 이상 지역', f'{len(stats):,}곳')
    c4.metric('오늘 개설', f"{(df['개설등록일자_dt'] == today_ts).sum():,}개")

    if latest_data_date:
        st.caption(f'원천데이터 기준일자: {latest_data_date} · 유효한 개설등록일자 {valid_dates:,}건')
    else:
        st.caption(f'유효한 개설등록일자 {valid_dates:,}건')

    if stats.empty:
        st.info(f'최근 {days}일 동안 같은 지역에 신규 {min_count}개 이상인 곳이 현재 데이터에는 없습니다.')
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

    cols = ['개설등록일자','중개사무소명','대표자명','전화번호','개설등록번호','소재지도로명주소','소재지지번주소','개업공인중개사종별구분']
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


with st.sidebar:
    st.header('📂 전국입주 DB')
    page = st.radio('메뉴', ['🏢 아파트 입주 DB', '🏠 신규 부동산 DB'], key='main_page')
    st.divider()

if page == '🏢 아파트 입주 DB':
    render_apartment_db()
else:
    render_broker_db()

st.caption('전국입주 DB · 공식/공공 원천데이터 기반')
