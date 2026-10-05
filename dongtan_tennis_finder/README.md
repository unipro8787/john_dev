# 동탄 테니스코트 예약 가능 시간대 조회

동탄 지역 테니스코트를 인터넷에서 탐색해 **오늘(또는 지정한 기간) 예약 가능한 코트와 시간대**를 정리해주는 파이썬 프로그램.

## 데이터 소스

**화성시 통합예약시스템 (yeyak.hscity.go.kr)** — 화성시 전체 공공 테니스장 9곳, 24개 코트를 조회한다 (2026-10-06 확장, 이전에는 동탄구 4곳 13면).
로그인이 필요 없다. 사이트의 코트 상세페이지 "예약현황" 탭이 내부적으로 호출하는 공개 JSON API
(`POST /stadium/stadiumReserveUseList.do`)를 그대로 사용한다 (`hscity_client.py`).
웹앱은 코트별 조회를 동시에 6개씩 보내고, 코트·월 단위 결과를 3분간 캐시한다.

조회 대상 코트는 `courts.py`에 등록되어 있다 (권역은 사이트의 [1부]/[2부] 운영 구분을 따름):

- **동탄·병점권** — 여울공원(1~3), 금반저류지(1~2), 왕배산체육공원(1,2,5,6,7,8 — 3,4번은 사용수익허가 코트라
  이 시스템에서 실제 예약 불가해 제외), 중동(1~2), 돌모루 근린공원(8번)
- **서부권** — 비봉체육공원(1~3), 도원체육공원(1~4, 평일 오후 무료), 매송안보테마공원(1~2), 경기화성바이오밸리(마도)(1)

전체 목록 재확인: `https://yeyak.hscity.go.kr/1053/3026/stadiumList.do?searchKeyword=테니스&recordCountPerPage=100`

### 부천시 (2026-10-06 추가)

**부천시 공공서비스예약 (reserv.bucheon.go.kr)** — 테니스장 10곳 (원미구 7, 소사구 3). `bucheon_client.py`.
테니스장 상세 페이지(`/site/main/lending/lendingDetail?lending_info_seq=…&sch_year=…&sch_month=…`)의
"예약현황" 달력이 로그인 없이 날짜·시간대별로 예약가능(`li.grn`)/예약완료(`li.red`)를 그려 준다.
코트별이 아니라 **시설 단위**라 코트 이름 자리에 "시설 대관"으로 표시한다.

- 예약완료 칸의 예약자 이름 일부(예: 임*정)는 파싱·저장하지 않는다 (상태 class만 읽음).
- 다음 달 예약은 매달 20일 10시에 열려서, 그 전에는 다음 달 달력이 비어 있다.
- 오정레포츠센터 테니스장(188)은 접수종료라 제외. 목록 재확인: `lendingList?lending_inst_nm=tennis&inst_cate=01`
- 부천 상세 페이지는 응답이 2초 안팎이라, 10곳 첫 조회가 4초쯤 걸린다 (이후 3분 캐시).

화면 맨 위 "지역" 탭에서 화성시/부천시를 고르고, 도시마다 고른 시설을 따로 기억한다
(localStorage `tennisFinder.v3`, 예전 `selectedFacilities.v2` 값은 화성시 선택으로 옮겨 담음).
`/api/facilities`는 `{cities: [{name, booking_url, booking_name, regions: [{name, facilities: [...]}]}]}` 형태,
`/api/search` 결과 항목에 `city`가 붙는다. `facility`를 지정하지 않으면 화성시 전체를 조회한다.

### 다른 시·구 조사 결과 (2026-10-06)

로그인 없이 시간대별 현황 공개 + robots.txt 허용 + 접속 차단 장치 없음 조건으로 확인했다.
불가: 수원·고양 등 경기공유서비스 사용 시군(robots 전체 금지 + NetFunnel), 서울(예약 달력 AJAX에 비정상 접근 차단),
의왕·세종·부산 스포원(robots 전체 금지), 고양도시관리공사(`/rent/` 금지), 용인(본인인증 후에만 시간대 표시),
인천(월 단위 접수, 시간대 비공개), 오산(네이버 예약), 성남(테니스장 미등록), 평택·안양·대구·광주·대전·울산(온라인 실시간 시스템 미확인).
조건부: 경주(날짜 단위 예약가능 여부만 공개), 서울 강남구(공공데이터포털 "강남구_테니스장 현황" API, 키 신청 후 확인 필요).

### 수원은 왜 없나

수원시 공공 테니스장(만석공원, 나촌배수지 등)은 수원시 홈페이지(suwon.go.kr/web/reserv/faci)에 "외부예약"으로만
올라와 있고 실제 예약은 경기공유서비스(share.gg.go.kr)에서 받는다. 수원시 페이지의 예약현황 API는 빈 배열만 준다.
경기공유서비스는 robots.txt가 전체 수집을 금지(`Disallow: /`)하고 모든 접속을 NetFunnel 대기열로 통과시키므로,
자동 조회를 붙이지 않았다 (사이트 정책 존중). 소개 페이지 FAQ에 이 안내를 넣어 두었다.

## 사용법

```bash
pip install -r requirements.txt
python check_availability.py              # 오늘 하루 조회
python check_availability.py --days 7      # 오늘부터 7일간 조회
python check_availability.py --date 2026-09-20   # 특정 날짜만 조회
```

