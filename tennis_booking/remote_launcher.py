# 폰에서 book_court.py 실행 자체를 원격으로 트리거할 수 있게 하는 상시 대기 서버.
# PC에서 이 스크립트를 실행해 터미널을 계속 열어두면, ngrok으로 열리는 고정 링크(카카오로도 전송됨)에
# 폰으로 접속해 언제든 "지금 예약 시도 시작"을 누를 수 있다. 실행이 시작되면 같은 페이지가 자동으로
# 보안문자 입력 화면으로 바뀐다 (book_court.py의 remote_captcha 흐름을 그대로 재사용).
#
# 사용법: python remote_launcher.py  (Ctrl+C로 종료)

import calendar
import hashlib
import os
import queue
import secrets
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pyngrok import ngrok

import book_court

SCRIPT_DIR = Path(__file__).resolve().parent
ICON_BYTES = (SCRIPT_DIR / "icon.png").read_bytes()
# 아이콘 내용이 바뀔 때마다 값이 달라져서, 아이폰/사파리가 이전 아이콘 이미지를 계속 캐싱해
# "고쳤는데도 안 바뀐다"는 문제가 생기지 않도록 URL 자체를 매번 새로 만든다.
ICON_VERSION = hashlib.md5(ICON_BYTES).hexdigest()[:8]

# 폰에서 손으로 옮겨 적어도 헷갈리지 않도록 0/O, 1/l/I처럼 헷갈리는 문자를 뺀 알파벳.
_TOKEN_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"


def _make_token(length: int = 10) -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length))


_TOKEN_FILE = SCRIPT_DIR / ".remote_token"


def _load_or_create_token() -> str:
    # 폰 홈 화면에 추가한 아이콘의 주소(도메인/토큰)가 재시작할 때마다 안 바뀌도록,
    # 한 번 만든 토큰을 파일에 저장해두고 다음 실행부터는 그대로 재사용한다.
    if _TOKEN_FILE.exists():
        saved = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    token = _make_token()
    _TOKEN_FILE.write_text(token, encoding="utf-8")
    return token


def _render_time_options(selected: str | None = None) -> str:
    return "".join(
        f'<option value="{opt}"{" selected" if opt == selected else ""}>{opt}</option>'
        for opt in book_court.TIME_SLOTS
    )


def _default_target_slots() -> list[tuple[datetime, str]]:
    # 대기 화면을 열 때마다 "오늘 기준 다음달의 매주 토요일 06:00~08:00"을 새로 계산해 기본값으로 채운다.
    today = datetime.now()
    year, month = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    return [
        (datetime(year, month, day), "06:00~08:00")
        for day in range(1, days_in_month + 1)
        if datetime(year, month, day).weekday() == 5  # 5 = 토요일
    ]


# 3, 4번은 book_court.SKIP_COURTS(사용수익허가 코트)라 애초에 선택지에도 넣지 않는다.
_SELECTABLE_COURTS = [c for c in sorted(book_court.COURTS) if c not in book_court.SKIP_COURTS]


def _render_court_checkboxes(selected: list[int]) -> str:
    return "".join(
        f'<label style="display:inline-block; margin:4px 8px; font-size:16px;">'
        f'<input type="checkbox" name="court" value="{c}"{" checked" if c in selected else ""}> {c}번</label>'
        for c in _SELECTABLE_COURTS
    )


def _parse_courts_from_body(body: str) -> list[int]:
    parsed = parse_qs(body)
    courts = []
    for value in parsed.get("court", []):
        try:
            court_num = int(value)
        except ValueError:
            continue
        if court_num in _SELECTABLE_COURTS:
            courts.append(court_num)
    return courts


def _render_slot_rows(slots: list[tuple[datetime, str]]) -> str:
    if not slots:
        slots = [(None, book_court.TIME_SLOTS[0])]
    rows = []
    for target_date, time_label in slots:
        date_val = target_date.strftime("%Y-%m-%d") if target_date else ""
        rows.append(
            '<div class="slot-row" style="margin:8px 0; display:flex; gap:8px; '
            'justify-content:center; align-items:center;">'
            f'<input type="date" name="date" required value="{date_val}" '
            'style="font-size:16px; padding:6px;">'
            f'<select name="time" required style="font-size:16px; padding:6px;">'
            f'{_render_time_options(time_label)}</select>'
            '<button type="button" onclick="removeSlot(this)" style="padding:6px 10px;">삭제</button>'
            "</div>"
        )
    return "\n".join(rows)


def _parse_slots_from_body(body: str) -> list[tuple[datetime, str]]:
    parsed = parse_qs(body)
    dates = parsed.get("date", [])
    times = parsed.get("time", [])
    slots: list[tuple[datetime, str]] = []
    for date_str, time_label in zip(dates, times):
        date_str = date_str.strip()
        if not date_str or time_label not in book_court.TIME_SLOTS:
            continue
        try:
            slots.append((datetime.strptime(date_str, "%Y-%m-%d"), time_label))
        except ValueError:
            continue
    return slots

