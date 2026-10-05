# 서울 강남구 통합예약(life.gangnam.go.kr) 시설예약 화면이 쓰는 공개 REST API를 부른다.
# 로그인 없이 응답하며, robots.txt도 전체 허용이다.
#   - rest/facilities/place_month_state_list      : 날짜별 상태 (state_cd 10/11/15 = 온라인 신청 가능,
#                                                    20 = 예약불가/마감, 30 = 대회·휴관일)
#   - rest/facilities/place_month_time_state_list : 한 달치 시간대 목록 (use_yn Y=예약됨, E=마감,
#                                                    U=예약불가, D=추첨접수, 그 밖=빈 시간)
# 시설예약 화면(modules_fmcs_facilities default.js)과 같은 규칙으로 판정한다.
#
# 시간대 응답의 detail 필드에는 예약 단체·예약자 실명이 들어 있다. 여기서는 use_yn만 읽고
# detail은 읽지도 저장하지도 않는다.
#
# 강남구는 매월 25일까지 다음 달 대관을 온라인으로 받고, 그 뒤 남은 시간은 각 시설에 전화로 예약한다.
# 그래서 빈 시간은 두 종류로 나눈다.
#   AVAILABLE       : 날짜가 온라인 신청 가능 상태 → 통합예약에서 바로 신청
#   AVAILABLE_PHONE : 그 달 온라인 신청기간(전달 25일까지)이 끝난 뒤 남은 칸 → 시설에 전화로 예약
# 아직 신청을 받기 전인 달(전달 25일 이전이고 온라인 신청 가능 날짜도 없음)은 정기 대관 몇 칸만 빼고
# 전부 비어 보여 사실과 다르므로 빈 시간으로 내보내지 않는다. 판정은 한국 시간 기준.
#
# 코트 id는 "company_code:part_code:place_code" 문자열이다 (예: "GNCC05:04:34").

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import requests

from hscity_client import Slot

BASE = "https://life.gangnam.go.kr"
HEADERS = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}
RENT_TYPE = "1001"  # 시설예약 화면 기본 선택값 (개인 대관)

ONLINE_STATES = {"10", "11", "15"}
CLOSED_DAY_STATES = {"30"}  # 대회, 휴관일
TAKEN_USE_YN = {"Y", "E", "U", "D"}
KST = timezone(timedelta(hours=9))
ONLINE_CLOSE_DAY = 25  # 다음 달 온라인 신청 마감일 (이 날이 지나면 남은 칸은 전화 예약)


def _phone_window_open(year: int, month: int, today: date | None = None) -> bool:
    """year/month의 온라인 신청기간(전달 25일까지)이 끝났는지."""
    today = today or datetime.now(KST).date()
    prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
    return (today.year, today.month, today.day) > (prev_y, prev_m, ONLINE_CLOSE_DAY)


def _get(session: requests.Session, path: str, params: dict) -> list:
    resp = session.get(f"{BASE}/rest/facilities/{path}", headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def fetch_month(session: requests.Session, court_key: str, year: int, month: int) -> list[Slot]:
    company, part, place = court_key.split(":")
    params = {
        "company_code": company,
        "part_code": part,
        "place_code": place,
        "rent_type": RENT_TYPE,
        "mem_no": "",
        "base_date": f"{year}{month:02d}01",
    }
    month_prefix = f"{year}-{month:02d}"
    day_state = {
        r["date"]: str(r.get("state_cd"))
        for r in _get(session, "place_month_state_list", params)
        if str(r.get("date", "")).startswith(month_prefix)
    }
    times = [
        r for r in _get(session, "place_month_time_state_list", params)
        if str(r.get("date", "")).startswith(f"{year}{month:02d}") and r.get("start_time") and r.get("end_time")
    ]

    allocated = _phone_window_open(year, month)

    slots: list[Slot] = []
    for r in times:
        raw = str(r["date"])
        date_str = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        state = day_state.get(date_str, "")
        if state in CLOSED_DAY_STATES:
            continue
        if r.get("use_yn") in TAKEN_USE_YN:
            status = "BOOKED"
        elif state in ONLINE_STATES:
            status = "AVAILABLE"
        elif allocated:
            status = "AVAILABLE_PHONE"
        else:
            continue  # 아직 신청을 받기 전인 달
        slots.append(Slot(date=date_str, begin=r["start_time"], end=r["end_time"], status=status))
    return slots
