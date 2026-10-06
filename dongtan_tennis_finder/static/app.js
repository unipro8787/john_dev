(() => {
  const DOW = ["일", "월", "화", "수", "목", "금", "토"];

  const startInput = document.getElementById("start-date");
  const endInput = document.getElementById("end-date");
  const quickRange = document.getElementById("quick-range");
  const timeRange = document.getElementById("time-range");
  const timeStartInput = document.getElementById("time-start");
  const timeEndInput = document.getElementById("time-end");
  const facilityFilter = document.getElementById("facility-filter");
  const cityTabs = document.getElementById("city-tabs");
  const searchBtn = document.getElementById("search-btn");
  const statusArea = document.getElementById("status-area");
  const resultsEl = document.getElementById("results");

  let selectedFacilities = new Set();
  let allFacilities = [];

  // toISOString()은 UTC라 한국 시간 자정~오전 9시에는 하루 전 날짜가 된다
  function toISODate(d) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function setQuickRange(days) {
    const today = new Date();
    const start = new Date(today);
    const end = new Date(today);
    end.setDate(end.getDate() + days - 1);
    startInput.value = toISODate(start);
    endInput.value = toISODate(end);
    [...quickRange.querySelectorAll(".quick-btn")].forEach((btn) => {
      btn.classList.toggle("active", Number(btn.dataset.days) === days);
    });
  }

  quickRange.addEventListener("click", (e) => {
    const btn = e.target.closest(".quick-btn");
    if (!btn) return;
    setQuickRange(Number(btn.dataset.days));
  });

  [startInput, endInput].forEach((el) => {
    el.addEventListener("change", () => {
      [...quickRange.querySelectorAll(".quick-btn")].forEach((btn) => btn.classList.remove("active"));
    });
  });

  function setTimeRange(startTime, endTime) {
    timeStartInput.value = startTime;
    timeEndInput.value = endTime;
    [...timeRange.querySelectorAll(".time-btn")].forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.start === startTime && btn.dataset.end === endTime);
    });
  }

  timeRange.addEventListener("click", (e) => {
    const btn = e.target.closest(".time-btn");
    if (!btn) return;
    setTimeRange(btn.dataset.start, btn.dataset.end);
  });

  [timeStartInput, timeEndInput].forEach((el) => {
    el.addEventListener("change", () => {
      [...timeRange.querySelectorAll(".time-btn")].forEach((btn) => btn.classList.remove("active"));
    });
  });

  const PREF_KEY = "tennisFinder.v3"; // { city, selected: { 도시명: [시설명...] } }
  const OLD_KEY = "selectedFacilities.v2"; // 화성만 있던 시절의 선택값 (한 번 옮겨 담는다)
  let cities = [];
  let currentCity = null;
  const selectedByCity = new Map(); // 도시명 → Set(시설명)

  function savePrefs() {
    try {
      const selected = {};
      for (const [city, set] of selectedByCity) selected[city] = [...set];
      localStorage.setItem(PREF_KEY, JSON.stringify({ city: currentCity, selected }));
    } catch (e) {
      // 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서는 기억만 못 할 뿐 검색은 그대로 된다
    }
  }

  function loadPrefs() {
    let prefs = null;
    try {
      prefs = JSON.parse(localStorage.getItem(PREF_KEY) || "null");
      if (!prefs) {
        const old = JSON.parse(localStorage.getItem(OLD_KEY) || "null");
        if (Array.isArray(old)) prefs = { city: "화성시", selected: { 화성시: old } };
      }
    } catch (e) {
      prefs = null;
    }
    cities.forEach((city) => {
      const names = city.regions.flatMap((r) => r.facilities.map((f) => f.name));
      const saved = prefs && prefs.selected && Array.isArray(prefs.selected[city.name])
        ? prefs.selected[city.name].filter((n) => names.includes(n))
        : null;
      selectedByCity.set(city.name, new Set(saved && saved.length ? saved : names));
    });
    const savedCity = prefs && cities.some((c) => c.name === prefs.city) ? prefs.city : null;
    currentCity = savedCity || cities[0].name;
  }

  function syncRegionToggles() {
    facilityFilter.querySelectorAll(".region-group").forEach((group) => {
      const chips = [...group.querySelectorAll(".facility-chip")];
      const allOn = chips.every((c) => selectedFacilities.has(c.dataset.name));
      const toggle = group.querySelector(".region-toggle");
      toggle.textContent = allOn ? "모두 해제" : "모두 선택";
      toggle.setAttribute("aria-pressed", String(allOn));
    });
  }

  function setChip(chip, on) {
    const name = chip.dataset.name;
    if (on) selectedFacilities.add(name);
    else selectedFacilities.delete(name);
    chip.classList.toggle("active", on);
    chip.setAttribute("aria-pressed", String(on));
  }

  function renderCityTabs() {
    cityTabs.innerHTML = "";
    cities.forEach((city) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "city-tab" + (city.name === currentCity ? " active" : "");
      tab.setAttribute("aria-pressed", String(city.name === currentCity));
      const courts = city.regions.reduce((n, r) => n + r.facilities.reduce((m, f) => m + f.courts.length, 0), 0);
      tab.innerHTML = `${city.name} <span>${courts}</span>`;
      tab.addEventListener("click", () => {
        if (city.name === currentCity) return;
        currentCity = city.name;
        renderCityTabs();
        renderFacilities();
        savePrefs();
        runSearch();
      });
      cityTabs.appendChild(tab);
    });
  }

  function renderFacilities() {
    const city = cities.find((c) => c.name === currentCity);
    selectedFacilities = selectedByCity.get(city.name);
    allFacilities = city.regions.flatMap((r) => r.facilities.map((f) => f.name));
    facilityFilter.innerHTML = "";

    city.regions.forEach((region) => {
      const group = document.createElement("div");
      group.className = "region-group";

      const head = document.createElement("div");
      head.className = "region-head";
      const title = document.createElement("span");
      title.className = "region-name";
      const courtCount = region.facilities.reduce((n, f) => n + f.courts.length, 0);
      title.textContent = city.name === "부천시"
        ? `${region.name} · ${region.facilities.length}곳`
        : `${region.name} · ${courtCount}면`;
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "region-toggle";
      head.append(title, toggle);
      group.appendChild(head);

      const chips = document.createElement("div");
      chips.className = "region-chips";
      region.facilities.forEach((f) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "facility-chip";
        chip.dataset.name = f.name;
        chip.textContent = f.name.replace(/ ?테니스장$/, "");
        chip.title = `${f.name}${f.note ? " · " + f.note : ""}`;
        setChip(chip, selectedFacilities.has(f.name));
        chip.addEventListener("click", () => {
          setChip(chip, !selectedFacilities.has(f.name));
          syncRegionToggles();
          savePrefs();
        });
        chips.appendChild(chip);
      });
      group.appendChild(chips);

      toggle.addEventListener("click", () => {
        const list = [...chips.querySelectorAll(".facility-chip")];
        const allOn = list.every((c) => selectedFacilities.has(c.dataset.name));
        list.forEach((c) => setChip(c, !allOn));
        syncRegionToggles();
        savePrefs();
      });

      facilityFilter.appendChild(group);
    });

    const note = document.createElement("p");
    note.className = "city-note";
    note.innerHTML = `예약은 <a href="${city.booking_url}" target="_blank" rel="noopener">${city.booking_name}</a>에서 직접 하세요.` +
      (city.name === "부천시" ? " 부천은 코트별이 아니라 시설 단위로 예약 가능 여부가 나오며, 다음 달 예약은 매달 20일부터 열립니다." : "") +
      (city.day_only ? ` ${city.name.replace(/시$/, "")}는 날짜 단위로만 예약 가능 여부를 공개해서 "그날 빈 시간 있음"으로 표시하고, 시간대 필터는 적용되지 않습니다.` : "") +
      (city.name === "서울 강남구"
        ? " 강남구는 매월 25일까지 다음 달을 온라인으로 신청받고, 그 뒤 남은 시간(☎ 표시)은 시설에 전화로 예약합니다. 봉은 02-2176-0890 · 포이 02-2176-0876 · 세곡 02-2176-0870. 다음 달은 신청기간이 끝난 26일부터 보입니다."
        : "");
    facilityFilter.appendChild(note);
    syncRegionToggles();
  }

  async function loadFacilities() {
    const res = await fetch("/api/facilities");
    const data = await res.json();
    cities = data.cities;
    facilityUrls = new Map(cities.flatMap((c) => c.regions.flatMap((r) => r.facilities.map((f) => [f.name, f.url]))));
    loadPrefs();
    renderCityTabs();
    renderFacilities();
  }

  function setStatus(html, isError = false) {
    statusArea.innerHTML = html
      ? `<div class="status-msg${isError ? " error" : ""}">${html}</div>`
      : "";
  }

  let facilityUrls = new Map(); // 시설명 → 테니스장 안내 페이지

  function dayInfo(dateStr) {
    const d = new Date(dateStr + "T00:00:00");
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diff = Math.round((d - today) / 86400000);
    return {
      month: d.getMonth() + 1,
      day: d.getDate(),
      dow: d.getDay(),
      tag: diff === 0 ? "오늘" : diff === 1 ? "내일" : "",
    };
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function slotChip(s) {
    const chip = el("span", "time-slot" + (s.day_only ? " day-only" : "") + (s.phone_only ? " phone-only" : ""));
    // 경주처럼 날짜 단위로만 공개하는 곳은 시간 대신 "빈 시간 있음"으로 보여 준다
    chip.textContent = s.day_only ? "그날 빈 시간 있음" : `${s.begin}~${s.end}`;
    if (s.day_only) chip.title = "몇 시가 비었는지는 예약 사이트에서 날짜를 눌러 확인하세요";
    if (s.phone_only) {
      // 강남구: 온라인 신청기간이 끝난 달의 남은 칸은 시설에 전화로 예약한다
      chip.textContent = `☎ ${s.begin}~${s.end}`;
      chip.title = "온라인 신청기간이 끝나 시설에 전화로 예약해야 하는 빈 시간";
    }
    return chip;
  }

  function renderResults(items) {
    resultsEl.innerHTML = "";
    if (items.length === 0) {
      setStatus("고른 기간·시간에 비어 있는 코트가 없어요. 기간을 넓히거나 다른 시간대로 찾아보세요.");
      return;
    }
    setStatus("");

    // 날짜 → 시설 → 코트 → 빈 시간
    const byDate = new Map();
    for (const item of items) {
      if (!byDate.has(item.date)) byDate.set(item.date, new Map());
      const byFacility = byDate.get(item.date);
      if (!byFacility.has(item.facility)) byFacility.set(item.facility, new Map());
      const byCourt = byFacility.get(item.facility);
      if (!byCourt.has(item.court)) byCourt.set(item.court, []);
      byCourt.get(item.court).push(item);
    }

    const summary = el("div", "result-summary");
    const first = dayInfo(startInput.value);
    const last = dayInfo(endInput.value || startInput.value);
    const range = startInput.value === (endInput.value || startInput.value)
      ? `${first.month}월 ${first.day}일`
      : `${first.month}월 ${first.day}일 ~ ${last.month === first.month ? "" : last.month + "월 "}${last.day}일`;
    const strong = el("b", null, `${byDate.size}일에 빈 시간 ${items.length}칸`);
    summary.append(strong, el("span", null, `${currentCity} · ${range}`));
    resultsEl.appendChild(summary);

    for (const [dateStr, byFacility] of byDate) {
      const info = dayInfo(dateStr);
      const group = el("div", "day-group" + (info.dow === 6 ? " sat" : info.dow === 0 ? " sun" : ""));

      const header = el("div", "day-header");
      const num = el("span", "day-num");
      num.append(el("small", null, `${info.month}.`), String(info.day));
      header.append(num, el("span", "dow", `${DOW[info.dow]}요일`));
      if (info.tag) header.appendChild(el("span", "day-tag", info.tag));
      group.appendChild(header);

      const body = el("div", "day-body");
      for (const [facility, byCourt] of byFacility) {
        const block = el("div", "fac-block");
        const name = el("div", "fac-name");
        const url = facilityUrls.get(facility);
        if (url) {
          const a = el("a", null, facility);
          a.href = url;
          name.appendChild(a);
        } else {
          name.textContent = facility;
        }
        block.appendChild(name);

        // 부천처럼 시설 단위로만 나오는 곳은 코트 이름 칸을 비운다
        const solo = byCourt.size === 1 && byCourt.has("시설 대관");
        for (const [court, slots] of byCourt) {
          const label = court.replace(/ 코트/, "");
          const row = el("div", "court-row" + (solo ? " solo" : label.length > 4 ? " long" : ""));
          if (!solo) row.appendChild(el("div", "court-name", label));
          const slotsEl = el("div", "time-slots");
          slots.sort((a, b) => a.begin.localeCompare(b.begin)).forEach((s) => slotsEl.appendChild(slotChip(s)));
          row.appendChild(slotsEl);
          block.appendChild(row);
        }
        body.appendChild(block);
      }
      group.appendChild(body);
      resultsEl.appendChild(group);
    }
  }

  async function runSearch() {
    const start = startInput.value;
    const end = endInput.value || start;
    if (!start) {
      setStatus("시작일을 선택해주세요.", true);
      return;
    }
    if (selectedFacilities.size === 0) {
      resultsEl.innerHTML = "";
      setStatus("시설을 하나 이상 골라 주세요.", true);
      return;
    }

    searchBtn.disabled = true;
    searchBtn.textContent = "찾는 중…";
    setStatus("각 예약 사이트에서 빈 시간을 모으는 중이에요…");
    resultsEl.innerHTML = "";

    try {
      const params = new URLSearchParams({ start, end });
      for (const f of selectedFacilities) params.append("facility", f);
      if (timeStartInput.value) params.set("time_start", timeStartInput.value);
      if (timeEndInput.value) params.set("time_end", timeEndInput.value);

      const res = await fetch(`/api/search?${params.toString()}`);
      const data = await res.json();

      if (!res.ok) {
        setStatus(data.error || "검색 중 오류가 발생했습니다.", true);
        return;
      }

      renderResults(data.results);
    } catch (err) {
      setStatus("서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.", true);
    } finally {
      searchBtn.disabled = false;
      searchBtn.textContent = "빈 코트 찾기";
    }
  }

  searchBtn.addEventListener("click", runSearch);

  (async () => {
    await loadFacilities();
    setQuickRange(7);
    setTimeRange("", "");
    runSearch();
  })();
})();
