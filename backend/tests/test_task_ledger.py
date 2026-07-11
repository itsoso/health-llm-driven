"""统一任务账本(Harness 自由度升级 Slice 4)测试。

覆盖:五源混合完整 + (kind, title, when) 去重;空态诚实返回 [];
单源查询抛错 fail-loud 计入 failed_sources 而非整包 500;API shape。
"""
from datetime import datetime, timedelta

from app.models.desktop_job import DesktopJob
from app.models.write_intent import WriteIntent
from app.services import health_problem_service
from app.services.task_ledger_service import build_ledger
from app.utils.timezone import get_user_today
from tests.conftest import create_authenticated_user


def _add_write_intent(db, user_id, *, kind, title, status="pending",
                      created_at=None, decided_at=None):
    wi = WriteIntent(user_id=user_id, kind=kind, title=title, status=status)
    if created_at is not None:
        wi.created_at = created_at
    if decided_at is not None:
        wi.decided_at = decided_at
    db.add(wi)
    db.commit()
    return wi


def _add_desktop_job(db, user_id, *, job_type, status, source_name=None):
    job = DesktopJob(user_id=user_id, job_type=job_type, status=status,
                     source_name=source_name)
    db.add(job)
    db.commit()
    return job


def _add_followup_problem(db, user_id, *, name, next_due):
    return health_problem_service.create_problem(db, user_id, {
        "name": name,
        "risk_level": "P1",
        "follow_up": {"next_due": str(next_due), "what_to_check": "复查"},
    })


def test_ledger_unions_five_sources_and_dedupes(db):
    """五源都有数据时账本完整;(kind, title, when) 重复只留一条。"""
    user, _ = create_authenticated_user(db)
    now = datetime.now()
    today = get_user_today(db, user.id)

    # 源1 write_intents:pending ×2(完全同 kind/title/when → 应去重成 1)+ 近 48h 已裁决 + 过期已裁决
    fixed_created = now - timedelta(hours=1)
    _add_write_intent(db, user.id, kind="checkup_reminder", title="建立复查提醒",
                      created_at=fixed_created)
    _add_write_intent(db, user.id, kind="checkup_reminder", title="建立复查提醒",
                      created_at=fixed_created)
    _add_write_intent(db, user.id, kind="measurement_prompt", title="补测血压",
                      status="executed", decided_at=now - timedelta(hours=2))
    _add_write_intent(db, user.id, kind="measurement_prompt", title="很久前办完的",
                      status="executed", decided_at=now - timedelta(days=5))

    # 源2 desktop_jobs:active 进账本;completed 不进
    _add_desktop_job(db, user.id, job_type="medical_report_import",
                     status="running", source_name="体检报告.pdf")
    _add_desktop_job(db, user.id, job_type="medical_report_import",
                     status="completed", source_name="旧报告.pdf")

    # 源3 agenda:48h 内到期复查进账本;远期(30 天后)不进
    _add_followup_problem(db, user.id, name="胃镜复查", next_due=today + timedelta(days=1))
    _add_followup_problem(db, user.id, name="远期复查", next_due=today + timedelta(days=30))

    ledger = build_ledger(user.id, db)
    assert ledger["failed_sources"] == []
    items = ledger["items"]

    # 去重:两条完全相同的 pending write_intent 折成一条
    pending = [i for i in items if i["source"] == "write_intent" and i["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["kind"] == "checkup_reminder"

    # 近 48h 已裁决在账本里;5 天前的不在
    executed_titles = [i["title"] for i in items
                       if i["source"] == "write_intent" and i["status"] == "executed"]
    assert executed_titles == ["补测血压"]

    # desktop_jobs 只收 active
    jobs = [i for i in items if i["source"] == "desktop_job"]
    assert len(jobs) == 1
    assert jobs[0]["title"] == "体检报告.pdf"
    assert jobs[0]["status"] == "running"

    # agenda 只收 48h 窗口内的复查
    agenda = [i for i in items if i["source"] == "agenda"]
    assert len(agenda) == 1
    assert agenda[0]["title"] == "复查:胃镜复查"
    assert agenda[0]["status"] == "scheduled"
    assert agenda[0]["when"] == str(today + timedelta(days=1))

    # 统一 shape:每条五个键齐全
    for item in items:
        assert set(item.keys()) == {"kind", "title", "status", "when", "source"}

    # 按 when 升序(有 when 的在前,字符串 ISO 序)
    whens = [i["when"] for i in items if i["when"]]
    assert whens == sorted(whens)


def test_ledger_empty_state_returns_empty_list(db):
    """空态诚实:无任何后台活时 items 为 [],不伪造。"""
    user, _ = create_authenticated_user(db)
    ledger = build_ledger(user.id, db)
    assert ledger["items"] == []
    assert ledger["failed_sources"] == []


def test_ledger_single_source_failure_is_isolated_and_visible(db, monkeypatch):
    """单源抛错 fail-loud:计入 failed_sources,其余源照常返回,不整包炸。"""
    user, _ = create_authenticated_user(db)
    _add_desktop_job(db, user.id, job_type="medical_report_import",
                     status="queued", source_name="报告.pdf")

    from app.services import agenda_service

    def _boom(*args, **kwargs):
        raise RuntimeError("agenda source exploded")

    monkeypatch.setattr(agenda_service, "range_view", _boom)

    ledger = build_ledger(user.id, db)
    assert [f["source"] for f in ledger["failed_sources"]] == ["agenda"]
    assert "agenda source exploded" in ledger["failed_sources"][0]["error"]
    # 其余源不受影响
    assert [i["title"] for i in ledger["items"]] == ["报告.pdf"]


def test_agent_tasks_endpoint_shape_and_auth(client, db):
    """GET /api/v1/agent/tasks:登录必需;返回 items + failed_sources。"""
    user, token = create_authenticated_user(db)
    _add_write_intent(db, user.id, kind="checkup_reminder", title="建立复查提醒")

    # 未登录 → 401
    assert client.get("/api/v1/agent/tasks").status_code == 401

    res = client.get("/api/v1/agent/tasks",
                     headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["failed_sources"] == []
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "建立复查提醒"
    assert body["items"][0]["source"] == "write_intent"

    # 跨用户隔离:另一个用户看不到别人的账本
    _, other_token = create_authenticated_user(db)
    other = client.get("/api/v1/agent/tasks",
                       headers={"Authorization": f"Bearer {other_token}"})
    assert other.status_code == 200
    assert other.json()["items"] == []
