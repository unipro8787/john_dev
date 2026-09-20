# 동탄 테니스코트 예약 가능 시간대 조회

동탄 지역 테니스코트를 인터넷에서 탐색해 **오늘(또는 지정한 기간) 예약 가능한 코트와 시간대**를 정리해주는 파이썬 프로그램.

## 데이터 소스

**화성시 통합예약시스템 (yeyak.hscity.go.kr)** — 동탄구 소재 공공 테니스장 15개 코트를 조회한다.
로그인이 필요 없다. 사이트의 코트 상세페이지 "예약현황" 탭이 내부적으로 호출하는 공개 JSON API
(`POST /stadium/stadiumReserveUseList.do`)를 그대로 사용한다 (`hscity_client.py`).

조회 대상 코트는 `courts.py`에 등록되어 있다:

- 여울공원 테니스장 (1~3번)
- 금반저류지 테니스장 (1~2번)
- 왕배산체육공원 테니스장 (1,2,5,6,7,8번 — 3,4번은 사용수익허가 코트라 이 시스템에서 실제 예약 불가해 제외)
- 중동 테니스장 (1~2번)

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
- `GET /api/search?start=YYYY-MM-DD&end=YYYY-MM-DD&facility=시설명` — 예약 가능 시간대 목록 (JSON)
  - `facility`는 반복 지정 가능, 생략 시 전체 시설
  - 조회 기간은 최대 45일 (`app.py`의 `MAX_RANGE_DAYS`)
