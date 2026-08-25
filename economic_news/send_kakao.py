# 경제뉴스 요약 텍스트를 카카오톡 "나에게 보내기"로 전송하는 스크립트.
#
# tennis_booking의 kakao_send_to_me()와 달리, 매일 무인으로 돌아가는 스케줄 작업에서
# 쓰기 위해 access_token을 저장해두지 않고 매번 refresh_token으로 새로 발급받아 사용한다.
# (access_token은 발급 후 몇 시간이면 만료되지만, refresh_token은 보통 60일간 유효)
#
# 사전 준비: kakao_get_token.py 로 KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN 을 발급받아
#           .env 에 저장 (.env.example 참고)
#
# 사용법:
#   python send_kakao.py "보낼 텍스트"
#   echo "보낼 텍스트" | python send_kakao.py

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CHUNK_SIZE = 180  # 카카오 기본 텍스트 템플릿 글자 제한(약 200자)보다 여유를 둔 값


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def refresh_access_token(rest_api_key: str, refresh_token: str) -> str:
    params = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET")
    if client_secret:
        params["client_secret"] = client_secret
    body = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request("https://kauth.kakao.com/oauth/token", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"[카카오] access_token 갱신 실패 ({exc.code}): {detail}\n"
            "refresh_token이 만료됐을 수 있습니다. kakao_get_token.py를 다시 실행해 재발급하세요."
        ) from exc

    if "refresh_token" in data:
        # 카카오는 refresh_token 만료가 얼마 안 남았을 때만 새 refresh_token을 함께 내려준다.
        print(
            f"[카카오] 새 refresh_token이 발급됐습니다. .env / 스케줄 설정의 "
            f"KAKAO_REFRESH_TOKEN을 아래 값으로 갱신하세요:\n{data['refresh_token']}",
            file=sys.stderr,
        )
    return data["access_token"]


def _chunks(text: str, size: int) -> list[str]:
    """줄 단위를 최대한 유지하면서 size 이하로 나눈다 (헤드라인이 메시지 중간에서 잘리지 않도록)."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(line) <= size:
            current = line
        else:
            for i in range(0, len(line), size):
                chunks.append(line[i : i + size])
            current = ""
    if current:
        chunks.append(current)
    return chunks or [""]


def kakao_send_to_me(text: str) -> None:
    rest_api_key = os.environ.get("KAKAO_REST_API_KEY")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
    if not rest_api_key or not refresh_token:
        raise SystemExit(
            "KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN이 설정되지 않았습니다. "
            "kakao_get_token.py로 발급받아 .env에 저장하세요."
        )

    access_token = refresh_access_token(rest_api_key, refresh_token)

    parts = _chunks(text, CHUNK_SIZE)
    for i, part in enumerate(parts, start=1):
        prefix = f"[경제뉴스 {i}/{len(parts)}]\n" if len(parts) > 1 else ""
        template = {
            "object_type": "text",
            "text": prefix + part,
            "link": {"web_url": "https://news.naver.com/section/101", "mobile_web_url": "https://news.naver.com/section/101"},
        }
        body = urllib.parse.urlencode(
            {"template_object": json.dumps(template, ensure_ascii=False)}
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            data=body,
            headers={"Authorization": f"Bearer {access_token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"[카카오] 전송 실패 ({exc.code}): {detail}") from exc

    print(f"[카카오] 전송 완료 ({len(parts)}개 메시지)")


def main() -> None:
    load_dotenv(SCRIPT_DIR / ".env")
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    text = text.strip()
    if not text:
        raise SystemExit("보낼 텍스트가 없습니다.")
    kakao_send_to_me(text)


if __name__ == "__main__":
    main()
