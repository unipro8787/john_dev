# Hwaseong Integrated Reservation System (yeyak.hscity.go.kr) — 왕배산체육공원 테니스장 예약 자동화.
#
# 흐름: 로그인(쿠키만 확보) -> 대상 날짜/시간대마다 코트(1~8번, 3/4번은 이용수익허가 코트라 자동 제외)를
#       각자 별도 브라우저 창에서 동시에 확인(거주지역 인증 -> 날짜/시간대 비어있는지 확인) ->
#       가장 먼저 빈 코트를 찾은 창만 보안문자 입력(PC 터미널 또는 폰 중 먼저 입력되는 쪽)부터 최종
#       신청까지 진행, 그 사이 다른 코트 창들은 대기하거나 이미 성공한 게 있으면 즉시 중단하고 닫힘 ->
#       다음 날짜/시간대는 기본적으로 순서대로 시작하되, 앞 순서가 대기열에 걸려 멈추면 기다리는 동안
#       바로 이어서 병렬로 시작(보안문자 입력만 전역 락으로 한 번에 한 코트씩 직렬화) ->
#       결과를 텍스트 파일로 저장.
#
# 사용법: python book_court.py
# 환경변수(.env 참고): HSCITY_ID, HSCITY_PW, HSCITY_RESIDENT1, HSCITY_RESIDENT2,
#                      HSCITY_REFUND_BANK(기본 081=하나은행), HSCITY_REFUND_ACCOUNT, HSCITY_DEPOSITOR,
#                      TARGET_DATE(기본 2026-07-31), TARGET_TIME_LABEL(기본 "06:00~08:00"),
#                      KAKAO_ACCESS_TOKEN(선택 - 없으면 카카오 알림 생략),
#                      NGROK_AUTHTOKEN(폰 원격 입력용 - 없어도 PC 터미널 입력은 그대로 동작)

import json
import os
import queue
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from pyngrok import ngrok

from remote_captcha import RemoteCaptchaServer

BASE = "https://yeyak.hscity.go.kr"
SCRIPT_DIR = Path(__file__).resolve().parent

# 왕배산체육공원 테니스장 코트 번호 -> stadiumIdx (2026-07-27 기준 실제 사이트에서 확인)
COURTS = {1: 230, 2: 231, 3: 232, 4: 233, 5: 235, 6: 236, 7: 237, 8: 238}
# 3, 4번 코트는 2026년 2월부터 "사용수익허가 코트"로 이 시스템에서 이용 불가 (사이트 공지 확인됨)
SKIP_COURTS = {3, 4}

TIME_SLOTS = [
    "06:00~08:00", "08:00~10:00", "10:00~12:00", "12:00~14:00",
    "14:00~16:00", "16:00~18:00", "18:00~20:00", "20:00~22:00",
]

# 보안문자 입력을 사람이 몇 분째 응답 안 하면(폰 알림을 놓쳤거나 잠들었거나) 이 코트를
# 영원히 붙들고 있지 말고 건너뛴다. 안 그러면 captcha_lock을 붙든 채 멈춰서
# 남은 모든 날짜/코트가 다같이 막히고, run_once가 끝까지 못 가 결과 파일/카톡 요약도
# 전혀 오지 않는다(마치 "다 조용히 실패"한 것처럼 보이는 원인이 될 수 있음).
CAPTCHA_WAIT_TIMEOUT_S = int(os.environ.get("CAPTCHA_TIMEOUT_SECONDS", "180"))

LOG_PATH = SCRIPT_DIR / "book_court.log"


def _log(msg: str) -> None:
    """print()와 함께 파일에도 남긴다 - 터미널 스크롤이 사라져도 나중에 왜 실패했는지 확인 가능하게."""
    print(msg)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:
        pass


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"환경변수 {name} 이(가) 설정되지 않았습니다. .env.example을 참고해 .env를 만들어주세요.")
    return value


