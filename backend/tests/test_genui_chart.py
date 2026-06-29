"""GenUI line_chart 测试 — 数据确定性 + 意图检测 + 能力协商 + 块结构。

铁律验证 (R4): 图表数值必须来自 seeded DB 行, 绝不来自 LLM。
本文件不依赖真实 LLM; caps-gated e2e 用 monkeypatch 让 _call_llm 在被调时炸,
证明 genui 路径根本不进 LLM 数据路径。
"""

import json
from datetime import date, timedelta
from statistics import mean

import pytest

from app.models.daily_health import GarminData
from app.models.weight import WeightRecord
from app.orchestrator import OrchestratorRequest, run_orchestrator
from app.services.genui import (
    SUPPORTED_METRICS,
    build_line_chart,
    detect_chart_request,
    render_reva_ui_block,
)
from app.services.genui.chart_builder import compute_chart, MIN_POINTS

from tests.conftest import create_authenticated_user


# ---------------------------------------------------------------------------
# seed helpers
# ---------------------------------------------------------------------------


def _seed_hrv_across_months(db, user_id, monthly_values):
    """对每个 (month_offset, [daily hrv values]) 写 GarminData 日行。

    monthly_values: dict {month_label_date: [v1, v2, ...]}.
    返回 {YYYY-MM 桶起始: mean(values)} 供断言。
    """
    base = date.today().replace(day=1)
    seeded_means = {}
    for offset, vals in monthly_values.items():
        # offset 个月之前的那个月
        month_start = base
        for _ in range(offset):
            month_start = (month_start - timedelta(days=1)).replace(day=1)
        for i, v in enumerate(vals):
            d = month_start + timedelta(days=i + 1)
            db.add(GarminData(user_id=user_id, record_date=d, hrv=v))
        seeded_means[(month_start.year, month_start.month)] = round(mean(vals), 1)
    db.commit()
    return seeded_means


# ---------------------------------------------------------------------------
# detect_chart_request — 正反例
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected",
    [
        ("帮我绘制最近半年的HRV曲线", ("hrv", "6m")),
        ("画一下近三个月的静息心率趋势", ("resting_hr", "3m")),
        ("看看我这个月的体重变化图", ("weight", "1m")),
        ("展示一下我的压力趋势", ("stress", "6m")),          # 默认 6m
        ("plot my hrv trend over the last 3 months", ("hrv", "3m")),
        ("画一张睡眠时长的曲线", ("sleep", "6m")),
    ],
)
def test_detect_chart_request_positive(query, expected):
    assert detect_chart_request(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "我最近睡眠怎么样",          # 有 metric 无 绘制+图
        "记录一下我今天喝了500ml水",  # 记录意图
        "绘制一张油画",              # 有动词+图 但无 metric
        "我的HRV正常吗",            # 有 metric 但非图表请求
        "",
        "帮我分析血压",
    ],
)
def test_detect_chart_request_negative(query):
    assert detect_chart_request(query) is None


# ---------------------------------------------------------------------------
# compute_chart — 纯计算核心 (无 DB, 无 LLM)
# ---------------------------------------------------------------------------


def test_compute_chart_monthly_means_match_input():
    """6m → 月桶, 每桶 points == 该月输入均值。"""
    base = date.today().replace(day=1)
    m0 = base
    m1 = (m0 - timedelta(days=1)).replace(day=1)
    pts = [
        (m1 + timedelta(days=1), 50.0),
        (m1 + timedelta(days=2), 60.0),   # m1 mean = 55.0
        (m0 + timedelta(days=1), 70.0),
        (m0 + timedelta(days=2), 80.0),   # m0 mean = 75.0
    ]
    block = compute_chart(pts, "hrv", "6m")
    assert block is not None
    assert len(block["series"][0]["points"]) == len(block["x"])
    pt_map = dict(zip(block["x"], block["series"][0]["points"]))
    assert pt_map[f"{m1.month}月"] == 55.0
    assert pt_map[f"{m0.month}月"] == 75.0


