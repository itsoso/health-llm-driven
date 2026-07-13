"""医生周报 (Telegram) — 周度数据摘要生成 + 推送路径单测."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


# ─────────────── helpers 单测 ───────────────


class TestMedicationAdherenceBlock:
    def test_empty_when_no_medicine_templates(self, db):
        from app.tasks.notifications import _build_doctor_medication_adherence_block
        assert _build_doctor_medication_adherence_block(
            db, user_id=1, since_date=date.today() - timedelta(days=7)
        ) == ""

    def test_100pct_no_warning(self, db):
        from app.models.checkin import CheckinTemplate, CheckinRecord
        from app.tasks.notifications import _build_doctor_medication_adherence_block

        t = CheckinTemplate(
            user_id=2, name="美托洛尔", category="medicine", frequency="daily",
            is_active=True, is_archived=False,
        )
        db.add(t); db.commit(); db.refresh(t)

        today = date.today()
        for i in range(7):
            db.add(CheckinRecord(
                template_id=t.id, user_id=2,
                checkin_date=today - timedelta(days=i),
                value=1,
            ))
        db.commit()

        out = _build_doctor_medication_adherence_block(
            db, user_id=2, since_date=today - timedelta(days=7))
        assert "美托洛尔" in out
        assert "7/7" in out or "100%" in out
        assert "⚠️" not in out

    def test_low_adherence_flagged(self, db):
        from app.models.checkin import CheckinTemplate, CheckinRecord
        from app.tasks.notifications import _build_doctor_medication_adherence_block

        t = CheckinTemplate(
            user_id=3, name="华法林", category="medicine", frequency="daily",
            is_active=True, is_archived=False,
        )
        db.add(t); db.commit(); db.refresh(t)

        today = date.today()
        for i in range(3):  # 7 天只打了 3 次 = 42%
            db.add(CheckinRecord(
                template_id=t.id, user_id=3,
                checkin_date=today - timedelta(days=i),
                value=1,
            ))
        db.commit()

        out = _build_doctor_medication_adherence_block(
            db, user_id=3, since_date=today - timedelta(days=7))
        assert "华法林" in out
        assert "3/7" in out
        assert "⚠️" in out  # < 70% 标警

    def test_skips_non_medicine_category(self, db):
        """只抓 category='medicine', 运动打卡不应出现."""
        from app.models.checkin import CheckinTemplate
        from app.tasks.notifications import _build_doctor_medication_adherence_block

        db.add(CheckinTemplate(
            user_id=4, name="跑步", category="exercise", frequency="daily",
            is_active=True, is_archived=False,
        ))
        db.commit()

        assert _build_doctor_medication_adherence_block(
            db, user_id=4, since_date=date.today() - timedelta(days=7)
        ) == ""

    def test_skips_archived(self, db):
        from app.models.checkin import CheckinTemplate
        from app.tasks.notifications import _build_doctor_medication_adherence_block

        db.add(CheckinTemplate(
            user_id=5, name="已停药", category="medicine", frequency="daily",
            is_active=True, is_archived=True,
        ))
        db.commit()

        assert _build_doctor_medication_adherence_block(
            db, user_id=5, since_date=date.today() - timedelta(days=7)
        ) == ""


class TestJournalSummaryBlock:
    def test_empty_when_no_entries(self, db):
        from app.tasks.notifications import _build_doctor_journal_summary_block
        assert _build_doctor_journal_summary_block(
            db, user_id=10, since_date=date.today() - timedelta(days=7)
        ) == ""

    def test_counts_by_theme(self, db):
        from app.models.clinical_journal import CaseThread, ClinicalJournalEntry
        from app.tasks.notifications import _build_doctor_journal_summary_block

        thread_rhinitis = CaseThread(user_id=11, theme="rhinitis", title="鼻炎", status="active")
        thread_sleep = CaseThread(user_id=11, theme="sleep_quality", title="睡眠", status="active")
        db.add_all([thread_rhinitis, thread_sleep]); db.commit()
        db.refresh(thread_rhinitis); db.refresh(thread_sleep)

        for _ in range(3):
            db.add(ClinicalJournalEntry(
                user_id=11, case_thread_id=thread_rhinitis.id,
                assessment="鼻炎评估",
            ))
        for _ in range(2):
            db.add(ClinicalJournalEntry(
                user_id=11, case_thread_id=thread_sleep.id,
                assessment="睡眠评估",
            ))
        db.commit()

        out = _build_doctor_journal_summary_block(
            db, user_id=11, since_date=date.today() - timedelta(days=7))
        assert "5 条" in out
        assert "鼻炎×3" in out
        assert "睡眠×2" in out

    def test_highlights_priority_entry(self, db):
        from app.models.clinical_journal import CaseThread, ClinicalJournalEntry
        from app.tasks.notifications import _build_doctor_journal_summary_block

        thread = CaseThread(user_id=12, theme="liver", title="肝", status="active")
        db.add(thread); db.commit(); db.refresh(thread)

        db.add(ClinicalJournalEntry(
            user_id=12, case_thread_id=thread.id,
            assessment="正常",
        ))
        db.add(ClinicalJournalEntry(
            user_id=12, case_thread_id=thread.id,
            assessment="⚠️ ALT 升至 120", subjective="肝功能恶化迹象",
        ))
        db.commit()

        out = _build_doctor_journal_summary_block(
            db, user_id=12, since_date=date.today() - timedelta(days=7))
        assert "最需关注" in out
        assert "ALT 升至 120" in out


# ─────────────── 端到端 generate_doctor_weekly_report ───────────────


def _setup_minimal_user_with_garmin(db, user_id: int = 100):
    from app.models.user import User, GarminCredential
    from app.models.daily_health import GarminData

    user = User(
        id=user_id, username=f"u{user_id}", email=f"u{user_id}@t.c",
        hashed_password="x", name=f"测试用户{user_id}",
        is_active=True, is_approved=True,
    )
    db.add(user); db.commit(); db.refresh(user)

    cred = GarminCredential(
        user_id=user_id, garmin_email=f"u{user_id}@garmin.c",
        encrypted_password="encrypted_x",
        sync_enabled=True, credentials_valid=True,
    )
    db.add(cred)

    today = date.today()
    for i in range(7):
        db.add(GarminData(
            user_id=user_id, record_date=today - timedelta(days=i),
            steps=8000 + i * 100, resting_heart_rate=60, hrv=45,
            sleep_score=75, stress_level=30, spo2_avg=96,
        ))
    db.commit()
    return user


class TestGenerateDoctorWeeklyReport:
    def test_telegram_not_configured_skips(self, db, monkeypatch):
        """Telegram 未配置时仍然写 Journal SOAP (持久化), telegram_sent=0 但 generated>=1."""
        from app.tasks import notifications as n
        _setup_minimal_user_with_garmin(db)

        # Mock SessionLocal 返回同一个 db (测试隔离)
        monkeypatch.setattr(n, "SessionLocal", lambda: _DbCtx(db))

        with patch("app.services.notification.telegram_push.TelegramPushService") as MockSvc:
            MockSvc.return_value.configured = False
            result = n.generate_doctor_weekly_report()

        assert result.get("telegram_sent") == 0
        assert "email_sent" in result  # 新通道字段存在
        assert result.get("telegram_skip_reason") == "telegram_not_configured"
        # generated 字段反映 Journal 写入数 (至少 >= 0, 若有 Garmin 数据就 >= 1)
        assert "generated" in result

    def test_generates_and_includes_disclaimer(self, db, monkeypatch):
        """主路径: 有 garmin + 配了 telegram → 生成报告并调 send_message."""
        from app.tasks import notifications as n
        _setup_minimal_user_with_garmin(db)
        monkeypatch.setattr(n, "SessionLocal", lambda: _DbCtx(db))

        sent_messages = []

        async def fake_send(text, **kwargs):
            sent_messages.append(text)
            return {"success": True}

        with patch("app.services.notification.telegram_push.TelegramPushService") as MockSvc:
            MockSvc.return_value.configured = True
            MockSvc.return_value.send_message = fake_send
            result = n.generate_doctor_weekly_report()

        assert result.get("generated", 0) == 1
        assert len(sent_messages) == 1
        msg = sent_messages[0]
        # 必须含合规免责声明
        assert "不构成医疗建议" in msg
        # 标题改名为"周度数据摘要"
        assert "周度数据摘要" in msg
        # Garmin 数据
        assert "HRV" in msg
        # 关注点措辞非诊断性
        assert "偏低" not in msg or "参考下限" in msg

    def test_no_garmin_user_skipped(self, db, monkeypatch):
        """用户有 credential 但无 GarminData → 跳过 (无数据可报)."""
        from app.models.user import User, GarminCredential
        from app.tasks import notifications as n

        u = User(id=200, username="empty", email="e@t.c", hashed_password="x",
                 name="空", is_active=True, is_approved=True)
        db.add(u)
        db.add(GarminCredential(
            user_id=200, garmin_email="e@garmin.c", encrypted_password="x",
            sync_enabled=True, credentials_valid=True,
        ))
        db.commit()

        monkeypatch.setattr(n, "SessionLocal", lambda: _DbCtx(db))

        sent = []
        with patch("app.services.notification.telegram_push.TelegramPushService") as MockSvc:
            MockSvc.return_value.configured = True
            MockSvc.return_value.send_message = AsyncMock(side_effect=lambda t: sent.append(t))
            result = n.generate_doctor_weekly_report()

        assert result.get("generated", 0) == 0
        assert sent == []

    def test_ios_fallback_uses_push_service_so_8am_is_quiet(self, db, monkeypatch):
        """医生周报 APNs 兜底必须走 PushService, 否则 08:00 补跑会绕过静默时间。"""
        from app.models.notification import UserNotificationSetting
        from app.tasks import notifications as n

        user = _setup_minimal_user_with_garmin(db, user_id=300)
        db.add(UserNotificationSetting(
            user_id=user.id,
            enabled=True,
            ios_push_enabled=True,
            ios_device_token="ios-token",
            quiet_hours_start="22:00",
            quiet_hours_end="09:00",
        ))
        db.commit()

        monkeypatch.setattr(n, "SessionLocal", lambda: _DbCtx(db))
        sent_via_push_service = []

        async def fake_send_notification(**kwargs):
            sent_via_push_service.append(kwargs)
            return {"success": False, "reason": "delayed_for_quiet_hours"}

        with patch("app.services.notification.telegram_push.TelegramPushService") as MockTelegram, \
             patch("app.services.notification.push_service.PushService.send_notification", new=AsyncMock(side_effect=fake_send_notification)):
            MockTelegram.return_value.configured = False
            result = n.generate_doctor_weekly_report()

        assert result.get("generated", 0) == 1
        assert len(sent_via_push_service) == 1
        payload = sent_via_push_service[0]
        assert payload["user_id"] == user.id
        assert payload["notification_type"] == "doctor_weekly_summary"
        assert payload["severity"] == "info"
        assert payload["data"]["type"] == "doctor_weekly_summary"


class _DbCtx:
    """测试用的 Session context manager 包装, 让 `with SessionLocal() as db:` 可用."""
    def __init__(self, db): self.db = db
    def __enter__(self): return self.db
    def __exit__(self, *args): pass
