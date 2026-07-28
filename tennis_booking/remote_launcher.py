# 폰에서 book_court.py 실행 자체를 원격으로 트리거할 수 있게 하는 상시 대기 서버.
# PC에서 이 스크립트를 실행해 터미널을 계속 열어두면, ngrok으로 열리는 고정 링크(카카오로도 전송됨)에
# 폰으로 접속해 언제든 "지금 예약 시도 시작"을 누를 수 있다. 실행이 시작되면 같은 페이지가 자동으로
# 보안문자 입력 화면으로 바뀐다 (book_court.py의 remote_captcha 흐름을 그대로 재사용).
#
# 사용법: python remote_launcher.py  (Ctrl+C로 종료)

import os
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pyngrok import ngrok

import book_court

SCRIPT_DIR = Path(__file__).resolve().parent

# 폰에서 손으로 옮겨 적어도 헷갈리지 않도록 0/O, 1/l/I처럼 헷갈리는 문자를 뺀 알파벳.
_TOKEN_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"


def _make_token(length: int = 10) -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length))

IDLE_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>테니스 예약 원격 실행</title></head>
<body style="font-family:sans-serif; text-align:center; padding:24px;">
<h3>테니스 예약 원격 실행</h3>
<p>{target_slots}</p>
<form method="POST" action="/run/{token}">
  <button type="submit" style="font-size:20px; padding:16px 32px;">지금 예약 시도 시작</button>
</form>
{last_result_block}
</body></html>"""

RUNNING_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="3">
<title>테니스 예약 실행 중</title></head>
<body style="font-family:sans-serif; text-align:center; padding:24px;">
<h3>예약 시도 실행 중...</h3>
<p>보안문자가 뜨면 이 페이지가 자동으로 바뀝니다. (3초마다 새로고침)</p>
</body></html>"""

CAPTCHA_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>보안문자 입력</title></head>
<body style="font-family:sans-serif; text-align:center; padding:24px;">
<h3>테니스 예약 - 보안문자 입력</h3>
<img src="/captcha_image/{token}?v={version}" style="max-width:90%; border:1px solid #ccc; border-radius:4px;"/>
<form method="POST" action="/submit/{token}">
  <div style="margin-top:20px;">
    <input name="code" autocomplete="off" autofocus
           style="font-size:22px; padding:10px; width:60%; text-align:center;"/>
  </div>
  <button type="submit" style="font-size:18px; padding:12px 28px; margin-top:16px;">입력 완료</button>