def test_compute_chart_insufficient_returns_none():
    base = date.today()
    pts = [(base, 50.0)]  # 1 point < MIN_POINTS
    assert compute_chart(pts, "hrv", "6m") is None
    assert MIN_POINTS >= 2


def test_compute_chart_empty_bucket_yields_null():
    """跨度内中间空桶应出 null, points.length == x.length 不变。"""
    base = date.today().replace(day=1)
    m0 = base
    m2 = m0
    for _ in range(2):
        m2 = (m2 - timedelta(days=1)).replace(day=1)
    pts = [
        (m2 + timedelta(days=1), 40.0),
        (m2 + timedelta(days=2), 50.0),
        (m0 + timedelta(days=1), 90.0),
        (m0 + timedelta(days=2), 100.0),
    ]
    block = compute_chart(pts, "hrv", "6m")
    assert block is not None
    # 3 个桶 (m2, m1空, m0), 中间 None
    assert len(block["x"]) == len(block["series"][0]["points"])
    assert None in block["series"][0]["points"]


def test_compute_chart_unknown_metric_none():
    pts = [(date.today(), 1.0)] * 5
    assert compute_chart(pts, "nonexistent_metric", "6m") is None


# ---------------------------------------------------------------------------
# build_line_chart — 真 DB 数据
# ---------------------------------------------------------------------------


def test_build_line_chart_points_from_seeded_db_rows(db):
    """关键: 块里的 points 必须等于 seeded GarminData 行的月均值 (非 LLM 编造)。"""
    user, _ = create_authenticated_user(db)
    seeded = _seed_hrv_across_months(
        db, user.id, {0: [70, 80, 90], 1: [50, 60, 55], 2: [40, 42, 44]}
    )

    block = build_line_chart(db, user.id, "hrv", range="6m")
    assert block is not None
    assert block["component"] == "line_chart"
    assert block["unit"] == "ms"

    pts = block["series"][0]["points"]
    assert len(pts) == len(block["x"])

    # 每个非空桶值精确等于 seeded 均值
    label_to_val = dict(zip(block["x"], pts))
    for (yr, mo), expected_mean in seeded.items():
        from app.services.genui.chart_builder import _MONTH_NAMES
        assert label_to_val[_MONTH_NAMES[mo]] == expected_mean

    # data_note 反映真实天数 (9 天)
    assert "9" in block["data_note"]


def test_build_line_chart_insufficient_data_returns_none(db):
    """数据不足 → None (调用方显数据不足, 绝不补点)。"""
    user, _ = create_authenticated_user(db)
    # 只 seed 1 天
    db.add(GarminData(user_id=user.id, record_date=date.today(), hrv=55.0))
    db.commit()
    assert build_line_chart(db, user.id, "hrv", range="6m") is None


def test_build_line_chart_skips_zero_and_null(db):
    """0/None 视为缺值, 不计入。跨 2 月以满足 trend (≥2 桶)。"""
    user, _ = create_authenticated_user(db)
    this_month = date.today().replace(day=1)
    prev_month = (this_month - timedelta(days=1)).replace(day=1)
    rows = [
        GarminData(user_id=user.id, record_date=prev_month + timedelta(days=1), hrv=0),     # skip
        GarminData(user_id=user.id, record_date=prev_month + timedelta(days=2), hrv=None),  # skip
        GarminData(user_id=user.id, record_date=prev_month + timedelta(days=3), hrv=60.0),
        GarminData(user_id=user.id, record_date=this_month + timedelta(days=1), hrv=70.0),
        GarminData(user_id=user.id, record_date=this_month + timedelta(days=2), hrv=80.0),
    ]
    db.add_all(rows)
    db.commit()
    block = build_line_chart(db, user.id, "hrv", range="6m")
    assert block is not None
    assert "3" in block["data_note"]  # 仅 3 个有效点


