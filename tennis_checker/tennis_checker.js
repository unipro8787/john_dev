// Hwaseong Integrated Reservation System (yeyak.hscity.go.kr) — 왕배산체육공원 테니스장 availability checker.
// Checks courts 1-8 and prints every time slot marked "가" (예약가능 / Available).
//
// Usage: node tennis_checker.js [daysAhead]
//   daysAhead - how many days from today to scan (default: today ~ end of current month)
//
// Results are printed to the console AND saved to a .txt file
// (availability_YYYY-MM.txt) in this same folder.
//
// Requires Node.js 18+ (built-in fetch). No external dependencies.

const fs = require("fs");
const path = require("path");

const BASE_URL = "https://yeyak.hscity.go.kr";
const LOGIN_URL = `${BASE_URL}/login/loginAjax.do`;
const RESERVE_LIST_URL = `${BASE_URL}/stadium/stadiumReserveUseList.do`;

// --- Credentials -------------------------------------------------------
// Login isn't actually required to read availability (the data endpoint is
// public), but we log in anyway so the session matches what you'd see
// signed in on the site.
//
// Credentials come from environment variables (HSCITY_ID / HSCITY_PW),
// loaded from a local .env file next to this script if present. .env is
// gitignored — keep it private and never commit it.
function loadDotEnv() {
  const envPath = path.join(__dirname, ".env");
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx === -1) continue;
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
    if (!(key in process.env)) process.env[key] = value;
  }
}
loadDotEnv();

const CREDENTIALS = {
  memberId: process.env.HSCITY_ID,
  userPassword: process.env.HSCITY_PW,
};

if (!CREDENTIALS.memberId || !CREDENTIALS.userPassword) {
  console.error(
    "HSCITY_ID / HSCITY_PW 환경변수가 설정되지 않았습니다.\n" +
      ".env 파일을 만들거나 환경변수를 설정한 뒤 다시 실행하세요. (.env.example 참고)"
  );
  process.exit(1);
}

// Wangbaesan Sports Park (왕배산체육공원) tennis courts 1-8 -> stadiumIdx
const COURTS = {
  1: 230,
  2: 231,
  3: 232,
  4: 233,
  5: 235,
  6: 236,
  7: 237,
  8: 238,
};

function pad2(n) {
  return String(n).padStart(2, "0");
}

function ymd(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function endOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

async function login(cookieJar) {
  const body = new URLSearchParams({
    memberId: CREDENTIALS.memberId,
    userPassword: CREDENTIALS.userPassword,
    returnUrl: "",
  });

  const res = await fetch(LOGIN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: body.toString(),
  });

  const setCookie = res.headers.get("set-cookie");
  if (setCookie) {
    setCookie.split(",").forEach((part) => {
      const kv = part.split(";")[0].trim();
      if (kv.includes("=")) cookieJar.set(kv.split("=")[0], kv);
    });
  }

  const data = await res.json();
  if (data.RESULT !== "SUCCESS") {
    console.warn(`Login did not succeed (RESULT=${data.RESULT}). Continuing without a session — availability data is public.`);
    return false;
  }
  return true;
}

function cookieHeader(cookieJar) {
  return Array.from(cookieJar.values()).join("; ");
}

async function fetchMonth(stadiumIdx, year, month, cookieJar) {
  const body = new URLSearchParams({
    stadiumIdx: String(stadiumIdx),
    searchYear: String(year),
    searchMonth: pad2(month),
  });

  const res = await fetch(RESERVE_LIST_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest",
      Cookie: cookieHeader(cookieJar),
    },
    body: body.toString(),
  });

  return res.json();
}

