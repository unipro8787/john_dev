# 카카오톡 "나에게 보내기" 알림에 필요한 토큰을 처음 한 번 발급받기 위한 헬퍼.
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
# 출력된 KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN 값을 economic_news/.env 에 저장하세요.
# (send_kakao.py는 매번 refresh_token으로 access_token을 새로 발급받아 사용하므로 access_token 자체는
#  저장할 필요가 없습니다. refresh_token은 보통 60일간 유효하며, 만료 임박 시에만 값이 바뀝니다.)

import json
import os
import urllib.error
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

    token_params = {
        "grant_type": "authorization_code",
        "client_id": rest_api_key,
        "redirect_uri": REDIRECT_URI,
        "code": received_code,
    }
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET")
    if client_secret:
        token_params["client_secret"] = client_secret

    token_req = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=urllib.parse.urlencode(token_params).encode("utf-8"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(token_req, timeout=10) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"\n토큰 발급 실패 (HTTP {exc.code}):\n{detail}\n")
        if not client_secret:
            print(
                "-> 401이면서 에러 코드가 KOE010/invalid_client 라면, 카카오 디벨로퍼스 콘솔의\n"
                "   '카카오 로그인 > 보안'에서 Client Secret이 '사용함'으로 켜져 있을 가능성이 높습니다.\n"
                "   콘솔에서 Client Secret 코드를 발급/확인한 뒤:\n"
                "     set KAKAO_CLIENT_SECRET=발급받은_값\n"
                "   으로 설정하고 다시 실행하거나, 콘솔에서 Client Secret 사용을 꺼두세요."
            )
        raise SystemExit(1) from exc

    print("\n발급 완료. 아래 값을 economic_news/.env 에 저장하세요:\n")
    print(f"KAKAO_REST_API_KEY={rest_api_key}")
    if "refresh_token" in token_data:
        print(f"KAKAO_REFRESH_TOKEN={token_data['refresh_token']}")
    else:
        print("(refresh_token이 응답에 없습니다 - scope에 talk_message가 포함됐는지 확인하세요)")


if __name__ == "__main__":
    main()
