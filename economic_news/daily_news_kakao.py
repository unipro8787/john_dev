# 국내+해외 경제뉴스 RSS를 모아 헤드라인을 정리하고 카카오톡 "나에게 보내기"로 전송한다.
#
# GitHub Actions(.github/workflows/daily_news_kakao.yml)에서 매일 실행되는 것을 전제로
# 작성했다 - 로컬 PC가 꺼져 있어도 동작하도록, 그리고 클로드 클라우드 루틴의 샌드박스
# 네트워크 정책이 카카오 API(kauth.kakao.com/kapi.kakao.com)를 차단하는 문제를 피하기 위해
# GitHub의 러너에서 직접 RSS 수집 + 카카오 전송까지 끝낸다.
#
# 외부 패키지 없이 표준 라이브러리만 사용한다(feedparser 등 pip 설치 불필요).
#
# 사용법:
#   python daily_news_kakao.py            # RSS 수집 + 카카오 전송
#   python daily_news_kakao.py --dry-run  # 전송 없이 결과 텍스트만 출력 (로컬 테스트용)

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

# (구분, 언론사, RSS URL) - 국내는 한국어 원문, 해외는 영어 원문 그대로 사용한다.
FEEDS = [
    ("국내", "연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("국내", "한국경제", "https://www.hankyung.com/feed/economy"),
    ("국내", "한국경제(증권)", "https://www.hankyung.com/feed/finance"),
    ("국내", "조선비즈", "https://biz.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml"),
    ("국내", "뉴시스", "http://www.newsis.com/RSS/economy.xml"),
    ("국내", "아시아경제", "https://www.asiae.co.kr/rss/economy.htm"),
    ("해외", "CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("해외", "BBC", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("해외", "Financial Times", "https://www.ft.com/rss/home"),
    ("해외", "MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("해외", "Investing.com", "https://www.investing.com/rss/news_285.rss"),
]


def fetch_feed_titles(url: str, limit: int) -> list[str]:
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

    titles = []
    for item in root.iter("item"):
        title_el = item.find("title")
        if title_el is None or not title_el.text:
            continue
        title = " ".join(title_el.text.split())
        if title:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def collect_headlines() -> list[tuple[str, str, str]]:
    """[(구분, 언론사, 제목), ...] 를 TOTAL_LIMIT개까지 모은다."""
    collected: list[tuple[str, str, str]] = []
    seen_titles: set[str] = set()
    for section, source, url in FEEDS:
        for title in fetch_feed_titles(url, PER_FEED_LIMIT):
            if title in seen_titles:
                continue
            seen_titles.add(title)
            collected.append((section, source, title))
    return collected[:TOTAL_LIMIT]


def format_message(headlines: list[tuple[str, str, str]]) -> str:
    from datetime import datetime, timezone, timedelta

    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%m/%d")

    lines = [f"[오늘의 경제뉴스 {today}] 총 {len(headlines)}건", ""]
    current_section = None
    idx = 0
    for section, source, title in headlines:
        if section != current_section:
            current_section = section
            lines.append(f"■ {section}")
        idx += 1
        lines.append(f"{idx}. [{source}] {title}")
    return "\n".join(lines)


def main() -> None:
    load_dotenv(SCRIPT_DIR / ".env")
    dry_run = "--dry-run" in sys.argv[1:]

    headlines = collect_headlines()
    if not headlines:
        raise SystemExit("뉴스 헤드라인을 하나도 가져오지 못했습니다.")

    message = format_message(headlines)

    if dry_run:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(message)
        return

    kakao_send_to_me(message)


if __name__ == "__main__":
    main()