// Mirrors the site's own client-side classification logic
// (see reserveStatus() in stadiumDetail.do) so results match what the
// "예약현황" tab shows in the browser.
function classify(item) {
  if (item.applyStatusCd === null) return "AVAILABLE"; // 가 / 예약가능
  if (item.applyStatusCd === "AP") {
    return item.payDivCd === "PC" || item.payDivCd === "EC" ? "BOOKED" : "PAYMENT_PENDING";
  }
  if (item.applyStatusCd === "DE") return "HOLD"; // 승인보류
  if (item.applyStatusCd === "RC") return "SCHEDULED"; // 승인예정
  if (item.applyStatusCd === "CLOSE") return "CLOSED"; // 예약불가
  return "UNKNOWN";
}

async function checkCourt(courtNum, stadiumIdx, todayStr, endStr, cookieJar, monthCache) {
  const results = [];
  const start = new Date(todayStr);
  const end = new Date(endStr);

  const months = new Set();
  for (let d = new Date(start); d <= end; d.setMonth(d.getMonth() + 1, 1)) {
    months.add(`${d.getFullYear()}-${pad2(d.getMonth() + 1)}`);
  }
  // ensure the end month itself is included even if loop stepped past it
  months.add(`${end.getFullYear()}-${pad2(end.getMonth() + 1)}`);

  for (const key of months) {
    const [year, month] = key.split("-").map(Number);
    const cacheKey = `${stadiumIdx}:${key}`;
    if (!monthCache.has(cacheKey)) {
      monthCache.set(cacheKey, await fetchMonth(stadiumIdx, year, month, cookieJar));
    }
    const data = monthCache.get(cacheKey);
    for (const item of data.useCntList || []) {
      if (!item.sorDate) continue;
      if (item.sorDate < todayStr || item.sorDate > endStr) continue;
      if (classify(item) !== "AVAILABLE") continue;
      results.push({
        court: courtNum,
        date: item.sorDate,
        time: `${item.stadiumBeginHm}~${item.stadiumEndHm}`,
      });
    }
  }
  return results;
}

async function main() {
  const today = new Date();
  const daysArg = process.argv[2] ? parseInt(process.argv[2], 10) : null;
  const end = daysArg
    ? new Date(today.getFullYear(), today.getMonth(), today.getDate() + daysArg)
    : endOfMonth(today);
  const todayStr = ymd(today);
  const endStr = ymd(end);

  const cookieJar = new Map();
  await login(cookieJar);

  const lines = [];
  lines.push(`왕배산체육공원 테니스장 - "가"(예약가능) 시간대 조회`);
  lines.push(`기간: ${todayStr} ~ ${endStr}`);
  lines.push("");

  const monthCache = new Map();
  const allResults = [];
  for (const [courtNum, stadiumIdx] of Object.entries(COURTS)) {
    const results = await checkCourt(Number(courtNum), stadiumIdx, todayStr, endStr, cookieJar, monthCache);
    allResults.push(...results);
  }

  if (allResults.length === 0) {
    lines.push("현재 조회 기간 내 예약 가능한 시간대가 없습니다.");
  } else {
    // group by date, then court
    const byDate = new Map();
    for (const r of allResults) {
      if (!byDate.has(r.date)) byDate.set(r.date, []);
      byDate.get(r.date).push(r);
    }

    const sortedDates = Array.from(byDate.keys()).sort();
    for (const date of sortedDates) {
      lines.push(`■ ${date}`);
      const entries = byDate.get(date).sort((a, b) => a.court - b.court || a.time.localeCompare(b.time));
      for (const e of entries) {
        lines.push(`   코트 ${e.court}번  |  ${e.time}`);
      }
    }
    lines.push("");
    lines.push(`총 ${allResults.length}개의 예약 가능 시간대를 찾았습니다.`);
  }

  const output = lines.join("\n");
  console.log(output);

  const outFileName = `availability_${today.getFullYear()}-${pad2(today.getMonth() + 1)}.txt`;
  const outPath = path.join(__dirname, outFileName);
  fs.writeFileSync(outPath, output + "\n", "utf8");
  console.log(`\n결과 파일 저장: ${outPath}`);
}

main().catch((err) => {
  console.error("오류 발생:", err);
  process.exit(1);
});
