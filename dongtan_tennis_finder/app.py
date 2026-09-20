# 동탄 테니스코트 예약 가능 시간대 조회 웹앱 (Flask).
# check_availability.py의 조회 로직을 그대로 재사용하고, 검색 UI + JSON API를 얹은 것.
#
# 로컬 실행: python app.py  (http://127.0.0.1:5000)
# 배포 실행: gunicorn app:app

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, render_template, request
import requests

from courts import FACILITIES
from hscity_client import fetch_month

app = Flask(__name__)

MAX_RANGE_DAYS = 45  # 한 번에 조회 가능한 최대 기간 (API 부하 방지)
CACHE_TTL_SECONDS = 180  # 코트별 월 데이터 캐시 유지 시간

_month_cache: dict[tuple[int, int, int], tuple[float, list]] = {}
_session = requests.Session()


def _cached_fetch_month(stadium_idx: int, year: int, month: int) -> list:
    key = (stadium_idx, year, month)
    now = time.time()
    cached = _month_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    slots = fetch_month(_session, stadium_idx, year, month)
    _month_cache[key] = (now, slots)
    return slots


def _fetch_range_cached(stadium_idx: int, start: date, end: date) -> list:
    months: set[tuple[int, int]] = set()
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.add((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    start_str, end_str = start.isoformat(), end.isoformat()
    result = []
    for year, month in months:
        for slot in _cached_fetch_month(stadium_idx, year, month):
            if start_str <= slot.date <= end_str:
                result.append(slot)
    return result


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/facilities")
def api_facilities():
    return jsonify(FACILITIES)


@app.get("/api/search")
def api_search():
    today = date.today()

    start_raw = request.args.get("start")
    end_raw = request.args.get("end")

    try:
        start = datetime.strptime(start_raw, "%Y-%m-%d").date() if start_raw else today
    except ValueError:
        return jsonify({"error": "start 날짜 형식이 잘못되었습니다 (YYYY-MM-DD)"}), 400

    try:
        end = datetime.strptime(end_raw, "%Y-%m-%d").date() if end_raw else start
    except ValueError:
        return jsonify({"error": "end 날짜 형식이 잘못되었습니다 (YYYY-MM-DD)"}), 400

    if end < start:
        return jsonify({"error": "end는 start보다 이전일 수 없습니다"}), 400

    if (end - start).days + 1 > MAX_RANGE_DAYS:
        return jsonify({"error": f"한 번에 조회 가능한 기간은 최대 {MAX_RANGE_DAYS}일입니다"}), 400

    selected = request.args.getlist("facility") or None  # None이면 전체

    results = []
    for facility_name, courts in FACILITIES.items():
        if selected and facility_name not in selected:
            continue
        for court_label, stadium_idx in courts.items():
            slots = _fetch_range_cached(stadium_idx, start, end)
            available = [s for s in slots if s.status == "AVAILABLE"]
            for slot in available:
                results.append(
                    {
                        "facility": facility_name,
                        "court": court_label,
                        "date": slot.date,
                        "begin": slot.begin,
                        "end": slot.end,
                    }
                )

    results.sort(key=lambda r: (r["date"], r["begin"], r["facility"], r["court"]))
    return jsonify(
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "count": len(results),
            "results": results,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
