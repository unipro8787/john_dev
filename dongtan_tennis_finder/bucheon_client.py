# 부천시 공공서비스예약(reserv.bucheon.go.kr)의 테니스장 상세 페이지 "예약현황" 달력을 읽는다.
# 로그인 없이 보이는 공개 페이지이며, 시설(lending_info_seq)마다 날짜·시간대별로
# "예약가능"(li.grn) / "예약완료"(li.red) 가 서버에서 그려져 나온다.
#
# 예약완료 칸에는 예약자 이름 일부(예: 임*정)가 함께 표시되지만, 여기서는 상태(class)만 읽고
# 이름은 파싱하지도 저장하지도 않는다.
#
# 부천은 매달 20일 오전 10시에 다음 달 예약을 연다. 그 전에는 다음 달 달력이 비어 있다.

from __future__ import annotations

import re

import requests

from hscity_client import Slot

BASE = "https://reserv.bucheon.go.kr"
DETAIL_URL = f"{BASE}/site/main/lending/lendingDetail"
HEADERS = {"User-Agent": "Mozilla/5.0"}

_DAY_RE = re.compile(r'<ul class="reservation" id="(\d{4})">(.*?)</ul>', re.S)
_LI_RE = re.compile(r'<li class="([^"]*)"[^>]*>(.*?)</li>', re.S)
_TIME_RE = re.compile(r"(\d{2}:\d{2})~(\d{2}:\d{2})")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def fetch_month(session: requests.Session, lending_info_seq: int, year: int, month: int) -> list[Slot]:
    """지정한 테니스장(lending_info_seq)의 해당 연/월 시간대 상태를 가져온다."""
    resp = session.get(
        DETAIL_URL,
        headers=HEADERS,
        params={
            "lending_info_seq": str(lending_info_seq),
            "inst_cate": "0103",
            "lending_inst_nm": "tennis",
            "sch_year": str(year),
            "sch_month": f"{month:02d}",
        },
        timeout=15,
    )
    resp.raise_for_status()

    slots: list[Slot] = []
    for day in _DAY_RE.finditer(resp.text):
        mmdd = day.group(1)
        date_str = f"{year}-{mmdd[:2]}-{mmdd[2:]}"
        if int(mmdd[:2]) != month:  # 달력 앞뒤로 붙는 다른 달 칸은 버린다
            continue
        current = None
        # 시간 칸(li.tm) 바로 뒤에 상태 칸(li.grn / li.red ...)이 짝지어 나온다
        for cls, inner in _LI_RE.findall(_COMMENT_RE.sub("", day.group(2))):
            classes = cls.split()
            if "tm" in classes:
                current = _TIME_RE.search(inner)
                continue
            if current:
                status = "AVAILABLE" if "grn" in classes else "BOOKED"
                slots.append(Slot(date=date_str, begin=current.group(1), end=current.group(2), status=status))
                current = None
    return slots
