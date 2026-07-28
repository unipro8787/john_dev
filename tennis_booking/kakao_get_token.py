# 카카오톡 "나에게 보내기" 알림에 필요한 Access Token을 처음 한 번 발급받기 위한 헬퍼.
#
# 사전 준비 (https://developers.kakao.com):
#   1. 로그인 후 "내 애플리케이션" > "애플리케이션 추가하기"
#   2. 앱 선택 > "앱 키"에서 REST API 키 확인
#   3. "카카오 로그인" 메뉴에서 활성화 ON
#   4. "Redirect URI"에 http://localhost:5000/oauth 등록 (아래 REDIRECT_URI와 반드시 동일해야 함)
#   5. "카카오 로그인 > 동의항목"에서 "카카오톡 메시지 전달" (talk_message) 를 "선택 동의"로 설정
#      (개인 개발자가 자기 자신에게 보내는 "나에게 보내기"는 별도 비즈니스 심사 없이 사용 가능합니다.)
#
# 사용법:
#   set KAKAO_REST_API_KEY=발급받은_REST_API_키   (PowerShell: $env:KAKAO_REST_API_KEY="...")
#   python kakao_get_token.py
#
# 브라우저가 열리면 카카오 로그인 후 동의하면, 이 스크립트가 access_token / refresh_token을 출력합니다.
# 출력된 access_token 값을 .env의 KAKAO_ACCESS_TOKEN에 붙여넣으세요.
# (access_token은 보통 몇 시간~수십일 후 만료됩니다. 만료되면 refresh_token으로 재발급하거나
#  이 스크립트를 다시 실행하세요.)

import json
import os
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

REDIRECT_URI = "http://localhost:5000/oauth"
PORT = 5000

received_code: str | None = None


class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        global received_code
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if code:
            received_code = code
            self.wfile.write("인증 완료. 이 창을 닫고 터미널로 돌아가세요.".encode("utf-8"))
        else:
            self.wfile.write("인증 코드가 없습니다. 다시 시도해주세요.".encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - silence default logging
        pass


def main() -> None:
    rest_api_key = os.environ.get("KAKAO_REST_API_KEY")
    if not rest_api_key:
        rest_api_key = input("카카오 REST API 키를 입력하세요: ").strip()
    if not rest_api_key:
        raise SystemExit("REST API 키가 필요합니다.")

    auth_url = (
        "https://kauth.kakao.com/oauth/authorize?"
        + urllib.parse.urlencode(
            {
                "client_id": rest_api_key,
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": "talk_message",
            }
        )
    )
    print(f"브라우저를 엽니다. 열리지 않으면 아래 주소를 직접 방문하세요:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", PORT), OAuthHandler)
    print(f"http://localhost:{PORT} 에서 인증 코드를 기다리는 중...")
    while received_code is None:
        server.handle_request()

    token_req = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": rest_api_key,
                "redirect_uri": REDIRECT_URI,
                "code": received_code,
            }
        ).encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(token_req, timeout=10) as resp:
        token_data = json.loads(resp.read().decode("utf-8"))

    print("\n발급 완료. 아래 값을 tennis_booking/.env 에 저장하세요:\n")
    print(f"KAKAO_ACCESS_TOKEN={token_data['access_token']}")
    if "refresh_token" in token_data:
        print(f"KAKAO_REFRESH_TOKEN={token_data['refresh_token']}")


if __name__ == "__main__":
    main()
