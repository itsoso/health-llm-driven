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
from app.services.genui.chart_rich import compute_chart_rich

from tests.conftest import create_authenticated_user


@pytest.fixture(autouse=True)
def _clear_agent_dup_cache():
    """agent/stream 的 in-memory 防双发缓存是模块级, 跨测试存活 →
    多个 agent_stream 测试用同一 user_id+message 会撞 429。每测试前后清空。"""
    from app.api.agent import _RECENT_DUP_CACHE
    _RECENT_DUP_CACHE.clear()
    yield
    _RECENT_DUP_CACHE.clear()


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


def _seed_daily_hrv(db, user_id, start_days_ago, values, data_source="garmin"):
    """从今天往前 start_days_ago 起, 每天一行 GarminData.hrv (指定 data_source)。

    values 按日期升序; values[i] 落在 (today - start_days_ago + i) 这天。
    返回 {date: value} 供断言。
    """
    today = date.today()
    out = {}
    for i, v in enumerate(values):
        d = today - timedelta(days=start_days_ago - i)
        db.add(GarminData(user_id=user_id, record_date=d, hrv=v, data_source=data_source))
        out[d] = v
    db.commit()
    return out


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


def test_build_line_chart_monthly_metric_points_from_seeded_db_rows(db):
    """关键 (月/周分桶路径回归): 非 rich metric (stress) 块里的 points 必须等于
    seeded GarminData 行的月均值 (非 LLM 编造)。HRV 已走富日级路径, 见下方 rich 测试。
    """
    user, _ = create_authenticated_user(db)
    base = date.today().replace(day=1)
    seeded = {}
    for offset, vals in {0: [70, 80, 90], 1: [50, 60, 55], 2: [40, 42, 44]}.items():
        month_start = base
        for _ in range(offset):
            month_start = (month_start - timedelta(days=1)).replace(day=1)
        for i, v in enumerate(vals):
            db.add(GarminData(user_id=user.id,
                              record_date=month_start + timedelta(days=i + 1),
                              stress_level=v))
        seeded[(month_start.year, month_start.month)] = round(mean(vals), 1)
    db.commit()

    block = build_line_chart(db, user.id, "stress", range="6m")
    assert block is not None
    assert block["component"] == "line_chart"

    pts = block["series"][0]["points"]
    assert len(pts) == len(block["x"])

    # 每个非空桶值精确等于 seeded 均值
    label_to_val = dict(zip(block["x"], pts))
    for (yr, mo), expected_mean in seeded.items():
        from app.services.genui.chart_builder import _MONTH_NAMES
        assert label_to_val[_MONTH_NAMES[mo]] == expected_mean

    # data_note 反映真实天数 (9 天), 月度均值 grain
    assert "9" in block["data_note"]
    assert block["series"][0]["name"] == "月度均值"


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
# compute_chart_rich — 富日级纯计算 (无 DB, 无 LLM)
# ---------------------------------------------------------------------------


def _daily(start_days_ago, values):
    """{date: value}, values[i] 落在 today - start_days_ago + i 天。"""
    today = date.today()
    return {today - timedelta(days=start_days_ago - i): float(v)
            for i, v in enumerate(values)}


def test_rich_daily_grain_all_series_aligned():
    """每条 series.points 长度 == x 长度 (日级对齐, 缺日 null)。"""
    g = _daily(9, [50, 52, 54, 56, 58, 60, 62, 64, 66, 68])  # 10 连续日
    block = compute_chart_rich(g, {}, "hrv", "6m")
    assert block is not None
    n = len(block["x"])
    assert n == 10
    for s in block["series"]:
        assert len(s["points"]) == n, f"series {s['role']} 长度未对齐"


def test_rich_x_is_daily_dates_with_gaps_nulled():
    """跨度内缺的日子在 x 上仍占位, raw series 该位置为 null。"""
    # 第 5 天故意缺值
    today = date.today()
    g = {}
    for i in [0, 1, 2, 4, 5]:  # 缺第 3 天 (index 3)
        g[today - timedelta(days=5 - i)] = float(50 + i)
    block = compute_chart_rich(g, {}, "hrv", "6m")
    assert block is not None
    assert len(block["x"]) == 6  # 跨度 6 天 (含缺日)
    raw = next(s for s in block["series"] if s["role"] == "raw")["points"]
    assert raw.count(None) == 1  # 恰一个缺日为 null