def kakao_send_to_me(text: str, image_url: str | None = None, link_url: str | None = None) -> None:
    token = os.environ.get("KAKAO_ACCESS_TOKEN")
    if not token:
        print("[카카오] KAKAO_ACCESS_TOKEN이 없어 알림을 건너뜁니다. (kakao_get_token.py로 발급 가능)")
        return
    if image_url:
        url = link_url or BASE
        template = {
            "object_type": "feed",
            "content": {
                "title": text,
                "image_url": image_url,
                "link": {"web_url": url, "mobile_web_url": url},
            },
        }
    else:
        template = {
            "object_type": "text",
            "text": text,
            "link": {"web_url": BASE, "mobile_web_url": BASE},
        }
    body = urllib.parse.urlencode(
        {"template_object": json.dumps(template, ensure_ascii=False)}
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        data=body,
        headers={"Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        print("[카카오] 나에게 보내기 알림 전송 완료")
    except Exception as exc:  # noqa: BLE001 - best-effort notification only
        print(f"[카카오] 알림 전송 실패 (무시하고 계속 진행): {exc}")


def _terminal_reader(prompt: str, q: "queue.Queue[tuple[str, str]]") -> None:
    """PC 터미널에서 직접 입력하는 경로. 폰 웹페이지 제출과 같은 큐를 공유해 먼저 오는 쪽이 이긴다."""
    try:
        value = input(prompt)
        q.put(("terminal", value))
    except (EOFError, RuntimeError):
        pass


def dismiss_info_modal(page: Page, timeout: int = 3000) -> bool:
    """폭염특보/예약방식 안내 등 '체크박스 + 확인완료' 팝업이 뜨면 닫는다."""
    try:
        btn = page.get_by_role("button", name="확인완료")
        btn.wait_for(state="visible", timeout=timeout)
    except Exception:
        return False
    container = btn.locator("xpath=ancestor::*[.//input[@type='checkbox']][1]")
    try:
        container.locator("input[type=checkbox]").first.check(force=True)
    except Exception:
        pass
    btn.click()
    page.wait_for_timeout(300)
    return True


def goto_target_month(page: Page, target_year: int, target_month: int) -> None:
    for _ in range(24):  # safety cap
        header = page.locator("text=/\\d{4}\\.\\s*\\d{2}/").first.inner_text()
        m = re.search(r"(\d{4})\D+(\d{2})", header)
        if not m:
            break
        year, month = int(m.group(1)), int(m.group(2))
        if year == target_year and month == target_month:
            return
        # 실제 마크업: <a class="arrow prev" onclick="fnSearchMonth('YYYY-MM')"><span class="blind">이전 달 바로가기</span></a>
        # 화살표는 화면에 보이는 텍스트(">"/"<")가 아니라 스크린리더용 숨김 텍스트뿐이라 class로 찾아야 한다.
        if (year, month) < (target_year, target_month):
            page.locator("a.arrow.next").first.click()
        else:
            page.locator("a.arrow.prev").first.click()
        page.wait_for_timeout(400)


def click_calendar_day(page: Page, target_date: datetime) -> str:
    """달력에서 target_date를 클릭한다. 반환값: 'clicked' | 'disabled' | 'not_found'.
    실제 사이트 원본 HTML로 확인한 구조: 예약 가능한 미래 날짜만
    <a id="day_YYYY-MM-DD" onclick="fnSelectDay(...)"><strong>N</strong></a> 로 렌더링되고,
    지난 날짜/마감된 날짜는 앵커 없이 <strong>N</strong>만 정적으로 표시된다."""
    day_id = f"day_{target_date.year:04d}-{target_date.month:02d}-{target_date.day:02d}"
    locator = page.locator(f'a[id="{day_id}"]')
    try:
        locator.wait_for(state="visible", timeout=10000)
    except Exception:
        pass
    if locator.count() == 0:
        return "disabled"  # 지난 날짜이거나 이 날짜는 예약 자체가 마감/미개방
    locator.first.click()
    return "clicked"


def find_time_slot_state(page: Page, label: str) -> tuple[str, int] | None:
    """이용시간 체크박스 중 label에 해당하는 것의 (id, index)를 찾고 사용 가능 여부 확인."""
    idx = TIME_SLOTS.index(label)
    checkbox_id = f"applyTimeList[{idx}].stadiumTimeSn"
    locator = page.locator(f'input[id="{checkbox_id}"]')
    if locator.count() == 0:
        return None
    disabled = locator.is_disabled()
    return ("disabled" if disabled else "available"), idx


def book_court(page: Page, court_num: int, stadium_idx: int, target_date: datetime,
                time_label: str, config: dict, remote_server: RemoteCaptchaServer,
                public_url: str, dialog_messages: list[str],
                success_event: threading.Event, captcha_lock: threading.Lock,
                queue_event: threading.Event) -> dict | None:
    if success_event.is_set():
        return None
    print(f"\n=== {court_num}번 코트 (stadiumIdx={stadium_idx}) 확인 중 ===")
    page.goto(f"{BASE}/1053/3026/stadiumDetail.do?stadiumIdx={stadium_idx}")
    dismiss_info_modal(page)

    apply_link = page.get_by_text("신청하기", exact=True).first
    apply_link.click()
    # 신청자가 몰리면 대기열 화면에서 한동안 머무를 수 있다(최대 10분 가정).
    # 짧은 타임아웃으로 나눠서 반복 대기하다가, 곧바로 넘어가지 못하면(=대기열에 걸림) queue_event를
    # 세워서 이 날짜/시간대를 기다리는 동안 run_once가 다음 날짜/시간대를 바로 이어서 병렬로 시작하게 한다.
    QUEUE_POLL_MS = 5000
    QUEUE_TOTAL_MS = 600_000
    waited_ms = 0
    arrived = False
    while waited_ms < QUEUE_TOTAL_MS:
        if success_event.is_set():
            return None
        try:
            page.wait_for_url(
                lambda url: "stadiumAreaConfirm" in url or "stadiumApply" in url,
                timeout=QUEUE_POLL_MS,
            )
            arrived = True
            break
        except PlaywrightTimeoutError:
            waited_ms += QUEUE_POLL_MS
            queue_event.set()
    if not arrived:
        print(f"  -> {court_num}번 코트: 대기열에서 10분 넘게 넘어가지 않아 건너뜁니다.")
        return None
    if success_event.is_set():
        return None
    page.wait_for_load_state("networkidle")

    if "stadiumAreaConfirm" in page.url:
        page.fill('input[name="resident1"]', config["resident1"])
        page.fill('input[name="resident2"]', config["resident2"])
        page.locator("#privacyAgree").check(force=True)
        page.get_by_role("button", name="인증확인").click()
        page.wait_for_load_state("networkidle")

    if "stadiumApply" not in page.url:
        print(f"  -> 예상치 못한 페이지({page.url}), 이 코트는 건너뜁니다.")
        return None

    dismiss_info_modal(page)  # 테니스장 예약방식 안내

    goto_target_month(page, target_date.year, target_date.month)
    result = click_calendar_day(page, target_date)
    if result != "clicked":
        debug_path = SCRIPT_DIR / f"debug_calendar_{court_num}.png"
        try:
            page.screenshot(path=str(debug_path), full_page=True)
        except Exception:
            pass
        print(
            f"  -> {target_date.date()} 선택 불가({result}, url={page.url}). "
            f"다음 코트로 넘어갑니다. (화면 캡처: {debug_path.name})"
        )
        return None
    page.wait_for_timeout(500)

    slot_state = find_time_slot_state(page, time_label)
    if slot_state is None or slot_state[0] != "available":
        print(f"  -> {time_label} 시간대 예약 불가. 다음 코트로 넘어갑니다.")
        return None

    checkbox_id = f"applyTimeList[{slot_state[1]}].stadiumTimeSn"
    page.locator(f'input[id="{checkbox_id}"]').check(force=True)

    if success_event.is_set():
        return None

    # 보안문자 입력 UI(터미널/폰)와 최종 신청 버튼은 코트마다 하나뿐인 공유 자원이라,
    # 여러 코트 창이 동시에 여기 도달해도 한 번에 한 코트씩만 진행하도록 잠근다.
    # (동시에 두 코트가 신청까지 끝내버리는 이중 예약도 이 락으로 함께 방지된다.)
    acquired = False
    while not success_event.is_set():
        acquired = captcha_lock.acquire(timeout=0.5)
        if acquired:
            break
    if success_event.is_set():
        if acquired:
            captcha_lock.release()
        return None

    try:
        # --- 보안문자: PC 터미널 또는 폰(카카오 링크) 중 먼저 입력되는 쪽을 사용 ---
        for attempt in range(5):
            if success_event.is_set():
                return None
            captcha_path = SCRIPT_DIR / f"captcha_{court_num}_{attempt}.png"
            page.locator("#capchaImage").screenshot(path=str(captcha_path))
            remote_server.update_captcha(captcha_path)
            try:
                os.startfile(captcha_path)  # Windows에서 기본 이미지 뷰어로 열기
            except Exception:
                pass
            if public_url:
                page_url = remote_server.page_url(public_url)
                image_url = remote_server.image_url(public_url)
                kakao_send_to_me(
                    f"[테니스예약] {court_num}번 코트 보안문자 확인 필요 - 눌러서 입력하세요",
                    image_url=image_url,
                    link_url=page_url,
                )
                print(f"[{court_num}번 코트] 보안문자: 아래 터미널에 직접 입력하거나, 폰에서 {page_url} 접속해 입력하세요.")
            else:
                kakao_send_to_me(f"[테니스예약] {court_num}번 코트 보안문자 확인 필요 - PC 화면을 확인해주세요")
                print(f"[{court_num}번 코트] 보안문자: PC 화면(또는 자동으로 열린 스크린샷)에서 확인 후 아래 터미널에 입력하세요.")
            threading.Thread(
                target=_terminal_reader,
                args=(f"[{court_num}번 코트] 보안문자 (새 문자 받으려면 r): ", remote_server.result_queue),
                daemon=True,
            ).start()

            # 사람이 시간 내에 응답하지 않으면(폰 알림을 놓쳤거나 잠들었거나) 이 코트를
            # 무한정 붙들지 않고 건너뛴다 - 그래야 captcha_lock이 풀려 다른 날짜/코트가
            # 이어서 진행되고, run_once가 끝까지 가서 결과 파일/카톡 요약이 나간다.
            deadline = time.monotonic() + CAPTCHA_WAIT_TIMEOUT_S
            got = None
            while time.monotonic() < deadline:
                if success_event.is_set():
                    return None
                try:
                    got = remote_server.result_queue.get(timeout=0.5)
                    break
                except queue.Empty:
                    continue
            if got is None:
                _log(
                    f"  -> {court_num}번 코트: 보안문자 입력 대기 {CAPTCHA_WAIT_TIMEOUT_S}초 초과 "
                    f"(응답 없음, attempt {attempt + 1}). 이 코트를 건너뜁니다."
                )
                return None
            source, code = got
            code = code.strip()
            if code.lower() == "r":
                page.get_by_role("button", name="새로고침").click()
                page.wait_for_timeout(500)
                continue
            page.fill('input[name="capchaText"]', code)
            dialogs_before = len(dialog_messages)
            page.click("#costSumText")
            page.wait_for_timeout(1200)
            new_dialogs = dialog_messages[dialogs_before:]
            if new_dialogs:
                # 사이트가 직접 알림창으로 알려주는 실패 사유 (예: "보안문자가 일치하지 않습니다" 또는
                # "이미 마감/선점된 시간대입니다" 등 - 후자라면 보안문자를 다시 입력해도 소용없지만,
                # 정확한 문구를 실제로 로그로 본 적이 없어 아직은 구분하지 않고 모두 재시도한다.
                # 다음에 이 상황이 재현되면 book_court.log에서 실제 문구를 확인할 수 있다.
                _log(f"  -> {court_num}번 코트, attempt {attempt + 1}: 사이트 응답: {new_dialogs[-1]} 다시 시도합니다.")
                continue
            # "이용료 *" 라벨(버튼 옆)과 구분하기 위해 콜론이 붙은 결과 텍스트("이용료 : 13,000원")만 매칭한다.
            fee_locator = page.get_by_text(re.compile(r"이용료\s*[:：]"))
            fee_text = fee_locator.first.inner_text() if fee_locator.count() > 0 else ""
            fee_match = re.search(r"[1-9][\d,]*", fee_text)
            if fee_match:
                _log(f"  -> {court_num}번 코트: 이용료 확인 완료 ({source}에서 입력): {fee_match.group(0)}원")
                break
            debug_fee_path = SCRIPT_DIR / f"debug_fee_{court_num}_{attempt}.png"
            try:
                page.screenshot(path=str(debug_fee_path), full_page=True)
            except Exception:
                pass
            _log(
                f"  -> {court_num}번 코트, attempt {attempt + 1}: 이용료 확인 실패로 보입니다 "
                f"(알림창은 없었음, 표시된 텍스트: {fee_text.strip()!r}, 화면 캡처: {debug_fee_path.name}). 다시 시도합니다."
            )
        else:
            _log(f"  -> {court_num}번 코트: 보안문자 확인을 5회 실패했습니다. 이 코트를 건너뜁니다.")
            return None

        # --- 신청자 정보 ---
        page.locator('input[name="usePurposeCd"][value="GN"]').check(force=True)  # 사용 용도: 일반
        page.fill('input[name="usePurpose"]', config["event_content"])  # 행사내용
        page.fill('input[name="personNum"]', str(config["person_num"]))  # 사용인원
        page.fill('input[name="refundAccount"]', config["refund_account"])
        page.locator('select[name="refundBankCd"]').select_option(config["refund_bank_cd"])
        page.fill('input[name="depositor"]', config["depositor"])
        page.get_by_role("button", name="계좌확인").click()
        page.wait_for_timeout(1500)

        page.locator("#privacyAgree").check(force=True)
        page.get_by_role("button", name="신청하기").click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        return {
            "court": court_num,
            "stadium_idx": stadium_idx,
            "date": target_date.strftime("%Y-%m-%d"),
            "time": time_label,
            "fee": fee_text.strip(),
            "result_url": page.url,
            "result_page_text": page.locator("body").inner_text()[:2000],
        }
    finally:
        captcha_lock.release()


def parse_target_slots(raw: str) -> list[tuple[datetime, str]]:
    """'2026-07-30 06:00~08:00; 2026-07-31 06:00~08:00' 형태를 (날짜, 시간대) 목록으로 변환."""
    slots = []
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        date_str, time_label = entry.split(None, 1)
        slots.append((datetime.strptime(date_str, "%Y-%m-%d"), time_label.strip()))
    return slots


def build_config() -> dict:
    default_slot = f"{env('TARGET_DATE', '2026-07-31')} {env('TARGET_TIME_LABEL', '06:00~08:00')}"
    return {
        "resident1": env("HSCITY_RESIDENT1", required=True),
        "resident2": env("HSCITY_RESIDENT2", required=True),
        "refund_account": env("HSCITY_REFUND_ACCOUNT", required=True),
        "refund_bank_cd": env("HSCITY_REFUND_BANK", "081"),  # 081 = 하나은행
        "depositor": env("HSCITY_DEPOSITOR", "안유현"),
        "event_content": env("HSCITY_EVENT_CONTENT", "테니스 경기"),
        "person_num": env("HSCITY_PERSON_NUM", "4"),
        "user_id": env("HSCITY_ID", required=True),
        "user_pw": env("HSCITY_PW", required=True),
        # 여러 날짜/시간을 세미콜론으로 구분해 적어두면 각각을 순서대로 시도하고,
        # 가능한 만큼(여러 건이라도) 전부 예약한다. 예: "2026-07-30 06:00~08:00; 2026-07-31 18:00~20:00"
        "target_slots": parse_target_slots(env("TARGET_SLOTS", default_slot)),
        "court_order": [int(c) for c in env("TARGET_COURTS", "1,2,5,6,7,8").split(",")],
    }


def _login_and_collect_cookies(config: dict) -> list[dict]:
    """한 번만 로그인해서 세션 쿠키를 얻어온다. 코트별 병렬 창들은 이 쿠키를 그대로 주입해
    (같은 서버 세션을 공유하는) 별도의 브라우저 프로세스로 뜨기 때문에, 동시에 여러 번
    로그인하면서 서로의 세션을 끊어버리는 문제가 없다."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(f"{BASE}/memberLogin.do")
        page.fill("#userId", config["user_id"])
        page.fill("#pwd", config["user_pw"])
        page.get_by_role("button", name="로그인", exact=True).click()
        page.wait_for_load_state("networkidle")
        cookies = page.context.cookies()
        browser.close()
    return cookies


def book_slot_parallel(cookies: list[dict], target_date: datetime, time_label: str, config: dict,
                        remote_server: RemoteCaptchaServer, public_url: str | None,
                        captcha_lock: threading.Lock, queue_event: threading.Event) -> dict | None:
    """이 날짜/시간대에 대해 court_order의 코트들을 각자 자기 브라우저 창에서 동시에 확인한다.
    (플레이라이트 동기 API는 스레드 세이프하지 않아 창마다 완전히 독립된 Playwright 인스턴스를 띄운다.)
    먼저 예약까지 끝낸 코트가 나오면 success_event로 나머지 창들에게 즉시 알려 중단/종료시킨다.
    captcha_lock은 run_once에서 모든 날짜/시간대가 함께 쓰는 전역 락이다 (PC 터미널/폰이 하나뿐이라
    여러 날짜/시간대가 동시에 진행되더라도 보안문자 입력만큼은 한 번에 한 코트씩 순서대로 진행해야 한다).
    queue_event는 이 날짜/시간대 전용으로, 코트 중 하나라도 대기열에 걸리면 세워져 run_once가 다음
    날짜/시간대를 이어서 병렬로 시작할 수 있게 신호를 준다."""
    success_event = threading.Event()
    result_box: list[dict] = []
    result_lock = threading.Lock()

    def worker(court_num: int, stadium_idx: int) -> None:
        if success_event.is_set():
            return
        result = None
        dialog_messages: list[str] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                context.add_cookies(cookies)
                page = context.new_page()
                page.on(
                    "dialog",
                    lambda d: (dialog_messages.append(d.message), _log(f"[{court_num}번 코트] 사이트 알림: {d.message}"), d.accept()),
                )
                result = book_court(
                    page, court_num, stadium_idx, target_date, time_label, config,
                    remote_server, public_url, dialog_messages, success_event, captcha_lock,
                    queue_event,
                )
                browser.close()
        except Exception as exc:  # noqa: BLE001
            _log(f"  -> {court_num}번 코트 처리 중 오류: {exc}")
            result = None
        if result:
            with result_lock:
                if not result_box:
                    result_box.append(result)
                    success_event.set()

    threads = []
    for court_num in config["court_order"]:
        if court_num in SKIP_COURTS:
            print(f"{court_num}번 코트는 이용수익허가 코트라 건너뜁니다.")
            continue
        stadium_idx = COURTS.get(court_num)
        if not stadium_idx:
            continue
        t = threading.Thread(target=worker, args=(court_num, stadium_idx), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return result_box[0] if result_box else None


def run_once(config: dict, remote_server: RemoteCaptchaServer, public_url: str | None) -> str:
    """이미 떠 있는 remote_server(및 ngrok 터널, 선택)를 재사용해 로그인 -> (날짜/시간별) 코트 병렬 확인 -> 결과 저장까지 실행한다.
    target_slots에 여러 날짜/시간이 있으면 기본적으로 순서대로 하나씩 시도하되, 앞 순서 날짜/시간대가
    대기열에 걸려 멈추면(book_court의 queue_event) 그걸 기다리는 동안 바로 다음 날짜/시간대를 이어서
    병렬로 시작한다. 보안문자 입력(PC 터미널/폰)은 물리적으로 하나뿐이라 captcha_lock으로 전역 직렬화한다.
    반환값은 결과 파일에 쓴 텍스트 전체(호출자가 화면에 그대로 보여줄 수 있게)."""
    cookies = _login_and_collect_cookies(config)

    successes: list[dict] = []
    failures: list[tuple[datetime, str]] = []
    results_lock = threading.Lock()
    captcha_lock = threading.Lock()

    def slot_task(target_date: datetime, time_label: str, queue_event: threading.Event) -> None:
        print(f"\n##### 대상: {target_date.strftime('%Y-%m-%d')} {time_label} (코트 {len(config['court_order'])}개 병렬 확인) #####")
        booking_result = book_slot_parallel(
            cookies, target_date, time_label, config, remote_server, public_url,
            captcha_lock, queue_event,
        )
        with results_lock:
            if booking_result:
                successes.append(booking_result)
            else:
                failures.append((target_date, time_label))

    slot_threads: list[threading.Thread] = []
    for target_date, time_label in config["target_slots"]:
        queue_event = threading.Event()
        t = threading.Thread(target=slot_task, args=(target_date, time_label, queue_event), daemon=True)
        slot_threads.append(t)
        t.start()
        # 이 날짜/시간대가 끝나거나(대개 대기열 없이 빠르게 끝남) 대기열에 걸려 멈추는 즉시
        # 다음 날짜/시간대를 이어서 시작한다. 둘 다 아니면 최대 0.3초 간격으로 계속 확인한다.
        while t.is_alive() and not queue_event.is_set():
            queue_event.wait(timeout=0.3)

    for t in slot_threads:
        t.join()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = SCRIPT_DIR / f"reservation_result_{timestamp}.txt"
    slots_desc = ", ".join(f"{d.strftime('%Y-%m-%d')} {t}" for d, t in config["target_slots"])
    lines = [
        "화성특례시 통합예약시스템 - 왕배산체육공원 테니스장 예약 결과",
        f"실행 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"대상 날짜/시간 목록: {slots_desc}",
        "",
    ]
    if successes:
        lines.append(f"예약 성공 {len(successes)}건:")
        for r in successes:
            lines.append(f"- {r['date']} {r['time']} / 코트: {r['court']}번 / 이용료: {r['fee']} / 결과 페이지: {r['result_url']}")
        lines.append("")
    if failures:
        lines.append(f"예약 실패 {len(failures)}건 (코트 모두 실패 또는 마감):")
        for d, t in failures:
            lines.append(f"- {d.strftime('%Y-%m-%d')} {t}")
        lines.append("")
    if successes:
        lines += ["--- 마지막 성공 결과 페이지 내용 ---", successes[-1]["result_page_text"]]

    if successes:
        summary = ", ".join(f"{r['date']} {r['time']} {r['court']}번" for r in successes)
        kakao_send_to_me(f"[테니스예약] 예약 완료 {len(successes)}건: {summary}")
    if failures:
        failed_desc = ", ".join(f"{d.strftime('%Y-%m-%d')} {t}" for d, t in failures)
        kakao_send_to_me(f"[테니스예약] 예약 실패 {len(failures)}건: {failed_desc}")

    result_text = "\n".join(lines)
    result_path.write_text(result_text, encoding="utf-8")
    print(f"\n결과 파일 저장: {result_path}")

    return result_text


def main() -> None:
    load_dotenv(SCRIPT_DIR / ".env")
    config = build_config()

    remote_server = RemoteCaptchaServer(port=int(env("REMOTE_CAPTCHA_PORT", "5001")))
    ngrok_authtoken = os.environ.get("NGROK_AUTHTOKEN")
    tunnel = None
    public_url = None
    if ngrok_authtoken:
        try:
            ngrok.set_auth_token(ngrok_authtoken)
            tunnel = ngrok.connect(remote_server.port, "http")
            public_url = tunnel.public_url
            print(f"[원격 입력] 폰에서 보안문자 입력용 주소: {public_url}/captcha/{remote_server.token}")
            print("          (카카오 알림에도 같은 링크가 포함됩니다)")
        except Exception as exc:  # noqa: BLE001
            print(f"[ngrok] 터널 생성 실패, PC 터미널 입력만 사용합니다: {exc}")
    else:
        print("[안내] NGROK_AUTHTOKEN이 없어 폰 원격 입력은 비활성화됩니다. (PC 터미널 입력은 그대로 동작합니다)")

    run_once(config, remote_server, public_url)

    remote_server.shutdown()
    if tunnel:
        ngrok.disconnect(tunnel.public_url)
        ngrok.kill()


if __name__ == "__main__":
    main()
