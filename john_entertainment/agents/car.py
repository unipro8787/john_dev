"""차량 관리 매니저 — GV70 소모품/점검 주기.

점검 카톡 알림(kakao_alert)은 GitHub Actions(.github/workflows/car_maintenance_kakao.yml)가 매일 실행한다.
그래서 data/car.json 은 git 으로 관리되고, 대시보드에서 바꾸면 _sync_to_github() 로 바로 push 한다.
알림 기록(car_alert_state.json)은 Actions 만 쓰고 커밋한다 (로컬과 서로 같은 파일을 고치지 않아 충돌이 없도록)."""
import datetime as dt
import os
import subprocess
from . import kakao
from .base import DATA, load_json, save_json, report, today

F = DATA / "car.json"
ALERT_STATE = DATA / "car_alert_state.json"
_CAR_JSON = F
_ON_ACTIONS = bool(os.environ.get("GITHUB_ACTIONS"))


def _sync_to_github(what):
    """바뀐 car.json 을 커밋·push 해서 GitHub Actions 알림이 최신 정비 기록을 보게 한다. 실패해도 기록 자체는 유지."""
    if _ON_ACTIONS or F != _CAR_JSON:  # Actions 실행 중이거나 테스트(경로 교체) 중이면 건너뜀
        return []
    rel = F.relative_to(DATA.parent.parent).as_posix()
    cwd = DATA.parent.parent

    def git(*a):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60)

    if not git("status", "--porcelain", "--", rel).stdout.strip():
        return []
    steps = [("add", "--", rel), ("commit", "-m", f"car: {what}", "--", rel),
             ("pull", "--rebase", "--autostash"), ("push")]
    for a in steps:
        r = git(*a) if isinstance(a, tuple) else git(a)
        if r.returncode:
            return ["", f"⚠️ GitHub 반영 실패 (`git {a if isinstance(a, str) else ' '.join(a[:2])}`): {(r.stderr or r.stdout).strip()[:300]}",
                    "→ 알림이 예전 기록으로 나갈 수 있습니다. `git push` 를 직접 실행해 주세요."]
    return ["", "GitHub 에 반영했습니다 (내일 아침 알림부터 적용)."]


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return dt.date(y, m, min(d.day, (nxt - dt.timedelta(days=1)).day))


def _status(c):
    """항목별 상태 [(icon, name, detail, level)] — level: due(교체 시기) / warn(곧 도래·기록 없음) / ok."""
    odo, out = c["odometer_km"], []
    for it in c["items"]:
        if it["last_km"] is None:
            out.append(("🟡", it["name"], f"기록 없음 → 점검/교환 이력 확인 필요 (주기 {it['interval_km']:,}km/{it['interval_months']}개월)",
                        "due" if odo >= it["interval_km"] else "warn"))
            continue
        left_km = it["last_km"] + it["interval_km"] - odo
        last = dt.date.fromisoformat(it["last_date"]) if it["last_date"] else today()
        due_date = _add_months(last, it["interval_months"])
        left_d = (due_date - today()).days
        if left_km <= 0 or left_d <= 0:
            icon, level = "🔴 교체 시기", "due"
        elif left_km <= 1500 or left_d <= 30:
            icon, level = "🟠 곧 도래", "warn"
        else:
            icon, level = "🟢 양호", "ok"
        out.append((icon, it["name"], f"남은 {left_km:,}km / {due_date} 까지 (D-{left_d})" if left_d > 0 else f"남은 {left_km:,}km / 기간 {-left_d}일 지남", level))
    return out


def _date_events(c, within_days=30):
    """보험 갱신·정기검사 중 within_days 이내(또는 지난) 일정 [(이름, 날짜, D-day)]."""
    ev = []
    for k, n in (("insurance_renewal", "보험 갱신"), ("inspection_due", "정기검사")):
        if c.get(k):
            d = (dt.date.fromisoformat(c[k]) - today()).days
            if d <= within_days:
                ev.append((n, c[k], d))
    return ev


def maintenance_check(**_):
    c = load_json(F)
    odo = c["odometer_km"]
    lines = [f"## {c['model']} 정비 현황 (현재 {odo:,}km)", "", f"> {c['note']}", ""]
    st = _status(c)
    due = [n for _, n, _, lv in st if lv == "due"]
    warn = [n for _, n, _, lv in st if lv == "warn"]
    for icon, name, detail, _ in st:
        lines.append(f"- {icon} {name}: {detail}")
    for k, n in (("insurance_renewal", "보험 갱신일"), ("inspection_due", "정기검사일")):
        lines.append(f"- {n}: {c[k] or '미등록 (data/car.json 에 입력)'}")
    props = [{"text": "정비소 예약 및 점검/교체 진행: " + ", ".join(due), "kind": "info"}] if due else []
    return report("GV70 정비 현황", lines,
                  [f"{odo:,}km", f"점검/교체 필요 {len(due)}건", f"기록 없는 항목 포함 확인 필요 {len(warn)}건"], props)


