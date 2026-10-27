"""
전국입주 DB - 아파트 입주 DB 화면용 디자인 섹션
  1. 월별 입주 세대수
  2. 시·도별 입주 비중
  3. 입주 예정 단지 표

streamlit_app.py 의 render_apartment_db() 안에서 사용합니다.
    render_charts(f)   # 월별 그래프 + 시·도 비중
    render_table(f)    # 단지 표
CSS는 이 섹션들 안에서만 적용되고, 기존 화면에는 영향을 주지 않습니다.
"""
import html

import altair as alt
import pandas as pd
import streamlit as st

# 데이터 컬럼 이름 (streamlit_app.py 의 입주 DB 컬럼과 동일)
COLS = {
    "month": "입주예정월",   # 'YYYY-MM'
    "sido": "시도",
    "sigungu": "시군구",
    "name": "단지명",
    "units": "세대수",
    "builder": "시공사",
    "source": "출처",       # 청약홈 / LH청약플러스 / 공식 보완DB
    "naver": "_naver_url",  # 단지명 클릭 시 열 네이버 부동산 주소 (없으면 링크 없음)
    "origin": "원문",        # 공식 원문 주소
}

ACCENT = "#1E3A6E"      # 남색
HIGHLIGHT = "#C2571A"   # 주황 (이번 달)
PAGE_SIZE = 20
TOP_REGIONS = 6

SOURCE_TAGS = {
    "청약홈": ("#EEF1F6", "#1E3A6E"),
    "LH청약플러스": ("#E6F2EB", "#1F5C3A"),
    "공식 보완DB": ("#FBEDE3", "#8F3E10"),
}
TAG_DEFAULT = ("#F0EFEA", "#4A535E")

# '인천광역시', '경기도' 등을 '인천', '경기'로 통일
SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

.st-key-apt_monthly, .st-key-apt_region, .st-key-apt_table {{
  background:#FFFFFF; border:1px solid #DDE0DA; border-radius:14px; padding:22px;
  color:#141A22;
}}
.st-key-apt_table {{ padding:0; overflow:hidden; }}
.st-key-apt_monthly, .st-key-apt_region, .st-key-apt_table,
.st-key-apt_monthly *, .st-key-apt_region *, .st-key-apt_table * {{
  font-family:'IBM Plex Sans KR', sans-serif;
}}
.st-key-apt_monthly .apt-mono, .st-key-apt_region .apt-mono, .st-key-apt_table .apt-mono {{
  font-family:'IBM Plex Mono', monospace;
}}

