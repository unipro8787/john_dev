# 각 시·구 예약 사이트의 공개 상세 페이지에서 테니스장별 기본 정보(주소·운영시간·요금·문의처 등)를 모아
# data/facility_info.json 으로 저장한다. 시설 소개 페이지(/courts/...)가 이 파일을 읽는다.
#
# 실행: python tools/collect_facility_info.py   (dongtan_tennis_finder 폴더에서)
# 시설이 바뀌거나 요금이 바뀌면 다시 돌려서 파일을 갱신하고, 결과를 눈으로 한 번 확인한 뒤 커밋한다.
# 예약자 이름 같은 개인정보는 가져오지 않는다 (각 사이트의 시설 정보 칸만 읽음).

from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from courts import BUCHEON_FACILITIES, FACILITIES, GANGNAM_FACILITIES, GANGNAM_PHONES, GYEONGJU_FACILITIES  # noqa: E402

OUT = ROOT / "data" / "facility_info.json"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"


def _clean(x: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", x)).split())


def _pairs(page: str) -> dict[str, str]:
    """<dt>/<dd>, <th>/<td> 짝을 {이름: 값}으로 모은다."""
    out: dict[str, str] = {}
    found = re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", page, re.S)
    found += re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", page, re.S)
    for k, v in found:
        k, v = _clean(k), _clean(v)
        if k and v and len(k) < 20 and k not in out:
            out[k] = v
    return out


def hscity(name: str, courts: dict[str, int]) -> dict:
    idx = next(iter(courts.values()))
    url = f"https://yeyak.hscity.go.kr/stadiumDetail.do?stadiumIdx={idx}"
    page = S.get(url, timeout=30).text
    p = _pairs(page)
    loc = re.search(r"(경기\s*화성시[^,<\"']+?)\s*,\s*(\d+\.\d+)\s*,\s*(\d+\.\d+)", page)
    return {
        "address": loc.group(1).strip() if loc else None,
        "lat": float(loc.group(2)) if loc else None,
        "lng": float(loc.group(3)) if loc else None,
        "hours": p.get("사용시간"),
        "operator": p.get("운영기관"),
        "payment": p.get("결제여부"),
        "rules": p.get("신청기간 안내"),
        "note": p.get("비고"),
        "phone": p.get("문의처"),
        "source_url": url,
    }


def bucheon(name: str, courts: dict[str, int]) -> dict:
    seq = next(iter(courts.values()))
    url = f"https://reserv.bucheon.go.kr/site/main/lending/lendingDetail?lending_info_seq={seq}&inst_cate=01&lending_inst_nm=tennis"
    p = _pairs(S.get(url, timeout=30).text)
    slots = p.get("대관시간", "")
    return {
        "hours": (slots.split(",")[0].split("~")[0].strip() + "~" + slots.split(",")[-1].split("~")[-1].strip()) if slots else None,
        "slot_unit": "2시간" if slots else None,
        "days": p.get("대관요일"),
        "fee": p.get("대관료"),
        "operator": p.get("담당기관"),
        "phone": p.get("연락처"),
        "source_url": url,
    }


def gyeongju(name: str, courts: dict[str, str]) -> dict:
    mem, items = next(iter(courts.values())).split(":", 1)
    url = f"https://www.gyeongju.go.kr/reserve/sports_facilities/facility_view.jsp?mem_id={mem}&item_id={items.split(',')[0]}"
    p = _pairs(S.get(url, timeout=30).text)
    return {
        "address": p.get("주소"),
        "fee": p.get("사용료"),
        "phone": p.get("문의전화"),
        "source_url": url,
    }


GANGNAM_INFO_PAGES = {"봉은테니스장": 107, "포이테니스장": 108, "강남세곡체육공원 테니스장": 501}


def gangnam(name: str, courts: dict[str, str]) -> dict:
    company, part, place = next(iter(courts.values())).split(":")
    detail = S.get(
        "https://life.gangnam.go.kr/rest/facilities/place_detail",
        params={"company_code": company, "part_code": part, "place_code": place},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    ).json()
    url = f"https://life.gangnam.go.kr/fmcs/{GANGNAM_INFO_PAGES[name]}"
    text = _clean(re.sub(r"<script.*?</script>|<style.*?</style>", "", S.get(url, timeout=30).text, flags=re.S))
    addr = re.search(r"주소\s+(서울\s*강남구[^지]+?)\s+(?:지하철|버스|층별)", text)
    hours = re.search(r"운영시간\s+(\d{2}:\d{2}\s*~\s*\d{2}:\d{2})", text)
    subway = re.search(r"지하철\s+(지하철[^버]+?)\s+버스", text)
    return {
        "address": addr.group(1).strip() if addr else None,
        "hours": hours.group(1).replace(" ", "") if hours else None,
        "subway": subway.group(1).strip() if subway else None,
        "phone": detail.get("tel") or GANGNAM_PHONES.get(name),
        "confirm_type": detail.get("confirm_type"),
        "receipt_period_example": detail.get("receipt_period"),
        "source_url": url,
    }


def main() -> None:
    info: dict[str, dict] = {}
    for fetch, facilities in ((hscity, FACILITIES), (bucheon, BUCHEON_FACILITIES),
                              (gyeongju, GYEONGJU_FACILITIES), (gangnam, GANGNAM_FACILITIES)):
        for name, courts in facilities.items():
            try:
                info[name] = {k: v for k, v in fetch(name, courts).items() if v not in (None, "")}
            except Exception as e:  # 한 곳이 실패해도 나머지는 모은다
                print(f"[실패] {name}: {e}", file=sys.stderr)
                info[name] = {}
            print(f"{name}: {', '.join(info[name])}")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"collected": date.today().isoformat(), "facilities": info}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