def kakao_alert(force="0", **_):
    """점검 주기가 된 항목을 카카오톡 '나에게 보내기'로 알린다.
    같은 내용은 alert.remind_days(기본 7일)마다 한 번만, 내용이 바뀌면 바로 보낸다."""
    c = load_json(F)
    cfg = {"remind_days": 7, "date_within_days": 30, "odometer_stale_days": 30, **c.get("alert", {})}
    st = _status(c)
    due = [n for _, n, _, lv in st if lv == "due"]
    warn = [n for _, n, _, lv in st if lv == "warn"]
    events = _date_events(c, cfg["date_within_days"])
    odo_age = (today() - dt.date.fromisoformat(c["odometer_date"])).days if c.get("odometer_date") else None
    stale = odo_age is None or odo_age >= cfg["odometer_stale_days"]

    if not (due or warn or events):
        return report("정비 카톡 알림", ["점검/교체 도래 항목이 없어 알림을 보내지 않았습니다."], ["알림 없음"])

    msg = [f"🚗 {c['model']} 점검 알림 (차정비)", f"주행 {c['odometer_km']:,}km 기준"]
    if due:
        msg.append("🔴 점검/교체: " + ", ".join(due))
    if warn:
        msg.append("🟠 곧 도래·확인: " + ", ".join(warn))
    for n, d, left in events:
        msg.append(f"📅 {n} {d} ({'D-' + str(left) if left >= 0 else str(-left) + '일 지남'})")
    if stale:
        msg.append(f"※ 주행거리 {odo_age if odo_age is not None else '?'}일째 미갱신 — 대시보드에서 갱신해 주세요")
    text = "\n".join(msg)

    key = "|".join(sorted(due) + ["/"] + sorted(warn) + ["/"] + [f"{n}{d}" for n, d, _ in events])
    sent = load_json(ALERT_STATE, {})
    last = dt.date.fromisoformat(sent["date"]) if sent.get("date") else None
    if str(force) not in ("1", "true", "yes") and sent.get("key") == key and last and (today() - last).days < cfg["remind_days"]:
        return report("정비 카톡 알림", [f"같은 내용을 {sent['date']} 에 이미 보냈습니다 ({cfg['remind_days']}일 후 재알림).", "", text],
                      ["중복 생략"])

    kakao.send(text, label="차량점검")
    if _ON_ACTIONS or F != _CAR_JSON:  # 로컬(대시보드) 수동 전송은 기록하지 않음 — 기록 파일은 Actions 전용
        save_json(ALERT_STATE, {"date": today().isoformat(), "key": key})
    return report("정비 카톡 알림", ["카카오톡으로 아래 내용을 보냈습니다.", "", text],
                  ["전송 완료", f"교체 {len(due)}건", f"확인 {len(warn) + len(events)}건"])


def update_odometer(km="0", **_):
    c = load_json(F)
    c["odometer_km"] = int(str(km).replace(",", ""))
    c["odometer_date"] = today().isoformat()
    save_json(F, c)
    return report("주행거리 갱신", [f"현재 {c['odometer_km']:,}km 로 기록", *_sync_to_github(f"odometer {c['odometer_km']}km")],
                  [f"{c['odometer_km']:,}km"])


def log_service(item_id="", cost="", **_):
    c = load_json(F)
    for it in c["items"]:
        if it["id"] == item_id:
            it["last_km"], it["last_date"] = c["odometer_km"], today().isoformat()
            save_json(F, c)
            return report("정비 기록", [f"{it['name']} 을(를) {c['odometer_km']:,}km 에 수행 완료로 기록 (비용 {cost or '-'})",
                                    *_sync_to_github(f"{item_id} serviced at {c['odometer_km']}km")], [it["name"]])
    ids = ", ".join(i["id"] for i in c["items"])
    return report("정비 기록 실패", [f"알 수 없는 항목입니다. 사용 가능: {ids}"], ["실패"])


ACTIONS = {
    "maintenance_check": {"label": "정비 현황 점검", "fn": maintenance_check},
    "kakao_alert": {"label": "점검 카톡 알림", "fn": kakao_alert,
                    "params": [{"name": "force", "label": "중복이어도 보내기 (1=예)", "default": "0"}]},
    "update_odometer": {"label": "주행거리 갱신", "fn": update_odometer,
                        "params": [{"name": "km", "label": "현재 주행거리(km)", "default": ""}]},
    "log_service": {"label": "정비 수행 기록", "fn": log_service, "params": [
        {"name": "item_id", "label": "항목 ID (engine_oil, tire_rotation, aircon_filter, brake_pad, brake_fluid, transmission, spark_plug, battery, wiper)", "default": "engine_oil"},
        {"name": "cost", "label": "비용", "default": ""}]},
}
DEFAULT_ACTION = "maintenance_check"
