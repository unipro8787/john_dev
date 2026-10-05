# 화성시 통합예약시스템(yeyak.hscity.go.kr)에 등록된 화성시 전체 공공 테니스장 코트 목록.
# /1053/3026/stadiumList.do?searchKeyword=테니스 로 전체 목록을 직접 조회해 확인한 값 (2026-10-05 기준, 26면).
#
# 왕배산체육공원 3, 4번 코트(stadiumIdx 232, 233)는 사용수익허가 코트로 이 시스템에서 실제 신청이 불가능해
# 제외했다 (tennis_booking/book_court.py의 SKIP_COURTS와 동일한 이유. 예약현황 API도 늘 예약가능 0건).
#
# 권역은 사이트가 코트 이름 앞에 붙인 운영 구분([1부]/[2부])을 따른다. 1부는 동탄·병점 쪽,
# 2부는 서부(비봉·매송·마도 등) 시설이다.

FACILITIES: dict[str, dict[str, int]] = {
    # ── 동탄·병점권 ([1부])
    "여울공원 테니스장": {
        "1번 코트": 193,
        "2번 코트": 195,
        "3번 코트": 196,
    },
    "금반저류지 테니스장": {
        "1번 코트": 212,
        "2번 코트": 243,
    },
    "왕배산체육공원 테니스장": {
        "1번 코트": 230,
        "2번 코트": 231,
        "5번 코트": 235,
        "6번 코트": 236,
        "7번 코트": 237,
        "8번 코트": 238,
    },
    "중동 테니스장": {
        "1번 코트": 245,
        "2번 코트": 246,
    },
    "돌모루 근린공원 테니스장": {
        "8번 코트": 213,
    },
    # ── 서부권 ([2부])
    "비봉체육공원 테니스장": {
        "1번 코트": 207,
        "2번 코트": 208,
        "3번 코트": 242,
    },
    "도원체육공원 테니스장": {
        "1번 코트(평일 오후)": 226,
        "2번 코트(평일 오후)": 227,
        "3번 코트(평일 오후)": 228,
        "4번 코트(평일 오후)": 229,
    },
    "매송안보테마공원 테니스장": {
        "1번 코트": 209,
        "2번 코트": 210,
    },
    "경기화성바이오밸리(마도) 테니스장": {
        "1번 코트": 205,
    },
}

REGIONS: dict[str, list[str]] = {
    "동탄·병점권": [
        "여울공원 테니스장",
        "금반저류지 테니스장",
        "왕배산체육공원 테니스장",
        "중동 테니스장",
        "돌모루 근린공원 테니스장",
    ],
    "서부권": [
        "비봉체육공원 테니스장",
        "도원체육공원 테니스장",
        "매송안보테마공원 테니스장",
        "경기화성바이오밸리(마도) 테니스장",
    ],
}

# 이용 조건이 다른 시설에 붙이는 짧은 안내 (화면 시설 목록에 함께 표시)
FACILITY_NOTES: dict[str, str] = {
    "도원체육공원 테니스장": "평일 오후 무료 개방",
}

assert sorted(f for names in REGIONS.values() for f in names) == sorted(FACILITIES), "REGIONS와 FACILITIES가 어긋남"


# ── 부천시 공공서비스예약(reserv.bucheon.go.kr) 테니스장 (2026-10-05 기준, 접수중 10곳)
# lendingList?lending_inst_nm=tennis 목록에서 확인한 lending_info_seq 값. 부천은 코트별이 아니라
# 시설 단위로 시간대별 예약가능 여부를 보여 주므로 코트 이름 자리에 "시설 대관"을 둔다.
# 오정레포츠센터 테니스장(188)은 접수종료 상태라 제외했다.
BUCHEON_FACILITIES: dict[str, dict[str, int]] = {
    "복사골테니스장": {"시설 대관": 111},
    "원미테니스장": {"시설 대관": 112},
    "종합운동장테니스장": {"시설 대관": 115},
    "부천체육관테니스장(하드)": {"시설 대관": 192},
    "부천실내테니스장": {"시설 대관": 195},
    "해그늘체육공원 테니스장": {"시설 대관": 194},
    "해그늘체육공원 테니스장(인조잔디)": {"시설 대관": 205},
    "성주산체육공원테니스장": {"시설 대관": 116},
    "소사배수지테니스장": {"시설 대관": 114},
    "남부수자원테니스장": {"시설 대관": 193},
}

BUCHEON_REGIONS: dict[str, list[str]] = {
    "원미구": [
        "복사골테니스장",
        "원미테니스장",
        "종합운동장테니스장",
        "부천체육관테니스장(하드)",
        "부천실내테니스장",
        "해그늘체육공원 테니스장",
        "해그늘체육공원 테니스장(인조잔디)",
    ],
    "소사구": [
        "성주산체육공원테니스장",
        "소사배수지테니스장",
        "남부수자원테니스장",
    ],
}

FACILITY_NOTES["부천실내테니스장"] = "실내"

assert sorted(f for names in BUCHEON_REGIONS.values() for f in names) == sorted(BUCHEON_FACILITIES), "부천 REGIONS 어긋남"


