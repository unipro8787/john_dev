# 같은 지역 테니스장 비교 표(테니스장 페이지·지역 가이드 페이지 아래쪽)에 쓰는 짧은 값.
#
# 새로 조사한 값은 없다. facility_details.py의 공식 안내 정리(DETAILS_CHECKED)와 data/facility_info.json에서
# 코트 수·운영시간·평일 낮 요금만 뽑아 짧게 적었다. 공식 안내에 없는 값은 "—"로 두고 지어내지 않는다.
# 시설 규정을 고치면 여기 값도 함께 고친다.
#
# online: 이 사이트에서 빈 시간을 보여 주는(온라인 예약) 코트 수 / court: 코트 구성 / hours: 운영시간(온라인 예약 기준)
# fee: 평일 낮 요금 / note: 비교할 때 알아 둘 한 줄

from __future__ import annotations

_HS = "8,000원 (2시간)"
_BC = "6,000원 (2시간)"

COMPARE: dict[str, dict] = {
    # 화성시
    "여울공원 테니스장": {"online": 3, "court": "야외 3면", "hours": "06~22시", "fee": _HS, "note": "이른 아침·저녁 모두 가능"},
    "금반저류지 테니스장": {"online": 2, "court": "야외 2면", "hours": "14~22시", "fee": _HS, "note": "2번 코트는 조명 없음(어두운 시간 무료)"},
    "왕배산체육공원 테니스장": {"online": 6, "court": "온라인 6면 (전체 8면)", "hours": "06~22시", "fee": _HS, "note": "8번 코트는 평일 14~22시 아카데미 사용"},
    "중동 테니스장": {"online": 2, "court": "야외 2면", "hours": "06~22시", "fee": _HS, "note": "2026년 8월부터 유료"},
    "돌모루 근린공원 테니스장": {"online": 1, "court": "온라인 1면 (전체 8면)", "hours": "06~22시", "fee": _HS, "note": "1~7번 코트는 현장 발권"},
    "비봉체육공원 테니스장": {"online": 3, "court": "야외 3면", "hours": "평일 12~22시 예약", "fee": "—", "note": "평일 오전 무료 개방(선착순)"},
    "도원체육공원 테니스장": {"online": 4, "court": "야외 4면", "hours": "평일 12~17시만 온라인", "fee": "—", "note": "저녁·휴일은 현장 예약"},
    "매송안보테마공원 테니스장": {"online": 2, "court": "야외 2면 (군 시설 안)", "hours": "주말·공휴일 06~16시", "fee": "—", "note": "평일 이용 불가, 출입 절차 있음"},
    "경기화성바이오밸리(마도) 테니스장": {"online": 1, "court": "야외 1면", "hours": "06~22시", "fee": _HS, "note": "이용일 2일 전 마감"},
    # 부천시 (시설 단위 예약)
    "복사골테니스장": {"online": 6, "court": "하드 3면 + 클레이 3면", "hours": "06~22시", "fee": _BC, "note": "하드·클레이 중 골라 칠 수 있음"},
    "원미테니스장": {"online": 6, "court": "인조잔디 6면", "hours": "06~22시", "fee": _BC, "note": ""},
    "종합운동장테니스장": {"online": 13, "court": "하드 13면", "hours": "06~22시", "fee": _BC, "note": "부천에서 코트가 가장 많음"},
    "부천체육관테니스장(하드)": {"online": 2, "court": "야외 하드 2면", "hours": "06~22시", "fee": _BC, "note": "실내테니스장과 다른 예약 항목"},
    "부천실내테니스장": {"online": 3, "court": "실내 하드 3면", "hours": "06~22시", "fee": "30,000원 (2시간)", "note": "날씨 상관없음, 20일 오후 7시 오픈"},
    "해그늘체육공원 테니스장": {"online": 2, "court": "하드 2면", "hours": "10~18시", "fee": "무료", "note": "16일 오전 9시 오픈, 노쇼 1회 1개월 제한"},
    "해그늘체육공원 테니스장(인조잔디)": {"online": 2, "court": "인조잔디 2면", "hours": "10~18시", "fee": "무료", "note": "A코트 평일 10~14시 어르신 전용"},
    "성주산체육공원테니스장": {"online": 1, "court": "하드 1면", "hours": "06~22시", "fee": _BC, "note": ""},
    "소사배수지테니스장": {"online": 2, "court": "하드 2면", "hours": "06~21시", "fee": _BC, "note": "다른 곳보다 1시간 일찍 닫음"},
    "남부수자원테니스장": {"online": 3, "court": "하드 3면", "hours": "06~22시", "fee": _BC, "note": "온라인으로만 예약"},
    # 경주시
    "강변테니스장(북천)": {"online": 8, "court": "온라인 8면 (3~10번)", "hours": "연중무휴", "fee": "1,500원 (1시간)", "note": "경주시민만 신청"},
    "시민테니스장(북천)": {"online": 4, "court": "클레이, 온라인 4면", "hours": "연중무휴", "fee": "1,500원 (1시간)", "note": "클레이 전용 신발"},
    "건천테니스장": {"online": 1, "court": "—", "hours": "06~18시", "fee": "1인 1,500원 (1시간)", "note": "승인은 평일에만"},
    "외동생활체육공원 테니스장": {"online": 2, "court": "2면", "hours": "09~22시, 월요일 휴무", "fee": "개인 1인 1,500원 (1시간)", "note": "야간 조명비 별도"},
    # 서울 강남구
    "봉은테니스장": {"online": 4, "court": "4면, 탈의실", "hours": "06~22시", "fee": "—", "note": "삼성중앙역·봉은사역 근처"},
    "포이테니스장": {"online": 2, "court": "3면 (반코트 1면 포함)", "hours": "06~22시", "fee": "—", "note": "온라인 A·B 코트"},
    "강남세곡체육공원 테니스장": {"online": 4, "court": "4면, 샤워실", "hours": "화~일 06~22시", "fee": "—", "note": "월요일 휴무"},
}


