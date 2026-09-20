# 동탄 지역 공공 테니스장(화성시 통합예약시스템 등록분)의 예약 가능 시간대를 조회한다.
# 로그인 불필요 - "예약현황" 탭이 쓰는 공개 API를 그대로 호출한다 (hscity_client.py 참고).
#
# 사용법:
#   python check_availability.py            # 오늘 하루 조회
#   python check_availability.py --days 7    # 오늘부터 7일간 조회
#   python check_availability.py --date 2026-09-20   # 특정 날짜만 조회

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

import requests

from courts import FACILITIES
from hscity_client import fetch_range

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 기본 cp949에서 한글 깨짐 방지


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="동탄 지역 테니스장 예약 가능 시간대 조회")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, help="오늘부터 N일간 조회 (기본: 오늘 하루)")
    group.add_argument("--date", type=str, help="특정 날짜만 조회 (YYYY-MM-DD)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    today = date.today()

    if args.date:
        start = end = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.days:
        start = today
        end = today + timedelta(days=args.days - 1)
    else:
        start = end = today

    period_desc = start.isoformat() if start == end else f"{start.isoformat()} ~ {end.isoformat()}"
    print(f"동탄 지역 테니스장 예약 가능 시간대 조회 ({period_desc})\n")

    session = requests.Session()
    found_any = False
    lines: list[str] = [f"동탄 지역 테니스장 예약 가능 시간대 ({period_desc})", ""]

    for facility_name, courts in FACILITIES.items():
        facility_lines: list[str] = []
        for court_label, stadium_idx in courts.items():
            slots = fetch_range(session, stadium_idx, start, end)
            available = [s for s in slots if s.status == "AVAILABLE"]
            for slot in sorted(available, key=lambda s: (s.date, s.begin)):
                facility_lines.append(f"  [{court_label}] {slot.date} {slot.begin}~{slot.end}")
        if facility_lines:
            found_any = True
            header = f"■ {facility_name}"
            print(header)
            lines.append(header)
            for line in facility_lines:
                print(line)
                lines.append(line)
            print()
            lines.append("")

    if not found_any:
        msg = "조회 기간 내 예약 가능한 시간대가 없습니다."
        print(msg)
        lines.append(msg)

    out_name = f"availability_{start.isoformat()}_{end.isoformat()}.txt"
    with open(out_name, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"결과 파일 저장: {out_name}")


if __name__ == "__main__":
    main()
