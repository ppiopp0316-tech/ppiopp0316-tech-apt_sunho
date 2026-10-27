import test from "node:test";
import assert from "node:assert/strict";
import {
  filterApts,
  filterKic,
  classifyKic,
  bounds,
  addMonths,
  naverUrl,
  esc,
  safeUrl,
  csvText,
  brokerStats,
  managedSummary,
  validateKic,
  KIC_COLUMNS,
} from "../sites_app/logic.mjs";
const row = {
  센터명: "A",
  주소: "경기도 주소",
  사업상태: "공사 중",
  준공예정일: "2027-03",
  입주시작일: "미확인",
};
test("KIC month precision and 12 calendar months", () => {
  assert.deepEqual(bounds("2026-10"), ["2026-10-01", "2026-10-31"]);
  assert.equal(addMonths("2024-02-29", 12), "2025-02-28");
  assert.equal(classifyKic(row, "2026-10-27"), "준공 예정 · 입주일 미확인");
  assert.equal(
    classifyKic({ ...row, 준공예정일: "2028-01" }, "2026-10-27"),
    "기간 외·완료",
  );
  assert.equal(bounds("2027-02-29"), null);
});
test("KIC separates candidate queue from scheduled results", () => {
  const rows = [row, { ...row, 센터명: "B", 준공예정일: "미확인" }];
  assert.equal(filterKic(rows, {}, "2026-10-27").length, 1);
  assert.equal(
    filterKic(rows, { scope: "unknown" }, "2026-10-27")[0]["센터명"],
    "B",
  );
  assert.equal(filterKic(rows, { scope: "archive" }, "2026-10-27").length, 2);
});
test("Five apartment filters combine and support literal keywords", () => {
  const rows = [
    {
      단지명: "테스트[1]",
      주소: "안양",
      시공사: "DL",
      시도: "경기",
      입주예정월: "2027-03",
      세대수: 1000,
    },
    {
      단지명: "기타",
      주소: "서울",
      시공사: "DL",
      시도: "서울",
      입주예정월: "2027-03",
      세대수: 500,
    },
  ];
  assert.equal(
    filterApts(rows, {
      sido: "경기도",
      year: "2027",
      month: "03",
      minimum: 900,
      keyword: "[1]",
    }).length,
    1,
  );
  assert.equal(filterApts(rows, { keyword: "없는값" }).length, 0);
});
test("Naver query safely encodes apartment name", () => {
  const u = new URL(naverUrl({ 단지명: "A & B", 시도: "경기도" }));
  assert.equal(u.searchParams.get("query"), "경기도 A & B");
  assert.equal(u.hash, "");
});
test("Untrusted data stays text and unsafe links are rejected", () => {
  assert.equal(safeUrl("javascript:alert(1)"), "");
  assert.equal(safeUrl("data:text/html,hi"), "");
  assert.ok(!esc('<img onerror="x">').includes("<"));
  assert.ok(csvText([{ a: '=HYPERLINK("x")' }], ["a"]).includes("'=HYPERLINK"));
});
test("Brokers exclude future registrations and aggregate recent days", () => {
  const rows = [
    { 지역: "서울 마포구", 개설등록일자: "2026-10-27" },
    { 지역: "서울 마포구", 개설등록일자: "2026-10-24" },
    { 지역: "서울 마포구", 개설등록일자: "2027-01-01" },
  ];
  const stats = brokerStats(rows, 30, 2, "2026-10-27");
  assert.equal(stats[0]["신규수"], 2);
  assert.equal(stats[0]["오늘신규"], 1);
  assert.equal(stats[0]["7일신규"], 2);
});
test("Managed salesperson and measured blog author are separate", () => {
  const snap = {
    queries: { q: { time: "2026-10-15T12:00:00Z" } },
    offices: [
      {
        name: "업체",
        keywords: ["q"],
        matches: [
          {
            keyword: "q",
            rank: 3,
            author: "블로그작성자",
            url: "https://blog.naver.com/example",
          },
        ],
      },
    ],
  };
  const [result] = managedSummary(
    [{ 업체명: "업체", 영업담당자: "영업담당" }],
    snap,
  );
  assert.equal(result["영업담당자"], "영업담당");
  assert.equal(result.proof.matches[0].author, "블로그작성자");
  assert.equal(result["최고순위"], 3);
});
test("Invalid or empty upload cannot replace KIC", () => {
  assert.throws(() => validateKic([]));
  assert.throws(() => validateKic([{ 센터명: "A" }]));
  const good = Object.fromEntries(KIC_COLUMNS.map((c) => [c, "미확인"]));
  Object.assign(good, row, { 출처URL: "https://example.gov.kr" });
  assert.equal(validateKic([good]).length, 1);
  assert.throws(() => validateKic([{ ...good, 준공예정일: "2027-13" }]));
});