def test_build_line_chart_weight_from_weight_record(db):
    user, _ = create_authenticated_user(db)
    this_month = date.today().replace(day=1)
    prev_month = (this_month - timedelta(days=1)).replace(day=1)
    db.add(WeightRecord(user_id=user.id, record_date=prev_month + timedelta(days=1), weight=70.0))
    db.add(WeightRecord(user_id=user.id, record_date=prev_month + timedelta(days=2), weight=71.0))
    db.add(WeightRecord(user_id=user.id, record_date=this_month + timedelta(days=1), weight=72.0))
    db.add(WeightRecord(user_id=user.id, record_date=this_month + timedelta(days=2), weight=69.5))
    db.commit()
    block = build_line_chart(db, user.id, "weight", range="6m")
    assert block is not None
    assert block["unit"] == "kg"
    assert block["source"] == "scale"


def test_build_line_chart_sleep_minutes_to_hours(db):
    user, _ = create_authenticated_user(db)
    this_month = date.today().replace(day=1)
    prev_month = (this_month - timedelta(days=1)).replace(day=1)
    # 上月: 480 min = 8h, 420 = 7h, 540 = 9h → 均值 8.0h
    for i, mins in enumerate([480, 420, 540]):
        db.add(GarminData(user_id=user.id, record_date=prev_month + timedelta(days=i + 1),
                          total_sleep_duration=mins))
    # 本月: 一个点凑够 2 桶
    db.add(GarminData(user_id=user.id, record_date=this_month + timedelta(days=1),
                      total_sleep_duration=450))  # 7.5h
    db.commit()
    block = build_line_chart(db, user.id, "sleep", range="6m")
    assert block is not None
    assert block["unit"] == "h"
    from app.services.genui.chart_builder import _MONTH_NAMES
    label_to_val = dict(zip(block["x"], block["series"][0]["points"]))
    # 上月桶均值 = (8+7+9)/3 = 8.0h (分钟→小时换算正确)
    assert label_to_val[_MONTH_NAMES[prev_month.month]] == 8.0


def test_build_line_chart_unknown_metric_none(db):
    user, _ = create_authenticated_user(db)
    assert build_line_chart(db, user.id, "bogus", range="6m") is None


def test_build_line_chart_bad_range_none(db):
    user, _ = create_authenticated_user(db)
    assert build_line_chart(db, user.id, "hrv", range="99y") is None


# ---------------------------------------------------------------------------
# block 渲染 + JSON 合法性
# ---------------------------------------------------------------------------


def test_render_block_parses_as_valid_json(db):
    user, _ = create_authenticated_user(db)
    _seed_hrv_across_months(db, user.id, {0: [70, 80, 90], 1: [50, 60, 55]})
    block = build_line_chart(db, user.id, "hrv", range="6m")
    rendered = render_reva_ui_block(block)
    assert rendered.startswith("```reva-ui\n")
    assert rendered.rstrip().endswith("```")
    inner = rendered[len("```reva-ui\n"):].rstrip()[:-len("```")].strip()
    parsed = json.loads(inner)
    assert parsed["v"] == 1
    assert parsed["component"] == "line_chart"
    assert len(parsed["series"][0]["points"]) == len(parsed["x"])


# ---------------------------------------------------------------------------
# 能力协商 e2e (run_orchestrator) — caps-gated + no-LLM-in-data-path
# ---------------------------------------------------------------------------


