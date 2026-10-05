# 화성시·부천시 공공 테니스코트 예약 가능 시간대 조회 웹앱 (Flask).
# check_availability.py의 조회 로직을 그대로 재사용하고, 검색 UI + JSON API를 얹은 것.
#
# 로컬 실행: python app.py  (http://127.0.0.1:5000)
# 배포 실행: gunicorn app:app
#
# 배포 환경변수 (모두 선택, 없으면 해당 기능만 꺼진다)
#   SITE_URL                  정식 주소 (예: https://dongtantennis.kr). 설정하면 canonical·사이트맵에 쓰이고,
#                             다른 호스트(예: *.onrender.com)로 들어온 페이지 요청은 이 주소로 301 이동한다.
#   GOOGLE_SITE_VERIFICATION  구글 서치 콘솔 HTML 태그의 content 값
#   NAVER_SITE_VERIFICATION   네이버 서치어드바이저 HTML 태그의 content 값
#   ADSENSE_CLIENT            애드센스 게시자 ID (예: ca-pub-1234567890123456). 광고 스크립트와 ads.txt가 켜진다.
#   CONTACT_EMAIL             소개·개인정보처리방침에 표시할 문의 메일

from __future__ import annotations

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from urllib.parse import urlparse

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for
import requests

import bucheon_client
import hscity_client
from courts import CITIES, FACILITY_CITY, FACILITY_NOTES

# 예약 시스템(source)별 월 단위 조회 함수
FETCHERS = {
    "hscity": hscity_client.fetch_month,
    "bucheon": bucheon_client.fetch_month,
}
ALL_FACILITIES: dict[str, dict[str, int]] = {name: courts for c in CITIES for name, courts in c["facilities"].items()}

app = Flask(__name__)

MAX_RANGE_DAYS = 45  # 한 번에 조회 가능한 최대 기간 (API 부하 방지)
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
CACHE_TTL_SECONDS = 180  # 코트별 월 데이터 캐시 유지 시간

FETCH_WORKERS = 6  # 코트별 조회를 동시에 보내는 수 (조회 시간 단축, 원 사이트 부하는 캐시로 제한)

_month_cache: dict[tuple[str, int, int, int], tuple[float, list]] = {}
_cache_lock = threading.Lock()
_local = threading.local()  # requests.Session은 스레드 간 공유가 안전하지 않아 스레드마다 하나씩 둔다


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def _cached_fetch_month(source: str, court_id: int, year: int, month: int) -> list:
    key = (source, court_id, year, month)
    now = time.time()
    with _cache_lock:
        cached = _month_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    slots = FETCHERS[source](_session(), court_id, year, month)
    with _cache_lock:
        _month_cache[key] = (now, slots)
    return slots


def _fetch_range_cached(source: str, court_id: int, start: date, end: date) -> list:
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
        for slot in _cached_fetch_month(source, court_id, year, month):
            if start_str <= slot.date <= end_str:
                result.append(slot)
    return result


SITE_NAME = "화성·부천 테니스코트 찾기"
POLICY_EFFECTIVE = "2026-10-06"  # 개인정보처리방침 시행일 (방침을 바꾸면 함께 갱신)
PAGES_UPDATED = "2026-10-06"     # 사이트맵 lastmod (페이지 내용을 바꾸면 함께 갱신)
_ADSENSE_RE = re.compile(r"^ca-pub-\d{10,20}$")


