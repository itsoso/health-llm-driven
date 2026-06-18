"""HealthKit 导入: 整夜逐分钟血氧序列 (RingConn / Apple Watch) → spo2_samples 表.

逐分钟 SpO2 是夜间低氧"持续负荷"(ODI / below-90% 时长占比) 的唯一数据源 —— 日聚合单点
spo2_min 算不出, 而 vitals.spo2_min_nocturnal_severe 需要它们做佐证才拉 CRITICAL
(否则降级 INFO, 2026-06-17 裁决)。Garmin 血氧已整源剔除, 在此之前多设备用户的逐秒 SpO2
没有任何入口 → 夜间低氧规则只能靠日聚合单点最低值判断。本路径补齐缺口。

契约 (给 mobile 段定死):
  - import record.spo2_samples: [{value (0-100 百分数), measured_at (ISO)}]
  - response.spo2_sample_imported_count
  - 落库 source = data_source (apple-watch / ringconn / …, 非 garmin → 不被夜间低氧规则剔除)
"""
from datetime import date, datetime

from tests.conftest import create_authenticated_user


def _post(client, token, records):
    return client.post(
        "/api/v1/devices/healthkit/import",
        json={"records": records},
        headers={"Authorization": f"Bearer {token}"},
    )


def _night_samples(values, day="2026-06-15", base_minute=0):
    """构造 [{value, measured_at}]; measured_at 带 +08:00 (CST) 偏移, 逐分钟递增。"""
    out = []
    for i, v in enumerate(values):
        minute = base_minute + i
        hh, mm = divmod(minute, 60)
        out.append({
            "value": v,
            "measured_at": f"{day}T{2 + hh:02d}:{mm:02d}:00+08:00",
        })
    return out


def test_spo2_samples_persist_with_source(client, db):
    """整夜逐分钟血氧落 spo2_samples 表, source=data_source, 计数正确。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-15",
        "data_source": "apple-watch",
        "spo2_samples": _night_samples([97, 96, 95, 94, 96]),
    }]
    resp = _post(client, token, records)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["spo2_sample_imported_count"] == 5
    assert body["errors"] == []

    from app.models.daily_health import SpO2Sample
    rows = (
        db.query(SpO2Sample)
        .filter(SpO2Sample.user_id == user.id, SpO2Sample.record_date == date(2026, 6, 15))
        .order_by(SpO2Sample.epoch_ms)
        .all()
    )
    assert len(rows) == 5
    assert all(r.source == "apple-watch" for r in rows)
    assert [r.spo2_value for r in rows] == [97, 96, 95, 94, 96]
    # value 是 0-100 百分数已由 mobile ×100; 后端按整数存
    assert all(isinstance(r.spo2_value, int) for r in rows)


def test_spo2_samples_idempotent_per_source(client, db):
    """同 (user, date, source) 重导 → 删后插, 不增行 (幂等)。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-15",
        "data_source": "ringconn",
        "spo2_samples": _night_samples([96, 95, 94]),
    }]
    r1 = _post(client, token, records)
    assert r1.json()["spo2_sample_imported_count"] == 3
    r2 = _post(client, token, records)
    assert r2.json()["spo2_sample_imported_count"] == 3  # 删后插, 仍写 3 条

    from app.models.daily_health import SpO2Sample
    rows = db.query(SpO2Sample).filter(SpO2Sample.user_id == user.id).all()
    assert len(rows) == 3  # 不是 6 — 重导不增行


def test_spo2_per_source_delete_does_not_wipe_other_source(client, db):
    """删除按 (user, date, source) 缩窄 — apple-watch 重导不抹掉同日 garmin / ringconn 样本。"""
    user, token = create_authenticated_user(db)

    # 先直接塞一条同日 garmin 样本 (模拟 Garmin 采集器已写)
    from app.models.daily_health import SpO2Sample
    db.add(SpO2Sample(
        user_id=user.id, record_date=date(2026, 6, 15),
        sample_time=datetime(2026, 6, 15, 3, 0).time(), epoch_ms=1, spo2_value=80, source="garmin",
    ))
    db.commit()

    # apple-watch 导入两次
    records = [{
        "record_date": "2026-06-15", "data_source": "apple-watch",
        "spo2_samples": _night_samples([96, 95]),
    }]
    _post(client, token, records)
    _post(client, token, records)  # 第二次只删 apple-watch 自己的, 不碰 garmin

    garmin_rows = db.query(SpO2Sample).filter(
        SpO2Sample.user_id == user.id, SpO2Sample.source == "garmin",
    ).all()
    aw_rows = db.query(SpO2Sample).filter(
        SpO2Sample.user_id == user.id, SpO2Sample.source == "apple-watch",
    ).all()
    assert len(garmin_rows) == 1   # garmin 样本完好
    assert len(aw_rows) == 2       # apple-watch 幂等, 不重复


