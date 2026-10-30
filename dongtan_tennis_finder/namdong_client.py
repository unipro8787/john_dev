# 인천 남동구 공공체육시설예약(www.namdong.go.kr/tennisRental) 테니스장 월별 예약현황을 읽는다.
# 로그인 없이 보이는 공개 페이지(rentalScheduleMonth.do?inst_cd=…&rental_seq=…&sch_ym=YYYY-MM)이며,
# robots.txt는 /job/, /jbWanted/ 만 막는다 (2026-10-30 확인).
#
# 빈 시간 칸은 신청 화면 링크(rentalApplyRegForm.do)로 나오고 title에 "2026년 11월  2일 12:30~14:30"처럼
# 날짜와 시간이 적혀 있다. 예약된 칸(li.close)에는 예약자 이름 일부(예: 김*섭)가 표시되지만,
# 여기서는 빈 칸의 title만 읽고 예약된 칸과 이름은 파싱하지도 저장하지도 않는다.
#
# 남동구 홈페이지에는 웹 방화벽이 있어 연속 요청을 막을 수 있다(조사 중 한 번 차단됨).
# 그래서 이 모듈의 요청은 프로세스 안에서 동시에 MAX_CONCURRENT개까지만, 시작 간격을 MIN_INTERVAL초 이상 두고 보낸다.
# (한 번에 하나씩만 보내면 21면 조회에 20초가 넘게 걸려 gunicorn 기본 제한 30초에 걸린다)
# 결과 캐시는 app.py에서 다른 지역보다 길게(CACHE_TTL_BY_SOURCE) 둔다.
#
# 예약 오픈: 남동구민은 전월 13일 10시, 일반은 전월 20일 10시. 그 전에는 다음 달 빈 칸이 나오지 않는다.

from __future__ import annotations

import re
import threading
import time

import requests

from hscity_client import Slot

BASE = "https://www.namdong.go.kr"
SCHEDULE_URL = f"{BASE}/tennisRental/rentalScheduleMonth.do"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; tennisbinjari.kr court availability)"}
MAX_CONCURRENT = 3
MIN_INTERVAL = 0.15  # 초. 요청을 시작하는 최소 간격

_OPEN_RE = re.compile(
    r'href="/tennisRental/rentalApplyRegForm\.do\?[^"]*"\s+title="(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*'
    r'(\d{2}:\d{2})~(\d{2}:\d{2})"'
)

_slots = threading.BoundedSemaphore(MAX_CONCURRENT)
_start_lock = threading.Lock()
_last_start = 0.0


def _get(session: requests.Session, params: dict) -> str:
    global _last_start
    with _slots:  # 동시에 MAX_CONCURRENT개까지
        with _start_lock:  # 시작 간격을 둔다
            wait = _last_start + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_start = time.monotonic()
        resp = session.get(SCHEDULE_URL, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    if "WEBFRONT" in resp.text[:2000] or "rentalScheduleMonth" not in resp.text:
        # 방화벽 차단 화면이나 엉뚱한 페이지를 빈 결과로 오해하지 않도록 실패로 처리한다
        raise requests.RequestException("남동구 예약현황 페이지를 읽지 못함")
    return resp.text


def fetch_month(session: requests.Session, court_key: str, year: int, month: int) -> list[Slot]:
    """court_key("inst_cd:rental_seq", 예: "tc03:5") 코트의 해당 연/월 빈 시간을 돌려준다."""
    inst_cd, rental_seq = court_key.split(":")
    text = _get(session, {"inst_cd": inst_cd, "rental_seq": rental_seq, "sch_ym": f"{year}-{month:02d}"})
    slots = []
    for y, m, d, begin, end in _OPEN_RE.findall(text):
        if int(y) != year or int(m) != month:
            continue
        slots.append(Slot(date=f"{year}-{month:02d}-{int(d):02d}", begin=begin, end=end, status="AVAILABLE"))
    return slots
