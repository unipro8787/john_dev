# 검색 결과와 테니스장 페이지에 붙이는 시설 특징(실내/실외, 바닥, 조명).
# 각 예약 사이트의 시설 안내에 적힌 것만 넣는다(2026-10-27 확인). 안내에 없는 항목은 None으로 두고 화면에 표시하지 않는다.
#
# 실내/실외: 실내 테니스장은 시설 이름과 안내에 "실내"가 붙는다. 화성은 안내에 "야외 코트"로 나오고,
# 부천·경주도 "실내"가 붙은 곳(부천실내테니스장) 말고는 실외로 본다. 강남은 확인하지 못해 비워 둔다.
#
# 조명 판단 기준
# - 안내에 조명 설비가 직접 나오면(조명 버튼·스위치·조명 설정·조명 사용료) 있음
# - 18~22시 야간 요금을 따로 받는 곳은 있음 (화성은 조명이 없는 금반 2번 코트만 어두운 시간을 무료로 운영한다고 따로 안내함)
# - 그 밖에는 None

from __future__ import annotations

# light: True(야간 조명 있음) / False(조명 없음) / 문자열(일부 코트만, 화면에 그대로 표시) / None(모름)
FEATURES: dict[str, dict] = {
    # 화성: 시설 안내에 "야외 코트". 바닥 재질은 안내에 없어서, 운영자가 직접 이용해 확인한 곳만 넣었다(2026-10-27).
    "여울공원 테니스장": {"indoor": False, "surface": "인조잔디", "light": True},     # 야간 조명 버튼 박스 안내, 바닥은 운영자 확인
    "금반저류지 테니스장": {"indoor": False, "surface": "하드", "light": "1번 코트만 조명"},  # 2번 코트는 조명시설 없음, 바닥은 운영자 확인
    "왕배산체육공원 테니스장": {"indoor": False, "surface": "하드", "light": True},   # 조·야간(18~22시) 요금, 바닥·조명은 운영자 확인
    "중동 테니스장": {"indoor": False, "surface": "인조잔디", "light": True},         # 조명 OFF 스위치 안내, 바닥은 운영자 확인
    "돌모루 근린공원 테니스장": {"indoor": False, "surface": "하드", "light": True},  # 조·야간(18~22시) 요금, 바닥·조명은 운영자 확인
    "비봉체육공원 테니스장": {"indoor": False, "surface": "마사토", "light": None},    # 바닥은 운영자 확인
    "도원체육공원 테니스장": {"indoor": False, "surface": "인조잔디", "light": None},  # 온라인은 평일 12~17시뿐, 바닥은 운영자 확인
    "매송안보테마공원 테니스장": {"indoor": False, "surface": None, "light": None},    # 06~16시 운영
    "경기화성바이오밸리(마도) 테니스장": {"indoor": False, "surface": None, "light": True},  # 조간 조명 설정 안내
    # 부천: 시설 안내에 코트 종류가 적혀 있다. 18~22시 야간 요금을 받는다(해그늘은 10~18시 무료 운영).
    "복사골테니스장": {"indoor": False, "surface": "하드·클레이", "light": True},
    "원미테니스장": {"indoor": False, "surface": "인조잔디", "light": True},
    "종합운동장테니스장": {"indoor": False, "surface": "하드", "light": True},
    "부천체육관테니스장(하드)": {"indoor": False, "surface": "하드", "light": True},
    "부천실내테니스장": {"indoor": True, "surface": "하드", "light": None},          # 실내라 조명은 따로 표시하지 않는다
    "해그늘체육공원 테니스장": {"indoor": False, "surface": "하드", "light": None},
    "해그늘체육공원 테니스장(인조잔디)": {"indoor": False, "surface": "인조잔디", "light": None},
    "성주산체육공원테니스장": {"indoor": False, "surface": "하드", "light": True},
    "소사배수지테니스장": {"indoor": False, "surface": "하드", "light": True},       # 야간은 21시까지
    "남부수자원테니스장": {"indoor": False, "surface": "하드", "light": True},
    # 경주: 시민테니스장만 클레이로 안내. 외동은 야간 조명 사용료가 있다.
    "강변테니스장(북천)": {"indoor": False, "surface": None, "light": None},
    "시민테니스장(북천)": {"indoor": False, "surface": "클레이", "light": None},
    "건천테니스장": {"indoor": False, "surface": None, "light": None},               # 06~18시 운영
    "외동생활체육공원 테니스장": {"indoor": False, "surface": None, "light": True},
    # 강남: 안내에 실내외·바닥·조명이 나오지 않는다.
    "봉은테니스장": {"indoor": None, "surface": None, "light": None},
    "포이테니스장": {"indoor": None, "surface": None, "light": None},
    "강남세곡체육공원 테니스장": {"indoor": None, "surface": None, "light": None},
}


def feature_tags(name: str) -> list[str]:
    """화면에 붙일 짧은 표시들. 예: ["실외", "하드", "야간 조명"]"""
    f = FEATURES.get(name) or {}
    tags = []
    if f.get("indoor") is not None:
        tags.append("실내" if f["indoor"] else "실외")
    if f.get("surface"):
        tags.append(f["surface"])
    light = f.get("light")
    if light is True:
        tags.append("야간 조명")
    elif light is False:
        tags.append("조명 없음")
    elif isinstance(light, str):
        tags.append(light)
    return tags
