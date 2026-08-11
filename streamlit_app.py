
import io, re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote
import pandas as pd
import requests
import streamlit as st

BASE_DIR=Path(__file__).parent
SUPPLEMENT_PATH=BASE_DIR/'supplemental_verified.csv'
APPLYHOME_API='https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail'
LH_URL='https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?mi=1042&sUppAisTpCd=06'
st.set_page_config(page_title='전국 신규 아파트 입주 DB',page_icon='🏢',layout='wide')
st.markdown('''
<style>
.block-container{padding-top:1rem}.apt-card{border:1px solid rgba(128,128,128,.25);border-radius:14px;padding:14px;margin-bottom:12px}.movein{font-size:1.08rem;font-weight:800}.apt-name{font-size:1.05rem;font-weight:700;margin:4px 0 8px}.meta{font-size:.92rem;line-height:1.65}@media(max-width:768px){.block-container{padding-left:.7rem;padding-right:.7rem}h1{font-size:1.5rem!important}}
</style>''',unsafe_allow_html=True)

def normalize_key(k):
    k=(k or '').strip()
    for _ in range(2):
        d=unquote(k)
        if d==k: break
        k=d
    return k

def get_api_key():
    try:return normalize_key(st.secrets.get('APPLYHOME_SERVICE_KEY',''))
    except:return ''

def clean_int(v):
    d=re.sub(r'[^\\d]','',str(v)); return int(d) if d else 0

def normalize_movein(v):
    if v is None:return None
    s=str(v).strip();m=re.search(r'(\\d{4})\\s*년?\\s*0?(\\d{1,2})',s)
    if m:return f'{m.group(1)}-{int(m.group(2)):02d}'
    d=re.sub(r'[^\\d]','',s);return f'{d[:4]}-{d[4:6]}' if len(d)>=6 else None

def guess_sigungu(a):
    for w in str(a or '').split():
        if w.endswith(('시','군','구')) and not w.endswith(('특별시','광역시')):return w
    return ''

@st.cache_data(ttl=3600,show_spinner=False)
def fetch_applyhome(key):
    if not key:return pd.DataFrame()
    start=(date.today()-timedelta(days=365*7)).strftime('%Y-%m-%d');end=date.today().strftime('%Y-%m-%d');rows=[]
    for page in range(1,51):
        params={'page':page,'perPage':500,'returnType':'JSON','serviceKey':normalize_key(key),'cond[RCRIT_PBLANC_DE::GTE]':start,'cond[RCRIT_PBLANC_DE::LTE]':end}
        r=requests.get(APPLYHOME_API,params=params,timeout=30)
        if r.status_code==401:raise RuntimeError('청약홈 인증키 오류(401)')
        r.raise_for_status();data=r.json();batch=data.get('data',[]);rows.extend(batch)
        total=int(data.get('totalCount',len(rows)) or len(rows))
        if len(rows)>=total or len(batch)<500:break
    out=[]
    for x in rows:
        mv=normalize_movein(x.get('MVN_PREARNGE_YM'))
        if not mv:continue
        out.append({'입주예정월':mv,'시도':x.get('SUBSCRPT_AREA_CODE_NM') or '','시군구':guess_sigungu(x.get('HSSPLY_ADRES')),'단지명':x.get('HOUSE_NM') or '','세대수':clean_int(x.get('TOT_SUPLY_HSHLDCO')),'시공사':x.get('CNSTRCT_ENTRPS_NM') or '','주소':x.get('HSSPLY_ADRES') or '','출처':'청약홈','원문':x.get('PBLANC_URL') or '','최근확인':date.today().isoformat(),'검증상태':'공식 API'})
    return pd.DataFrame(out)

@st.cache_data(ttl=3600,show_spinner=False)
def fetch_lh():
    r=requests.get(LH_URL,headers={'User-Agent':'Mozilla/5.0'},timeout=30);r.raise_for_status();target=None
    for t in pd.read_html(io.StringIO(r.text)):
        cols=[str(c).replace('\\n',' ').strip() for c in t.columns];t.columns=cols
        if '지역' in cols and any('지구명' in c for c in cols) and any('입주예정' in c for c in cols):target=t;break
    if target is None:return pd.DataFrame()
    def fc(k):return next((c for c in target.columns if k in str(c)),None)
    f=pd.DataFrame({'시도':target[fc('지역')].astype(str).str.strip(),'단지명':target[fc('지구명')].astype(str).str.strip(),'세대수':target[fc('공급호수')].map(clean_int),'입주예정월':target[fc('입주예정')].map(normalize_movein)})
    f=f[(f['단지명']!='')&f['입주예정월'].notna()].groupby(['시도','단지명','입주예정월'],as_index=False).agg(세대수=('세대수','sum'))
    f['시군구']='';f['시공사']='LH';f['주소']='';f['출처']='LH청약플러스';f['원문']=LH_URL;f['최근확인']=date.today().isoformat();f['검증상태']='공식 공급계획'
    return f[['입주예정월','시도','시군구','단지명','세대수','시공사','주소','출처','원문','최근확인','검증상태']]

def load_supplement():
    if not SUPPLEMENT_PATH.exists():return pd.DataFrame()
    f=pd.read_csv(SUPPLEMENT_PATH,encoding='utf-8-sig');f['세대수']=f['세대수'].map(clean_int);return f

