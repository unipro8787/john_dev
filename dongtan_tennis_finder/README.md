# 동탄 테니스코트 예약 가능 시간대 조회

동탄 지역 테니스코트를 인터넷에서 탐색해 **오늘(또는 지정한 기간) 예약 가능한 코트와 시간대**를 정리해주는 파이썬 프로그램.

## 데이터 소스

**화성시 통합예약시스템 (yeyak.hscity.go.kr)** — 화성시 전체 공공 테니스장 9곳, 24개 코트를 조회한다 (2026-10-05 확장, 이전에는 동탄구 4곳 13면).
로그인이 필요 없다. 사이트의 코트 상세페이지 "예약현황" 탭이 내부적으로 호출하는 공개 JSON API
(`POST /stadium/stadiumReserveUseList.do`)를 그대로 사용한다 (`hscity_client.py`).
웹앱은 코트별 조회를 동시에 6개씩 보내고, 코트·월 단위 결과를 3분간 캐시한다.

조회 대상 코트는 `courts.py`에 등록되어 있다 (권역은 사이트의 [1부]/[2부] 운영 구분을 따름):

- **동탄·병점권** — 여울공원(1~3), 금반저류지(1~2), 왕배산체육공원(1,2,5,6,7,8 — 3,4번은 사용수익허가 코트라
  이 시스템에서 실제 예약 불가해 제외), 중동(1~2), 돌모루 근린공원(8번)
- **서부권** — 비봉체육공원(1~3), 도원체육공원(1~4, 평일 오후 무료), 매송안보테마공원(1~2), 경기화성바이오밸리(마도)(1)

전체 목록 재확인: `https://yeyak.hscity.go.kr/1053/3026/stadiumList.do?searchKeyword=테니스&recordCountPerPage=100`

### 부천시 (2026-10-05 추가)

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

### 경주시 (2026-10-05 추가, 날짜 단위)

**경주시 통합예약 (www.gyeongju.go.kr/reserve)** — 테니스 15면: 강변(북천) 3~10번, 시민(북천) 2~5번, 건천 1면,
외동생활체육공원 1·2번. `gyeongju_client.py`. 시설 상세 페이지가 달을 바꿀 때 부르는
`/reserve/ajxAgent/loadItemCal.jsp` (POST `mem_id`, `item_id`, `selMonth=YYYYMM01`)가 로그인 없이 날짜별
예약가능(`p.reserveYES`, `id="selRsvDate_YYYYMMDD"`)/예약불가를 돌려준다.

- **날짜 단위만** 공개된다. 시간대 API(`ajxRsvExplodTime.jsp`)는 로그인 세션 없이 부르면 모든 시간을
  예약됨으로 돌려줘 믿을 수 없어서 쓰지 않는다. 결과는 begin/end가 빈 슬롯(`day_only: true`)으로 내보내고
  화면에서는 "그날 빈 시간 있음"으로 표시하며, 시간대 필터를 적용하지 않는다.
- 인터넷 예약 일반 테니스 코트만 넣었다. 방문 예약(강변 1·2), 전화 예약(시민 1), 소프트테니스장은 제외.
- 외동은 계절(10~3월 / 4~9월)마다 항목이 나뉘어 있어 코트 값에 두 item_id를 쉼표로 적고 결과를 합친다.
- 사이트 이름은 지역이 셋이 되어 "테니스코트 빈자리 찾기"로 바꿨다 (검색 제목에는 화성·동탄·부천·경주 유지).

### 서울 강남구 (2026-10-05 추가)

**강남구 통합예약 (life.gangnam.go.kr)** — 봉은 1~4번, 포이 A·B, 강남세곡체육공원 1~4번 (10면). `gangnam_client.py`.
robots.txt 전체 허용. 시설예약 화면(`/fmcs/54`, 스크립트 `modules_fmcs_facilities/default/js/default.js`)이
로그인 없이 부르는 REST API를 같은 규칙으로 쓴다.

- 코트 코드: `rest/common/company?type=F` → `rest/common/part` → `rest/common/place` 로 확인한 `company:part:place`
  (봉은 GNCC05:04:34~37, 포이 GNCC06:04:15·16, 세곡 GNCC33:04:13~16).
- `rest/facilities/place_month_state_list`(날짜 상태)와 `place_month_time_state_list`(한 달치 시간대)를
  코트·월마다 한 번씩 부른다 (각 0.1초 안팎).
- 날짜 상태 10/11/15 = 온라인 신청 가능, 20 = 예약불가/마감, 30 = 대회·휴관. 시간대 `use_yn` Y/E/U/D는 빈 시간 아님.
- 강남구는 **매월 25일까지 다음 달을 온라인으로** 받고, 그 뒤 남은 시간은 시설 전화 예약이다.
  온라인 신청기간이 끝난 달(전달 26일 이후, 한국 시간)의 빈 칸은 `AVAILABLE_PHONE` → 화면에 ☎ 표시.
  신청기간이 끝나기 전 달은 정기 대관 몇 칸만 빼고 전부 비어 보여 사실과 달라서 내보내지 않는다.
- 시간대 응답의 `detail`에는 예약 단체·예약자 실명이 들어 있다. `use_yn`만 읽고 `detail`은 읽지도 저장하지도 않는다.
- 공공데이터포털 "서울특별시 강남구_테니스장 현황" 데이터셋은 2025-09-04 일회성 자료라 쓰지 않았다.

### 다른 시·구 조사 결과 (2026-10-05)

로그인 없이 시간대별 현황 공개 + robots.txt 허용 + 접속 차단 장치 없음 조건으로 확인했다.
불가: 수원·고양 등 경기공유서비스 사용 시군(robots 전체 금지 + NetFunnel), 서울(예약 달력 AJAX에 비정상 접근 차단),
의왕·세종·부산 스포원(robots 전체 금지), 고양도시관리공사(`/rent/` 금지), 용인(본인인증 후에만 시간대 표시),
인천(월 단위 접수, 시간대 비공개), 오산(네이버 예약), 성남(테니스장 미등록), 평택·안양·대구·광주·대전·울산(온라인 실시간 시스템 미확인).


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

### 콘텐츠 페이지 (애드센스 심사 대비, 2026-10-05 추가)

- `/courts` 테니스장 목록, `/courts/<slug>` 테니스장별 페이지 26개 (주소·운영시간·요금·문의처·예약 방법 +
  앞으로 2주 빈 시간을 `/api/search`로 바로 보여 줌, SportsActivityLocation JSON-LD)
- `/guide` 예약 가이드 목록, `/guide/<city>` 지역별 예약 방법 4편 (`content.py`의 `GUIDES`, Article JSON-LD)
- `/terms` 이용약관, `/contact` 문의(`CONTACT_EMAIL` 필요), 사용자 404 페이지, 위쪽 주 메뉴
- 시설 정보는 `python tools/collect_facility_info.py`가 각 기관 공개 상세 페이지에서 모아 `data/facility_info.json`에 저장한다.
  요금·운영시간이 바뀌면 다시 돌리고 결과를 확인한 뒤 커밋한다. 시설 페이지 주소(`content.FACILITY_SLUGS`)는 바꾸지 않는다.
- 가이드 문구는 공식 안내를 바탕으로 직접 정리한 글이다. 규정이 바뀌면 `GUIDES`와 `GUIDE_CHECKED`를 함께 고친다.