HOME_SCREEN_HEAD = f"""
<link rel="apple-touch-icon" href="/icon.png?v={ICON_VERSION}">
<link rel="icon" href="/icon.png?v={ICON_VERSION}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="테니스 예약">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#178246">
"""

IDLE_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + HOME_SCREEN_HEAD + """
<title>테니스 예약 원격 실행</title></head>
<body style="font-family:sans-serif; text-align:center; padding:24px;">
<h3>테니스 예약 원격 실행</h3>
<form method="POST" action="/run/{token}">
  <div id="slots">
{slot_rows}
  </div>
  <button type="button" onclick="addSlot()" style="font-size:14px; padding:8px 16px; margin-top:8px;">+ 날짜/시간 추가</button>
  <div style="margin-top:20px;">
    <div style="font-size:14px; color:#555;">시도할 코트</div>
    <div>{court_checkboxes}</div>
  </div>
  <div style="margin-top:20px;">
    <button type="submit" style="font-size:20px; padding:16px 32px;">지금 예약 시도 시작</button>
  </div>
</form>
{last_result_block}
<template id="slot-template">
  <div class="slot-row" style="margin:8px 0; display:flex; gap:8px; justify-content:center; align-items:center;">
    <input type="date" name="date" required style="font-size:16px; padding:6px;">
    <select name="time" required style="font-size:16px; padding:6px;">{time_options}</select>
    <button type="button" onclick="removeSlot(this)" style="padding:6px 10px;">삭제</button>
  </div>
</template>
<script>
function addSlot() {{
  const tpl = document.getElementById('slot-template');
  document.getElementById('slots').appendChild(tpl.content.cloneNode(true));
}}
function removeSlot(btn) {{
  const rows = document.querySelectorAll('#slots .slot-row');
  if (rows.length > 1) {{
    btn.closest('.slot-row').remove();
  }}
}}
</script>
</body></html>"""

RUNNING_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="3">
""" + HOME_SCREEN_HEAD + """
<title>테니스 예약 실행 중</title></head>
<body style="font-family:sans-serif; text-align:center; padding:24px;">
<h3>예약 시도 실행 중...</h3>
<p>보안문자가 뜨면 이 페이지가 자동으로 바뀝니다. (3초마다 새로고침)</p>
</body></html>"""

CAPTCHA_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + HOME_SCREEN_HEAD + """
<title>보안문자 입력</title></head>
<body style="font-family:sans-serif; text-align:center; padding:24px;">
<h3>테니스 예약 - 보안문자 입력</h3>
<img src="/captcha_image/{token}?v={version}" style="max-width:90%; border:1px solid #ccc; border-radius:4px;"/>
<form method="POST" action="/submit/{token}">
  <div style="margin-top:20px;">
    <input name="code" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" autofocus
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
        self.token = _load_or_create_token()
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
                elif path_only == "/icon.png":
                    self._send(200, ICON_BYTES, "image/png")
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
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8") if length else ""
                    target_slots = _parse_slots_from_body(body)
                    court_order = _parse_courts_from_body(body)
                    server.start_run(target_slots or None, court_order or None)
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
    def start_run(self, target_slots: list[tuple[datetime, str]] | None = None,
                  court_order: list[int] | None = None) -> bool:
        with self._lock:
            if self.state != "idle":
                return False
            if target_slots:
                # 폰에서 고른 날짜/시간이 있으면 그걸로 이번 실행부터 사용하고,
                # 다음에 페이지를 다시 열었을 때도 기본값으로 그대로 보이게 남겨둔다.
                self.config["target_slots"] = target_slots
            if court_order:
                # 폰에서 고른 코트가 있으면 그걸로 이번 실행부터 사용하고, 다음에 페이지를
                # 다시 열었을 때도 체크박스 상태로 그대로 보이게 남겨둔다.
                self.config["court_order"] = court_order
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
        return IDLE_PAGE.format(
            token=self.token,
            slot_rows=_render_slot_rows(_default_target_slots()),
            time_options=_render_time_options(),
            court_checkboxes=_render_court_checkboxes(self.config.get("court_order", _SELECTABLE_COURTS)),
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
    # NGROK_DOMAIN(ngrok 대시보드에서 예약한 고정 도메인)을 설정해두면 재실행해도 링크가 바뀌지 않아,
    # 폰 홈 화면에 추가한 아이콘이 계속 같은 주소로 열린다.
    ngrok_domain = os.environ.get("NGROK_DOMAIN")
    tunnel = ngrok.connect(server.port, "http", domain=ngrok_domain) if ngrok_domain else ngrok.connect(server.port, "http")
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
