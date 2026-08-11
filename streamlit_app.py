
import io
import re
from datetime import date, timedelta
from urllib.parse import unquote

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="전국 신규 아파트 입주 DB",
    page_icon="🏢",
    layout="wide",
)

APPLYHOME_API = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"

def normalize_key(key):
    key = (key or "").strip()
    for _ in range(2):
        decoded = unquote(key)
        if decoded == key:
            break
        key = decoded
    return key

def get_api_key():
    try:
        return normalize_key(st.secrets.get("APPLYHOME_SERVICE_KEY", ""))
    except Exception:
        return ""

def clean_int(v):
    digits = re.sub(r"[^\d]", "", str(v))
    return int(digits) if digits else 0

def normalize_movein(v):
    if v is None:
        return None
    s = str(v).strip()
    m = re.search(r"(\d{4})\s*년?\s*0?(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    digits = re.sub(r"[^\d]", "", s)
    if len(digits) >= 6:
        return f"{digits[:4]}-{digits[4:6]}"
    return None

def guess_sigungu(address):
    for word in str(address or "").split():
        if word.endswith(("시", "군", "구")) and not word.endswith(("특별시", "광역시")):
            return word
    return ""

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_applyhome(api_key):
    if not api_key:
        return pd.DataFrame()

    start = (date.today() - timedelta(days=365 * 7)).strftime("%Y-%m-%d")
    end = date.today().strftime("%Y-%m-%d")
    rows = []

    for page in range(1, 51):
        params = {
            "page": page,
            "perPage": 500,
            "returnType": "JSON",
            "serviceKey": api_key,
            "cond[RCRIT_PBLANC_DE::GTE]": start,
            "cond[RCRIT_PBLANC_DE::LTE]": end,
        }

        r = requests.get(APPLYHOME_API, params=params, timeout=30)

        if r.status_code == 401:
            raise RuntimeError("청약홈 API 인증 실패(401)")

        r.raise_for_status()
        payload = r.json()

        batch = payload.get("data", [])
        rows.extend(batch)

        total = int(payload.get("totalCount", len(rows)) or len(rows))
        if len(rows) >= total or len(batch) < 500:
            break

    result = []

    for row in rows:
        movein = normalize_movein(row.get("MVN_PREARNGE_YM"))
        if not movein:
            continue

        result.append({
            "입주예정월": movein,
            "시도": row.get("SUBSCRPT_AREA_CODE_NM") or "",
            "시군구": guess_sigungu(row.get("HSSPLY_ADRES")),
            "단지명": row.get("HOUSE_NM") or "",
            "세대수": clean_int(row.get("TOT_SUPLY_HSHLDCO")),
            "시공사": row.get("CNSTRCT_ENTRPS_NM") or "",
            "주소": row.get("HSSPLY_ADRES") or "",
            "출처": "청약홈",
            "원문": row.get("PBLANC_URL") or "",
        })

    return pd.DataFrame(result)

def get_verified_supplements():
    # CSV 파일을 사용하지 않고 코드 안에 직접 보완단지를 넣습니다.
    return pd.DataFrame([
        {
            "입주예정월": "2026-04",
            "시도": "인천광역시",
            "시군구": "중구",
            "단지명": "영종 오션파크 모아엘가 그랑데",
            "세대수": 560,
            "시공사": "혜림건설(주)",
            "주소": "인천광역시 중구 운남동 1710-1",
            "출처": "공식 보완",
            "원문": "https://www.khba.or.kr/user/isale/isaleInfo.do?busiResuSeq=6&memSeq=2003-0300",
        }
    ])

def excel_bytes(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="입주DB")
    return out.getvalue()

st.title("🏢 전국 신규 아파트 입주 DB")
st.caption("300세대 이상 · 입주예정월 중심")

api_key = get_api_key()

frames = []

if api_key:
    try:
        with st.spinner("청약홈 자료를 불러오는 중..."):
            applyhome_df = fetch_applyhome(api_key)
        if not applyhome_df.empty:
            frames.append(applyhome_df)
    except Exception as e:
        st.warning(f"청약홈 자료를 불러오지 못했습니다: {e}")
else:
    st.warning("청약홈 API 인증키가 설정되지 않았습니다.")

# 공식 보완 자료는 항상 합칩니다.
frames.append(get_verified_supplements())

df = pd.concat(frames, ignore_index=True)

# 300세대 이상만
df = df[df["세대수"] >= 300].copy()

# 중복 정리
df["_key"] = (
    df["시도"].fillna("").astype(str)
    + "|"
    + df["단지명"].fillna("").astype(str).str.replace(r"[^가-힣A-Za-z0-9]", "", regex=True)
    + "|"
    + df["입주예정월"].fillna("").astype(str)
)
df = df.sort_values(["출처"]).drop_duplicates("_key", keep="last").drop(columns="_key")
df = df.sort_values(["입주예정월", "시도", "단지명"])

c1, c2, c3 = st.columns(3)
c1.metric("등록 단지", f"{len(df):,}개")
c2.metric("청약홈", f"{(df['출처'] == '청약홈').sum():,}개")
c3.metric("공식 보완", f"{(df['출처'] == '공식 보완').sum():,}개")

with st.sidebar:
    st.header("🔎 검색 조건")

    sido = st.selectbox(
        "시도",
        ["전체"] + sorted(df["시도"].dropna().unique().tolist())
    )

    years = sorted(set(str(x)[:4] for x in df["입주예정월"].dropna()))
    year = st.selectbox("입주연도", ["전체"] + years)

    month = st.selectbox(
        "입주월",
        ["전체"] + [f"{i:02d}" for i in range(1, 13)]
    )

    keyword = st.text_input("단지명/주소/시공사 검색")

filtered = df.copy()

if sido != "전체":
    filtered = filtered[filtered["시도"] == sido]

if year != "전체":
    filtered = filtered[filtered["입주예정월"].str.startswith(year)]

if month != "전체":
    filtered = filtered[filtered["입주예정월"].str[5:7] == month]

if keyword.strip():
    k = keyword.strip()
    filtered = filtered[
        filtered["단지명"].fillna("").str.contains(k, case=False, regex=False)
        | filtered["주소"].fillna("").str.contains(k, case=False, regex=False)
        | filtered["시공사"].fillna("").str.contains(k, case=False, regex=False)
    ]

st.subheader(f"검색 결과 · {len(filtered):,}개 단지")

st.dataframe(
    filtered[
        [
            "입주예정월",
            "시도",
            "시군구",
            "단지명",
            "세대수",
            "시공사",
            "출처",
            "원문",
        ]
    ],
    use_container_width=True,
    hide_index=True,
    height=600,
)

st.download_button(
    "⬇️ 현재 검색결과 Excel 다운로드",
    data=excel_bytes(filtered),
    file_name=f"전국_300세대이상_입주예정_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.success("영종 오션파크 모아엘가 그랑데는 공식 보완자료로 항상 포함됩니다.")