def nname(v):return re.sub(r'[^가-힣A-Za-z0-9]','',str(v or '')).lower()

def dedup(f):
    x=f.copy();x['_k']=x['시도'].fillna('')+'|'+x['단지명'].map(nname)+'|'+x['입주예정월'].fillna('');p={'공식 보완DB':0,'청약홈':1,'LH청약플러스':2};x['_p']=x['출처'].map(lambda s:p.get(str(s),9));return x.sort_values(['_k','_p']).drop_duplicates('_k').drop(columns=['_k','_p'])

def excel_bytes(f):
    b=io.BytesIO()
    with pd.ExcelWriter(b,engine='openpyxl') as w:f.to_excel(w,index=False,sheet_name='입주DB')
    return b.getvalue()

st.title('🏢 전국 신규 아파트 입주 DB')
st.caption('300세대 이상 · 입주예정월 중심 · 누락단지 공식 보완DB 포함')
errs=[]
with st.spinner('최신 입주정보 확인 중...'):
    try:a=fetch_applyhome(get_api_key())
    except Exception as e:a=pd.DataFrame();errs.append(f'청약홈: {e}')
    try:l=fetch_lh()
    except Exception as e:l=pd.DataFrame();errs.append(f'LH: {e}')
    s=load_supplement()
frames=[x for x in [a,l,s] if isinstance(x,pd.DataFrame) and not x.empty]
if not frames:st.error('입주정보를 불러오지 못했습니다.');st.stop()
df=dedup(pd.concat(frames,ignore_index=True));df=df[df['세대수']>=300].sort_values(['입주예정월','시도','단지명'])
this=pd.Timestamp.today().strftime('%Y-%m');m3=(pd.Timestamp.today()+pd.DateOffset(months=3)).strftime('%Y-%m')
c1,c2,c3,c4=st.columns(4);c1.metric('등록 단지',f'{len(df):,}개');c2.metric('이번 달 입주',f"{(df['입주예정월']==this).sum():,}개");c3.metric('3개월 내 입주',f"{((df['입주예정월']>=this)&(df['입주예정월']<=m3)).sum():,}개");c4.metric('공식 보완',f"{(df['출처']=='공식 보완DB').sum():,}개")
with st.sidebar:
    st.header('🔎 검색 조건');sido=st.selectbox('시도',['전체']+sorted(df['시도'].dropna().unique().tolist()));years=sorted(set(str(x)[:4] for x in df['입주예정월'].dropna()));year=st.selectbox('입주연도',['전체']+years);month=st.selectbox('입주월',['전체']+[f'{i:02d}' for i in range(1,13)]);minhh=st.number_input('최소 세대수',min_value=300,value=300,step=100);kw=st.text_input('단지명/주소/시공사 검색')
f=df[df['세대수']>=minhh].copy()
if sido!='전체':f=f[f['시도']==sido]
if year!='전체':f=f[f['입주예정월'].str.startswith(year)]
if month!='전체':f=f[f['입주예정월'].str[5:7]==month]
if kw.strip():
    k=kw.strip();f=f[f['단지명'].fillna('').str.contains(k,case=False,regex=False)|f['주소'].fillna('').str.contains(k,case=False,regex=False)|f['시공사'].fillna('').str.contains(k,case=False,regex=False)]
st.subheader(f'검색 결과 · {len(f):,}개 단지');mt,tt=st.tabs(['📱 모바일 보기','📋 표 보기'])
with mt:
    for _,r in f.head(200).iterrows():
        st.markdown(f"<div class='apt-card'><div class='movein'>📅 {r['입주예정월']} 입주예정</div><div class='apt-name'>{r['단지명']}</div><div class='meta'>📍 {r['시도']} {r['시군구']}<br>🏠 {int(r['세대수']):,}세대<br>🏗️ {r['시공사']}<br>🔎 {r['출처']} · {r['검증상태']}</div></div>",unsafe_allow_html=True)
        if r.get('원문'):
            with st.expander('상세정보'):
                st.write('주소:',r.get('주소',''));st.link_button('공식 원문 보기',r['원문'],use_container_width=True)
with tt:st.dataframe(f[['입주예정월','시도','시군구','단지명','세대수','시공사','출처','검증상태','최근확인','원문']],use_container_width=True,hide_index=True,height=600)
st.download_button('⬇️ 현재 검색결과 Excel 다운로드',excel_bytes(f),file_name=f'전국_300세대이상_입주예정_{date.today()}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
with st.expander('🧪 누락단지 테스트'):
    t=df[df['단지명'].str.contains('영종 오션파크 모아엘가 그랑데',case=False,regex=False)]
    if not t.empty:st.success('영종 오션파크 모아엘가 그랑데가 현재 DB에 포함되어 있습니다.');st.dataframe(t[['입주예정월','단지명','세대수','시공사','출처']],hide_index=True,use_container_width=True)
    else:st.error('supplemental_verified.csv가 GitHub에 같이 올라갔는지 확인하세요.')
if errs:
    with st.expander('일부 출처 오류'):
        for e in errs:st.write('•',e)
st.caption('청약홈/LH 누락 단지는 공식기관에서 확인된 값만 supplemental_verified.csv로 보완합니다.')