</form>
</body></html>"""


class LauncherServer:
    """book_court.run_once()가 기대하는 remote_server 인터페이스
    (update_captcha / result_queue / page_url / image_url)를 그대로 제공하면서,
    폰에서 '실행' 버튼으로 book_court 실행 자체를 트리거하는 기능을 더한 상시 서버."""

    def __init__(self, config: dict, port: int):
        self.config = config
        self.port = port
        self.token = _make_token()
        self.result_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._lock = threading.Lock()
        self.state = "idle"  # idle | running | waiting_captcha
        self._image_bytes = b""
        self._image_version = 0
        self.last_result_text = ""
        self.public_url: str | None = None

        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # noqa: A002 - silence default logging
                pass

            def _send(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                # 보안문자 이미지/상태 페이지가 폰 브라우저에 캐시되면 재시도 때마다 이전 문자를
                # 계속 보여줘서 "입력해도 계속 틀림" 현상이 생긴다. 항상 새로 받아오게 강제한다.
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                path_only = urlsplit(self.path).path
                if path_only == f"/{server.token}":
                    self._send(200, server._render_home().encode("utf-8"), "text/html; charset=utf-8")
                elif path_only == f"/captcha_image/{server.token}":
                    with server._lock:
                        data = server._image_bytes
                    self._send(200, data, "image/png")
                elif path_only in (f"/run/{server.token}", f"/submit/{server.token}"):
                    # 브라우저가 이전 POST 결과 주소를 새로고침한 경우 홈으로 되돌려보낸다.
                    self._redirect_home()
                else:
                    self._send(404, b"Not found", "text/plain")

            def _redirect_home(self) -> None:
                # 정적 텍스트로 끝내면 폰이 그 화면에 멈춰 상태 변화(보안문자 등장 등)를 못 본다.
                # 홈으로 돌려보내 항상 최신 상태(대기/실행중/보안문자)가 자동으로 보이게 한다.
                self.send_response(303)
                self.send_header("Location", f"/{server.token}")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):  # noqa: N802
                if self.path == f"/run/{server.token}":
                    server.start_run()
                    self._redirect_home()
                elif self.path == f"/submit/{server.token}":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8")
                    code = parse_qs(body).get("code", [""])[0]
                    server.submit_code(code)
                    self._redirect_home()
                else:
                    self._send(404, b"Not found", "text/plain")

        self._httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    # --- book_court.py가 기대하는 remote_server 인터페이스 (remote_captcha.RemoteCaptchaServer와 동일 형태) ---
    def update_captcha(self, image_path: Path) -> None:
        with self._lock:
            self._image_bytes = Path(image_path).read_bytes()
            self._image_version += 1
            self.state = "waiting_captcha"
        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                break

    def page_url(self, public_base: str) -> str:
        return f"{public_base.rstrip('/')}/{self.token}"

    def image_url(self, public_base: str) -> str:
        return f"{public_base.rstrip('/')}/captcha_image/{self.token}"

    # --- 원격 실행 트리거 ---
    def start_run(self) -> bool:
        with self._lock:
            if self.state != "idle":
                return False
            self.state = "running"
        threading.Thread(target=self._run_job, daemon=True).start()
        return True

    def submit_code(self, code: str) -> None:
        self.result_queue.put(("web", code))
        with self._lock:
            # 제출 직후에는 다음 문자/단계로 넘어가는 중이므로 '실행 중' 화면으로 되돌린다.
            # 재시도가 필요하면 update_captcha()가 다시 waiting_captcha로 바꿔준다.
            self.state = "running"

    def _run_job(self) -> None:
        try:
            self.last_result_text = book_court.run_once(self.config, self, self.public_url)
        except Exception as exc:  # noqa: BLE001
            self.last_result_text = f"실행 중 오류 발생: {exc}"
        finally:
            with self._lock:
                self.state = "idle"

    def _render_home(self) -> str:
        with self._lock:
            state = self.state
        if state == "waiting_captcha":
            return CAPTCHA_PAGE.format(token=self.token, version=self._image_version)
        if state == "running":
            return RUNNING_PAGE
        last_block = ""
        if self.last_result_text:
            head = "\n".join(self.last_result_text.splitlines()[:6])
            last_block = (
                '<pre style="text-align:left; white-space:pre-wrap; '
                f'background:#f5f5f5; padding:12px;">{head}</pre>'
            )
        slots_desc = ", ".join(f"{d.strftime('%Y-%m-%d')} {t}" for d, t in self.config["target_slots"])
        return IDLE_PAGE.format(
            token=self.token,
            target_slots=slots_desc,
            last_result_block=last_block,
        )

    def shutdown(self) -> None:
        self._httpd.shutdown()


def main() -> None:
    book_court.load_dotenv(SCRIPT_DIR / ".env")
    config = book_court.build_config()

    server = LauncherServer(config, port=int(book_court.env("REMOTE_CAPTCHA_PORT", "5001")))

    ngrok_authtoken = os.environ.get("NGROK_AUTHTOKEN")
    if not ngrok_authtoken:
        raise SystemExit("NGROK_AUTHTOKEN이 없으면 폰에서 접속할 링크를 만들 수 없습니다. .env에 설정해주세요.")
    ngrok.set_auth_token(ngrok_authtoken)
    tunnel = ngrok.connect(server.port, "http")
    server.public_url = tunnel.public_url
    link = server.page_url(server.public_url)

    print(f"[대기 서버] 폰에서 접속할 주소: {link}")
    print("[대기 서버] 이 창을 열어둔 채로 폰에서 위 주소에 접속해 '지금 예약 시도 시작'을 누르세요.")
    print("[대기 서버] 종료하려면 Ctrl+C")

    book_court.kakao_send_to_me(
        f"[테니스예약] 원격 실행 대기 중 - 아래 링크로 접속해 실행하세요:\n{link}",
        link_url=link,
    )

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        ngrok.disconnect(tunnel.public_url)
        ngrok.kill()


if __name__ == "__main__":
    main()
