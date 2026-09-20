# 화성시 통합예약시스템(yeyak.hscity.go.kr)의 "예약현황" 탭이 쓰는 공개 API를 그대로 호출한다.
# 로그인 없이도 월별 코트 예약 현황(시간대별 예약가능/예약완료/승인보류/승인예정/예약불가)을 JSON으로 준다.
# stadiumDetail.do?stadiumIdx=... 페이지의 reserveStatus() 함수(JS)를 그대로 이식한 분류 로직.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import requests

BASE = "https://yeyak.hscity.go.kr"
RESERVE_LIST_URL = f"{BASE}/stadium/stadiumReserveUseList.do"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

STATUS_LABELS = {
    "AVAILABLE": "예약가능",
    "BOOKED": "예약완료",
    "PAYMENT_PENDING": "승인(결제대기)",
    "HOLD": "승인보류",
    "SCHEDULED": "승인예정",
    "CLOSED": "예약불가",
    "UNKNOWN": "알수없음",
}


@dataclass
class Slot:
    date: str  # YYYY-MM-DD
    begin: str  # HH:MM
    end: str  # HH:MM
    status: str  # STATUS_LABELS의 key

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


def _classify(item: dict) -> str:
    status_cd = item.get("applyStatusCd")
    if status_cd is None:
        return "AVAILABLE"
    if status_cd == "AP":
        return "BOOKED" if item.get("payDivCd") in ("PC", "EC") else "PAYMENT_PENDING"
    if status_cd == "DE":
        return "HOLD"
    if status_cd == "RC":
        return "SCHEDULED"
    if status_cd == "CLOSE":
        return "CLOSED"
    return "UNKNOWN"


def fetch_month(session: requests.Session, stadium_idx: int, year: int, month: int) -> list[Slot]:
    """지정한 코트(stadiumIdx)의 해당 연/월 전체 시간대 상태를 가져온다."""
    resp = session.post(
        RESERVE_LIST_URL,
        headers=HEADERS,
        data={"stadiumIdx": str(stadium_idx), "searchYear": str(year), "searchMonth": f"{month:02d}"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    slots = []
    for item in data.get("useCntList", []):
        sor_date = item.get("sorDate")
        if not sor_date:
            continue
        slots.append(
            Slot(
                date=sor_date,
                begin=item.get("stadiumBeginHm", ""),
                end=item.get("stadiumEndHm", ""),
                status=_classify(item),
            )
        )
    return slots


def fetch_range(
    session: requests.Session, stadium_idx: int, start: date, end: date
) -> list[Slot]:
    """start~end(포함) 범위의 시간대 상태를 가져온다. 여러 달에 걸치면 달마다 나눠 호출한다."""
    months: set[tuple[int, int]] = set()
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.add((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    start_str, end_str = start.isoformat(), end.isoformat()
    result: list[Slot] = []
    for year, month in months:
        for slot in fetch_month(session, stadium_idx, year, month):
            if start_str <= slot.date <= end_str:
                result.append(slot)
    return result
