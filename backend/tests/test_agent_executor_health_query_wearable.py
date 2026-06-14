"""health_query 可穿戴维度 (activity/heart_rate/hrv/...) 读 GarminData 的迁移测试.

读层归一 (docs/design-canonical-read-layer.md step 2): 可穿戴 daily 维度过去走
/garmin-analysis/me/xxx HTTP + _api_get 截断, 与 Twin 的读路径 (GarminData +
device_source_priority 多源合并) 分叉. 现改为直读 canonical 层 (health_read).

核心断言: health_query 可穿戴维度的输出 ⊇ Twin physiological 分区对应关键指标值,
即"两条读路径同源一致" —— 防止迁移引入偏差.
"""
import asyncio
import uuid
from datetime import date, timedelta

import pytest

from app.models.daily_health import GarminData
from app.models.user import User
from app.services.agent_executor import AgentExecutor
from app.services import health_read
from app.twin import build_twin


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_user(db) -> User:
    user = User(
        username=f"wq_{uuid.uuid4().hex[:6]}",
        email=f"wq_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="Wearable Test User",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _garmin(user_id, record_date, **kw):
    return GarminData(user_id=user_id, record_date=record_date, **kw)


def _exec(db, user_id, dim="activity", **args):
    ex = AgentExecutor(db)
    ex._current_user_id = user_id
    return _run(ex._exec_health_query("http://x", {}, {"dimension": dim, **args}))


def test_wearable_output_superset_of_twin_physiological(db):
    """迁移后同源一致: health_query 可穿戴输出 ⊇ Twin physiological 关键指标值."""
    user = _make_user(db)
    today = date.today()
    db.add(_garmin(
        user.id, today,
        steps=8421,
        resting_heart_rate=54,
        hrv=46.0,
        sleep_score=82,
        stress_level=33,
        body_battery_current=67,
        spo2_avg=96.0,
        data_source="garmin",
    ))
    db.commit()

    twin = build_twin(db, user_id=user.id, use_cache=False)
    p = twin.physiological
    # Twin 确实读到了 (前提自检)
    assert p.steps_today == 8421
    assert p.resting_hr == 54
    assert p.hrv_latest == 46.0
    assert p.sleep_score_latest == 82

    out = _exec(db, user.id, dim="activity")
    # health_query 输出 ⊇ Twin physiological 的关键指标值 (同源)
    assert "8421" in out          # steps
    assert "54" in out            # resting_hr
    assert "46" in out            # hrv
    assert "82" in out            # sleep_score
    assert str(today.isoformat()) in out


def test_wearable_multi_day_not_truncated(db):
    """多天可穿戴数据不被截断 (旧 _api_get 截 3000 字符的 bug)."""
    user = _make_user(db)
    today = date.today()
    for i in range(20):
        db.add(_garmin(
            user.id, today - timedelta(days=i),
            steps=1000 + i,  # 唯一可识别值
            resting_heart_rate=50 + i,
            data_source="garmin",
        ))
    db.commit()

    out = _exec(db, user.id, dim="activity", days=30)
    # 全部 20 天都在 (尤其早于第 10 天的, 旧逻辑可能丢)
    for i in range(20):
        assert str(1000 + i) in out


def test_wearable_multi_source_priority_matches_twin(db):
    """同日多源 (garmin + apple-watch + ringconn) 按 device_source_priority 合并,
    与 Twin 同一套优先级: steps 腕表优先, hrv/spo2 戒指优先, resting_hr garmin 优先."""
    user = _make_user(db)
    today = date.today()
    # garmin: steps 弱, hrv 有值, rhr 有值
    db.add(_garmin(user.id, today, steps=3000, hrv=40.0, resting_heart_rate=55,
                   spo2_avg=94.0, data_source="garmin"))
    # apple-watch: steps 更准 (腕表优先)
    db.add(_garmin(user.id, today, steps=9999, data_source="apple-watch"))
    # ringconn: hrv / spo2 更准 (戒指优先)
    db.add(_garmin(user.id, today, hrv=52.0, spo2_avg=97.0, data_source="ringconn"))
    db.commit()

    twin = build_twin(db, user_id=user.id, use_cache=False)
    p = twin.physiological
    # Twin 合并结果: steps=apple-watch, hrv=ringconn, rhr=garmin
    assert p.steps_today == 9999
    assert p.hrv_latest == 52.0
    assert p.resting_hr == 55

    out = _exec(db, user.id, dim="activity")
    # health_query 用同一套优先级 → 同样的中标值
    assert "9999" in out      # steps from apple-watch
    assert "52" in out        # hrv from ringconn
    assert "55" in out        # resting_hr from garmin
    assert "3000" not in out  # garmin 的弱 steps 被腕表覆盖, 不应出现


def test_wearable_user_isolation(db):
    user1 = _make_user(db)
    user2 = _make_user(db)
    today = date.today()
    db.add(_garmin(user1.id, today, steps=1111, data_source="garmin"))
    db.add(_garmin(user2.id, today, steps=2222, data_source="garmin"))
    db.commit()

    out = _exec(db, user1.id, dim="activity")
    assert "1111" in out
    assert "2222" not in out


def test_wearable_no_data_friendly_message(db):
    user = _make_user(db)
    out = _exec(db, user.id, dim="activity")
    assert "未找到" in out
    # 不是裸异常 / 空串
    assert "Error" not in out


def test_wearable_dims_all_route_to_canonical(db):
    """heart_rate / hrv / body_battery / stress / activity 均走 canonical 同源读层."""
    user = _make_user(db)
    today = date.today()
    db.add(_garmin(user.id, today, steps=5000, hrv=48.0, resting_heart_rate=58,
                   body_battery_current=70, stress_level=25, data_source="garmin"))
    db.commit()
    for dim in ["activity", "heart_rate", "hrv", "body_battery", "stress"]:
        out = _exec(db, user.id, dim=dim)
        # 同一份合并数据, 任一别名都拿到逐日摘要 (不是空 / HTTP 错误)
        assert today.isoformat() in out, f"dim={dim} 未走 canonical"
        assert "5000" in out, f"dim={dim} 缺 steps"


def test_canonical_read_returns_none_for_unmigrated(db):
    """未迁维度 (genetic/diet/weight/...) canonical_read 返回 None → 调用方回退旧路径."""
    assert health_read.canonical_read(db, 1, "genetic") is None
    assert health_read.canonical_read(db, 1, "diet") is None
    assert health_read.canonical_read(db, 1, "weight") is None
    assert health_read.canonical_read(db, 1, "spo2") is None
    # 已迁维度返回非 None (字符串)
    assert health_read.canonical_read(db, 999, "medical_exam") is not None
    assert health_read.canonical_read(db, 999, "activity") is not None
