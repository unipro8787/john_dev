"""카카오톡 '나에게 보내기' — economic_news/send_kakao.py 의 전송 로직과 .env(키/refresh_token)를 재사용."""
import sys
from .base import PROJECTS

_NEWS = PROJECTS / "economic_news"


def send(text, label="존엔터", link_url="http://127.0.0.1:8800"):
    if str(_NEWS) not in sys.path:
        sys.path.insert(0, str(_NEWS))
    from send_kakao import kakao_send_to_me, load_dotenv
    load_dotenv(_NEWS / ".env")
    try:
        kakao_send_to_me(text, label=label, link_url=link_url)
    except SystemExit as e:  # send_kakao 는 실패 시 SystemExit — 서버/직원 실행이 죽지 않도록 일반 예외로 바꾼다
        raise RuntimeError(str(e)) from None
