export const SIDOS = [
  "서울특별시",
  "부산광역시",
  "대구광역시",
  "인천광역시",
  "광주광역시",
  "대전광역시",
  "울산광역시",
  "세종특별자치시",
  "경기도",
  "강원특별자치도",
  "충청북도",
  "충청남도",
  "전북특별자치도",
  "전라남도",
  "경상북도",
  "경상남도",
  "제주특별자치도",
];
const aliases = {
  서울: "서울특별시",
  서울시: "서울특별시",
  부산: "부산광역시",
  대구: "대구광역시",
  인천: "인천광역시",
  광주: "광주광역시",
  대전: "대전광역시",
  울산: "울산광역시",
  세종: "세종특별자치시",
  경기: "경기도",
  강원: "강원특별자치도",
  강원도: "강원특별자치도",
  충북: "충청북도",
  충남: "충청남도",
  전북: "전북특별자치도",
  전라북도: "전북특별자치도",
  전남: "전라남도",
  경북: "경상북도",
  경남: "경상남도",
  제주: "제주특별자치도",
  제주도: "제주특별자치도",
};
export const normalizeSido = (s) => aliases[s] || s || "";
export const KIC_COLUMNS = [
  "센터명",
  "시도",
  "시군구",
  "주소",
  "사업상태",
  "허가일",
  "착공일",
  "준공예정일",
  "사용승인일",
  "입주시작일",
  "시행사",
  "시공사",
  "연락처",
  "공식출처",
  "출처URL",
  "최근확인",
  "검증상태",
];
export const unknown = (v) =>
  ["", "미확인", "미정", "-", "확인중", "nan", "None", "NaT"].includes(
    String(v ?? "").trim(),
  );
export const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const safeUrl = (v) => {
  try {
    const u = new URL(v);
    return ["https:", "http:"].includes(u.protocol) ? esc(u.href) : "";
  } catch {
    return "";
  }
};
export const seoulToday = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export function addMonths(day, n) {
  const [y, m, d] = day.split("-").map(Number);
  const last = new Date(Date.UTC(y, m + n, 0)).getUTCDate();
  return new Date(Date.UTC(y, m - 1 + n, Math.min(d, last)))
    .toISOString()
    .slice(0, 10);
}
export function bounds(v) {
  v = String(v ?? "").trim();
  if (unknown(v)) return null;
  if (!/^\d{4}-\d{2}(-\d{2})?$/.test(v)) return null;
  const [y, m, d] = v.split("-").map(Number);
  if (m < 1 || m > 12 || y < 1900) return null;
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  if (d && (d < 1 || d > last)) return null;
  return d ? [v, v] : [v + "-01", v + "-" + last];
}
export function classifyKic(r, today = seoulToday()) {
  const end = addMonths(today, 12),
    move = bounds(r["입주시작일"]),
    complete = bounds(r["준공예정일"]),
    approved = bounds(r["사용승인일"]);
  const within = (p) => p && p[1] >= today && p[0] <= end;
  if (move) return within(move) ? "입주 예정" : "기간 외·완료";
  if (/입주완료|준공완료|사용승인완료/.test(r["사업상태"] || ""))
    return "기간 외·완료";
  if (approved && approved[1] < today) return "기간 외·완료";
  if (complete)
    return within(complete) ? "준공 예정 · 입주일 미확인" : "기간 외·완료";
  return /공사|착공|건설|허가/.test(r["사업상태"] || "")
    ? "공사 중 · 일정 미확인"
    : "기간 외·완료";
}
export const targetMonth = (r) =>
  String(unknown(r["입주시작일"]) ? r["준공예정일"] : r["입주시작일"]).slice(
    0,
    7,
  );
