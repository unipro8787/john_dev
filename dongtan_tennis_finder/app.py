# 화성시·부천시·경주시·서울 강남구 공공 테니스코트 예약 가능 시간대 조회 웹앱 (Flask).
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
#   ALLOW_ADS_WITH            광고를 켠 상태에서도 보여 줄 "상업적 이용 제한" 지역의 source (쉼표 구분, 예: gangnam).
#                             해당 기관에서 이용 허락을 받은 뒤에만 설정한다. 광고가 꺼져 있으면 의미 없음.

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
import gangnam_client
import gyeongju_client
import hscity_client
from courts import CITIES, FACILITY_CITY, FACILITY_NOTES
from content import CITY_KEYWORDS, CITY_SLUGS, FACILITY_BY_SLUG, FACILITY_SLUGS, GUIDE_CHECKED, GUIDES, INFO_COLLECTED, facility_entries

# 예약 시스템(source)별 월 단위 조회 함수
FETCHERS = {
    "hscity": hscity_client.fetch_month,
    "bucheon": bucheon_client.fetch_month,
    "gyeongju": gyeongju_client.fetch_month,  # 날짜 단위(begin/end 빈 슬롯)
    "gangnam": gangnam_client.fetch_month,    # 온라인 마감 뒤 남은 칸은 AVAILABLE_PHONE
}
AVAILABLE_STATUSES = {"AVAILABLE", "AVAILABLE_PHONE"}
ALL_FACILITIES: dict[str, dict[str, int | str]] = {name: courts for c in CITIES for name, courts in c["facilities"].items()}

app = Flask(__name__)

MAX_RANGE_DAYS = 45  # 한 번에 조회 가능한 최대 기간 (API 부하 방지)
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
CACHE_TTL_SECONDS = 180  # 코트별 월 데이터 캐시 유지 시간

FETCH_WORKERS = 6  # 코트별 조회를 동시에 보내는 수 (조회 시간 단축, 원 사이트 부하는 캐시로 제한)

_month_cache: dict[tuple[str, int | str, int, int], tuple[float, list]] = {}
_cache_lock = threading.Lock()
_local = threading.local()  # requests.Session은 스레드 간 공유가 안전하지 않아 스레드마다 하나씩 둔다


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def _cached_fetch_month(source: str, court_id: int | str, year: int, month: int) -> list:
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


def _fetch_range_cached(source: str, court_id: int | str, start: date, end: date) -> list:
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


SITE_NAME = "테니스코트 빈자리 찾기"
POLICY_EFFECTIVE = "2026-10-05"  # 개인정보처리방침 시행일 (방침을 바꾸면 함께 갱신)
PAGES_UPDATED = "2026-10-08"     # 사이트맵 lastmod (페이지 내용을 바꾸면 함께 갱신)
_ADSENSE_RE = re.compile(r"^ca-pub-\d{10,20}$")