@pytest.fixture
def _explode_llm(monkeypatch):
    """让 orchestrator 的 _call_llm 一旦被调就炸。

    genui 短路路径不应触发它; 若触发说明数据路径混入了 LLM (R4 违规)。
    """
    async def _boom(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("LLM must NOT be called on the GenUI chart path (R4)")

    monkeypatch.setattr("app.orchestrator.orchestrator._call_llm", _boom)


@pytest.mark.asyncio
async def test_genui_chart_e2e_caps_present_no_llm(db, _explode_llm):
    """caps=genui-v1 + 图表意图 + 真数据 → 块出现, 且 _call_llm 从未被调。"""
    user, _ = create_authenticated_user(db)
    _seed_hrv_across_months(db, user.id, {0: [70, 80, 90], 1: [50, 60, 55], 2: [40, 42, 44]})

    req = OrchestratorRequest(
        query="帮我绘制最近半年的HRV曲线",
        client_caps=["genui-v1"],
        stream=False,
    )
    resp = await run_orchestrator(db, user.id, req)
    assert "```reva-ui" in resp.synthesis

    # 解析出块, 验证数值来自 seeded 数据 (40-90 区间, 月均值)
    inner = resp.synthesis.split("```reva-ui\n", 1)[1].rsplit("```", 1)[0].strip()
    block = json.loads(inner)
    non_null = [p for p in block["series"][0]["points"] if p is not None]
    assert non_null  # 有真值
    assert all(40.0 <= p <= 90.0 for p in non_null)


@pytest.mark.asyncio
async def test_genui_chart_caps_absent_no_block(db, monkeypatch):
    """无 caps → 不出块。zero regression: 走现状全流程 (这里 stub LLM 仅证明 block 不出)。"""
    user, _ = create_authenticated_user(db)
    _seed_hrv_across_months(db, user.id, {0: [70, 80, 90], 1: [50, 60, 55]})

    async def _stub_llm(*args, **kwargs):  # noqa: ANN001
        return "（这是现状 LLM 合成回答，不含图表块）"

    monkeypatch.setattr("app.orchestrator.orchestrator._call_llm", _stub_llm)

    req = OrchestratorRequest(
        query="帮我绘制最近半年的HRV曲线",
        client_caps=[],  # 旧端: 不声明 genui
        stream=False,
    )
    resp = await run_orchestrator(db, user.id, req)
    assert "```reva-ui" not in resp.synthesis


@pytest.mark.asyncio
async def test_genui_chart_caps_present_insufficient_data_text(db, _explode_llm):
    """caps + 图表意图 但数据不足 → '数据不足' 文本, 无块, 无 LLM。"""
    user, _ = create_authenticated_user(db)
    db.add(GarminData(user_id=user.id, record_date=date.today(), hrv=55.0))
    db.commit()

    req = OrchestratorRequest(
        query="画一下我的HRV趋势图",
        client_caps=["genui-v1"],
        stream=False,
    )
    resp = await run_orchestrator(db, user.id, req)
    assert "```reva-ui" not in resp.synthesis
    assert "数据" in resp.synthesis and "不足" in resp.synthesis


@pytest.mark.asyncio
async def test_genui_non_chart_query_with_caps_falls_through(db, monkeypatch):
    """caps 在但非图表意图 → 不短路, 走现状 (证明只对图表意图介入)。"""
    user, _ = create_authenticated_user(db)

    async def _stub_llm(*args, **kwargs):  # noqa: ANN001
        return "现状回答"

    monkeypatch.setattr("app.orchestrator.orchestrator._call_llm", _stub_llm)

    req = OrchestratorRequest(
        query="我最近睡眠质量怎么样",
        client_caps=["genui-v1"],
        stream=False,
    )
    resp = await run_orchestrator(db, user.id, req)
    assert "```reva-ui" not in resp.synthesis


# ---------------------------------------------------------------------------
# API 头解析
# ---------------------------------------------------------------------------


def test_api_parse_client_caps():
    from app.api.orchestrator import _parse_client_caps
    assert _parse_client_caps("genui-v1") == ["genui-v1"]
    assert _parse_client_caps("genui-v1, foo") == ["genui-v1", "foo"]
    assert _parse_client_caps("GENUI-V1") == ["genui-v1"]
    assert _parse_client_caps(None) == []
    assert _parse_client_caps("") == []


def test_supported_metrics_allowlist():
    assert "hrv" in SUPPORTED_METRICS
    for m in ("hrv", "resting_hr", "stress", "sleep", "weight"):
        assert m in SUPPORTED_METRICS
