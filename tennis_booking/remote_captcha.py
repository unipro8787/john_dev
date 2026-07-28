# 폰에서도 보안문자를 확인/입력할 수 있게 하는 초소형 로컬 웹서버.
# ngrok으로 이 서버를 임시 공개 URL에 연결하면, 카카오톡으로 받은 링크를 눌러
# 모바일 페이지에서 보안문자를 보고 입력 -> 제출하면 PC의 book_court.py가 그 값을 받아 계속 진행한다.
#
# 보안: URL에 무작위 토큰이 포함되어 있어(추측 불가능한 경로) 링크를 아는 사람만 접근 가능하다.
# 그래도 임시로 인터넷에 열리는 작은 서버이므로, 예약이 끝나면 스크립트를 종료해 터널도 함께 닫는 것이 좋다.

import queue
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

# 폰에서 손으로 옮겨 적어도 헷갈리지 않도록 0/O, 1/l/I처럼 헷갈리는 문자를 뺀 알파벳.
_TOKEN_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"


def _make_token(length: int = 10) -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length))


PAGE_TEMPLATE = """<!doctype html>
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


class RemoteCaptchaServer:
    def __init__(self, port: int = 5001):
        self.port = port
        self.token = _make_token()
        self.result_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._image_bytes = b""
        self._image_version = 0
        self._lock = threading.Lock()

        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # noqa: A002 - silence default logging
                pass

            def _send(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                # 보안문자 이미지가 폰 브라우저에 캐시되면 재시도 때 이전 문자를 계속 보여줄 수 있다.
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                path_only = urlsplit(self.path).path
                if path_only == f"/captcha/{server.token}":
                    with server._lock:
                        version = server._image_version
                    html = PAGE_TEMPLATE.format(token=server.token, version=version)
                    self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                elif path_only == f"/captcha_image/{server.token}":
                    with server._lock:
                        data = server._image_bytes
                    self._send(200, data, "image/png")
                else:
                    self._send(404, b"Not found", "text/plain")

            def do_POST(self):  # noqa: N802
                if self.path == f"/submit/{server.token}":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8")
                    code = parse_qs(body).get("code", [""])[0]
                    server.result_queue.put(("web", code))
                    msg = "입력 완료. 이 창은 닫아도 됩니다.".encode("utf-8")
                    self._send(200, msg, "text/plain; charset=utf-8")
                else:
                    self._send(404, b"Not found", "text/plain")

        self._httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def update_captcha(self, image_path: Path) -> None:
        with self._lock:
            self._image_bytes = Path(image_path).read_bytes()
            self._image_version += 1
        # 이전 시도에서 남은 제출값은 버린다 (새 문자에 대한 답이 아니므로).
        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                break

    def page_url(self, public_base: str) -> str:
        return f"{public_base.rstrip('/')}/captcha/{self.token}"

    def image_url(self, public_base: str) -> str:
        return f"{public_base.rstrip('/')}/captcha_image/{self.token}"

    def shutdown(self) -> None:
        self._httpd.shutdown()
