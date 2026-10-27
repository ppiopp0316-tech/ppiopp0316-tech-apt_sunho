"""Exercise all existing Streamlit pages and real filter controls."""
from streamlit.testing.v1 import AppTest
from pathlib import Path

a = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'), default_timeout=90).run()
assert not a.exception
assert a.metric[0].value == '16개'
a.sidebar.selectbox(key='apt_sido').set_value('인천광역시')
a.sidebar.selectbox(key='apt_year').set_value('2026')
a.sidebar.selectbox(key='apt_month').set_value('04')
a.sidebar.number_input(key='apt_minhh').set_value(500)
a.sidebar.text_input(key='apt_kw').set_value('모아엘가').run()
assert not a.exception
assert any(x.value == '검색 결과 · 1개 단지' for x in a.subheader)
for page in ['🏠 신규 부동산 DB', '🏭 지식산업센터 DB', '📒 애드플래닝 관리업체']:
    a.sidebar.radio(key='main_page').set_value(page).run(timeout=90)
    assert not a.exception, [e.message for e in a.exception]
    print(page, [(m.label, m.value) for m in a.metric])
a.sidebar.radio(key='main_page').set_value('🏭 지식산업센터 DB').run()
a.sidebar.selectbox(key='kic_region').set_value('서울특별시').run()
assert a.metric[0].value == '0개'
a.sidebar.selectbox(key='kic_region').set_value('경기도')
a.sidebar.selectbox(key='kic_year').set_value('2027')
a.sidebar.selectbox(key='kic_month').set_value('03').run()
assert a.metric[0].value == '1개'
assert not a.exception
print('PASS: 4 Streamlit pages, compound apartment filters, empty KIC filter and month/year KIC filter')
