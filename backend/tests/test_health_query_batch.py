"""health_query_batch — 声明式批查询执行器测试 (Slice 1).

覆盖:
  1. 多条子查询各维度正例 (mock 数据面)
  2. 未知 dimension → fail-loud 且列合法值
  3. 超 6 条 → fail-loud
  4. compare diff / ratio 正确
  5. 空数据子查询 → value null + note, 整体不失败
  6. 别名维度 (time_range / 中文维度别名) 经 normalize 归一成功
  另加: agg 数学、未知 agg fail-loud、fetch 抛错显式挂账 (非静默)、
        build_wearable_series 真 DB 序列 (证明数据面适配非 fake)。

fail-loud / 只读契约见 services/health_query_batch.py 顶部 docstring。
"""

import json
from datetime import date, timedelta

import pytest

from app.models.daily_health import GarminData
from app.models.user import User
from app.services import health_query_batch as hqb


# ── mock 数据面: (dimension, days) → BatchFetchResult ────────────────────────
def make_fetch(table):
    """table: dict[(dimension, days) | dimension] -> BatchFetchResult。"""

    async def _fetch(dimension, days):
        if (dimension, days) in table:
            return table[(dimension, days)]
        if dimension in table:
            return table[dimension]
        return hqb.BatchFetchResult(
            series=[], raw=f"{dimension}: no data", aggregatable=True
        )

    return _fetch


# 用真 schema 维度全集, 让 fail-loud 报错里的合法值清单是真实维度。
VALID = hqb.known_dimensions()


def test_batch_tool_description_does_not_claim_unrepresentable_calendar_windows():
    from app.services.tool_schema_registry import HEALTH_TOOLS

    tool = next(
        item
        for item in HEALTH_TOOLS
        if item["function"]["name"] == "health_query_batch"
    )
    description = tool["function"]["description"]

    assert "这周和上周" not in description
    assert "任意日期区间" in description


def test_single_query_tool_description_does_not_claim_calendar_days_aliases():
    from app.services.tool_schema_registry import HEALTH_TOOLS

    tool = next(
        item for item in HEALTH_TOOLS if item["function"]["name"] == "health_query"
    )
    description = tool["function"]["description"]
    days_description = tool["function"]["parameters"]["properties"]["days"][
        "description"
    ]

    assert '问"昨天" → days=1' not in description
    assert "不能表示昨天" in description
    assert "不能表达昨天/上周/去年" in days_description


def test_query_schema_describes_only_rolling_upload_and_batch_windows():
    from app.services.tool_schema_registry import HEALTH_TOOLS

    single = next(
        item for item in HEALTH_TOOLS if item["function"]["name"] == "health_query"
    )
    batch = next(
        item
        for item in HEALTH_TOOLS
        if item["function"]["name"] == "health_query_batch"
    )
    uploaded_days = single["function"]["parameters"]["properties"]["uploaded_days"][
        "description"
    ]
    single_properties = single["function"]["parameters"]["properties"]
    batch_description = batch["function"]["description"]

    assert "昨天上传=1" not in uploaded_days
    assert "最近 N×24 小时" in uploaded_days
    assert "uploaded_since" not in single_properties
    assert "这周" not in batch_description
    assert "本周" not in batch_description


# ── 1. 多维度正例 ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_multi_metric_positive():
    table = {
        ("hrv", 7): hqb.BatchFetchResult(
            series=[50, 60, 70], unit="ms", aggregatable=True
        ),
        ("sleep", 7): hqb.BatchFetchResult(
            series=[70, 72, 80], unit="", aggregatable=True
        ),
        ("activity", 7): hqb.BatchFetchResult(
            series=[8000, 9000, 10000], unit="", aggregatable=True
        ),
    }
    plan = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "avg"},
            {"dimension": "sleep", "days": 7, "agg": "trend"},
            {"dimension": "activity", "days": 7, "agg": "max"},
        ]
    }
    out = await hqb.execute_batch(plan, make_fetch(table), valid_dimensions=VALID)
    data = json.loads(out)
    q = data["queries"]
    assert len(q) == 3
    assert q[0] == {
        "dimension": "hrv",
        "days": 7,
        "agg": "avg",
        "value": 60,
        "unit": "ms",
        "n": 3,
    }
    assert q[1]["agg"] == "trend" and q[1]["value"] == 10  # 80 - 70 首尾差
    assert q[2]["agg"] == "max" and q[2]["value"] == 10000
    assert data["meta"] == {"executed": 3, "failed": 0}
    assert "compare" not in data