def _env(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip()
    return value or None


def _site_url() -> str:
    return (_env("SITE_URL") or request.url_root).rstrip("/")


def _adsense_client() -> str | None:
    value = _env("ADSENSE_CLIENT")
    return value if value and _ADSENSE_RE.match(value) else None


@app.before_request
def _redirect_to_canonical_host():
    # 정식 도메인을 연결한 뒤에는 onrender.com 주소로 들어온 페이지를 정식 주소로 보낸다
    # (검색엔진에 같은 페이지가 두 주소로 잡히지 않게). API와 헬스체크는 그대로 둔다.
    site = _env("SITE_URL")
    if not site or request.path.startswith("/api/") or request.path == "/healthz":
        return None
    target = urlparse(site)
    if target.netloc and request.host != target.netloc:
        qs = ("?" + request.query_string.decode()) if request.query_string else ""
        return redirect(f"{target.scheme}://{target.netloc}{request.path}{qs}", code=301)
    return None


@app.context_processor
def _inject_site():
    return {
        "site_name": SITE_NAME,
        "site_url": _site_url(),
        "google_site_verification": _env("GOOGLE_SITE_VERIFICATION"),
        "naver_site_verification": _env("NAVER_SITE_VERIFICATION"),
        "adsense_client": _adsense_client(),
        "contact_email": _env("CONTACT_EMAIL"),
        "cities": CITIES,
        "facility_notes": FACILITY_NOTES,
        "facility_count": len(ALL_FACILITIES),
        "court_count": sum(len(c) for c in ALL_FACILITIES.values()),
        "policy_effective": POLICY_EFFECTIVE,
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/about")
def about():
    return render_template("about.html")


@app.get("/privacy")
def privacy():
    return render_template("privacy.html")


@app.get("/robots.txt")
def robots_txt():
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/",
        f"Sitemap: {_site_url()}/sitemap.xml",
        "",
    ])
    return Response(body, mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    site = _site_url()
    pages = [("index", "1.0"), ("about", "0.6"), ("privacy", "0.3")]
    urls = "".join(
        f"<url><loc>{site}{url_for(name)}</loc><lastmod>{PAGES_UPDATED}</lastmod><priority>{prio}</priority></url>"
        for name, prio in pages
    )
    body = ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    return Response(body, mimetype="application/xml")


@app.get("/ads.txt")
def ads_txt():
    client = _adsense_client()
    if not client:
        abort(404)
    # 애드센스 표준 형식: google.com, pub-XXXX, DIRECT, (Google 인증기관 ID)
    return Response(f"google.com, {client.removeprefix('ca-')}, DIRECT, f08c47fec0942fa0\n", mimetype="text/plain")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/facilities")
def api_facilities():
    # 도시 → 권역 → 시설 → 코트 이름 (예약 시스템 내부 번호는 내보내지 않는다)
    return jsonify({
        "cities": [
            {
                "name": city["name"],
                "booking_url": city["booking_url"],
                "booking_name": city["booking_name"],
                "regions": [
                    {
                        "name": region,
                        "facilities": [
                            {"name": f, "courts": list(city["facilities"][f]), "note": FACILITY_NOTES.get(f)}
                            for f in names
                        ],
                    }
                    for region, names in city["regions"].items()
                ],
            }
            for city in CITIES
        ]
    })


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

    time_start = request.args.get("time_start") or None
    time_end = request.args.get("time_end") or None
    for label, value in (("time_start", time_start), ("time_end", time_end)):
        if value and not _TIME_RE.match(value):
            return jsonify({"error": f"{label} 시간 형식이 잘못되었습니다 (HH:MM)"}), 400
    if time_start and time_end and time_end <= time_start:
        return jsonify({"error": "종료 시간은 시작 시간보다 이후여야 합니다"}), 400

    # 시설을 고르지 않으면 첫 번째 도시(화성시) 전체를 본다
    if not selected:
        selected = list(CITIES[0]["facilities"])
    targets = [
        (FACILITY_CITY[name][0], FACILITY_CITY[name][1], name, court_label, court_id)
        for name in dict.fromkeys(selected)
        if name in ALL_FACILITIES
        for court_label, court_id in ALL_FACILITIES[name].items()
    ]
    try:
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            fetched = list(pool.map(lambda t: _fetch_range_cached(t[1], t[4], start, end), targets))
    except requests.RequestException:
        return jsonify({"error": "예약 시스템에서 예약 현황을 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502

    results = []
    for (city_name, _, facility_name, court_label, _), slots in zip(targets, fetched):
        available = [s for s in slots if s.status == "AVAILABLE"]
        # 시간대 필터: 선택한 시간 구간과 겹치는 슬롯만 남김
        if time_start:
            available = [s for s in available if s.end > time_start]
        if time_end:
            available = [s for s in available if s.begin < time_end]
        for slot in available:
            results.append(
                {
                    "city": city_name,
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
