# 국내 경제뉴스 RSS를 모아 주요 뉴스를 Claude API로 쉽게 요약한 뒤
# 카카오톡 "나에게 보내기"로 전송한다.
#
# GitHub Actions(.github/workflows/daily_news_kakao.yml)에서 매일 실행되는 것을 전제로
# 작성했다 - 로컬 PC가 꺼져 있어도 동작하도록, 그리고 클로드 클라우드 루틴의 샌드박스
# 네트워크 정책이 카카오 API(kauth.kakao.com/kapi.kakao.com)를 차단하는 문제를 피하기 위해
# GitHub의 러너에서 직접 RSS 수집 + 요약 + 카카오 전송까지 끝낸다.
#
# 외부 패키지 없이 표준 라이브러리만 사용한다(feedparser, anthropic SDK 등 pip 설치 불필요.
# Claude API도 REST(urllib)로 직접 호출한다).
#
# 사전 준비: ANTHROPIC_API_KEY를 .env(로컬) / GitHub Secrets(Actions)에 등록해야 한다.
#
# 사용법:
#   python daily_news_kakao.py            # RSS 수집 + 요약 + 카카오 전송
#   python daily_news_kakao.py --dry-run  # 전송 없이 결과 텍스트만 출력 (로컬 테스트용)

import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_kakao import kakao_send_to_me, load_dotenv  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
USER_AGENT = "Mozilla/5.0 (compatible; economic-news-bot/1.0)"
PER_FEED_LIMIT = 6
TOTAL_LIMIT = 50
DESCRIPTION_MAX_LEN = 400
SUMMARY_COUNT = 10

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-5"

# (구분, 언론사, RSS URL) - 국내 경제뉴스만 수집한다.
FEEDS = [
    ("국내", "연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("국내", "한국경제", "https://www.hankyung.com/feed/economy"),
    ("국내", "한국경제(증권)", "https://www.hankyung.com/feed/finance"),
    ("국내", "조선비즈", "https://biz.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml"),
    ("국내", "뉴시스", "http://www.newsis.com/RSS/economy.xml"),
    ("국내", "아시아경제", "https://www.asiae.co.kr/rss/economy.htm"),
]

_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(raw: str) -> str:
    """RSS 필드에 섞인 HTML 태그/엔티티를 제거하고 공백을 정리한다."""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return " ".join(text.split())


def fetch_feed_items(url: str, limit: int) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"[뉴스] {url} 가져오기 실패: {exc}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        print(f"[뉴스] {url} 파싱 실패: {exc}", file=sys.stderr)
        return []

    items = []
    for item in root.iter("item"):
        title_el = item.find("title")
        if title_el is None or not title_el.text:
            continue
        title = _clean_text(title_el.text)
        if not title:
            continue

        desc_el = item.find("description")
        description = _clean_text(desc_el.text) if desc_el is not None and desc_el.text else ""

        items.append({"title": title, "description": description[:DESCRIPTION_MAX_LEN]})
        if len(items) >= limit:
            break
    return items


def collect_articles() -> list[dict]:
    """[{source, title, description}, ...] 를 TOTAL_LIMIT개까지 모은다."""
    collected: list[dict] = []
    seen_titles: set[str] = set()
    for _section, source, url in FEEDS:
        for item in fetch_feed_items(url, PER_FEED_LIMIT):
            if item["title"] in seen_titles:
                continue
            seen_titles.add(item["title"])
            collected.append({"source": source, **item})
    return collected[:TOTAL_LIMIT]


def _build_prompt(articles: list[dict]) -> str:
    lines = []
    for i, a in enumerate(articles, start=1):
        lines.append(f"{i}. [{a['source']}] {a['title']}")
        if a["description"]:
            lines.append(f"   설명: {a['description']}")
    articles_block = "\n".join(lines)

    return (
        f"아래는 오늘 국내 경제 뉴스 헤드라인 목록입니다 (총 {len(articles)}건).\n\n"
        f"{articles_block}\n\n"
        f"이 중 경제적으로 가장 중요하다고 판단되는 뉴스 {SUMMARY_COUNT}개를 골라주세요.\n"
        "각 뉴스마다 무슨 내용인지, 경제 지식이 없는 사람도 이해할 수 있도록 쉬운 말로 "
        "2문장 이내로 설명해 주세요. 전문 용어는 풀어쓰거나 간단히 덧붙여 설명하세요.\n\n"
        "다른 설명, 인사말, 머리말 없이 아래 형식만 정확히 그대로 출력하세요:\n"
        "1. [언론사] 한 줄 소제목\n"
        "   → 쉬운 설명\n"
        "2. [언론사] 한 줄 소제목\n"
        "   → 쉬운 설명\n"
        f"...(총 {SUMMARY_COUNT}개까지)"
    )


def summarize_with_claude(articles: list[dict]) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다. .env(로컬) / GitHub Secrets(Actions)에 등록하세요."
        )

    payload = {
        "model": os.environ.get("ANTHROPIC_MODEL", ANTHROPIC_MODEL),
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": _build_prompt(articles)}],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"[Claude] 요약 요청 실패 ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"[Claude] 요약 요청 실패: {exc}") from exc

    text = "\n".join(
        block["text"] for block in data.get("content", []) if block.get("type") == "text"
    ).strip()
    if not text:
        raise SystemExit(f"[Claude] 응답에서 텍스트를 찾지 못했습니다: {data}")
    return text


def format_message(summary_text: str, article_count: int) -> str:
    from datetime import datetime, timezone, timedelta

    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%m/%d")

    header = f"[오늘의 국내 경제뉴스 {today}] 주요 뉴스 {SUMMARY_COUNT}건 요약 (수집 {article_count}건 중)"
    return f"{header}\n\n{summary_text}"


def main() -> None:
    load_dotenv(SCRIPT_DIR / ".env")
    dry_run = "--dry-run" in sys.argv[1:]

    articles = collect_articles()
    if not articles:
        raise SystemExit("뉴스 헤드라인을 하나도 가져오지 못했습니다.")

    summary_text = summarize_with_claude(articles)
    message = format_message(summary_text, len(articles))

    if dry_run:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(message)
        return

    kakao_send_to_me(message)


if __name__ == "__main__":
    main()
