import {
  SIDOS,
  KIC_COLUMNS,
  esc,
  safeUrl,
  normalizeSido,
  seoulToday,
  addMonths,
  classifyKic,
  targetMonth,
  filterApts,
  filterKic,
  filterBrokers,
  recentRows,
  brokerStats,
  managedSummary,
  naverUrl,
  csvText,
  validateKic,
} from "./logic.mjs";
const $ = (s) => document.querySelector(s),
  fmt = (n) => Number(n || 0).toLocaleString("ko-KR");
const pages = {
  apartments: {
    label: "아파트 입주 DB",
    title: "전국 신규 아파트 입주 DB",
    sub: "입주예정월 중심 · 300세대 이상 기본 조회 · 공식 원문 연결",
    icon: "▥",
  },
  brokers: {
    label: "신규 부동산 DB",
    title: "신규 부동산중개사무소 DB",
    sub: "공식 개설등록일 기준 · 지역별 신규 등록과 업체 연락처",
    icon: "⌂",
  },
  kic: {
    label: "지식산업센터 DB",
    title: "전국 지식산업센터 DB",
    sub: "향후 12개월 입주·준공 일정 · 공식 근거와 미확인 정보 구분",
    icon: "▦",
  },
  managed: {
    label: "애드플래닝 관리업체",
    title: "애드플래닝 관리업체",
    sub: "업체 정보와 네이버 블로그 검색 노출순위 · 기존 관리업체 전체 보존",
    icon: "▤",
  },
};
let page = "apartments",
  meta = {},
  data = {},
  original = {},
  current = [],
  summary = [],
  rankings = null,
  pageNum = 1,
  view = matchMedia("(max-width:850px)").matches ? "cards" : "table",
  loadSerial = 0;
const loaded = new Map(),
  uploads = new Set(),
  filters = {
    apartments: { minimum: 300 },
    brokers: { days: 30, mincount: 3 },
    kic: { scope: "future" },
    managed: {},
  };
