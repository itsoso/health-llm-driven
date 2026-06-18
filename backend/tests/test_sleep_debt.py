"""get_sleep_debt: severe 分支建议须按年龄段推荐时长，而非硬编码 8 小时。"""
import uuid
from datetime import date, timedelta

from app.models.user import User
from app.models.daily_health import GarminData
from app.services.sleep_analysis_service import SleepAnalysisService, _get_norm, NSF_RECS


def _make_user(db, age: int) -> User:
    today = date.today()
    user = User(
        username=f"sleep_{uuid.uuid4().hex[:6]}",
        email=f"sleep_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="sleep debt test",
        is_active=True,
        is_approved=True,
        birth_date=date(today.year - age, 1, 1),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_severe_recovery_plan_uses_age_band_for_older_user(db):
    """66+ 年龄段(NSF 推荐 7-8h)出现严重睡眠债务时,
    severe 建议应引用该年龄段推荐范围,不应硬编码 '至少8小时'。"""
    user = _make_user(db, age=70)
    rec_lo, rec_hi = _get_norm(70, NSF_RECS)
    assert (rec_lo, rec_hi) == (7, 8)  # 非成人段 — 与硬编码 8h 不同

    # 14 晚每晚仅睡 4h → 累积赤字远超 10h → severe
    today = date.today()
    for i in range(14):
        db.add(GarminData(
            user_id=user.id,
            record_date=today - timedelta(days=i + 1),
            total_sleep_duration=4 * 60,
            data_source="garmin",
        ))
    db.commit()

    out = SleepAnalysisService().get_sleep_debt(db, user.id, days=14)

    assert out["status"] == "success"
    assert out["debt_severity"] == "severe"
    plan = out["recovery_plan"]
    assert "至少8小时" not in plan          # 旧的硬编码措辞已移除
    assert "7-8小时" in plan                # 引用 66+ 年龄段推荐范围