# ── 2. 未知 dimension → fail-loud 列合法值 ───────────────────────────────────
@pytest.mark.asyncio
async def test_unknown_dimension_fails_loud_and_lists_valid():
    plan = {"queries": [{"dimension": "hrv"}, {"dimension": "telepathy"}]}
    # fetch 若被调用即视为静默跳过 —— 这里断言在校验期就报错, 根本不取数。
    called = {"n": 0}

    async def _fetch(dimension, days):
        called["n"] += 1
        return hqb.BatchFetchResult(series=[1], aggregatable=True)

    out = await hqb.execute_batch(plan, _fetch, valid_dimensions=VALID)
    assert out.startswith("Error:")
    assert "telepathy" in out
    assert "合法值" in out
    assert "sleep" in out and "hrv" in out  # 真实维度清单
    assert called["n"] == 0  # 绝不静默跳过某条: 一条坏 → 整个 plan 不执行


@pytest.mark.asyncio
async def test_illness_dimension_fails_loud_before_fetch():
    called = {"n": 0}

    async def _fetch(dimension, days):  # noqa: ARG001
        called["n"] += 1
        return hqb.BatchFetchResult(raw="must not fetch")

    out = await hqb.execute_batch(
        {"queries": [{"dimension": "illness"}]},
        _fetch,
        valid_dimensions=VALID,
    )

    assert out.startswith("Error:")
    assert "illness" in out
    assert "单条 health_query" in out
    assert "dimension='illness'" in out
    assert called["n"] == 0
    assert "illness" not in hqb.known_dimensions()


# ── 3. 超 6 条 → fail-loud ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_too_many_queries_fails_loud():
    plan = {"queries": [{"dimension": "hrv"} for _ in range(7)]}
    out = await hqb.execute_batch(plan, make_fetch({}), valid_dimensions=VALID)
    assert out.startswith("Error:")
    assert "6" in out and "7" in out


# ── 4. compare diff / ratio ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_compare_diff():
    table = {
        ("hrv", 7): hqb.BatchFetchResult(
            series=[60, 60, 60], unit="ms", aggregatable=True
        ),
        ("hrv", 14): hqb.BatchFetchResult(
            series=[50, 50, 50], unit="ms", aggregatable=True
        ),
    }
    plan = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "avg"},
            {"dimension": "hrv", "days": 14, "agg": "avg"},
        ],
        "compare": {"a": 0, "b": 1, "op": "diff"},
    }
    data = json.loads(
        await hqb.execute_batch(plan, make_fetch(table), valid_dimensions=VALID)
    )
    assert data["compare"] == {"a": 0, "b": 1, "op": "diff", "value": 10, "unit": "ms"}


@pytest.mark.asyncio
async def test_compare_ratio():
    table = {
        ("activity", 7): hqb.BatchFetchResult(
            series=[10000], unit="", aggregatable=True
        ),
        ("activity", 30): hqb.BatchFetchResult(
            series=[8000], unit="", aggregatable=True
        ),
    }
    plan = {
        "queries": [
            {"dimension": "activity", "days": 7, "agg": "avg"},
            {"dimension": "activity", "days": 30, "agg": "avg"},
        ],
        "compare": {"a": 0, "b": 1, "op": "ratio"},
    }
    data = json.loads(
        await hqb.execute_batch(plan, make_fetch(table), valid_dimensions=VALID)
    )
    assert data["compare"]["op"] == "ratio"
    assert data["compare"]["value"] == 1.25  # 10000 / 8000


@pytest.mark.asyncio
async def test_compare_out_of_range_index_fails_loud():
    plan = {
        "queries": [{"dimension": "hrv", "agg": "avg"}],
        "compare": {"a": 0, "b": 5, "op": "diff"},
    }
    out = await hqb.execute_batch(plan, make_fetch({}), valid_dimensions=VALID)
    assert out.startswith("Error:") and "下标" in out


