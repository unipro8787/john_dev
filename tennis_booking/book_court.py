# Hwaseong Integrated Reservation System (yeyak.hscity.go.kr) — 왕배산체육공원 테니스장 예약 자동화.
#
# 흐름: 로그인 -> 코트(1~8번, 3/4번은 이용수익허가 코트라 자동 제외) 순서대로 -> 거주지역 인증(주민번호) ->
#       대상 날짜/06:00~08:00 시간대가 비어있는 코트를 찾아 선택 -> 보안문자는 PC 터미널 또는 폰(ngrok+카카오 링크)
#       중 먼저 입력되는 쪽으로 사람이 직접 처리 -> 이용목적/행사내용/사용인원/환불계좌 입력 -> 계좌확인 ->
#       최종 신청 -> 결과를 텍스트 파일로 저장.
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
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
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
                public_url: str, dialog_messages: list[str]) -> dict | None:
    print(f"\n=== {court_num}번 코트 (stadiumIdx={stadium_idx}) 확인 중 ===")
    page.goto(f"{BASE}/1053/3026/stadiumDetail.do?stadiumIdx={stadium_idx}")
    dismiss_info_modal(page)

    apply_link = page.get_by_text("신청하기", exact=True).first
    apply_link.click()
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

    # --- 보안문자: PC 터미널 또는 폰(카카오 링크) 중 먼저 입력되는 쪽을 사용 ---
    for attempt in range(5):
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
        source, code = remote_server.result_queue.get()
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
            # 사이트가 직접 알림창으로 알려주는 실패 사유 (예: "보안문자가 일치하지 않습니다").
            print(f"  -> 사이트 응답: {new_dialogs[-1]} 다시 시도합니다.")
            continue
        # "이용료 *" 라벨(버튼 옆)과 구분하기 위해 콜론이 붙은 결과 텍스트("이용료 : 13,000원")만 매칭한다.
        fee_locator = page.get_by_text(re.compile(r"이용료\s*[:：]"))
        fee_text = fee_locator.first.inner_text() if fee_locator.count() > 0 else ""
        fee_match = re.search(r"[1-9][\d,]*", fee_text)
        if fee_match:
            print(f"  -> 이용료 확인 완료 ({source}에서 입력): {fee_match.group(0)}원")
            break
        debug_fee_path = SCRIPT_DIR / f"debug_fee_{court_num}_{attempt}.png"
        try:
            page.screenshot(path=str(debug_fee_path), full_page=True)
        except Exception:
            pass
        print(
            f"  -> 이용료 확인 실패로 보입니다 (알림창은 없었음, 표시된 텍스트: {fee_text.strip()!r}, "
            f"화면 캡처: {debug_fee_path.name}). 다시 시도합니다."
        )
    else:
        print("  -> 보안문자 확인을 5회 실패했습니다. 이 코트를 건너뜁니다.")
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


def run_once(config: dict, remote_server: RemoteCaptchaServer, public_url: str | None) -> str:
    """이미 떠 있는 remote_server(및 ngrok 터널, 선택)를 재사용해 로그인 -> (날짜/시간별) 코트 순회 -> 결과 저장까지 실행한다.
    target_slots에 여러 날짜/시간이 있으면 각각 시도해 가능한 만큼 모두 예약한다.
    반환값은 결과 파일에 쓴 텍스트 전체(호출자가 화면에 그대로 보여줄 수 있게)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        dialog_messages: list[str] = []
        page.on("dialog", lambda d: (dialog_messages.append(d.message), print(f"[사이트 알림] {d.message}"), d.accept()))

        page.goto(f"{BASE}/memberLogin.do")
        page.fill("#userId", config["user_id"])
        page.fill("#pwd", config["user_pw"])
        page.get_by_role("button", name="로그인", exact=True).click()
        page.wait_for_load_state("networkidle")

        successes: list[dict] = []
        failures: list[tuple[datetime, str]] = []
        for target_date, time_label in config["target_slots"]:
            print(f"\n##### 대상: {target_date.strftime('%Y-%m-%d')} {time_label} #####")
            booking_result = None
            for court_num in config["court_order"]:
                if court_num in SKIP_COURTS:
                    print(f"{court_num}번 코트는 이용수익허가 코트라 건너뜁니다.")
                    continue
                stadium_idx = COURTS.get(court_num)
                if not stadium_idx:
                    continue
                try:
                    booking_result = book_court(
                        page, court_num, stadium_idx, target_date, time_label, config,
                        remote_server, public_url, dialog_messages,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"  -> {court_num}번 코트 처리 중 오류: {exc}")
                    booking_result = None
                if booking_result:
                    break
            if booking_result:
                successes.append(booking_result)
            else:
                failures.append((target_date, time_label))

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

        browser.close()

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
