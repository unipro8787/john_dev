# 테니스장 페이지의 날씨 예보. 노르웨이 기상청(MET Norway) Locationforecast API를 쓴다.
# 키 없이 쓸 수 있고 데이터는 CC BY 4.0이라 출처만 밝히면 광고가 붙은 사이트에서도 쓸 수 있다.
# 이용 조건: 사이트를 알 수 있는 User-Agent, 좌표는 소수 4자리 이하, 응답의 Expires 전에는 다시 요청하지 않기.
# https://api.met.no/doc/TermsOfService

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
USER_AGENT = "tennisbinjari.kr/1.0 (+https://tennisbinjari.kr)"
KST = timezone(timedelta(hours=9))
TIMEOUT_SECONDS = 4
MIN_CACHE_SECONDS = 30 * 60   # Expires가 없거나 너무 짧아도 30분은 다시 묻지 않는다
STALE_OK_SECONDS = 6 * 3600   # 새로 받지 못하면 6시간 안의 예보는 그대로 보여 준다
DAY_HOURS = (6, 22)           # 하루 요약은 테니스장 운영 시간(06~22시)만 본다
DAYS_SHOWN = 7
RAIN_MM = 0.1                 # 이 이상이면 "비 예보"로 본다
WINDY_MS = 6.0                # 공이 눈에 띄게 흔들리기 시작하는 바람 세기

# 시설 안내에 좌표가 없는 곳은 주소(동)로 한 번 찾아 둔 대략적인 위치를 쓴다.
# 날씨는 몇 km 안에서는 거의 같아서 동 단위 위치로 충분하다. (OpenStreetMap Nominatim, 2026-10-27)
WEATHER_POINTS: dict[str, tuple[float, float]] = {
    "복사골테니스장": (37.50, 126.76),             # 부천시 중2동
    "원미테니스장": (37.4927, 126.7914),           # 부천시 원미1동
    "종합운동장테니스장": (37.5019, 126.8020),      # 부천시 춘의동
    "부천체육관테니스장(하드)": (37.5060, 126.7626),
    "부천실내테니스장": (37.5134, 126.7632),        # 석천로 293
    "해그늘체육공원 테니스장": (37.5058, 126.7532),  # 부천시 상3동
    "해그늘체육공원 테니스장(인조잔디)": (37.5058, 126.7532),
    "성주산체육공원테니스장": (37.4734, 126.7948),   # 부천시 소사본동
    "소사배수지테니스장": (37.4734, 126.7948),       # 부천시 소사본1동
    "남부수자원테니스장": (37.4681, 126.8283),       # 부천시 옥길동
    "강변테니스장(북천)": (35.8283, 129.2262),       # 경주시 구황동
    "시민테니스장(북천)": (35.8492, 129.2394),
    "건천테니스장": (35.8409, 129.0982),
    "외동생활체육공원 테니스장": (35.7165, 129.3415),  # 외동읍 입실리
    "봉은테니스장": (37.5148, 127.0544),
    "포이테니스장": (37.4842, 127.0701),
    "강남세곡체육공원 테니스장": (37.4709, 127.1034),
}

# MET 날씨 기호(symbol_code)에 들어 있는 낱말 → (이름, 아이콘, 심한 정도). 위에서부터 먼저 맞는 것을 쓴다.
_SYMBOLS = [
    ("thunder", "뇌우", "⛈️", 6),
    ("sleet", "진눈깨비", "🌨️", 5),
    ("snow", "눈", "🌨️", 5),
    ("heavyrain", "많은 비", "🌧️", 5),
    ("rainshowers", "소나기", "🌦️", 4),
    ("lightrain", "약한 비", "🌦️", 4),
    ("rain", "비", "🌧️", 4),
    ("fog", "안개", "🌫️", 2),
    ("partlycloudy", "구름 조금", "⛅", 1),
    ("cloudy", "흐림", "☁️", 2),
    ("fair", "대체로 맑음", "🌤️", 0),
    ("clearsky", "맑음", "☀️", 0),
]

_cache: dict[tuple[float, float], tuple[float, float, dict]] = {}  # 좌표 → (다시 물어도 되는 시각, 받은 시각, 예보)
_lock = threading.Lock()
_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def _symbol(code: str | None) -> tuple[str, str, int]:
    code = (code or "").split("_")[0]  # clearsky_day → clearsky
    for word, name, icon, level in _SYMBOLS:
        if word in code:
            return name, icon, level
    return "", "", -1


def point_for(f: dict) -> tuple[float, float] | None:
    info = f.get("info") or {}
    if info.get("lat") and info.get("lng"):
        return float(info["lat"]), float(info["lng"])
    return WEATHER_POINTS.get(f["name"])