def test_imported_samples_feed_odi_below90_and_recover_critical(client, db):
    """端到端: 导入持续低氧序列 → builder 算出 below-90% 佐证 → 夜间低氧规则恢复 CRITICAL。

    这是本功能的核心价值: 没有逐分钟序列时 spo2_min_nocturnal_severe 只能降级 INFO
    (单点伪影无法证伪); 有了 apple-watch 逐分钟数据, 持续负荷被佐证 → 真低氧拉 CRITICAL。
    """
    user, token = create_authenticated_user(db)

    # 一夜 ~120 分钟; 5 个点 <90 (含一个 82 的明显低值) → below_90_pct ≈ 4.2% ≥ 1.0 佐证门槛
    values = [96] * 115 + [89, 88, 85, 82, 87]
    records = [{
        "record_date": "2026-06-15", "data_source": "apple-watch",
        "spo2_samples": _night_samples(values),
    }]
    resp = _post(client, token, records)
    assert resp.status_code == 200, resp.text
    assert resp.json()["spo2_sample_imported_count"] == len(values)

    # builder 主路径 (有非 garmin SpO2Sample) 计算佐证指标
    from app.twin.builder import _fill_spo2_overnight
    from app.twin.schema import HealthTwin, TwinMeta
    twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
    _fill_spo2_overnight(db, user.id, twin, set())

    assert twin.physiological.spo2_min_overnight == 82
    assert twin.physiological.spo2_below_90_pct is not None
    assert twin.physiological.spo2_below_90_pct >= 1.0  # 持续负荷佐证存在

    # 夜间低氧规则: 有佐证 + min<85 → CRITICAL (不再降级 INFO)
    from app.agents.safety_guardian.rules.vitals import spo2_min_nocturnal_severe
    from app.agents.safety_guardian.schema import Severity
    alert = spo2_min_nocturnal_severe(twin)
    assert alert is not None
    assert alert.severity == Severity.CRITICAL
    assert alert.requires_medical_attention is True


def test_garmin_app_spo2_samples_excluded_from_nocturnal_rule(client, db):
    """对抗用例: garmin-app (Garmin→HealthKit 镜像) 的逐分钟血氧是同一块腕式反射传感器,
    与 'garmin' 同样不准 —— 必须被夜间低氧规则剔除, 不得经 spo2_samples 表灌进 CRITICAL。

    若回退 EXCLUDED_SOURCES 里 'garmin-app' 的剔除, 本测试立即变红 (假性低值会拉 CRITICAL)。
    """
    user, token = create_authenticated_user(db)
    # 与 test_imported_samples_feed_odi_below90 相同的"持续低氧"序列, 但来源是 garmin-app
    values = [96] * 115 + [89, 88, 85, 82, 87]
    resp = _post(client, token, [{
        "record_date": "2026-06-15", "data_source": "garmin-app",
        "spo2_samples": _night_samples(values),
    }])
    assert resp.status_code == 200, resp.text
    assert resp.json()["spo2_sample_imported_count"] == len(values)  # 仍落库 (与 garmin 直采一致)

    # 但 builder 读侧剔除 garmin-app → 佐证指标不产出 → 规则不被假性低值触发
    from app.twin.builder import _fill_spo2_overnight
    from app.twin.schema import HealthTwin, TwinMeta
    twin = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.utcnow()))
    _fill_spo2_overnight(db, user.id, twin, set())
    assert twin.physiological.spo2_min_overnight is None
    assert twin.physiological.spo2_below_90_pct is None
    assert twin.physiological.spo2_odi is None

    from app.agents.safety_guardian.rules.vitals import spo2_min_nocturnal_severe
    assert spo2_min_nocturnal_severe(twin) is None  # 无数据 → 不告警 (不是假性 CRITICAL)


def test_bad_samples_tolerated_not_crash_batch(client, db):
    """坏样本 (缺 value / 缺 measured_at / 越界值) 跳过, 不崩整批; 合法点仍落库。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-15",
        "data_source": "apple-watch",
        "spo2_samples": [
            {"value": 96, "measured_at": "2026-06-15T02:00:00+08:00"},
            {"value": None, "measured_at": "2026-06-15T02:01:00+08:00"},   # 缺值 → 跳过
            {"value": 95},                                                  # 缺 measured_at → 跳过
            {"value": 130, "measured_at": "2026-06-15T02:03:00+08:00"},     # >100 越界 → 跳过
            {"value": 94.0, "measured_at": "2026-06-15T02:04:00+08:00"},    # float → 取整 94
        ],
    }]
    resp = _post(client, token, records)
    assert resp.status_code == 200, resp.text
    assert resp.json()["spo2_sample_imported_count"] == 2  # 只有两条合法
    assert not [e for e in resp.json()["errors"] if e["kind"] == "spo2"]

    from app.models.daily_health import SpO2Sample
    rows = db.query(SpO2Sample).filter(SpO2Sample.user_id == user.id).order_by(SpO2Sample.epoch_ms).all()
    assert [r.spo2_value for r in rows] == [96, 94]


def test_spo2_independent_of_daily_aggregate(client, db):
    """并行 try: 日聚合正常 + spo2 序列正常, 互不影响, 各自计数。"""
    user, token = create_authenticated_user(db)
    records = [{
        "record_date": "2026-06-15",
        "data_source": "apple-watch",
        "steps": 5000,
        "spo2_samples": _night_samples([96, 95, 94]),
    }]
    resp = _post(client, token, records)
    body = resp.json()
    assert body["imported_count"] == 1            # 日聚合
    assert body["spo2_sample_imported_count"] == 3  # 逐分钟序列
    assert body["errors"] == []


def test_response_shape_includes_spo2_count(client, db):
    """response 始终含 spo2_sample_imported_count (即使无 spo2 序列)。"""
    user, token = create_authenticated_user(db)
    resp = _post(client, token, [{"record_date": "2026-06-16", "data_source": "apple-watch", "steps": 100}])
    assert resp.status_code == 200, resp.text
    assert resp.json()["spo2_sample_imported_count"] == 0


def test_user_isolation_spo2_samples(client, db):
    """用户隔离: A 的血氧样本不进 B。"""
    user_a, token_a = create_authenticated_user(db)
    user_b, _ = create_authenticated_user(db)
    _post(client, token_a, [{
        "record_date": "2026-06-15", "data_source": "apple-watch",
        "spo2_samples": _night_samples([96, 95]),
    }])

    from app.models.daily_health import SpO2Sample
    assert db.query(SpO2Sample).filter(SpO2Sample.user_id == user_a.id).count() == 2
    assert db.query(SpO2Sample).filter(SpO2Sample.user_id == user_b.id).count() == 0
