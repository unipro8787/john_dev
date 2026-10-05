(() => {
  const DOW = ["일", "월", "화", "수", "목", "금", "토"];

  const startInput = document.getElementById("start-date");
  const endInput = document.getElementById("end-date");
  const quickRange = document.getElementById("quick-range");
  const timeRange = document.getElementById("time-range");
  const timeStartInput = document.getElementById("time-start");
  const timeEndInput = document.getElementById("time-end");
  const facilityFilter = document.getElementById("facility-filter");
  const searchBtn = document.getElementById("search-btn");
  const statusArea = document.getElementById("status-area");
  const resultsEl = document.getElementById("results");

  const selectedFacilities = new Set();
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

  const FACILITY_KEY = "selectedFacilities.v2";

  function saveSelection() {
    try {
      localStorage.setItem(FACILITY_KEY, JSON.stringify([...selectedFacilities]));
    } catch (e) {
      // 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서는 기억만 못 할 뿐 검색은 그대로 된다
    }
  }

  function loadSelection(names) {
    try {
      const saved = JSON.parse(localStorage.getItem(FACILITY_KEY) || "null");
      if (Array.isArray(saved)) {
        const valid = saved.filter((n) => names.includes(n));
        if (valid.length) return new Set(valid);
      }
    } catch (e) {
      // 저장된 값이 깨졌으면 무시하고 전체 선택으로 시작
    }
    return new Set(names);
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

  async function loadFacilities() {
    const res = await fetch("/api/facilities");
    const data = await res.json();
    allFacilities = data.regions.flatMap((r) => r.facilities.map((f) => f.name));
    const initial = loadSelection(allFacilities);
    facilityFilter.innerHTML = "";

    data.regions.forEach((region) => {
      const group = document.createElement("div");
      group.className = "region-group";

      const head = document.createElement("div");
      head.className = "region-head";
      const title = document.createElement("span");
      title.className = "region-name";
      const courtCount = region.facilities.reduce((n, f) => n + f.courts.length, 0);
      title.textContent = `${region.name} · ${courtCount}면`;
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
        chip.textContent = f.name.replace(/ 테니스장$/, "");
        chip.title = `${f.name} · ${f.courts.length}면${f.note ? " · " + f.note : ""}`;
        setChip(chip, initial.has(f.name));
        chip.addEventListener("click", () => {
          setChip(chip, !selectedFacilities.has(f.name));
          syncRegionToggles();
          saveSelection();
        });
        chips.appendChild(chip);
      });
      group.appendChild(chips);

      toggle.addEventListener("click", () => {
        const list = [...chips.querySelectorAll(".facility-chip")];
        const allOn = list.every((c) => selectedFacilities.has(c.dataset.name));
        list.forEach((c) => setChip(c, !allOn));
        syncRegionToggles();
        saveSelection();
      });

      facilityFilter.appendChild(group);
    });
    syncRegionToggles();
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
            chip.className = "time-slot";
            chip.textContent = `${s.begin}~${s.end}`;
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