def _periods(timeseries: list[dict]) -> list[dict]:
    """겹치지 않는 예보 구간 목록. 앞쪽은 1시간, 뒤쪽은 6시간 단위다."""
    out, covered_until = [], None
    for entry in timeseries:
        start = datetime.fromisoformat(entry["time"].replace("Z", "+00:00")).astimezone(KST)
        if covered_until and start < covered_until:
            continue
        data = entry["data"]
        hours = 1 if "next_1_hours" in data else 6 if "next_6_hours" in data else 0
        if not hours:
            continue
        nxt = data[f"next_{hours}_hours"]
        details = data["instant"]["details"]
        out.append({
            "start": start,
            "hours": hours,
            "rain": float(nxt.get("details", {}).get("precipitation_amount") or 0),
            "symbol": nxt.get("summary", {}).get("symbol_code"),
            "temp": details.get("air_temperature"),
            "wind": details.get("wind_speed"),
        })
        covered_until = start + timedelta(hours=hours)
    return out


def _summarize(payload: dict) -> dict:
    periods = _periods(payload["properties"]["timeseries"])
    today = datetime.now(KST).date()
    days, hours = [], {}
    for p in periods:
        if p["hours"] == 1:
            hours[p["start"].strftime("%Y-%m-%d %H")] = {"rain": round(p["rain"], 1), "wind": p["wind"], "temp": p["temp"]}

    for offset in range(DAYS_SHOWN):
        day = today + timedelta(days=offset)
        lo = datetime(day.year, day.month, day.day, DAY_HOURS[0], tzinfo=KST)
        hi = datetime(day.year, day.month, day.day, DAY_HOURS[1], tzinfo=KST)
        rain, temps, winds, worst, noon = 0.0, [], [], None, None
        for p in periods:
            end = p["start"] + timedelta(hours=p["hours"])
            overlap = (min(end, hi) - max(p["start"], lo)).total_seconds() / 3600
            if overlap <= 0:
                continue
            rain += p["rain"] * overlap / p["hours"]
            if lo <= p["start"] < hi:
                if p["temp"] is not None:
                    temps.append(p["temp"])
                if p["wind"] is not None:
                    winds.append(p["wind"])
            sym = _symbol(p["symbol"])
            if sym[2] >= 4 and (worst is None or sym[2] > worst[2]):
                worst = sym
            # 낮 날씨는 13시 구간으로 정하고, 13시가 이미 지난 오늘은 남은 시간의 첫 구간을 쓴다
            if p["start"] <= lo.replace(hour=13) < end or noon is None:
                noon = sym
        if not temps and noon is None:
            break  # 예보 범위를 넘었다
        if worst and rain >= RAIN_MM:
            name, icon, _ = worst
        elif noon:
            name, icon, _ = noon
        else:
            name, icon = "", ""
        days.append({
            "date": day.isoformat(),
            "label": f"{day.month}/{day.day} {'월화수목금토일'[day.weekday()]}",
            "weekday": day.weekday(),
            "name": name,
            "icon": icon,
            "tmax": round(max(temps)) if temps else None,
            "tmin": round(min(temps)) if temps else None,
            "rain": round(rain, 1),
            "wind": round(max(winds), 1) if winds else None,
            "windy": bool(winds) and max(winds) >= WINDY_MS,
        })
    return {"days": days, "hours": hours}


def forecast(lat: float, lng: float) -> dict | None:
    """좌표의 7일 요약과 시간별 예보. 받지 못하면 None (페이지는 날씨 없이 그린다)."""
    key = (round(lat, 2), round(lng, 2))  # 1km 안쪽은 같은 예보로 묶어 요청 수를 줄인다
    now = time.time()
    with _lock:
        cached = _cache.get(key)
    if cached and now < cached[0]:
        return cached[2]
    try:
        r = _session.get(API_URL, params={"lat": key[0], "lon": key[1]}, timeout=TIMEOUT_SECONDS)
        r.raise_for_status()
        result = _summarize(r.json())
        try:
            expires = parsedate_to_datetime(r.headers["Expires"]).timestamp()
        except (KeyError, TypeError, ValueError):
            expires = 0
        result["fetched"] = datetime.now(KST).strftime("%m/%d %H:%M")
        with _lock:
            _cache[key] = (max(expires, now + MIN_CACHE_SECONDS), now, result)
        return result
    except (requests.RequestException, ValueError, KeyError):
        if cached and now - cached[1] < STALE_OK_SECONDS:
            with _lock:  # 바로 다시 묻지 않도록 몇 분 뒤로 미룬다
                _cache[key] = (now + 300, cached[1], cached[2])
            return cached[2]
        return None