@pytest.mark.asyncio
async def test_compare_ratio_divide_by_zero_is_note_not_crash():
    table = {
        ("stress", 7): hqb.BatchFetchResult(series=[40], unit="", aggregatable=True),
        ("stress", 30): hqb.BatchFetchResult(series=[0], unit="", aggregatable=True),
    }
    plan = {
        "queries": [
            {"dimension": "stress", "days": 7, "agg": "avg"},
            {"dimension": "stress", "days": 30, "agg": "avg"},
        ],
        "compare": {"a": 0, "b": 1, "op": "ratio"},
    }
    data = json.loads(
        await hqb.execute_batch(plan, make_fetch(table), valid_dimensions=VALID)
    )
    assert data["compare"]["value"] is None
    assert "0" in data["compare"]["note"]


# ── 5. 空数据子查询 → value null + note, 整体不失败 ─────────────────────────
@pytest.mark.asyncio
async def test_empty_subquery_is_null_with_note_not_batch_failure():
    table = {
        ("hrv", 7): hqb.BatchFetchResult(series=[60, 62], unit="ms", aggregatable=True),
        ("sleep", 7): hqb.BatchFetchResult(
            series=[], raw="最近 7 天无可穿戴数据 (sleep)。", aggregatable=True
        ),
    }
    plan = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "avg"},
            {"dimension": "sleep", "days": 7, "agg": "avg"},
        ]
    }
    out = await hqb.execute_batch(plan, make_fetch(table), valid_dimensions=VALID)
    assert not out.startswith("Error:")  # 整体成功
    data = json.loads(out)
    assert data["queries"][0]["value"] == 61
    empty = data["queries"][1]
    assert empty["value"] is None
    assert "note" in empty
    assert empty["data"] == "最近 7 天无可穿戴数据 (sleep)。"  # 原文回灌
    assert data["meta"]["failed"] == 0  # 空数据 != 失败


# ── 6. 别名维度经 normalize 归一 ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_alias_dimension_and_time_range_normalized():
    # 复用既有 normalize_health_query_args 的别名表, 不重写:
    #   中文 "血压" → blood_pressure; time_range "最近30天" → days=30; 大写 "HRV" → hrv。
    captured = []

    async def _fetch(dimension, days):
        captured.append((dimension, days))
        return hqb.BatchFetchResult(
            series=[], raw=f"{dimension} raw", aggregatable=False
        )

    plan = {
        "queries": [
            {"dimension": "血压", "time_range": "最近30天"},
            {"dimension": "HRV", "days": 7, "agg": "avg"},
        ]
    }
    out = await hqb.execute_batch(plan, _fetch, valid_dimensions=VALID)
    assert not out.startswith("Error:")
    data = json.loads(out)
    assert data["queries"][0]["dimension"] == "blood_pressure"
    assert data["queries"][0]["days"] == 30
    assert data["queries"][1]["dimension"] == "hrv"
    assert ("blood_pressure", 30) in captured
    assert ("hrv", 7) in captured


# ── 附加: agg 数学纯函数 ─────────────────────────────────────────────────────
def test_aggregate_series_math():
    assert hqb.aggregate_series([10, 20, 30], "avg") == (20, None)
    assert hqb.aggregate_series([10, 20, 30], "min") == (10, None)
    assert hqb.aggregate_series([10, 20, 30], "max") == (30, None)
    assert hqb.aggregate_series([10, 20, 30], "latest") == (30, None)
    assert hqb.aggregate_series([10, 20, 30], "trend") == (20, None)  # 30 - 10
    assert hqb.aggregate_series([], "avg")[0] is None
    assert hqb.aggregate_series([5], "trend")[0] is None  # <2 点无趋势
    assert hqb.aggregate_series([10, 20], None) == (None, None)  # 不聚合


# ── 附加: 未知 agg fail-loud ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_unknown_agg_fails_loud():
    plan = {"queries": [{"dimension": "hrv", "agg": "median"}]}
    out = await hqb.execute_batch(plan, make_fetch({}), valid_dimensions=VALID)
    assert out.startswith("Error:")
    assert "median" in out and "avg" in out  # 列合法 agg