.apt-head {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px; }}
.apt-h2 {{ margin:0 !important; padding:0 !important; font-size:17px !important; font-weight:700 !important; color:#141A22; }}
.apt-legend {{ display:flex; gap:14px; font-size:13px; color:#4A535E; }}
.apt-legend span {{ display:flex; align-items:center; gap:6px; }}
.apt-dot {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}

.apt-region-row {{ margin-top:16px; }}
.apt-region-top {{ display:flex; justify-content:space-between; font-size:14px; }}
.apt-region-top b {{ font-weight:500; }}
.apt-region-top span {{ color:#4A535E; }}
.apt-track {{ height:8px; background:#ECEEEA; border-radius:4px; margin-top:6px; }}
.apt-fill {{ height:8px; background:{ACCENT}; border-radius:4px; }}

.apt-table-head {{ padding:18px 22px; border-bottom:1px solid #DDE0DA; }}
.apt-count {{ font-size:14px; font-weight:500; color:#4A535E; margin-left:6px; }}
.apt-scroll {{ overflow-x:auto; }}
.apt-table {{ width:100%; min-width:900px; border-collapse:collapse; font-size:14px; margin:0; }}
.apt-table th {{ background:#F7F8F6; text-align:left; color:#4A535E; font-weight:600;
  font-size:13px; padding:12px; border:none; white-space:nowrap; }}
.apt-table td {{ padding:14px 12px; border:none; border-top:1px solid #ECEEEA; color:#141A22; }}
.apt-table th:first-child, .apt-table td:first-child {{ padding-left:22px; }}
.apt-table th:last-child, .apt-table td:last-child {{ padding-right:22px; }}
.apt-table .num {{ text-align:right; white-space:nowrap; }}
.apt-table .sub {{ color:#4A535E; }}
.apt-table .strong {{ font-weight:600; }}
.apt-table .strong a {{ color:#141A22; text-decoration:none; border-bottom:1px solid #C9CEC6; }}
.apt-table .strong a:hover {{ color:{ACCENT}; border-color:{ACCENT}; }}
.apt-table .link a {{ color:{ACCENT}; font-size:13px; white-space:nowrap; }}
.apt-tag {{ display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:600; white-space:nowrap; }}
.apt-empty {{ padding:28px 22px; color:#4A535E; font-size:14px; }}

.st-key-apt_table [data-testid="stHorizontalBlock"],
.st-key-apt_table [data-testid="stRadio"] {{ padding:0 22px; }}
</style>
"""


def _css():
    st.markdown(_CSS, unsafe_allow_html=True)


def _get(df, key, default=""):
    c = COLS.get(key)
    if c and c in df.columns:
        return df[c].fillna(default)
    return pd.Series(default, index=df.index)


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    month = _get(df, "month").astype(str).str.strip()
    month = month.str.replace(r"[./]", "-", regex=True).str[:7]
    out["month"] = month.where(month.str.fullmatch(r"\d{4}-\d{2}"))
    sido = _get(df, "sido").astype(str).str.strip()
    out["sido"] = sido.map(lambda s: SIDO_SHORT.get(s, s))
    out["sigungu"] = _get(df, "sigungu").astype(str).str.strip()
    out["name"] = _get(df, "name").astype(str)
    out["units"] = pd.to_numeric(
        _get(df, "units", 0).astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0).astype(int)
    out["builder"] = _get(df, "builder").astype(str)
    out["source"] = _get(df, "source").astype(str)
    out["naver"] = _get(df, "naver").astype(str)
    out["origin"] = _get(df, "origin").astype(str)
    return out.dropna(subset=["month"])


def _esc(x) -> str:
    return html.escape("" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x))


def _safe_url(u: str) -> str:
    u = str(u or "").strip()
    return html.escape(u, quote=True) if u.startswith(("http://", "https://")) else ""


# ─────────────────────────────────────────────────────────────
# 1. 월별 입주 세대수
# ─────────────────────────────────────────────────────────────
def _render_monthly(d: pd.DataFrame):
    this_month = pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m")
    m = d.groupby("month", as_index=False)["units"].sum().sort_values("month")
    m["label"] = m["month"].str[2:].str.replace("-", ".")
    m["k"] = (m["units"] / 1000).round(1).astype(str) + "k"
    m["is_now"] = m["month"] == this_month

    with st.container(key="apt_monthly"):
        st.markdown(
            f"""<div class="apt-head">
              <h3 class="apt-h2">월별 입주 세대수</h3>
              <div class="apt-legend">
                <span><i class="apt-dot" style="background:{HIGHLIGHT}"></i>이번 달</span>
                <span><i class="apt-dot" style="background:{ACCENT}"></i>예정</span>
              </div></div>""",
            unsafe_allow_html=True,
        )
        if m.empty:
            st.caption("표시할 데이터가 없습니다.")
            return

        many = len(m) > 18
        x = alt.X("label:N", sort=None, title=None,
                  axis=alt.Axis(labelAngle=-45 if many else 0, labelFont="IBM Plex Mono",
                                labelFontSize=11, labelColor="#5B6470", ticks=False,
                                domainColor="#C9CEC6", labelOverlap=True))
        bars = alt.Chart(m).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=x,
            y=alt.Y("units:Q", title=None, axis=None),
            color=alt.condition("datum.is_now", alt.value(HIGHLIGHT), alt.value(ACCENT)),
            tooltip=[alt.Tooltip("month:N", title="입주월"),
                     alt.Tooltip("units:Q", title="세대수", format=",")],
        )
        chart = bars
        if not many:
            labels = alt.Chart(m).mark_text(dy=-8, font="IBM Plex Mono", fontSize=11,
                                            color="#4A535E").encode(x=x, y="units:Q", text="k:N")
            chart = bars + labels
        st.altair_chart(chart.properties(height=260).configure_view(strokeWidth=0),
                        use_container_width=True)


# ─────────────────────────────────────────────────────────────
# 2. 시·도별 입주 비중
# ─────────────────────────────────────────────────────────────
def _render_region(d: pd.DataFrame):
    r = d[d["sido"] != ""].groupby("sido")["units"].sum().sort_values(ascending=False)
    total = r.sum()
    with st.container(key="apt_region"):
        if total == 0:
            st.markdown('<h3 class="apt-h2">시·도별 입주 비중</h3>', unsafe_allow_html=True)
            st.caption("표시할 데이터가 없습니다.")
            return
        top = r.head(TOP_REGIONS)
        rest = r.iloc[TOP_REGIONS:].sum()
        items = list(top.items()) + ([("기타", rest)] if rest > 0 else [])
        maxv = max(v for _, v in items)
        rows = "".join(
            f'<div class="apt-region-row"><div class="apt-region-top"><b>{_esc(name)}</b>'
            f'<span class="apt-mono">{v / total * 100:.0f}%</span></div>'
            f'<div class="apt-track"><div class="apt-fill" style="width:{v / maxv * 100:.1f}%"></div></div></div>'
            for name, v in items
        )
        st.markdown(f'<h3 class="apt-h2">시·도별 입주 비중</h3>{rows}', unsafe_allow_html=True)


def render_charts(df: pd.DataFrame):
    """월별 입주 세대수 + 시·도별 비중 (가로 2:1 배치)"""
    _css()
    d = _prepare(df)
    left, right = st.columns([2, 1], gap="small")
    with left:
        _render_monthly(d)
    with right:
        _render_region(d)


# ─────────────────────────────────────────────────────────────
# 3. 입주 예정 단지 표
# ─────────────────────────────────────────────────────────────
def render_table(df: pd.DataFrame):
    _css()
    d = _prepare(df)
    with st.container(key="apt_table"):
        st.markdown(
            f'<div class="apt-table-head"><h3 class="apt-h2">입주 예정 단지'
            f'<span class="apt-count apt-mono">{len(d):,}건</span></h3></div>',
            unsafe_allow_html=True,
        )
        if d.empty:
            st.markdown('<div class="apt-empty">조건에 맞는 단지가 없습니다.</div>', unsafe_allow_html=True)
            return

        order = st.radio("정렬", ["입주월순", "세대수순"], horizontal=True,
                         label_visibility="collapsed", key="apt_sort")
        if order == "입주월순":
            d = d.sort_values(["month", "units"], ascending=[True, False])
        else:
            d = d.sort_values("units", ascending=False)

        pages = max(1, -(-len(d) // PAGE_SIZE))
        page = min(max(1, st.session_state.get("apt_page", 1)), pages)
        view = d.iloc[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

        body = []
        for row in view.itertuples(index=False):
            bg, fg = SOURCE_TAGS.get(row.source, TAG_DEFAULT)
            region = f"{row.sido} {row.sigungu}".strip()
            naver = _safe_url(row.naver)
            name = (f'<a href="{naver}" target="_blank" rel="noopener noreferrer" '
                    f'title="네이버 부동산 단지 검색">{_esc(row.name)}</a>') if naver else _esc(row.name)
            origin = _safe_url(row.origin)
            origin_link = f'<a href="{origin}" target="_blank" rel="noopener noreferrer">공식 원문</a>' if origin else ""
            tag = f'<span class="apt-tag" style="background:{bg};color:{fg}">{_esc(row.source)}</span>' if row.source else ""
            body.append(
                "<tr>"
                f'<td class="apt-mono">{_esc(row.month.replace("-", "."))}</td>'
                f'<td class="sub">{_esc(region)}</td>'
                f'<td class="strong">{name}</td>'
                f'<td class="num apt-mono">{row.units:,}</td>'
                f'<td class="sub">{_esc(row.builder)}</td>'
                f"<td>{tag}</td>"
                f'<td class="link">{origin_link}</td>'
                "</tr>"
            )
        st.markdown(
            '<div class="apt-scroll"><table class="apt-table"><thead><tr>'
            "<th>입주예정월</th><th>지역</th><th>단지명</th>"
            '<th class="num">세대수</th><th>시공사</th><th>출처</th><th>원문</th>'
            f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )

        if pages > 1:
            c1, c2, c3 = st.columns([1, 2, 1])
            if c1.button("‹ 이전", disabled=page <= 1, key="apt_prev"):
                st.session_state["apt_page"] = page - 1
                st.rerun()
            c2.markdown(f'<div style="text-align:center;padding-top:8px" class="apt-mono">{page} / {pages}</div>',
                        unsafe_allow_html=True)
            if c3.button("다음 ›", disabled=page >= pages, key="apt_next"):
                st.session_state["apt_page"] = page + 1
                st.rerun()
        st.write("")