def _won(fee: str) -> int:
    """"1인 1,500원 (1시간)" → 1500"""
    return int(fee.split("원")[0].split()[-1].replace(",", ""))


def compare_rows(facilities: list[dict]) -> list[dict]:
    """facility_entries() 결과(같은 지역 시설들)를 비교 표의 행으로 바꾼다."""
    return [{"name": f["name"], "slug": f["slug"], **COMPARE[f["name"]]} for f in facilities if f["name"] in COMPARE]


def highlights(name: str, facilities: list[dict]) -> list[str]:
    """같은 지역 안에서 이 시설이 눈에 띄는 점을 비교 표 값으로 계산해 짧은 문장으로 돌려준다."""
    rows = compare_rows(facilities)
    me = next((r for r in rows if r["name"] == name), None)
    if not me or len(rows) < 2:
        return []
    out = []
    most = max(r["online"] for r in rows)
    if me["online"] == most and sum(r["online"] == most for r in rows) == 1:
        out.append(f"이 지역에서 이 사이트로 빈 시간을 볼 수 있는 코트가 가장 많은 곳입니다({most}면). 원하는 시간이 꽉 찼을 때 먼저 확인해 볼 만합니다.")
    if me["online"] == 1:
        out.append("온라인으로 예약할 수 있는 코트가 1면뿐입니다. 원하는 시간이 이미 찼다면 아래 표에서 같은 지역의 코트가 많은 곳도 함께 보세요.")
    if me["fee"] == "무료":
        out.append("대관료가 없는 무료 테니스장입니다. 다만 미리 예약해야 쓸 수 있습니다.")
    paid = {r["name"]: _won(r["fee"]) for r in rows if r["fee"] not in ("—", "무료")}
    if name in paid and all(paid[name] > v for n, v in paid.items() if n != name):
        out.append("같은 지역 유료 코트 가운데 요금이 가장 높은 편입니다. 날씨와 상관없이 칠 수 있는지 등 차이를 확인하고 고르세요.")
    return out