# ── 附加: 非可聚合维度 + agg → null + 明确 note (非静默) ─────────────────────
@pytest.mark.asyncio
async def test_non_aggregatable_dimension_with_agg_gets_note():
    table = {
        ("diet", 1): hqb.BatchFetchResult(
            series=[], raw="今日饮食: 牛肉面", aggregatable=False
        ),
    }
    plan = {"queries": [{"dimension": "diet", "days": 1, "agg": "avg"}]}
    data = json.loads(
        await hqb.execute_batch(plan, make_fetch(table), valid_dimensions=VALID)
    )
    entry = data["queries"][0]
    assert entry["value"] is None
    assert "不支持数值聚合" in entry["note"]
    assert entry["data"] == "今日饮食: 牛肉面"
    assert data["meta"]["failed"] == 0


# ── 附加: fetch 抛错显式挂账 (fail-loud, 非静默跳过) ─────────────────────────
@pytest.mark.asyncio
async def test_fetch_exception_is_marked_not_silently_skipped():
    async def _fetch(dimension, days):
        if dimension == "sleep":
            raise RuntimeError("DB down")
        return hqb.BatchFetchResult(series=[60], unit="ms", aggregatable=True)

    plan = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "latest"},
            {"dimension": "sleep", "days": 7, "agg": "avg"},
        ]
    }
    data = json.loads(await hqb.execute_batch(plan, _fetch, valid_dimensions=VALID))
    assert len(data["queries"]) == 2  # 两条都在, 坏的没被丢
    assert data["queries"][0]["value"] == 60
    assert "error" in data["queries"][1]
    assert "DB down" in data["queries"][1]["error"]
    assert data["meta"]["failed"] == 1


# ── 校验层直接单测: 空 queries / 非法 shape ─────────────────────────────────
def test_validate_plan_rejects_empty_and_bad_shape():
    for bad in [{}, {"queries": []}, {"queries": "hrv"}, [1, 2, 3], {"queries": [42]}]:
        _, _, err = hqb.validate_plan(bad, valid_dimensions=VALID)
        assert err and err.startswith("Error:")


# ── 数据面适配层真 DB 测 (证明 build_wearable_series 非 fake) ────────────────
@pytest.fixture
def batch_user(db):
    u = User(
        username="hqbuser",
        email="hqb@example.com",
        hashed_password="x",
        name="HQB",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_build_wearable_series_real_rows_ascending(db, batch_user):
    today = date.today()
    # 三天 HRV, 乱序插入 + 多源 (apple-watch 优先) —— 期望按日升序合并成 [50, 55, 60]。
    db.add_all(
        [
            GarminData(
                user_id=batch_user.id,
                record_date=today,
                data_source="apple-watch",
                hrv=60.0,
            ),
            GarminData(
                user_id=batch_user.id, record_date=today, data_source="garmin", hrv=None
            ),
            GarminData(
                user_id=batch_user.id,
                record_date=today - timedelta(days=2),
                data_source="garmin",
                hrv=50.0,
            ),
            GarminData(
                user_id=batch_user.id,
                record_date=today - timedelta(days=1),
                data_source="garmin",
                hrv=55.0,
            ),
        ]
    )
    db.commit()

    series, unit, raw = hqb.build_wearable_series(db, batch_user.id, "hrv", 7)
    assert series == [50.0, 55.0, 60.0]  # 时间升序: trend/latest 依赖此序
    assert unit == "ms"
    assert "hrv" in raw

    # activity(步数)列全空 → 空序列 + note, 不抛 (rows 存在但该列均 None)。
    empty_series, _, empty_raw = hqb.build_wearable_series(
        db, batch_user.id, "activity", 7
    )
    assert empty_series == []
    assert "无可穿戴数据" in empty_raw or "均为空" in empty_raw


def test_series_dimensions_are_subset_of_known():
    """可聚合维度必须都是合法 health_query 维度 (防漂移)。"""
    assert hqb.SERIES_DIMENSIONS <= hqb.known_dimensions()
