(() => {
  const DOW = ["일", "월", "화", "수", "목", "금", "토"];

  const startInput = document.getElementById("start-date");
  const endInput = document.getElementById("end-date");
  const quickRange = document.getElementById("quick-range");
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

  async function loadFacilities() {
    const res = await fetch("/api/facilities");
    const data = await res.json();
    allFacilities = Object.keys(data);
    facilityFilter.innerHTML = "";
    allFacilities.forEach((name) => {
      selectedFacilities.add(name);
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "facility-chip active";
      chip.textContent = name;
      chip.dataset.name = name;
      chip.addEventListener("click", () => {
        if (selectedFacilities.has(name)) {
          selectedFacilities.delete(name);
          chip.classList.remove("active");
        } else {
          selectedFacilities.add(name);
          chip.classList.add("active");
        }
      });
      facilityFilter.appendChild(chip);
    });
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

    searchBtn.disabled = true;
    searchBtn.textContent = "검색 중...";
    setStatus("검색 중입니다...");
    resultsEl.innerHTML = "";

    try {
      const params = new URLSearchParams({ start, end });
      for (const f of selectedFacilities) params.append("facility", f);

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
    runSearch();
  })();
})();
