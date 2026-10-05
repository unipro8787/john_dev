# 경주시 통합예약(www.gyeongju.go.kr/reserve) 체육시설 예약 캘린더를 읽는다.
# 시설 상세 페이지가 달을 바꿀 때 부르는 /reserve/ajxAgent/loadItemCal.jsp 가 로그인 없이
# 날짜별 "예약가능"(p.reserveYES, id="selRsvDate_YYYYMMDD") / "예약불가"(p.reserveNO) 칸을 돌려준다.
#
# 경주는 날짜 단위로만 예약 가능 여부를 공개한다. 시간대별 상태를 주는 ajxRsvExplodTime.jsp 는
# 로그인 세션 없이 부르면 모든 시간을 예약됨으로 돌려줘 믿을 수 없으므로 쓰지 않는다.
# 그래서 여기서 돌려주는 Slot은 begin/end가 빈 문자열인 "하루 단위" 슬롯이다.
#
# 코트 id는 "mem_id:item_id" 문자열이다. 외동생활체육공원처럼 같은 코트가 계절별로 항목이
# 나뉜 경우 "mem_id:item_id1,item_id2" 로 적으면 두 항목의 예약가능 날짜를 합친다.

from __future__ import annotations

import re

import requests

from hscity_client import Slot

BASE = "https://www.gyeongju.go.kr"
CAL_URL = f"{BASE}/reserve/ajxAgent/loadItemCal.jsp"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

_YES_RE = re.compile(r'class="reserveYES"[^>]*>\s*<a[^>]*id="selRsvDate_(\d{8})"')


def _available_dates(session: requests.Session, mem_id: str, item_id: str, year: int, month: int) -> set[str]:
    resp = session.post(
        CAL_URL,
        headers=HEADERS,
        data={"mem_id": mem_id, "item_id": item_id, "selMonth": f"{year}{month:02d}01"},
        timeout=15,
    )
    resp.raise_for_status()
    prefix = f"{year}{month:02d}"
    return {d for d in _YES_RE.findall(resp.text) if d.startswith(prefix)}


def fetch_month(session: requests.Session, court_key: str, year: int, month: int) -> list[Slot]:
    """court_key("mem_id:item_id[,item_id…]") 코트의 해당 연/월 예약가능 날짜를 하루 단위 슬롯으로 돌려준다."""
    mem_id, items = court_key.split(":", 1)
    dates: set[str] = set()
    for item_id in items.split(","):
        dates |= _available_dates(session, mem_id, item_id.strip(), year, month)
    return [
        Slot(date=f"{d[:4]}-{d[4:6]}-{d[6:]}", begin="", end="", status="AVAILABLE")
        for d in sorted(dates)
    ]
