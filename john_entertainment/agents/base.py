import json, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
PROJECTS = ROOT.parent  # john_dev


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def today():
    return dt.date.today()


def won(n):
    return f"{int(round(n)):,}원"


def report(title, lines, highlights=None, proposals=None):
    """표준 결과 형식. proposals 는 총괄 매니저의 승인이 필요한 제안 목록."""
    return {
        "title": title,
        "body": "\n".join(lines),
        "highlights": highlights or [],
        "proposals": proposals or [],
    }
