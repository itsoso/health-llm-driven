"""卧室环境 × 睡眠结果关联分析 (设计文档 §9 / Phase 4 Outcome Proof).

覆盖:
- correlate_env_sleep: 分组对比 (高 CO2 vs 低 CO2 夜的深睡均值)
- N 不足 → insufficient_data (诚实)
- bedroom_intervention_effect: 接 effect_estimator, 有/无干预夜
- 无数据 → 降级返回纯先验 (N=0), 不抛
- DB 异常降级不抛
- 隐私守门: 分析产出不进 twin_to_prompt_blob, analyzer 不被 formatter 引用
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.daily_health import GarminData
from app.models.user import User
from app.services import bedroom_environment_service as svc
from app.services import bedroom_outcome_analyzer as analyzer


def _make_user(db) -> User:
    u = User(
        username=f"bout_{uuid.uuid4().hex[:8]}",
        email=f"bout_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="bedout",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _add_night(db, user_id: int, wake_dt: datetime, co2_max: float, deep_min: int):
    """造一夜数据: 起床日 wake_dt.date() 的睡眠 + 前一夜 22:00 的卧室快照 (co2_max)."""
    # 前一夜 22:00 的快照 → _sleep_night_key 归到 wake_dt.date().
    captured = (wake_dt - timedelta(days=1)).replace(
        hour=22, minute=0, second=0, microsecond=0
    )
    svc.record_snapshot(
        db,
        user_id,
        {
            "co2_ppm": co2_max,
            "temperature_c": 22.0,
            "humidity_percent": 50.0,
            "captured_at": captured.isoformat(),
        },
    )
    g = GarminData(
        user_id=user_id,
        record_date=wake_dt.date(),
        sleep_score=70,
        deep_sleep_duration=deep_min,
        awake_duration=20,
    )
    db.add(g)
    db.commit()


# ─────────────────────────── correlate ───────────────────────────

def test_correlate_groups(db):
    u = _make_user(db)
    base = datetime.now(timezone.utc) - timedelta(days=1)
    # 3 高 CO2 夜 (深睡少) + 3 低 CO2 夜 (深睡多), 分散在不同日期.
    for i in range(3):
        _add_night(db, u.id, base - timedelta(days=i), co2_max=1400, deep_min=50)
    for i in range(3, 6):
        _add_night(db, u.id, base - timedelta(days=i), co2_max=700, deep_min=90)

    res = analyzer.correlate_env_sleep(db, u.id, days=14)
    assert res["status"] == "ok", res
    assert res["high_co2_nights"] == 3
    assert res["low_co2_nights"] == 3
    m = res["metrics"]["sleep_deep_minutes"]
    assert m["low_co2_mean"] == 90.0
    assert m["high_co2_mean"] == 50.0
    # 低 CO2 夜深睡更多 → diff > 0.
    assert m["diff_low_minus_high"] == 40.0
    assert m["direction"] == "up"


def test_correlate_insufficient(db):
    u = _make_user(db)
    base = datetime.now(timezone.utc) - timedelta(days=1)
    # 只有 2 夜 → 不足 2*MIN_NIGHTS_PER_GROUP.
    _add_night(db, u.id, base, co2_max=1400, deep_min=50)
    _add_night(db, u.id, base - timedelta(days=1), co2_max=700, deep_min=90)
    res = analyzer.correlate_env_sleep(db, u.id, days=14)
    assert res["status"] == "insufficient_data"


def test_correlate_groups_too_small(db):
    u = _make_user(db)
    base = datetime.now(timezone.utc) - timedelta(days=1)
    # 6 夜全是高 CO2 → 低 CO2 组为空.
    for i in range(6):
        _add_night(db, u.id, base - timedelta(days=i), co2_max=1400, deep_min=50)
    res = analyzer.correlate_env_sleep(db, u.id, days=14)
    assert res["status"] == "insufficient_data"
    assert res["reason"] == "groups_too_small"


# ─────────────────── intervention effect (接 Phase 1) ───────────────────

def test_intervention_effect_with_data(db):
    u = _make_user(db)
    base = datetime.now(timezone.utc) - timedelta(days=1)
    # baseline (高 CO2) 夜深睡 ~50; treated (低 CO2) 夜深睡 ~90 → 正 delta.
    for i in range(4):
        _add_night(db, u.id, base - timedelta(days=i), co2_max=1400, deep_min=50)
    for i in range(4, 8):
        _add_night(db, u.id, base - timedelta(days=i), co2_max=700, deep_min=90)

    res = analyzer.bedroom_intervention_effect(db, u.id, metric_code="sleep_deep_minutes", days=28)
    assert res["intervention"] == "low_co2_bedroom_environment"
    assert res["n_baseline_nights"] == 4
    assert res["n_treated_nights"] == 4
    assert res["baseline_mean"] == 50.0
    assert res["metric_code"] == "sleep_deep_minutes"
    assert res["direction"] == "up"
    # delta ≈ +40 (90-50), effect 应为正.
    assert res["effect"] > 0
    assert res["n_observations"] == 4


def test_intervention_effect_no_data_falls_back_to_prior(db):
    """无任何夜数据 → 纯先验 (N=0), 不抛."""
    u = _make_user(db)
    res = analyzer.bedroom_intervention_effect(db, u.id, metric_code="sleep_deep_minutes")
    assert res["n_observations"] == 0
    assert res["n_treated_nights"] == 0
    assert res["baseline_mean"] is None
    # 先验: is_effective 应为 False (CI 跨 0).
    assert res["is_effective"] is False


def test_correlate_db_error_degrades(db, monkeypatch):
    """DB 异常 → insufficient_data, 不抛."""
    u = _make_user(db)

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(analyzer, "_aggregate_nights", boom)
    res = analyzer.correlate_env_sleep(db, u.id)
    assert res["status"] == "insufficient_data"
    assert res["reason"] == "load_failed"


def test_intervention_db_error_degrades(db, monkeypatch):
    """DB 异常 → 仍返回先验估计, 不抛."""
    u = _make_user(db)

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(analyzer, "_aggregate_nights", boom)
    res = analyzer.bedroom_intervention_effect(db, u.id)
    assert res["n_observations"] == 0


# ─────────────────────────── 隐私守门 ───────────────────────────

def test_outcome_not_in_llm_prompt_blob():
    """卧室 outcome 分析产出绝不进通用 LLM 上下文 (设计文档 §11 硬约束).

    反向护栏: formatter 不应 import/引用 bedroom_outcome_analyzer.
    """
    import app.twin.formatter as fmt

    src = open(fmt.__file__, encoding="utf-8").read().lower()
    assert "bedroom_outcome" not in src
    assert "bedroom_intervention" not in src
    assert "correlate_env_sleep" not in src


def test_outcome_module_does_not_feed_prompt_blob():
    """analyzer 自身不调用任何 LLM prompt-blob 注入 (本 PR 不接 LLM 上下文).

    扫描非注释代码行 (docstring/注释里允许写"绝不进 LLM"的说明).
    """
    import app.services.bedroom_outcome_analyzer as mod

    code_lines = []
    for line in open(mod.__file__, encoding="utf-8"):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        code_lines.append(line.lower())
    code = "".join(code_lines)
    # 不应调用 prompt-blob 注入函数 / import formatter (call/import 语法, 不含说明文字).
    assert "prompt_blob(" not in code
    assert "twin_to_prompt_blob(" not in code
    assert "import app.twin.formatter" not in code
    assert "from app.twin.formatter" not in code
    assert "from app.twin import formatter" not in code
