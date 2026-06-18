"""spo2_samples 逐分钟血氧的 DB 层幂等兜底 — 唯一约束 uq_spo2_user_date_time_source.

背景 (safety review, 2026-06-17): spo2_samples 此前只有非唯一索引。HealthKit
(_save_spo2_samples) 与 garmin 采集器 (_sync_spo2_samples) 都靠「按 (user,date,source) 删后
插」+「同源导入串行」假设保幂等。同一 (user, source) 两个**并发**导入会双删双插 → 同分钟落 2 行
→ 虚高 spo2_below_90_pct / spo2_odi → 污染 vitals.spo2_min_nocturnal_severe 的「持续负荷」
佐证 (单点伪影会被误当真低氧拉 CRITICAL)。修复 = (user_id, record_date, sample_time, source)
唯一约束 + healthkit 路径 commit 撞约束回滚视为幂等成功。

⚠️ 并发限界 (诚实标注, 见 feedback_adherence_writeback_idempotency_db_guard):
conftest 的 in-memory SQLite + StaticPool 是**单连接, 测不了真多线程并发**。本文件覆盖的是
「约束本身存在且生效」+「应用层撞约束时的收敛行为」，真竞态 (两连接交错 delete/insert) 的
正确性靠生产 PostgreSQL 的唯一索引语义推演 —— DB 永不接受第二条重复 (date,minute,source) 行,
无论交错顺序如何。下面的测试**不假装**覆盖了多线程竞态。
"""
from datetime import date, datetime, time

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.daily_health import SpO2Sample
from app.services.device_adapters.healthkit import HealthKitAdapter
from tests.conftest import create_authenticated_user


def _row(user_id, minute, source="apple-watch", value=95, day=date(2026, 6, 15)):
    hh, mm = divmod(minute, 60)
    return SpO2Sample(
        user_id=user_id,
        record_date=day,
        sample_time=time(hh % 24, mm),
        spo2_value=value,
        epoch_ms=minute * 60_000,
        source=source,
    )


def test_unique_constraint_blocks_duplicate_minute_same_source(db):
    """对抗用例: 同 (user, date, minute, source) 第二行被 DB 拒绝 (IntegrityError)。

    这正是并发双插会撞上的约束 —— 没有它, 重复分钟行会污染 ODI / below-90% 佐证。
    若回退模型上的 UniqueConstraint, 本测试立即变红 (第二行静默落库)。
    """
    user, _ = create_authenticated_user(db)
    db.add(_row(user.id, 130))
    db.commit()

    db.add(_row(user.id, 130, value=82))  # 同 user/date/minute/source, 不同值
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    rows = db.query(SpO2Sample).filter(SpO2Sample.user_id == user.id).all()
    assert len(rows) == 1
    assert rows[0].spo2_value == 95  # 第一条保留, 第二条被约束挡掉


def test_unique_constraint_allows_same_minute_different_source(db):
    """约束含 source: 多设备同日同分钟 (apple-watch vs ringconn vs garmin) 是不同槽, 正常并存。"""
    user, _ = create_authenticated_user(db)
    db.add(_row(user.id, 130, source="apple-watch", value=95))
    db.add(_row(user.id, 130, source="ringconn", value=96))
    db.add(_row(user.id, 130, source="garmin", value=80))
    db.commit()  # 三源同分钟, 不撞约束

    rows = db.query(SpO2Sample).filter(SpO2Sample.user_id == user.id).all()
    assert len(rows) == 3
    assert {r.source for r in rows} == {"apple-watch", "ringconn", "garmin"}


def test_save_spo2_converges_when_constraint_collision(db):
    """模拟并发收敛: 既有行已占住目标分钟槽 (模拟「并发写者先提交」), 再走删后插路径。

    单连接下 _save_spo2_samples 的 DELETE 会先清掉同 (user,date,source) 既有行, 故正常路径
    不会撞约束 —— 这验证「删后插」在串行下幂等不增行 (delete 让位给重插)。真并发下若 DELETE
    与另一连接的 INSERT 交错导致重插撞约束, commit 的 IntegrityError 分支回滚, 既有行保留。
    """
    user, _ = create_authenticated_user(db)
    # 预置一夜数据 (模拟首次导入已落库)
    record = {
        "record_date": "2026-06-15",
        "data_source": "apple-watch",
        "spo2_samples": [
            {"value": 96, "measured_at": "2026-06-15T02:00:00+08:00"},
            {"value": 95, "measured_at": "2026-06-15T02:01:00+08:00"},
            {"value": 94, "measured_at": "2026-06-15T02:02:00+08:00"},
        ],
    }
    n1 = HealthKitAdapter._save_spo2_samples(db, user.id, record, "apple-watch")
    assert n1 == 3

    # 重导同序列 (串行重试) → 删后插, 仍 3 条, 无重复分钟
    n2 = HealthKitAdapter._save_spo2_samples(db, user.id, record, "apple-watch")
    assert n2 == 3

    rows = db.query(SpO2Sample).filter(
        SpO2Sample.user_id == user.id, SpO2Sample.source == "apple-watch"
    ).all()
    assert len(rows) == 3  # 不是 6 — 唯一约束 + 删后插共同保证无重复分钟
    minute_keys = {(r.record_date, r.sample_time, r.source) for r in rows}
    assert len(minute_keys) == 3  # 每个分钟槽至多一行


def test_integrity_error_on_commit_is_swallowed_as_idempotent(db, monkeypatch):
    """对抗用例: 真并发下 commit 撞唯一约束 → IntegrityError 被回滚吞为幂等成功, 不崩整批。

    单连接测不出真竞态, 这里**注入** commit 抛 IntegrityError 来验证修复分支: 既有行不被
    破坏, 方法返回声称的条数 (内容等价的并发写者已提交)。若回退 commit 的 try/except,
    本测试立即变红 (IntegrityError 冒泡崩 batch_save 整条 record)。
    """
    user, _ = create_authenticated_user(db)
    # 先用正常路径落一夜 (代表「并发写者已先提交」的等价数据)
    record = {
        "record_date": "2026-06-15",
        "data_source": "ringconn",
        "spo2_samples": [
            {"value": 96, "measured_at": "2026-06-15T03:00:00+08:00"},
            {"value": 90, "measured_at": "2026-06-15T03:01:00+08:00"},
        ],
    }
    assert HealthKitAdapter._save_spo2_samples(db, user.id, record, "ringconn") == 2

    # 注入: 让下一次 commit 抛 IntegrityError (模拟并发双插撞约束)
    real_commit = db.commit
    state = {"fired": False}

    def flaky_commit():
        if not state["fired"]:
            state["fired"] = True
            raise IntegrityError("simulated concurrent collision", None, Exception())
        return real_commit()

    monkeypatch.setattr(db, "commit", flaky_commit)

    # 不应抛 —— IntegrityError 分支吞掉并回滚
    n = HealthKitAdapter._save_spo2_samples(db, user.id, record, "ringconn")
    assert n == 2  # 声称的条数 (并发等价写者已提交)

    monkeypatch.setattr(db, "commit", real_commit)
    # 既有数据完好, 没有半截/重复行
    rows = db.query(SpO2Sample).filter(
        SpO2Sample.user_id == user.id, SpO2Sample.source == "ringconn"
    ).order_by(SpO2Sample.epoch_ms).all()
    assert [r.spo2_value for r in rows] == [96, 90]
