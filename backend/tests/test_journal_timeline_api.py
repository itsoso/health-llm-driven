"""GET /api/v1/clinical-journal/timeline — case-thread 分组 timeline."""
from datetime import datetime, timedelta, timezone

from app.models.clinical_journal import CaseThread, ClinicalJournalEntry
from app.models.user import User


def _seed_threads_and_entries(db, user_id: int):
    now = datetime.now(timezone.utc)

    # Thread 1: 鼻炎管理 (1 entry within window)
    t1 = CaseThread(
        user_id=user_id, theme="鼻炎管理", title="我的鼻炎",
        status="active", opened_at=now - timedelta(days=20),
    )
    db.add(t1); db.commit(); db.refresh(t1)

    db.add_all([
        ClinicalJournalEntry(
            user_id=user_id, case_thread_id=t1.id,
            generated_at=now - timedelta(days=1),
            created_by="orchestrator",
            subjective="晨起鼻塞, 喷嚏连作, 前夜粉尘环境暴露",
            objective="...", assessment="...", plan="...",
        ),
        # 无 thread 的 entry (应该归入 "其他" bucket)
        ClinicalJournalEntry(
            user_id=user_id, case_thread_id=None,
            generated_at=now - timedelta(hours=6),
            created_by="briefing_task",
            subjective="周度摘要", objective="...",
            assessment="...", plan="...",
        ),
    ])
    db.commit()


def test_journal_timeline_empty_schema(client, auth_user_and_headers):
    """空库返回 {threads: []}."""
    _, headers = auth_user_and_headers
    r = client.get("/api/v1/clinical-journal/timeline", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"threads": []}


def test_journal_timeline_groups_by_thread_plus_others(client, db, auth_user_and_headers):
    """有 thread 的聚成 bucket, 无 thread 的归入 '其他 / 周度摘要' bucket."""
    _, headers = auth_user_and_headers
    user = db.query(User).first()
    _seed_threads_and_entries(db, user_id=user.id)

    r = client.get("/api/v1/clinical-journal/timeline?days=30", headers=headers)
    assert r.status_code == 200
    threads = r.json()["threads"]

    themes = {t["theme"] for t in threads}
    assert "鼻炎管理" in themes
    # 无 thread bucket 存在, thread_id 为 null
    no_thread = [t for t in threads if t["thread_id"] is None]
    assert len(no_thread) == 1
    assert len(no_thread[0]["entries"]) == 1


def test_journal_timeline_subjective_short_truncated_60_chars(client, db, auth_user_and_headers):
    """每个 entry 的 subjective_short 最多 60 字."""
    _, headers = auth_user_and_headers
    user = db.query(User).first()

    now = datetime.now(timezone.utc)
    long_subj = "这是一段很长的主诉." * 20  # >60 chars
    db.add(ClinicalJournalEntry(
        user_id=user.id, case_thread_id=None,
        generated_at=now - timedelta(hours=2),
        created_by="orchestrator",
        subjective=long_subj, objective="o", assessment="a", plan="p",
    ))
    db.commit()

    r = client.get("/api/v1/clinical-journal/timeline", headers=headers)
    entries = [e for t in r.json()["threads"] for e in t["entries"]]
    assert len(entries) >= 1
    assert all(len(e["subjective_short"]) <= 60 for e in entries)


def test_journal_timeline_days_filter(client, db, auth_user_and_headers):
    """超过 days 窗口的 entry 不返回."""
    _, headers = auth_user_and_headers
    user = db.query(User).first()

    now = datetime.now(timezone.utc)
    # 窗口内的
    db.add(ClinicalJournalEntry(
        user_id=user.id, case_thread_id=None,
        generated_at=now - timedelta(days=2),
        created_by="orchestrator",
        subjective="近期的", objective="o", assessment="a", plan="p",
    ))
    # 窗口外的 (90 天前)
    db.add(ClinicalJournalEntry(
        user_id=user.id, case_thread_id=None,
        generated_at=now - timedelta(days=90),
        created_by="orchestrator",
        subjective="太老了", objective="o", assessment="a", plan="p",
    ))
    db.commit()

    r = client.get("/api/v1/clinical-journal/timeline?days=30", headers=headers)
    flat = [e for t in r.json()["threads"] for e in t["entries"]]
    subjects = [e["subjective_short"] for e in flat]
    assert any("近期的" in s for s in subjects)
    assert not any("太老了" in s for s in subjects)
