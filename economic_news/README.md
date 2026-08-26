# 경제뉴스 카톡 요약 봇

매일 아침 국내 경제뉴스 RSS(최대 50건)를 모은 뒤, 그중 가장 중요한 뉴스 10건을 Claude API로
쉽게 풀어 요약해서 카카오톡 "나에게 보내기"로 보내는 자동화.

## 구조

- **GitHub Actions**(`.github/workflows/daily_news_kakao.yml`)가 매일 23:50 UTC(08:50 KST)에
  `daily_news_kakao.py`를 실행합니다. PC가 꺼져 있어도 동작합니다.
- `daily_news_kakao.py` — 국내 RSS 피드(연합뉴스/한국경제/한국경제(증권)/조선비즈/뉴시스/아시아경제)에서
  헤드라인+설명(description)을 모으고, Claude API(REST 직접 호출)에 넘겨 그중 주요 뉴스
  10건을 골라 쉬운 말로 요약한 뒤 `send_kakao.py`의 전송 로직으로 카카오톡으로 보냅니다.
  외부 패키지 설치 없이 표준 라이브러리만 사용합니다(feedparser, anthropic SDK 등 불필요 —
  Claude API도 urllib으로 직접 호출).
  - `python daily_news_kakao.py --dry-run` — 전송 없이 결과 텍스트만 로컬에서 확인
  - `python daily_news_kakao.py` — 실제 전송까지 로컬에서 테스트
- `send_kakao.py` — 임의의 텍스트를 카카오톡으로 전송하는 저수준 스크립트(`python send_kakao.py "텍스트"`).
- `kakao_get_token.py` — 최초 1회 카카오 REST API 키 + refresh_token을 발급받는 헬퍼
  (tennis_booking 프로젝트의 동일 스크립트와 같음).

**참고**: 원래는 클로드 클라우드 스케줄 루틴(claude.ai/code/routines)이 웹 검색으로 뉴스를 찾아
카카오로 보내도록 설계했으나, 그 클라우드 샌드박스의 아웃바운드 네트워크 정책이
`kauth.kakao.com`/`kapi.kakao.com`을 차단하고 있어(2026-08-25 확인) 카카오 전송이 항상 실패했습니다.
그래서 검색·요약·전송 전부를 GitHub Actions로 옮겼습니다(러너는 이 제약이 없음). 해당 클라우드
루틴은 비활성화해뒀습니다.

## 설정 방법

1. `python kakao_get_token.py` 실행 → 브라우저에서 카카오 로그인/동의 → 출력된
   `KAKAO_REST_API_KEY`, `KAKAO_REFRESH_TOKEN` 값을 `.env`에 저장 (`.env.example` 참고, 로컬 테스트용).
2. console.anthropic.com 에서 발급받은 API 키를 `.env`의 `ANTHROPIC_API_KEY`에 저장.
3. 로컬 테스트: `python daily_news_kakao.py --dry-run` 으로 결과 확인 후, `python daily_news_kakao.py`
   로 실제 전송까지 확인.
4. GitHub repo Settings → Secrets and variables → Actions 에서 아래 4개 secret을 등록:
   `KAKAO_REST_API_KEY`, `KAKAO_REFRESH_TOKEN`, `KAKAO_CLIENT_SECRET`, `ANTHROPIC_API_KEY`
   (https://github.com/unipro8787/john_dev/settings/secrets/actions)
5. Actions 탭에서 "경제뉴스 카톡 요약" 워크플로우를 `workflow_dispatch`로 한 번 수동 실행해서
   정상 동작하는지 확인.

## 참고

- `refresh_token`은 보통 60일간 유효합니다. 카카오가 만료 임박 시 새 refresh_token을 함께
  내려주면 스크립트가 stderr에 새 값을 출력합니다 — GitHub Actions 로그에서 확인해서
  `KAKAO_REFRESH_TOKEN` secret 값을 갱신해야 계속 동작합니다.
- 매일 60일 넘게 갱신을 놓치면 알림이 조용히 끊길 수 있으니, 가끔 카톡이 잘 오는지 확인해주세요.
- RSS 소스 URL이 나중에 바뀌거나 막히면(예: HTTP 403/404) 해당 피드만 조용히 건너뜁니다
  (`daily_news_kakao.py`의 `FEEDS` 목록을 수정하면 됩니다).