# ── 경주시 통합예약(www.gyeongju.go.kr/reserve) 테니스장 (2026-10-05 기준)
# sports_facilities/list.jsp 목록에서 "인터넷" 예약인 일반 테니스 코트만 넣었다.
# 방문 예약(강변 1·2코트), 전화 예약(시민 1코트), 소프트테니스장(정구)은 제외.
# 경주는 날짜 단위로만 예약 가능 여부를 공개하므로 결과도 "그날 빈 시간 있음"으로만 보여 준다.
# 코트 값은 "mem_id:item_id". 외동은 계절(10~3월 / 4~9월)마다 항목이 나뉘어 있어 두 항목을 합친다.
GYEONGJU_FACILITIES: dict[str, dict[str, str]] = {
    "강변테니스장(북천)": {f"{n}번 코트": f"B0000031:T00002{n + 57:02d}" for n in range(3, 11)},
    "시민테니스장(북천)": {f"{n}번 코트": f"B0000031:T00002{n + 67:02d}" for n in range(2, 6)},
    "건천테니스장": {"코트": "B0000033:T0000280"},
    "외동생활체육공원 테니스장": {
        "1번 코트": "B0000027:T0000341,T0000342",
        "2번 코트": "B0000027:T0000299,T0000313",
    },
}

GYEONGJU_REGIONS: dict[str, list[str]] = {
    "경주 시내": ["강변테니스장(북천)", "시민테니스장(북천)"],
    "건천·외동": ["건천테니스장", "외동생활체육공원 테니스장"],
}

assert sorted(f for names in GYEONGJU_REGIONS.values() for f in names) == sorted(GYEONGJU_FACILITIES), "경주 REGIONS 어긋남"


# ── 서울 강남구 통합예약(life.gangnam.go.kr) 테니스장 (2026-10-05 기준)
# rest/common/company(type=F) → part → place 로 확인한 코드. 값은 "company:part:place".
# 매월 25일까지 다음 달을 온라인으로 받고, 그 뒤 남은 시간은 각 시설에 전화 예약 (gangnam_client 참고).
GANGNAM_FACILITIES: dict[str, dict[str, str]] = {
    "봉은테니스장": {f"{n}번 코트": f"GNCC05:04:{33 + n}" for n in range(1, 5)},
    "포이테니스장": {"A코트": "GNCC06:04:15", "B코트": "GNCC06:04:16"},
    "강남세곡체육공원 테니스장": {f"{n}번 코트": f"GNCC33:04:{12 + n}" for n in range(1, 5)},
}

GANGNAM_REGIONS: dict[str, list[str]] = {
    "강남구": ["봉은테니스장", "포이테니스장", "강남세곡체육공원 테니스장"],
}

# 온라인 신청기간이 끝난 뒤 남은 시간은 전화로 예약한다 (통합예약 시설예약 안내 기준)
GANGNAM_PHONES: dict[str, str] = {
    "봉은테니스장": "02-2176-0890",
    "포이테니스장": "02-2176-0876",
    "강남세곡체육공원 테니스장": "02-2176-0870",
}
for _name, _tel in GANGNAM_PHONES.items():
    FACILITY_NOTES[_name] = f"전화 {_tel}"

assert sorted(f for names in GANGNAM_REGIONS.values() for f in names) == sorted(GANGNAM_FACILITIES), "강남 REGIONS 어긋남"


# ── 도시별 묶음. source는 어느 예약 시스템 클라이언트로 조회할지를 뜻한다.
CITIES: list[dict] = [
    {"name": "화성시", "source": "hscity", "facilities": FACILITIES, "regions": REGIONS,
     "booking_url": "https://yeyak.hscity.go.kr", "booking_name": "화성시 통합예약시스템"},
    {"name": "부천시", "source": "bucheon", "facilities": BUCHEON_FACILITIES, "regions": BUCHEON_REGIONS,
     "booking_url": "https://reserv.bucheon.go.kr", "booking_name": "부천시 공공서비스예약"},
    {"name": "경주시", "source": "gyeongju", "facilities": GYEONGJU_FACILITIES, "regions": GYEONGJU_REGIONS,
     "booking_url": "https://www.gyeongju.go.kr/reserve/sports_facilities/list.jsp", "booking_name": "경주시 통합예약",
     "day_only": True},
    {"name": "서울 강남구", "source": "gangnam", "facilities": GANGNAM_FACILITIES, "regions": GANGNAM_REGIONS,
     "booking_url": "https://life.gangnam.go.kr/fmcs/54", "booking_name": "강남구 통합예약"},
]

# 시설 이름 → (도시 이름, source). 시설 이름은 도시 사이에서도 겹치지 않아야 한다.
FACILITY_CITY: dict[str, tuple[str, str]] = {}
for _city in CITIES:
    for _name in _city["facilities"]:
        assert _name not in FACILITY_CITY, f"시설 이름 중복: {_name}"
        FACILITY_CITY[_name] = (_city["name"], _city["source"])