def test_rich_rolling_7d_math_correct():
    """7 日滚动均值 = trailing 7 日历窗口内 primary 非空值的均值。"""
    # 10 连续日, 值 = 10,20,...,100
    g = _daily(9, [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    block = compute_chart_rich(g, {}, "hrv", "6m")
    avg7 = next(s for s in block["series"] if s["role"] == "avg_7d")["points"]
    # 最后一天 (第 10 天) 窗口 = 第 4..10 天值 [40..100] → 均值 70.0
    assert avg7[-1] == 70.0
    # 第 1 天窗口仅 [10] → 10.0; 第 2 天 [10,20] → 15.0
    assert avg7[0] == 10.0
    assert avg7[1] == 15.0


def test_rich_rolling_30d_present():
    g = _daily(40, list(range(40, 80)))  # 40 连续日
    block = compute_chart_rich(g, {}, "hrv", "6m")
    roles = {s["role"] for s in block["series"]}
    assert "avg_30d" in roles
    avg30 = next(s for s in block["series"] if s["role"] == "avg_30d")["points"]
    assert len(avg30) == len(block["x"])
    assert avg30[-1] is not None


def test_rich_latest_annotation_factual():
    """latest annotation = 最新有值日 + 值 + 源, kind=latest, ≤3 条。"""
    g = _daily(4, [55, 56, 57, 58, 59])  # 最新 (今天) = 59.0, garmin 源
    block = compute_chart_rich(g, {}, "hrv", "6m")
    anns = block["annotations"]
    assert len(anns) <= 3
    latest = [a for a in anns if a["kind"] == "latest"]
    assert len(latest) == 1
    assert "最新" in latest[0]["label"]
    assert "59.0" in latest[0]["label"]
    assert "Garmin" in latest[0]["label"]


def test_rich_apple_watch_series_present_when_data_exists():
    """有 apple-watch 源数据 → 单独 device 线; data_note 标 Apple Watch 天数。"""
    g = _daily(5, [50, 51, 52, 53, 54, 55])
    a = _daily(5, [60, 61, 62, 63, 64, 65])
    block = compute_chart_rich(g, a, "hrv", "6m")
    roles = [s["role"] for s in block["series"]]
    assert "device" in roles
    device = next(s for s in block["series"] if s["role"] == "device")
    assert device["name"] == "Apple Watch HRV"
    assert "Apple Watch" in block["data_note"]


def test_rich_apple_watch_series_omitted_when_absent():
    """无 apple-watch 数据 → 不出 device 线 (不伪造), data_note 不提 Apple Watch。"""
    g = _daily(4, [50, 51, 52, 53, 54])
    block = compute_chart_rich(g, {}, "hrv", "6m")
    roles = [s["role"] for s in block["series"]]
    assert "device" not in roles
    assert "Apple Watch" not in block["data_note"]


def test_rich_series_count_le_5():
    g = _daily(5, [50, 51, 52, 53, 54, 55])
    a = _daily(5, [60, 61, 62, 63, 64, 65])
    block = compute_chart_rich(g, a, "hrv", "6m")
    assert len(block["series"]) <= 5


def test_rich_insufficient_data_returns_none():
    g = _daily(1, [50, 51])  # 2 天 < MIN_POINTS
    assert compute_chart_rich(g, {}, "hrv", "6m") is None


def test_rich_unknown_metric_none():
    g = _daily(4, [1, 2, 3, 4, 5])
    assert compute_chart_rich(g, {}, "bogus", "6m") is None


# ---------------------------------------------------------------------------
# build_line_chart 富路径 — 真 DB 数据 (HRV)
# ---------------------------------------------------------------------------


def test_build_hrv_routes_through_rich_daily_path(db):
    """HRV 走富日级路径: 日级 x + raw/avg_7d/avg_30d roles + latest annotation。"""
    user, _ = create_authenticated_user(db)
    _seed_daily_hrv(db, user.id, 6, [50, 52, 54, 56, 58, 60, 62])  # 7 连续日 garmin
    block = build_line_chart(db, user.id, "hrv", range="6m")
    assert block is not None
    roles = {s["role"] for s in block["series"]}
    assert {"raw", "avg_7d", "avg_30d"} <= roles
    assert all(s["role"] != "device" for s in block["series"])  # 无 apple
    assert any(a["kind"] == "latest" for a in block["annotations"])
    # 每条 series 与 x 等长
    for s in block["series"]:
        assert len(s["points"]) == len(block["x"])
    assert "每日" in block["data_note"]


def test_build_hrv_apple_watch_separate_series_from_db(db):
    """同用户 garmin + apple-watch 两源 HRV → 两条独立 series (不合并成一条)。"""
    user, _ = create_authenticated_user(db)
    today = date.today()
    # 同一天两源, 验证不互相覆盖 (唯一约束 (user,date,source) 允许)
    for i in range(6):
        d = today - timedelta(days=5 - i)
        db.add(GarminData(user_id=user.id, record_date=d, hrv=50 + i, data_source="garmin"))
        db.add(GarminData(user_id=user.id, record_date=d, hrv=70 + i, data_source="apple-watch"))
    db.commit()

    block = build_line_chart(db, user.id, "hrv", range="6m")
    assert block is not None
    raw = next(s for s in block["series"] if s["role"] == "raw")
    device = next(s for s in block["series"] if s["role"] == "device")
    # garmin 与 apple 值各自独立 (50-55 vs 70-75)
    raw_vals = [p for p in raw["points"] if p is not None]
    dev_vals = [p for p in device["points"] if p is not None]
    assert all(50 <= p <= 55 for p in raw_vals)
    assert all(70 <= p <= 75 for p in dev_vals)
    assert "Garmin" in block["data_note"] and "Apple Watch" in block["data_note"]


def test_build_hrv_apple_only_user_still_charts(db):
    """仅 apple-watch 源 (无 garmin) → 图仍出 (raw=garmin 主线全 null, device 有值)。

    HRV 的优先源是 ring-first (garmin 在 apple 之前), 故 primary 逐日回落 apple-watch,
    滚动均值/latest 基于 apple 值, 不整图失败。
    """
    user, _ = create_authenticated_user(db)
    _seed_daily_hrv(db, user.id, 4, [60, 61, 62, 63, 64], data_source="apple-watch")
    block = build_line_chart(db, user.id, "hrv", range="6m")
    assert block is not None
    roles = {s["role"] for s in block["series"]}
    assert "device" in roles
    avg7 = next(s for s in block["series"] if s["role"] == "avg_7d")["points"]
    assert any(v is not None for v in avg7)  # 滚动均值回落 apple 值
    latest = next(a for a in block["annotations"] if a["kind"] == "latest")
    assert "Apple Watch" in latest["label"]


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


# ---------------------------------------------------------------------------
# 能力协商 e2e (POST /agent/stream) — 统一聊天端点 (Mac/mobile 实际走的路径)
#
# 这是本次修复的核心: agent_stream 之前完全绕过 GenUI。下面验证:
#   1. caps=genui-v1 + 图表意图 → 流里出 reva-ui block + line_chart, 消息持久化,
#      且 AgentExecutor.run_stream 从未被调 (R4: 短路路径无 LLM)。
#   2. 无 caps → 不短路, 走普通 AgentExecutor 路径 (无 reva-ui)。
#   3. 数据不足 → fall through, 不 crash。
# ---------------------------------------------------------------------------


def _read_sse_body(resp) -> str:
    """TestClient 的 StreamingResponse: resp.text 即完整 SSE 文本。"""
    return resp.text


@pytest.fixture
def _explode_agent_run_stream(monkeypatch):
    """让 AgentExecutor.run_stream 一旦被调用就炸 (genui 短路不应触达它)。"""

    async def _boom(*args, **kwargs):  # noqa: ANN001
        raise AssertionError(
            "AgentExecutor.run_stream must NOT be called on the GenUI short-circuit (R4)"
        )
        yield  # pragma: no cover  (使其成为 async generator)

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", _boom
    )


def test_agent_stream_genui_caps_present_emits_block_no_llm(
    client, db, auth_user_and_headers, _explode_agent_run_stream
):
    """caps=genui-v1 + 图表意图 → SSE 含 reva-ui/line_chart, 消息持久化, 无 LLM。"""
    user, headers = auth_user_and_headers
    _seed_hrv_across_months(db, user.id, {0: [70, 80, 90], 1: [50, 60, 55], 2: [40, 42, 44]})

    resp = client.post(
        "/api/v1/agent/stream",
        json={"message": "绘制我最近半年的HRV曲线"},
        headers={**headers, "X-Reva-Client-Caps": "genui-v1"},
    )
    assert resp.status_code == 200
    body = _read_sse_body(resp)
    # block 出现在 token 事件里 (Mac WebView 扫描 fence)
    assert "reva-ui" in body
    assert "line_chart" in body
    # reva-ui 块在 token.data.content 内是 JSON 字符串 (SSE 再转义一层),
    # 解码 token 内容后再验组件字段 (body 里是 \"component\" 转义形态)。
    _decoded = ""
    for _l in body.split("\n"):
        if _l.startswith("data: "):
            try:
                _ev = json.loads(_l[6:])
            except Exception:
                continue
            if _ev.get("event") == "token":
                _decoded += _ev.get("data", {}).get("content", "")
    assert "line_chart" in _decoded and '"component"' in _decoded

    # done 事件携带真实 message_id, 且消息已持久化到对话存储
    from app.services.openclaw_service import OpenClawService

    convs = OpenClawService(db).get_conversations(user.id, limit=10)
    assert convs, "短路应创建/复用对话"
    detail = OpenClawService(db).get_conversation_detail(user.id, convs[0].id)
    assistant_msgs = [m for m in detail.messages if m.role == "assistant"]
    assert assistant_msgs, "assistant 消息必须持久化"
    assert any("reva-ui" in (m.content or "") for m in assistant_msgs)


def test_agent_stream_no_caps_falls_through_to_normal_path(
    client, db, auth_user_and_headers, monkeypatch
):
    """无 caps → 不短路, 走普通 AgentExecutor 路径, 流里不含 reva-ui。"""
    user, headers = auth_user_and_headers
    _seed_hrv_across_months(db, user.id, {0: [70, 80, 90], 1: [50, 60, 55]})

    async def _stub_run_stream(*args, **kwargs):  # noqa: ANN001
        yield {"event": "token", "data": {"content": "（普通路径回答，无图表）"}}
        yield {"event": "done", "data": {"conversation_id": 1, "message_id": 1, "mode": "agent"}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", _stub_run_stream
    )

    resp = client.post(
        "/api/v1/agent/stream",
        json={"message": "绘制我最近半年的HRV曲线"},
        headers=headers,  # 不带 X-Reva-Client-Caps
    )
    assert resp.status_code == 200
    body = _read_sse_body(resp)
    assert "reva-ui" not in body
    assert "普通路径回答" in body


def test_agent_stream_genui_insufficient_data_falls_through(
    client, db, auth_user_and_headers, monkeypatch
):
    """caps + 图表意图 但数据不足 → fall through 普通路径, 不 crash, 无 reva-ui。"""
    user, headers = auth_user_and_headers
    # 只 seed 1 天 → build_line_chart 返回 None
    db.add(GarminData(user_id=user.id, record_date=date.today(), hrv=55.0))
    db.commit()

    called = {"n": 0}

    async def _stub_run_stream(*args, **kwargs):  # noqa: ANN001
        called["n"] += 1
        yield {"event": "token", "data": {"content": "数据还不太够，等设备多同步一些。"}}
        yield {"event": "done", "data": {"conversation_id": 1, "message_id": 1, "mode": "agent"}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", _stub_run_stream
    )

    resp = client.post(
        "/api/v1/agent/stream",
        json={"message": "画一下我的HRV趋势图"},
        headers={**headers, "X-Reva-Client-Caps": "genui-v1"},
    )
    assert resp.status_code == 200
    body = _read_sse_body(resp)
    assert "reva-ui" not in body
    assert called["n"] == 1, "数据不足必须 fall through 到普通 AgentExecutor 路径"


def test_agent_stream_genui_non_chart_query_falls_through(
    client, db, auth_user_and_headers, monkeypatch
):
    """caps 在但非图表意图 → 不短路, 走普通路径。"""
    user, headers = auth_user_and_headers
    called = {"n": 0}

    async def _stub_run_stream(*args, **kwargs):  # noqa: ANN001
        called["n"] += 1
        yield {"event": "token", "data": {"content": "普通分析回答"}}
        yield {"event": "done", "data": {"conversation_id": 1, "message_id": 1, "mode": "agent"}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", _stub_run_stream
    )

    resp = client.post(
        "/api/v1/agent/stream",
        json={"message": "我最近睡眠质量怎么样"},
        headers={**headers, "X-Reva-Client-Caps": "genui-v1"},
    )
    assert resp.status_code == 200
    body = _read_sse_body(resp)
    assert "reva-ui" not in body
    assert called["n"] == 1