export function filterApts(rows, f = {}) {
  const kw = (f.keyword || "").trim().toLocaleLowerCase();
  return rows
    .filter(
      (r) =>
        (Number(r["세대수"]) || 0) >= Number(f.minimum ?? 300) &&
        (!f.sido || normalizeSido(r["시도"]) === f.sido) &&
        (!f.year || String(r["입주예정월"]).slice(0, 4) === f.year) &&
        (!f.month || String(r["입주예정월"]).slice(5, 7) === f.month) &&
        (!kw ||
          ["단지명", "주소", "시공사"].some((k) =>
            String(r[k] || "")
              .toLocaleLowerCase()
              .includes(kw),
          )),
    )
    .sort((a, b) =>
      f.sort === "units"
        ? Number(b["세대수"]) - Number(a["세대수"])
        : String(a["입주예정월"]).localeCompare(String(b["입주예정월"])) ||
          String(a["단지명"]).localeCompare(String(b["단지명"])),
    );
}
export function filterKic(rows, f = {}, today = seoulToday()) {
  return rows
    .map((r) => ({ ...r, 구분: classifyKic(r, today) }))
    .filter((r) => {
      const type = r["구분"],
        month = targetMonth(r),
        kw = (f.keyword || "").trim().toLowerCase();
      return (
        (f.scope === "archive" ||
          (f.scope === "unknown"
            ? type === "공사 중 · 일정 미확인"
            : ["입주 예정", "준공 예정 · 입주일 미확인"].includes(type))) &&
        (!f.sido || normalizeSido(r["시도"]) === f.sido) &&
        (!f.year || month.slice(0, 4) === f.year) &&
        (!f.month || month.slice(5, 7) === f.month) &&
        (!f.status || type === f.status) &&
        (!kw ||
          ["센터명", "주소", "시행사", "시공사"].some((k) =>
            String(r[k] || "")
              .toLowerCase()
              .includes(kw),
          ))
      );
    })
    .sort(
      (a, b) =>
        targetMonth(a).localeCompare(targetMonth(b)) ||
        a["센터명"].localeCompare(b["센터명"]),
    );
}
export function recentRows(rows, days, today = seoulToday()) {
  const end = Date.parse(today + "T00:00:00Z"),
    start = new Date(end - (days - 1) * 86400000).toISOString().slice(0, 10);
  return rows.filter(
    (r) => r["개설등록일자"] >= start && r["개설등록일자"] <= today,
  );
}
export function filterBrokers(rows, f = {}, today = seoulToday()) {
  const source = f.recent
    ? recentRows(rows, Number(f.days || 30), today)
    : rows;
  const kw = (f.keyword || "").trim().toLowerCase();
  return source
    .filter(
      (r) =>
        (!f.sido || normalizeSido(r["시도"]) === f.sido) &&
        (!kw ||
          ["중개사무소명", "주소", "소재지도로명주소", "대표자명"].some((k) =>
            String(r[k] || "")
              .toLowerCase()
              .includes(kw),
          )),
    )
    .sort((a, b) =>
      String(b["개설등록일자"]).localeCompare(String(a["개설등록일자"])),
    );
}
export function brokerStats(rows, days, min, today = seoulToday()) {
  const recent = recentRows(rows, days, today),
    week = new Set(recentRows(rows, 7, today));
  const groups = new Map();
  for (const r of recent) {
    const region = r["지역"];
    if (!region) continue;
    const g = groups.get(region) || {
      지역: region,
      신규수: 0,
      오늘신규: 0,
      "7일신규": 0,
      최근개업일: "",
    };
    g["신규수"]++;
    if (r["개설등록일자"] === today) g["오늘신규"]++;
    if (week.has(r)) g["7일신규"]++;
    if (r["개설등록일자"] > g["최근개업일"])
      g["최근개업일"] = r["개설등록일자"];
    groups.set(region, g);
  }
  return [...groups.values()]
    .filter((g) => g["신규수"] >= min)
    .sort(
      (a, b) =>
        b["오늘신규"] - a["오늘신규"] ||
        b["7일신규"] - a["7일신규"] ||
        b["신규수"] - a["신규수"],
    );
}
export function managedSummary(offices, snap) {
  const proof = new Map(snap.offices.map((o) => [o.name, o]));
  return offices.map((o) => {
    const p = proof.get(o["업체명"]) || { keywords: [], matches: [] },
      matches = p.matches
        .filter((m) => m.rank <= 10)
        .sort((a, b) => a.rank - b.rank),
      measured = p.keywords.filter((q) => snap.queries[q]?.time),
      top = new Map();
    for (const m of matches) {
      if (!top.has(m.keyword) && top.size < 5) top.set(m.keyword, m.rank);
    }
    const status = matches.length
      ? `10위 이내 ${top.size}개 확인`
      : !p.keywords.length
        ? "주소 확인 필요"
        : !measured.length
          ? "미측정 · 조회 대기"
          : "10위 이내 확인 키워드 없음";
    return {
      ...o,
      최고순위: matches[0]?.rank ?? null,
      "실제 노출키워드": [...top].map(([q, r]) => `${q} (${r}위)`).join(", "),
      확인키워드수: top.size,
      측정상태:
        status +
        (measured.length && measured.length < p.keywords.length
          ? " · 일부 미측정"
          : ""),
      게시물: matches[0]?.url || "",
      측정검색어수: `${measured.length}/${p.keywords.length}`,
      측정시각:
        measured
          .map((q) => snap.queries[q].time)
          .sort()
          .at(-1) || "",
      proof: p,
    };
  });
}
export function naverUrl(r) {
  return (
    "https://land.naver.com/search/complex.nhn?query=" +
    encodeURIComponent(
      [r["시도"], r["시군구"], r["단지명"]].filter(Boolean).join(" "),
    )
  );
}
export function csvText(rows, columns) {
  const cell = (v) => {
    let s = String(v ?? "");
    if (/^[\s]*[=+@-]/.test(s)) s = "'" + s;
    return '"' + s.replaceAll('"', '""') + '"';
  };
  return (
    "\uFEFF" +
    [
      columns.map(cell).join(","),
      ...rows.map((r) => columns.map((c) => cell(r[c])).join(",")),
    ].join("\r\n")
  );
}
export function validateKic(rows) {
  if (!rows.length)
    throw new Error("센터 데이터가 0건입니다. 기존 자료를 유지합니다.");
  const seen = new Set();
  for (const [i, r] of rows.entries()) {
    for (const col of KIC_COLUMNS)
      if (!(col in r)) throw new Error("필수 17개 열이 필요합니다: " + col);
    if (!r["센터명"] || !r["주소"])
      throw new Error(`${i + 2}행: 센터명과 주소는 필수입니다.`);
    const k = r["센터명"] + "|" + r["주소"];
    if (seen.has(k)) throw new Error(`${i + 2}행: 센터명·주소 중복입니다.`);
    seen.add(k);
    for (const c of [
      "허가일",
      "착공일",
      "준공예정일",
      "사용승인일",
      "입주시작일",
      "최근확인",
    ])
      if (!unknown(r[c]) && !bounds(r[c]))
        throw new Error(`${i + 2}행: ${c} 날짜 형식 오류`);
    if (!safeUrl(r["출처URL"]))
      throw new Error(`${i + 2}행: 공식 출처 URL이 필요합니다.`);
  }
  return rows;
}