def _env(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip()
    return value or None


def _site_url() -> str:
    return (_env("SITE_URL") or request.url_root).rstrip("/")


def _adsense_client() -> str | None:
    value = _env("ADSENSE_CLIENT")
    return value if value and _ADSENSE_RE.match(value) else None


SHORT_NAMES = {"화성시": "화성", "부천시": "부천", "경주시": "경주", "서울 강남구": "강남"}


def _active_cities() -> list[dict]:
    """광고가 켜져 있으면 이용약관상 상업적 이용이 제한된 지역(강남구)을 뺀다. 허락받은 곳은 ALLOW_ADS_WITH로 예외."""
    if not _adsense_client():
        return CITIES
    allowed = {x.strip() for x in (_env("ALLOW_ADS_WITH") or "").split(",") if x.strip()}
    return [c for c in CITIES if not c.get("commercial_restricted") or c["source"] in allowed]


def _active_facility_names() -> set[str]:
    return {name for c in _active_cities() for name in c["facilities"]}


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
    cities = _active_cities()
    return {
        "site_name": SITE_NAME,
        "site_url": _site_url(),
        "google_site_verification": _env("GOOGLE_SITE_VERIFICATION"),
        "naver_site_verification": _env("NAVER_SITE_VERIFICATION"),
        "adsense_client": _adsense_client(),
        "contact_email": _env("CONTACT_EMAIL"),
        "cities": cities,
        "facility_notes": FACILITY_NOTES,
        "facility_count": sum(len(c["facilities"]) for c in cities),
        "court_count": sum(len(v) for c in cities for v in c["facilities"].values()),
        # 페이지 문구에 쓰는 지역 이름 묶음 (광고 설정에 따라 빠지는 지역이 있어 동적으로 만든다)
        "area_short": "·".join(SHORT_NAMES[c["name"]] for c in cities),
        "area_title": "·".join(["화성", "동탄"] + [SHORT_NAMES[c["name"]] for c in cities if c["name"] != "화성시"]),
        "area_long": ", ".join(c["name"] for c in cities),
        "booking_names": ", ".join(c["booking_name"] for c in cities),
        "has_city": {c["name"] for c in cities},
        "policy_effective": POLICY_EFFECTIVE,
        "city_slugs": CITY_SLUGS,
        "facility_slugs": FACILITY_SLUGS,
        "city_keywords": CITY_KEYWORDS,
        # 제목에 쓰는 검색용 지역 이름: 동탄·화성·부천·경주·서울 강남구
        "area_kw": "·".join(CITY_KEYWORDS[c["name"]] for c in cities),
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


@app.get("/courts")
def courts_index():
    return render_template("courts.html", facility_list=facility_entries(_active_cities()))


@app.get("/courts/<slug>")
def court_page(slug: str):
    f = FACILITY_BY_SLUG.get(slug)
    if not f or f["name"] not in _active_facility_names():
        abort(404)
    site = _site_url()
    jsonld = {
        "@context": "https://schema.org",
        "@type": "SportsActivityLocation",
        "name": f["name"],
        "url": f"{site}{url_for('court_page', slug=slug)}",
        "sport": "Tennis",
        "areaServed": f["city"],
    }
    info = f["info"]
    if info.get("address"):
        jsonld["address"] = {"@type": "PostalAddress", "streetAddress": info["address"], "addressCountry": "KR"}
    if info.get("lat"):
        jsonld["geo"] = {"@type": "GeoCoordinates", "latitude": info["lat"], "longitude": info["lng"]}
    if info.get("phone"):
        jsonld["telephone"] = info["phone"]
    nearby = [x for x in facility_entries(_active_cities()) if x["city"] == f["city"] and x["slug"] != slug][:6]
    return render_template("court.html", f=f, nearby=nearby, jsonld=jsonld, collected=INFO_COLLECTED)


def _active_guides() -> dict:
    names = {c["name"] for c in _active_cities()}
    return {slug: g for slug, g in GUIDES.items() if g["city"] in names}


@app.get("/guide")
def guide_index():
    return render_template("guides.html", guides=_active_guides(), checked=GUIDE_CHECKED)


@app.get("/guide/<slug>")
def guide_page(slug: str):
    g = _active_guides().get(slug)
    if not g:
        abort(404)
    city = next(c for c in CITIES if c["name"] == g["city"])
    site = _site_url()
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": g["title"],
        "description": g["summary"],
        "inLanguage": "ko",
        "dateModified": GUIDE_CHECKED,
        "mainEntityOfPage": f"{site}{url_for('guide_page', slug=slug)}",
        "publisher": {"@type": "Organization", "name": SITE_NAME},
    }
    return render_template(
        "guide.html", g=g, jsonld=jsonld, checked=GUIDE_CHECKED,
        city_facilities=[x for x in facility_entries(_active_cities()) if x["city"] == g["city"]],
        booking_url=city["booking_url"], booking_name=city["booking_name"],
    )


@app.get("/terms")
def terms():
    return render_template("terms.html")


@app.get("/contact")
def contact():
    return render_template("contact.html")


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found"}), 404
    return render_template("404.html"), 404


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
    pages = [
        (url_for("index"), "1.0"),
        (url_for("courts_index"), "0.8"),
        (url_for("guide_index"), "0.8"),
        *[(url_for("guide_page", slug=s), "0.7") for s in _active_guides()],
        *[(url_for("court_page", slug=f["slug"]), "0.7") for f in facility_entries(_active_cities())],
        (url_for("about"), "0.5"),
        (url_for("contact"), "0.3"),
        (url_for("terms"), "0.2"),
        (url_for("privacy"), "0.2"),
    ]
    urls = "".join(
        f"<url><loc>{site}{path}</loc><lastmod>{PAGES_UPDATED}</lastmod><priority>{prio}</priority></url>"
        for path, prio in pages
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
                "day_only": bool(city.get("day_only")),
                "regions": [
                    {
                        "name": region,
                        "facilities": [
                            {
                                "name": f,
                                "courts": list(city["facilities"][f]),
                                "note": FACILITY_NOTES.get(f),
                                "url": url_for("court_page", slug=FACILITY_SLUGS[f]),
                            }
                            for f in names
                        ],
                    }
                    for region, names in city["regions"].items()
                ],
            }
            for city in _active_cities()
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

    # 시설을 고르지 않으면 첫 번째 도시(화성시) 전체를 본다. 광고 설정으로 빠진 지역의 시설은 무시한다.
    if not selected:
        selected = list(CITIES[0]["facilities"])
    active_names = _active_facility_names()
    selected = [name for name in selected if name in active_names]
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
        available = [s for s in slots if s.status in AVAILABLE_STATUSES]
        # 시간대 필터: 선택한 시간 구간과 겹치는 슬롯만 남김.
        # 날짜 단위 슬롯(경주, begin/end 없음)은 시간을 알 수 없으니 거르지 않고 그대로 둔다.
        if time_start:
            available = [s for s in available if not s.begin or s.end > time_start]
        if time_end:
            available = [s for s in available if not s.begin or s.begin < time_end]
        for slot in available:
            results.append(
                {
                    "city": city_name,
                    "facility": facility_name,
                    "court": court_label,
                    "date": slot.date,
                    "begin": slot.begin,
                    "end": slot.end,
                    "day_only": not slot.begin,
                    "phone_only": slot.status == "AVAILABLE_PHONE",
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