const PAGE_SIZE = 20;
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").style.display = "block";
  setTimeout(() => ($("#toast").style.display = "none"), 6000);
}
async function jsonFile(name) {
  if (loaded.has(name)) return loaded.get(name);
  const promise = (async () => {
    const r = await fetch(`./data/${name}.json.gz`, { cache: "no-cache" });
    if (!r.ok) throw new Error("자료 파일을 불러오지 못했습니다.");
    if (!("DecompressionStream" in window))
      throw new Error("최신 Chrome, Edge, Safari 브라우저에서 열어주세요.");
    return JSON.parse(
      await new Response(
        r.body.pipeThrough(new DecompressionStream("gzip")),
      ).text(),
    );
  })();
  loaded.set(name, promise);
  try {
    return await promise;
  } catch (e) {
    loaded.delete(name);
    throw e;
  }
}
function nav() {
  const p = pages[page];
  $("#navigation").innerHTML = Object.entries(pages)
    .map(
      ([key, x]) =>
        `<a href="#${key}" class="${key === page ? "active" : ""}" ${key === page ? 'aria-current="page"' : ""}><span class="nav-icon">${x.icon}</span>${x.label}</a>`,
    )
    .join("");
  document.title = `${p.label} · 전국입주 DB`;
}
function option(value, label, selected) {
  return `<option value="${esc(value)}" ${String(value) === String(selected ?? "") ? "selected" : ""}>${esc(label ?? value)}</option>`;
}
function select(name, label, values, selected, all = "전체") {
  return `<div class="field"><label for="f-${name}">${label}</label><select id="f-${name}" name="${name}">${all === null ? "" : option("", all, selected)}${values.map((v) => (Array.isArray(v) ? option(v[0], v[1], selected) : option(v, v, selected))).join("")}</select></div>`;
}
function number(name, label, value, min, max) {
  return `<div class="field"><label for="f-${name}">${label}</label><input id="f-${name}" type="number" name="${name}" min="${min}" max="${max}" value="${esc(value)}" required></div>`;
}
function renderFilters() {
  const f = filters[page],
    rows = data[page] || [];
  let fields = "";
  if (page === "apartments" || page === "kic") {
    fields = select("sido", "시도", SIDOS, f.sido);
    if (page === "kic")
      fields += select(
        "scope",
        "조회 범위",
        [
          ["future", "향후 12개월"],
          ["unknown", "일정 미확인 후보"],
          ["archive", "전체 보관자료"],
        ],
        f.scope,
        null,
      );
    const months = rows
      .map((r) => (page === "apartments" ? r["입주예정월"] : targetMonth(r)))
      .filter((m) => /^\d{4}-\d{2}$/.test(m));
    fields += `<div class="field-inline">${select("year", page === "kic" ? "일정 연도" : "입주연도", [...new Set(months.map((m) => m.slice(0, 4)))].sort(), f.year)}${select(
      "month",
      page === "kic" ? "일정 월" : "입주월",
      Array.from({ length: 12 }, (_, i) => [
        String(i + 1).padStart(2, "0"),
        `${i + 1}월`,
      ]),
      f.month,
    )}</div>`;
    if (page === "apartments")
      fields += number("minimum", "최소 세대수", f.minimum ?? 300, 0, 999999);
    else
      fields += select(
        "status",
        "일정 구분",
        [
          "입주 예정",
          "준공 예정 · 입주일 미확인",
          "공사 중 · 일정 미확인",
          "기간 외·완료",
        ],
        f.status,
      );
  }
  if (page === "brokers")
    fields =
      select(
        "sido",
        "조회 시도",
        [
          ...new Set(
            [...SIDOS, ...rows.map((r) => normalizeSido(r["시도"]))].filter(
              Boolean,
            ),
          ),
        ],
        f.sido,
      ) +
      number("days", "최근 등록 조회 기간 (일)", f.days || 30, 1, 365) +
      number("mincount", "지역별 최소 신규 수", f.mincount || 3, 1, 50) +
      `<label class="check"><input type="checkbox" name="recent" ${f.recent ? "checked" : ""}>최근 등록 업체만 보기</label>`;
  const placeholder =
    page === "apartments"
      ? "단지명 / 주소 / 시공사"
      : page === "kic"
        ? "센터명 / 주소 / 시행·시공사"
        : page === "managed"
          ? "업체명 / 지역 / 영업담당자"
          : "업체명 / 주소 / 대표자";
  fields += `<div class="field"><label for="f-keyword">키워드 검색</label><input id="f-keyword" type="search" name="keyword" value="${esc(f.keyword || "")}" placeholder="${placeholder}"></div>`;
  if (page === "managed") {
    fields += `<label class="check"><input type="checkbox" name="found" ${f.found ? "checked" : ""}>10위 이내 노출 확인 업체만</label>`;
    const people = [
      ...new Set(rows.map((r) => r["영업담당자"]).filter(Boolean)),
    ].sort();
    fields += select("person", "영업담당자", people, f.person);
  }
  $("#filterbox").innerHTML =
    `<h2>검색 조건</h2><form id="filters">${fields}<div class="filter-actions"><button class="primary" type="submit">조건 적용</button><button id="reset" type="button">초기화</button></div></form><p class="hint">필터를 선택한 뒤 조건 적용을 눌러주세요.</p>`;
  $("#filters").onsubmit = (e) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget),
      next = Object.fromEntries(form);
    next.recent = form.has("recent");
    next.found = form.has("found");
    filters[page] = { ...filters[page], ...next };
    pageNum = 1;
    render();
    closeMenu();
  };
  $("#reset").onclick = () => {
    filters[page] =
      page === "apartments"
        ? { minimum: 300 }
        : page === "brokers"
          ? { days: 30, mincount: 3 }
          : page === "kic"
            ? { scope: "future" }
            : {};
    pageNum = 1;
    renderFilters();
    render();
  };
}
const link = (url, label, cls = "") =>
  safeUrl(url)
    ? `<a class="${cls}" href="${safeUrl(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`
    : `<span class="text-muted">미확인</span>`;
const badge = (text, color = "") =>
  `<span class="tag ${color}">${esc(text || "미확인")}</span>`;
