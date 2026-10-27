# 전국입주 DB

기준본: `153a9b22ef4d4ef2178351437c0c09ff48f924fc` (2026-10-26).

기존 Streamlit의 아파트 입주 DB, 신규 부동산 DB, 지식산업센터 DB, 애드플래닝 관리업체를 유지합니다. `managed_offices.csv`, `knowledge_industry_centers.csv`의 기존 17열, 중개사무소 원천자료, 보완 DB 및 네이버 순위 원본은 변경하지 않았습니다.

## 실행

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

청약홈 API 키는 서버 환경변수 또는 Streamlit Secrets의 `APPLYHOME_SERVICE_KEY`로만 설정합니다. 원본 저장소나 Sites의 브라우저 코드에 키를 넣지 않습니다. 키가 없으면 LH와 저장된 자료를 조회하고, 청약홈 미수집 상태를 표시합니다.

## Sites용 화면

Sites는 Python Streamlit 프로세스를 실행하지 않으므로, 같은 데이터와 공통 분류 규칙으로 동작하는 HTML/JavaScript 화면을 `sites_app/`에 함께 제공합니다. Python 앱은 별도로 그대로 실행할 수 있습니다.

```bash
python scripts/build_sites.py --output /absolute/path/to/site/dist --refresh
```

`--refresh`는 LH 임대·분양 공급계획 전체 페이지와, 키가 설정된 경우 청약홈을 조회합니다. 원천 CSV를 변경하지 않고 `apartment_snapshot.csv`와 배포용 자료를 만듭니다. `--refresh`를 생략하면 기존 스냅샷을 사용합니다. 갱신 후 Sites를 다시 빌드·배포해야 호스팅 화면에 반영됩니다. 현재 GitHub 주간 KIC 작업이 Sites를 자동 배포하는 구성은 아닙니다.

사이트 기능: 4개 메뉴, 복합 필터, 카드/표, 페이지 이동, 네이버 단지 검색, 공식 출처 링크, 업체 상세, 순위 근거, CSV 및 Excel 내보내기, CSV/XLS/XLSX 임시 업로드. 임시 업로드는 현재 브라우저 메모리에만 적용하며 새로고침 시 원본으로 돌아갑니다.

SheetJS CE 0.20.3을 공식 배포본에서 가져와 자체 제공하며 라이선스를 동봉합니다. 조회 화면에서 외부 CDN을 사용하지 않습니다.

## 지식산업센터 규칙

- 향후 12개월은 한국 시간의 오늘부터 같은 날의 12개월 뒤까지입니다.
- `입주시작일`이 있으면 이를 우선하고, 없으면 `준공예정일`을 사용합니다.
- `YYYY-MM`은 월 단위 일정으로 보존하며 임의의 날짜를 만들어 표시하지 않습니다.
- 일정 미확인 공사 후보와 기간 외·완료 자료는 별도 범위로 조회합니다.
- 검증 배치는 기존 센터명+주소를 갱신하거나 추가합니다. 배치에 없는 기존 센터를 삭제하지 않습니다.
- 빈 파일, 잘못된 스키마, 검증되지 않은 배치는 기존 CSV를 덮어쓰지 않습니다.
- 전국 조회를 지원하는 것과 전국 수집이 완료된 것은 다릅니다. 현재 기준본은 준공예정 확인 1건이고 입주시작일 확인은 0건입니다.

```bash
python scripts/validate_kic.py knowledge_industry_centers.csv
python scripts/publish_verified_kic.py --reviewed reviewed_kic.csv
```

## 검증

```bash
python -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_sites.mjs
python tests/streamlit_smoke.py
```

배포 접근 제한은 Sites의 본인 전용 인증 정책으로 적용합니다. 검색 제외 메타 태그는 접근 제한 수단이 아닙니다. 현재 GitHub 저장소는 공개 상태이므로 Sites 비공개 설정이 원본 GitHub 자료를 숨기지는 않습니다.