실행하면 화면에 결과를 출력하고, 같은 폴더에 `availability_YYYY-MM-DD_YYYY-MM-DD.txt` 파일로도 저장한다.

## 왜 "테니스스타파크"는 빠져 있나

처음 요청은 "동탄 테니스스타파크"를 테스트 대상으로 했지만, 조사 결과:

- **테니스스타파크**는 실제로는 오산시 부산동 소재 사설 클럽으로, 온라인 예약 시스템 없이 전화/DM으로만
  예약을 받는다 (031-205-0005, 010-8898-8732). 조회할 수 있는 시간표 자체가 없다.
- 네이버 예약(booking.naver.com)에 연동되어 있을 가능성이 있으나, 이 환경의 브라우저/웹요청 도구가
  naver.com 도메인 전체를 정책상 접근 차단하고 있어(우회 불가) 실제 예약 페이지 구조를 확인하지 못했다.

**추후 네이버 예약 연동을 추가하려면**: 사용자가 직접 브라우저 개발자도구(F12) → Network 탭에서
"테니스스타파크"의 네이버 예약 페이지를 열어 예약 가능 여부를 조회하는 XHR 요청(URL, 요청/응답 본문)을
캡처해서 전달하면, 그 구조에 맞는 모듈(`naver_booking.py` 등)을 추가할 수 있다.

## 다른 동탄 코트 추가하기

`courts.py`에 `stadiumIdx`만 추가하면 된다. yeyak.hscity.go.kr에서 코트 상세페이지 URL의
`stadiumIdx=` 값을 그대로 쓰면 된다 (예: `stadiumDetail.do?stadiumIdx=230`).

## 웹앱 (검색 UI, 아이폰에서 사용)

CLI 스크립트와 별개로, 같은 조회 로직을 웹 UI로 감싼 Flask 앱(`app.py`)이 있다.
아이폰 Safari에서 접속 후 "홈 화면에 추가"하면 앱 아이콘처럼 쓸 수 있다 (PWA).

### 로컬 실행

```bash
pip install -r requirements.txt
python app.py
```

`http://127.0.0.1:5000` 접속. 같은 와이파이의 아이폰에서 쓰려면 PC의 내부 IP로 접속
(예: `http://192.168.0.x:5000`, `python app.py`는 기본적으로 로컬호스트만 바인딩하므로
필요하면 `app.run(host="0.0.0.0")`로 바꿔야 함).

### 배포 (Render 무료 플랜 예시)

1. 이 저장소를 GitHub에 push.
2. [render.com](https://render.com) 가입 후 "New Web Service" → 이 GitHub 저장소 선택.
3. **Root Directory**: `dongtan_tennis_finder`
4. **Build Command**: `pip install -r requirements.txt`
5. **Start Command**: `gunicorn app:app`
6. 배포 완료 후 발급되는 `https://xxxx.onrender.com` 주소를 아이폰 Safari에서 열고
   공유 버튼 → "홈 화면에 추가"로 저장.

무료 플랜은 일정 시간 미사용 시 슬립 상태가 되어 첫 요청이 느릴 수 있다.

### API 엔드포인트

- `GET /api/facilities` — 시설/코트 목록 (stadiumIdx 제외)
- `GET /api/search?start=YYYY-MM-DD&end=YYYY-MM-DD&facility=시설명&time_start=HH:MM&time_end=HH:MM` — 예약 가능 시간대 목록 (JSON)
  - `facility`는 반복 지정 가능, 생략 시 전체 시설
  - `time_start`/`time_end`는 생략 가능 (전체 시간). 지정한 시간 구간과 겹치는 슬롯만 반환
  - 조회 기간은 최대 45일 (`app.py`의 `MAX_RANGE_DAYS`)

### 검색 노출·광고 준비 (2026-10-05 추가)

페이지: `/`(검색 + 안내 글), `/about`(서비스 소개·FAQ), `/privacy`(개인정보처리방침).
검색엔진용: `/robots.txt`(`/api/` 제외), `/sitemap.xml`, 페이지별 canonical·OG 태그, 메인에 JSON-LD(WebApplication).
운영용: `/healthz`(상태 확인), `/ads.txt`(애드센스 ID를 설정했을 때만).

Render → 서비스 → **Environment** 에서 아래 값을 넣으면 코드 수정 없이 켜진다 (저장하면 자동 재배포):

| 변수 | 넣을 값 | 켜지는 것 |
|---|---|---|
| `SITE_URL` | 정식 도메인 (예: `https://dongtantennis.kr`) | canonical·사이트맵 주소, onrender.com → 정식 도메인 301 이동 |
| `GOOGLE_SITE_VERIFICATION` | 서치 콘솔 "HTML 태그" 방식의 `content` 값 | 구글 소유 확인 메타 태그 |
| `NAVER_SITE_VERIFICATION` | 네이버 서치어드바이저 "HTML 태그" 방식의 `content` 값 | 네이버 소유 확인 메타 태그 |
| `ADSENSE_CLIENT` | 애드센스 게시자 ID (`ca-pub-` + 숫자) | 광고 스크립트, `/ads.txt`, 개인정보처리방침의 광고 안내 |
| `CONTACT_EMAIL` | 문의 받을 메일 | 소개·개인정보처리방침의 문의처 |

개인정보처리방침이나 페이지 내용을 바꾸면 `app.py`의 `POLICY_EFFECTIVE`, `PAGES_UPDATED` 날짜도 함께 바꾼다.