function stat(label, value, unit = "개") {
  return `<div class="stat"><span class="label">${label}</span><span class="stat-icon">▧</span><strong>${fmt(value)}<span>${unit}</span></strong></div>`;
}
function filtered() {
  const f = filters[page],
    today = seoulToday();
  if (page === "apartments") return filterApts(data.apartments, f);
  if (page === "kic") return filterKic(data.kic, f, today);
  if (page === "brokers") return filterBrokers(data.brokers, f, today);
  const kw = (f.keyword || "").trim().toLowerCase();
  return summary
    .filter(
      (r) =>
        (!kw ||
          ["업체명", "지역주소", "영업담당자"].some((k) =>
            r[k].toLowerCase().includes(kw),
          )) &&
        (!f.found || r["최고순위"] !== null) &&
        (!f.person || r["영업담당자"] === f.person),
    )
    .sort((a, b) => (a["최고순위"] ?? 999) - (b["최고순위"] ?? 999));
}
function stats() {
  if (page === "apartments") {
    const month = seoulToday().slice(0, 7),
      m3 = addMonths(seoulToday(), 3).slice(0, 7);
    return (
      stat("검색된 단지", current.length) +
      stat(
        "입주 예정 세대",
        current.reduce((s, r) => s + Number(r["세대수"] || 0), 0),
        "세대",
      ) +
      stat(
        "이번 달 입주",
        current.filter((r) => r["입주예정월"] === month).length,
      ) +
      stat(
        "3개월 내 입주",
        current.filter((r) => r["입주예정월"] >= month && r["입주예정월"] <= m3)
          .length,
      )
    );
  }
  if (page === "kic")
    return (
      stat("조회 센터", current.length) +
      stat(
        "입주시작 일정 확인",
        current.filter((r) => r["구분"] === "입주 예정").length,
      ) +
      stat(
        "준공 예정 · 입주일 미확인",
        current.filter((r) => r["구분"] === "준공 예정 · 입주일 미확인").length,
      ) +
      stat(
        "일정 미확인 후보",
        data.kic.filter((r) => classifyKic(r) === "공사 중 · 일정 미확인")
          .length,
      )
    );
  if (page === "brokers") {
    const days = Number(filters.brokers.days || 30),
      recent = recentRows(current, days);
    return (
      stat("조회 중개사무소", current.length) +
      stat(`최근 ${days}일 등록`, recent.length) +
      stat(
        `${filters.brokers.mincount || 3}개 이상 지역`,
        brokerStats(current, days, Number(filters.brokers.mincount || 3))
          .length,
        "곳",
      ) +
      stat(
        "오늘 등록",
        recent.filter((r) => r["개설등록일자"] === seoulToday()).length,
      )
    );
  }
  return (
    stat("조회 관리업체", current.length) +
    stat(
      "10위 이내 노출 업체",
      current.filter((r) => r["최고순위"] !== null).length,
    ) +
    stat(
      "3~5개 키워드 확보",
      current.filter((r) => r["확인키워드수"] >= 3).length,
    ) +
    stat(
      "실측된 전체 검색어",
      Object.values(rankings.queries).filter((q) => q.time).length,
      "개",
    )
  );
}
function notices() {
  if (page === "apartments")
    return `<div class="notice"><span>ⓘ</span><div><b>공식 출처를 함께 확인하세요.</b> 입주예정월은 사업 일정에 따라 달라질 수 있습니다. 단지명을 누르면 네이버 부동산 단지 검색으로 연결됩니다.<small>자료 생성 ${esc(meta.builtAt?.slice(0, 16).replace("T", " "))} · ${esc((meta.warnings || []).join(" / "))} 현재 화면은 저장된 자료를 조회합니다.</small></div></div>`;
  if (page === "kic")
    return `<div class="notice warn"><span>ⓘ</span><div><b>조회 기간 ${seoulToday()} ~ ${addMonths(seoulToday(), 12)}</b><br>전국 17개 시도 조회를 지원하며, 현재 등록 ${fmt(data.kic.length)}건입니다. 전국 수집 완료를 의미하지 않습니다. 준공예정일과 입주시작일을 별도로 표시합니다.<small>일자가 없는 날짜는 월 단위 일정입니다. 일정 미확인 후보는 조회 범위를 바꾸면 볼 수 있습니다.</small></div></div>`;
  if (page === "brokers")
    return `<div class="notice warn"><span>ⓘ</span><div><b>전국 전체·실시간 자료가 아닙니다.</b> 공식 포털에서 수집한 원천 ${fmt(meta.brokerSource?.raw_rows)}행을 등록번호·상호·주소 기준으로 정리했습니다.<small>수집일 ${esc(meta.brokerSource?.retrieved_at)} · 개설등록일은 행정상 등록일입니다. 자료가 오래되어 최근 등록 결과가 0건일 수 있습니다. ${link(meta.brokerSource?.url, "공식 자료")}</small></div></div>`;
  return `<div class="notice"><span>ⓘ</span><div><b>네이버 블로그 실측 보관자료 · 2026-10-15~16</b><br>PC 비로그인 · 관련도순 · 광고 제외 · 업체별 10위 이내 검색어 최대 5개. 블로그 작성자와 영업담당자를 별도 표시합니다.<small>현재 순위가 아니며 미측정은 10위 밖 판정이 아닙니다. 업체 상세에서 측정 검색어와 근거 게시물을 확인하세요.</small></div></div>`;
}
function charts() {
  if (page !== "apartments" || !current.length) return "";
  const months = new Map(),
    regions = new Map();
  for (const r of current) {
    const n = Number(r["세대수"] || 0);
    months.set(r["입주예정월"], (months.get(r["입주예정월"]) || 0) + n);
    regions.set(r["시도"], (regions.get(r["시도"]) || 0) + n);
  }
  const ordered = [...months].sort(),
    max = Math.max(...months.values(), 1),
    total = [...regions.values()].reduce((a, b) => a + b, 0),
    regionMax = Math.max(...regions.values(), 1);
  return `<div class="chart-grid"><section class="panel panel-pad"><div class="panel-head"><h2>월별 입주 세대수</h2><small>■ 예정　<span style="color:#bd6d3e">■ 이번 달</span></small></div><div class="bar-scroll"><div class="bars">${ordered.map(([m, n]) => `<div class="bar-item"><div class="bar ${m === seoulToday().slice(0, 7) ? "now" : ""}" style="height:${Math.max((n / max) * 130, 2)}px" aria-label="${esc(m)} ${fmt(n)}세대"><strong>${fmt(n)}</strong></div><small>${esc(m.slice(2).replace("-", "."))}</small></div>`).join("")}</div></div></section><section class="panel panel-pad"><div class="panel-head"><h2>시·도별 입주 비중</h2><small>세대수 기준</small></div>${[
    ...regions,
  ]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(
      ([r, n]) =>
        `<div class="region-row"><div><span>${esc(r)}</span><span>${((n / total) * 100).toFixed(1)}%</span></div><div class="track"><div class="fill" style="width:${(n / regionMax) * 100}%"></div></div></div>`,
    )
    .join("")}</section></div>`;
}
function columns() {
  if (page === "apartments")
    return [
      "입주예정월",
      "시도",
      "시군구",
      "단지명",
      "세대수",
      "시공사",
      "출처",
      "원문",
    ];
  if (page === "kic")
    return [
      "구분",
      "센터명",
      "시도",
      "시군구",
      "준공예정일",
      "입주시작일",
      "시공사",
      "출처URL",
    ];
  if (page === "brokers")
    return [
      "개설등록일자",
      "중개사무소명",
      "대표자명",
      "전화번호",
      "소재지도로명주소",
      "데이터기준일자",
    ];
  return [
    "업체명",
    "영업담당자",
    "실제 노출키워드",
    "측정상태",
    "최고순위",
    "지역주소",
  ];
}
function displayCell(r, c) {
  const v = r[c];
  if (c === "단지명") return link(naverUrl(r), v, "name");
  if (["센터명", "업체명", "중개사무소명"].includes(c))
    return `<b class="name">${esc(v)}</b>`;
  if (["원문", "출처URL"].includes(c))
    return link(v, "공식 원문", "source-link");
  if (c === "출처") return badge(v, v?.includes("LH") ? "green" : "");
  if (c === "구분") return badge(v, v === "입주 예정" ? "green" : "amber");
  if (c === "세대수") return `<span class="mono">${fmt(v)}</span>`;
  if (c === "최고순위")
    return v
      ? badge(v + "위", "green")
      : '<span class="text-muted">미확인</span>';
  return esc(v || "미확인");
}
function empty() {
  return `<div class="empty"><strong>조건에 맞는 자료가 없습니다.</strong>검색 조건을 초기화하거나 조회 범위를 바꿔주세요.<br>${page === "kic" ? "확인되지 않은 일정을 추정해 표시하지 않습니다." : page === "brokers" ? "최근 등록 필터를 해제하면 기존 업체를 조회할 수 있습니다." : ""}</div>`;
}
function table(rows) {
  const cols = columns();
  return `<div class="panel">${rows.length ? `<div class="table-scroll"><table><thead><tr>${cols.map((c) => `<th class="${c === "세대수" ? "num" : ""}">${esc(c === "출처URL" ? "공식 출처" : c)}</th>`).join("")}<th>상세</th></tr></thead><tbody>${rows.map((r, i) => `<tr>${cols.map((c) => `<td class="${c === "세대수" ? "num" : ""}">${displayCell(r, c)}</td>`).join("")}<td><button class="detail-btn" data-detail="${(pageNum - 1) * PAGE_SIZE + i}">보기</button></td></tr>`).join("")}</tbody></table></div>` : empty()}${pagination()}</div>`;
}
function card(r, i) {
  let top = "",
    name = "",
    body = "",
    bottom = "";
  if (page === "apartments") {
    top = badge(r["입주예정월"] + " 입주예정") + badge(r["출처"], "green");
    name = link(naverUrl(r), r["단지명"]);
    body = `<p>${esc(r["시도"])} ${esc(r["시군구"])}</p><dl><dt>세대수</dt><dd>${fmt(r["세대수"])}세대</dd><dt>시공사</dt><dd>${esc(r["시공사"] || "미확인")}</dd><dt>주소</dt><dd>${esc(r["주소"] || "미확인")}</dd></dl>`;
    bottom = link(r["원문"], "공식 원문");
  } else if (page === "kic") {
    top = badge(r["구분"], r["구분"] === "입주 예정" ? "green" : "amber");
    name = esc(r["센터명"]);
    body = `<p>${esc(r["주소"])}</p><dl>${["준공예정일", "입주시작일", "시행사", "시공사", "연락처"].map((c) => `<dt>${c}</dt><dd>${esc(r[c] || "미확인")}</dd>`).join("")}</dl><p>${esc(r["검증상태"])}</p>`;
    bottom = link(r["출처URL"], "공식 출처");
  } else if (page === "brokers") {
    top =
      badge(r["개설등록일자"] || "등록일 미확인") + badge(r["시도"], "green");
    name = esc(r["중개사무소명"]);
    body = `<p>${esc(r["주소"] || r["소재지도로명주소"])}</p><dl><dt>대표자</dt><dd>${esc(r["대표자명"] || "미확인")}</dd><dt>전화번호</dt><dd>${esc(r["전화번호"] || "미확인")}</dd><dt>자료 기준일</dt><dd>${esc(r["데이터기준일자"] || "미확인")}</dd></dl>`;
    bottom = "공식 개설등록 자료";
  } else {
    top = badge(
      r["최고순위"] ? r["최고순위"] + "위" : "미확인",
      r["최고순위"] ? "green" : "amber",
    );
    name = esc(r["업체명"]);
    body = `<p>${esc(r["지역주소"])}</p><p>영업담당자 · ${esc(r["영업담당자"] || "미확인")}</p><p>${esc(r["실제 노출키워드"] || "확인된 노출키워드 없음")}</p><p>${esc(r["측정상태"])}</p>`;
    bottom = link(r["게시물"], "근거 게시물");
  }
  return `<article class="card"><div class="card-top">${top}</div><h3>${name}</h3>${body}<div class="card-bottom"><span>${bottom}</span><button class="detail-btn" data-detail="${(pageNum - 1) * PAGE_SIZE + i}">상세정보</button></div></article>`;
}
function pagination() {
  const total = Math.max(1, Math.ceil(current.length / PAGE_SIZE));
  return `<div class="pagination"><button data-move="-1" ${pageNum === 1 ? "disabled" : ""}>‹ 이전</button><span>${pageNum} / ${fmt(total)} 페이지 · ${fmt(current.length)}건</span><button data-move="1" ${pageNum >= total ? "disabled" : ""}>다음 ›</button></div>`;
}
function brokerRegionPanel() {
  if (page !== "brokers") return "";
  const f = filters.brokers,
    stats = brokerStats(current, Number(f.days || 30), Number(f.mincount || 3));
  return `<section class="panel panel-pad" style="margin-top:20px"><h2>최근 ${Number(f.days || 30)}일 신규 ${Number(f.mincount || 3)}개 이상 지역</h2>${stats.length ? `<div class="stats-table"><table><thead><tr><th>지역</th><th>신규</th><th>7일 신규</th><th>최근 등록일</th><th>상세</th></tr></thead><tbody>${stats.map((r, i) => `<tr><td>${esc(r["지역"])}</td><td>${r["신규수"]}</td><td>${r["7일신규"]}</td><td>${r["최근개업일"]}</td><td><button class="detail-btn" data-region="${i}">업체 보기</button></td></tr>`).join("")}</tbody></table></div><button class="detail-btn" id="region-export">지역 요약 Excel</button>` : '<p class="hint">수집된 자료에서 해당 기간 신규 등록 지역을 확인하지 못했습니다.</p>'}</section>`;
}
function render() {
  current = filtered();
  pageNum = Math.min(
    pageNum,
    Math.max(1, Math.ceil(current.length / PAGE_SIZE)),
  );
  const p = pages[page],
    f = filters[page],
    rows = current.slice((pageNum - 1) * PAGE_SIZE, pageNum * PAGE_SIZE);
  $("#main").innerHTML =
    `<div class="topline"><span class="crumb">AD PLANNING　/　데이터베이스</span><span class="pill">업무 공간</span></div><div class="page-title"><div><h1>${p.title}</h1><p class="subtitle">${p.sub}</p></div><div class="actions"><button id="import-btn">↑ 자료 임시 업로드</button><button id="csv-export">↓ CSV</button><button id="excel-export" class="primary">↓ Excel 다운로드</button></div></div>${notices()}${uploads.has(page) ? '<p class="upload-badge">브라우저 임시 업로드 자료 · 공식 출처 내용은 별도 확인 필요 <button class="clear-upload" id="clear-upload">원본으로 되돌리기</button></p>' : ""}<div class="stat-grid">${stats()}</div>${charts()}<div class="toolbar"><div class="result-title"><b>${page === "apartments" ? "입주 예정 단지" : page === "kic" ? "지식산업센터 목록" : page === "brokers" ? "중개사무소 목록" : "관리업체 목록"}</b><span class="count">${fmt(current.length)}건</span></div><div class="toolbar-end">${page === "apartments" ? `<select id="sort" aria-label="정렬"><option value="date" ${f.sort !== "units" ? "selected" : ""}>입주월순</option><option value="units" ${f.sort === "units" ? "selected" : ""}>세대수순</option></select>` : ""}<div class="segmented" aria-label="보기 방식"><button data-view="cards" aria-pressed="${view === "cards"}">▦ 카드</button><button data-view="table" aria-pressed="${view === "table"}">☷ 표</button></div></div></div>${view === "table" ? table(rows) : rows.length ? `<div class="cards">${rows.map(card).join("")}</div>${pagination()}` : empty()}${brokerRegionPanel()}<div class="dataset-status">화면 ${rows.length}건 표시 · 다운로드는 현재 검색결과 전체 ${fmt(current.length)}건 포함</div><footer class="footer"><span>전국입주 DB · 애드플래닝</span><span>공식·공공 원천자료　/　자료 생성 ${esc(meta.builtAt?.slice(0, 10))}</span></footer>`;
  document.querySelectorAll("[data-view]").forEach(
    (b) =>
      (b.onclick = () => {
        view = b.dataset.view;
        render();
      }),
  );
  document.querySelectorAll("[data-move]").forEach(
    (b) =>
      (b.onclick = () => {
        pageNum += Number(b.dataset.move);
        render();
      }),
  );
  document
    .querySelectorAll("[data-detail]")
    .forEach(
      (b) => (b.onclick = () => showDetail(current[Number(b.dataset.detail)])),
    );
  if ($("#sort"))
    $("#sort").onchange = (e) => {
      f.sort = e.target.value;
      pageNum = 1;
      render();
    };
  $("#csv-export").onclick = () => download("csv");
  $("#excel-export").onclick = () => download("xlsx");
  $("#import-btn").onclick = () => $("#upload").click();
  if ($("#clear-upload"))
    $("#clear-upload").onclick = () => {
      data[page] = original[page];
      uploads.delete(page);
      if (page === "managed") summary = managedSummary(data.managed, rankings);
      pageNum = 1;
      renderFilters();
      render();
    };
  if ($("#region-export"))
    $("#region-export").onclick = () =>
      exportRows(
        brokerStats(current, Number(f.days || 30), Number(f.mincount || 3)),
        ["지역", "신규수", "오늘신규", "7일신규", "최근개업일"],
        "xlsx",
        "신규지역요약",
      );
  document.querySelectorAll("[data-region]").forEach(
    (b) =>
      (b.onclick = () => {
        const stat = brokerStats(
          current,
          Number(f.days || 30),
          Number(f.mincount || 3),
        )[Number(b.dataset.region)];
        const rows = recentRows(current, Number(f.days || 30)).filter(
          (r) => r["지역"] === stat["지역"],
        );
        $("#detail-body").innerHTML =
          `<h2>${esc(stat["지역"])} 신규 업체</h2><p>${rows.length}곳 · 최근 ${f.days}일</p><button id="region-detail-export">Excel 다운로드</button><div class="table-scroll"><table><thead><tr><th>등록일</th><th>업체명</th><th>대표자</th><th>연락처</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r["개설등록일자"])}</td><td>${esc(r["중개사무소명"])}</td><td>${esc(r["대표자명"])}</td><td>${esc(r["전화번호"] || "미확인")}</td></tr>`).join("")}</tbody></table></div>`;
        $("#region-detail-export").onclick = () =>
          exportRows(
            rows,
            ["개설등록일자", "중개사무소명", "대표자명", "전화번호", "주소"],
            "xlsx",
            "선택지역업체",
          );
        $("#detail").showModal();
      }),
  );
}
function displayDate(v) {
  if (!v) return "미측정";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      dateStyle: "short",
      timeStyle: "medium",
    }).format(new Date(v));
  } catch {
    return "미확인";
  }
}
function showDetail(r) {
  let title = r["단지명"] || r["센터명"] || r["중개사무소명"] || r["업체명"];
  let fields =
    page === "managed"
      ? [
          "업체명",
          "지역주소",
          "영업담당자",
          "측정상태",
          "실제 노출키워드",
          "최고순위",
          "측정검색어수",
        ]
      : page === "kic"
        ? ["구분", ...KIC_COLUMNS]
        : Object.keys(r).filter((k) => !k.startsWith("_"));
  $("#detail-body").innerHTML =
    `<h2>${esc(title)}</h2><dl>${fields.map((k) => `<dt>${esc(k)}</dt><dd>${["원문", "출처URL", "게시물"].includes(k) ? link(r[k], "원문 보기") : esc(r[k] ?? "미확인") || "미확인"}</dd>`).join("")}</dl>${page === "managed" ? rankDetail(r) : ""}`;
  $("#detail").showModal();
}
function rankDetail(r) {
  const p = r.proof;
  return `<div class="rank-detail"><h2>검색어별 실측 근거</h2><p class="hint">영업담당자는 위의 업체 정보에 표시합니다. 아래 작성자는 실제 검색결과의 블로그 작성자입니다.</p>${
    p.keywords.length
      ? `<div class="table-scroll"><table><thead><tr><th>검색어</th><th>결과</th><th>블로그 작성자</th><th>근거 게시물</th><th>측정시각 (KST)</th></tr></thead><tbody>${p.keywords
          .map((q) => {
            const record = rankings.queries[q] || {},
              hits = p.matches
                .filter((m) => m.keyword === q && m.rank <= 10)
                .sort((a, b) => a.rank - b.rank),
              hit = hits[0];
            return `<tr><td>${esc(q)}</td><td>${!record.time ? "미측정 · 조회 대기" : hit ? hit.rank + "위" : "10위 이내 확인 게시물 없음"}</td><td>${esc(hit?.author || "미확인")}</td><td>${link(hit?.url, hit?.title || "게시물 보기")}</td><td>${esc(displayDate(record.time))}</td></tr>`;
          })
          .join("")}</tbody></table></div>`
      : '<p class="hint">주소 확인 후 측정 검색어를 추가할 수 있습니다.</p>'
  }</div>`;
}
function exportColumns() {
  if (page === "kic") return ["구분", ...KIC_COLUMNS];
  if (page === "managed")
    return [
      "업체명",
      "지역주소",
      "영업담당자",
      "실제 노출키워드",
      "확인키워드수",
      "측정상태",
      "최고순위",
      "게시물",
      "측정검색어수",
      "측정시각",
    ];
  return [...new Set(current.flatMap((r) => Object.keys(r)))].filter(
    (k) => !k.startsWith("_"),
  );
}
function download(type) {
  exportRows(current, exportColumns(), type, pages[page].label);
}
function exportRows(rows, cols, type, name) {
  const filename = name.replaceAll(" ", "_") + "_" + seoulToday() + "." + type;
  if (type === "csv") {
    const url = URL.createObjectURL(
        new Blob([csvText(rows, cols)], { type: "text/csv;charset=utf-8;" }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else {
    if (!window.XLSX) {
      toast("Excel 모듈을 불러오지 못했습니다. CSV를 사용해 주세요.");
      return;
    }
    const ws = XLSX.utils.aoa_to_sheet([
      cols,
      ...rows.map((r) => cols.map((c) => r[c] ?? "")),
    ]);
    ws["!cols"] = cols.map((c) => ({
      wch: ["주소", "지역주소", "공식출처", "실제 노출키워드"].includes(c)
        ? 50
        : 22,
    }));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "검색결과");
    const bytes = XLSX.write(wb, { type: "array", bookType: "xlsx" }),
      url = URL.createObjectURL(
        new Blob([bytes], { type: "application/octet-stream" }),
      ),
      anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  toast(`${fmt(rows.length)}건 다운로드를 시작했습니다.`);
}
function normalizeUpload(rows, key) {
  if (!rows.length)
    throw new Error("데이터가 0건입니다. 기존 자료를 유지합니다.");
  if (key === "kic") return validateKic(rows);
  const required =
    key === "apartments"
      ? ["단지명", "입주예정월", "세대수", "시도"]
      : key === "brokers"
        ? ["중개사무소명", "개설등록일자"]
        : ["업체명", "지역주소", "영업담당자"];
  for (const col of required)
    if (!(col in rows[0])) throw new Error("필수 열이 없습니다: " + col);
  return rows.map((r) => {
    r = { ...r };
    r["시도"] = normalizeSido(r["시도"]);
    if (key === "apartments") {
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(r["입주예정월"]))
        throw new Error("입주예정월은 YYYY-MM 형식이어야 합니다.");
      r["세대수"] = Number(String(r["세대수"]).replaceAll(",", ""));
      if (!Number.isFinite(r["세대수"]) || r["세대수"] < 0)
        throw new Error("세대수는 0 이상의 숫자여야 합니다.");
    }
    if (key === "brokers") {
      r["주소"] =
        r["주소"] || r["소재지지번주소"] || r["소재지도로명주소"] || "";
      const parts = r["주소"].split(/\s+/);
      r["시도"] = r["시도"] || normalizeSido(parts[0]);
      r["지역"] = r["지역"] || parts.slice(0, 3).join(" ");
      if (!r["개설등록일자"].match(/^\d{4}-\d{2}-\d{2}$/))
        r["개설등록일자"] = "";
    }
    return r;
  });
}
$("#upload").onchange = async (e) => {
  const file = e.target.files[0],
    key = page;
  e.target.value = "";
  if (!file) return;
  try {
    if (file.size > 25 * 1024 * 1024)
      throw new Error("업로드는 25MB 이하 파일을 사용해 주세요.");
    if (!window.XLSX) throw new Error("파일 모듈을 아직 불러오지 못했습니다.");
    const bytes = await file.arrayBuffer();
    let input = bytes,
      type = "array";
    if (file.name.toLowerCase().endsWith(".csv")) {
      input = new TextDecoder("utf-8").decode(bytes);
      if (input.includes("\uFFFD"))
        input = new TextDecoder("euc-kr").decode(bytes);
      type = "string";
    }
    const wb = XLSX.read(input, {
        type,
        raw: true,
        cellDates: false,
        codepage: 65001,
      }),
      rows = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], {
        defval: "",
        raw: false,
      });
    const checked = normalizeUpload(rows, key);
    data[key] = checked;
    uploads.add(key);
    if (key === "managed") summary = managedSummary(data.managed, rankings);
    pageNum = 1;
    renderFilters();
    render();
    toast(
      `${fmt(rows.length)}건을 현재 브라우저에 임시 적용했습니다. 새로고침하면 원본으로 돌아갑니다.`,
    );
  } catch (error) {
    toast(error.message);
  }
};
function closeMenu() {
  document.body.classList.remove("menu-open");
  $("#menu").setAttribute("aria-expanded", "false");
  const narrow = matchMedia("(max-width:850px)").matches;
  $("#sidebar").inert = narrow;
  $("#sidebar").setAttribute("aria-hidden", String(narrow));
}
$("#menu").onclick = () => {
  const open = document.body.classList.toggle("menu-open");
  $("#menu").setAttribute("aria-expanded", String(open));
  $("#sidebar").inert = !open;
  $("#sidebar").setAttribute("aria-hidden", String(!open));
};
$("#close-detail").onclick = () => $("#detail").close();
$("#detail").addEventListener("click", (e) => {
  if (e.target === $("#detail")) {
    const rect = $("#detail").getBoundingClientRect();
    if (
      e.clientX < rect.left ||
      e.clientX > rect.right ||
      e.clientY < rect.top ||
      e.clientY > rect.bottom
    )
      $("#detail").close();
  }
});
async function navigate() {
  const next = location.hash.slice(1);
  page = next in pages ? next : "apartments";
  const key = page,
    serial = ++loadSerial;
  pageNum = 1;
  nav();
  closeMenu();
  $("#main").innerHTML =
    '<div class="loading" role="status">자료를 불러오고 있습니다…</div>';
  $("#filterbox").innerHTML = "";
  try {
    if (!data[key]) {
      data[key] = await jsonFile(key);
      original[key] = data[key];
    }
    if (key === "managed" && !rankings) {
      rankings = await jsonFile("rankings");
      summary = managedSummary(data.managed, rankings);
    }
    if (serial !== loadSerial) return;
    renderFilters();
    render();
  } catch (error) {
    if (serial === loadSerial)
      $("#main").innerHTML =
        `<div class="empty"><strong>자료를 불러오지 못했습니다.</strong>${esc(error.message)}<p><button id="retry">다시 시도</button></p></div>`;
    if ($("#retry")) $("#retry").onclick = navigate;
  }
}
window.addEventListener("hashchange", navigate);
matchMedia("(max-width:850px)").addEventListener("change", closeMenu);
$(".skip").onclick = (e) => {
  e.preventDefault();
  $("#main").focus();
};
try {
  const response = await fetch("./data/meta.json", { cache: "no-cache" });
  if (!response.ok) throw new Error("자료 상태를 불러오지 못했습니다.");
  meta = await response.json();
  $("#build-date").textContent = "자료 생성 " + meta.builtAt.slice(0, 10);
  await navigate();
} catch (e) {
  $("#main").innerHTML =
    `<div class="empty"><strong>자료를 불러오지 못했습니다.</strong>${esc(e.message)}</div>`;
}
