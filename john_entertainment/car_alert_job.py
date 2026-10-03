"""GitHub Actions 전용 — 차정비 점검 카톡 알림만 실행한다.

저장소(공개)에는 차량 관련 파일(agents/base.py, car.py, kakao.py, data/car.json)만 올라가므로,
모든 직원을 불러오는 agents/__init__.py 를 거치지 않도록 agents 패키지를 빈 껍데기로 등록한 뒤 car 만 불러온다.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
pkg = types.ModuleType("agents")
pkg.__path__ = [str(ROOT / "agents")]
sys.modules["agents"] = pkg
sys.stdout.reconfigure(encoding="utf-8")

from agents import car  # noqa: E402

force = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("force=")), "0")
r = car.kakao_alert(force=force)
print(f"# {r['title']}\n\n{r['body']}")
