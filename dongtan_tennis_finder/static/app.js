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

  function toISODate(d) {
    return d.toISOString().slice(0, 10);
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
      (city.day_only ? ` ${city.name.replace(/시$/, "")}는 날짜 단위로만 예약 가능 여부를 공개해서 "그날 빈 시간 있음"으로 표시하고, 시간대 필터는 적용되지 않습니다.` : "");
    facilityFilter.appendChild(note);
    syncRegionToggles();
  }

  async function loadFacilities() {
    const res = await fetch("/api/facilities");
    const data = await res.json();
    cities = data.cities;
    loadPrefs();
    renderCityTabs();
    renderFacilities();
  }

  function setStatus(html, isError = false) {
    statusArea.innerHTML = html
      ? `<div class="status-msg${isError ? " error" : ""}">${html}</div>`
      : "";
  }

  function dowLabel(dateStr) {
    const d = new Date(dateStr + "T00:00:00");
    return DOW[d.getDay()];
  }

  function renderResults(items) {
    resultsEl.innerHTML = "";
    if (items.length === 0) {
      setStatus("조회 기간 내 예약 가능한 시간대가 없습니다.");
      return;
    }
    setStatus("");

    const byDate = new Map();
    for (const item of items) {
      if (!byDate.has(item.date)) byDate.set(item.date, new Map());
      const byCourt = byDate.get(item.date);
      const key = `${item.facility} · ${item.court}`;
      if (!byCourt.has(key)) byCourt.set(key, []);
      byCourt.get(key).push(item);
    }

    for (const [dateStr, byCourt] of byDate) {
      const group = document.createElement("div");
      group.className = "day-group";

      const header = document.createElement("div");
      header.className = "day-header";
      header.innerHTML = `${dateStr} <span class="dow">(${dowLabel(dateStr)})</span>`;
      group.appendChild(header);

      for (const [courtKey, slots] of byCourt) {
        const row = document.createElement("div");
        row.className = "court-row";

        const name = document.createElement("div");
        name.className = "court-name";
        const [facility, court] = courtKey.split(" · ");
        name.innerHTML = `${facility}<br><b>${court}</b>`;
        row.appendChild(name);

        const slotsEl = document.createElement("div");
        slotsEl.className = "time-slots";
        slots
          .sort((a, b) => a.begin.localeCompare(b.begin))
          .forEach((s) => {
            const chip = document.createElement("span");
            chip.className = "time-slot" + (s.day_only ? " day-only" : "");
            // 경주처럼 날짜 단위로만 공개하는 곳은 시간 대신 "빈 시간 있음"으로 보여 준다
            chip.textContent = s.day_only ? "그날 빈 시간 있음" : `${s.begin}~${s.end}`;
            if (s.day_only) chip.title = "몇 시가 비었는지는 예약 사이트에서 날짜를 눌러 확인하세요";
            slotsEl.appendChild(chip);
          });
        row.appendChild(slotsEl);

        group.appendChild(row);
      }

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
    searchBtn.textContent = "검색 중...";
    setStatus("검색 중입니다...");
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
      searchBtn.textContent = "검색";
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
