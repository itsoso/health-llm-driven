# -*- coding: utf-8 -*-
"""GenUI metric_table (latency-roadmap-phase2 rank1) — 后端从**已执行工具结果**确定性
建表, 消除强模型把工具结果重打成大 markdown 表的 decode 税。

覆盖:
  1. 建表器确定性 (单元格逐字来自工具结果字段) + 对抗 (字段缺失 → 绝不编造行)。
  2. strip 护栏覆盖伪造的 metric_table fence (与图表同一 R4 剥离器)。
  3. cap 缺失 → 零 emission + prompt 保持现状 (mac 指令原样); cap 声明 → fence 追加 +
     GenUI 格式契约注入 + mac 指令被覆盖，且不截断正文。
  4. 伪造 fence 被剥、确定性 fence 保留; kill-switch 关 → 即便声明 cap 也不发。
  5. R4 纪律: LLM 合成抛错 → 表格仍从工具结果确定性建出 (数值不来自 LLM)。

本文件不依赖真实 LLM/provider: e2e 用 monkeypatch 让 _call_llm_stream / _execute_tool
返回受控事件, 直接驱动 AgentExecutor.run_stream。
"""
import inspect
import json

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.genui import (
    GENUI_TABLE_CAP,
    GENUI_DIET_SUMMARY_CAP,
    GENUI_SLEEP_SUMMARY_CAP,
    build_table_from_tool_call,
    build_tables_from_tool_calls,
    strip_reva_ui_blocks,
    placeholder_reva_ui_blocks,
)


@pytest.fixture(autouse=True)
def _clear_agent_dup_cache():
    from app.api.agent import _RECENT_DUP_CACHE

    _RECENT_DUP_CACHE.clear()
    yield
    _RECENT_DUP_CACHE.clear()


# ---------------------------------------------------------------------------
# helpers: canned tool-result payloads
# ---------------------------------------------------------------------------

def _batch_result(**over):
    payload = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "avg", "value": 58, "unit": "ms", "n": 7},
            {"dimension": "sleep", "days": 7, "agg": "trend", "value": -5, "n": 7, "note": "略降"},
            {"dimension": "diet", "days": 7, "agg": None, "value": None, "data": "…"},
        ],
        "meta": {"executed": 3, "failed": 0},
        "compare": {"a": 0, "b": 1, "op": "diff", "value": 3, "unit": "ms"},
    }
    payload.update(over)
    return json.dumps(payload, ensure_ascii=False)


def _lab_single_result():
    return json.dumps(
        {
            "count": 2,
            "items": [
                {"name": "LDL", "value": 3.4, "unit": "mmol/L", "record_date": "2026-07-01",
                 "is_abnormal": True, "reference_low": 0, "reference_high": 3.3},
                {"name": "LDL", "value": 3.1, "unit": "mmol/L", "record_date": "2026-01-01",
                 "is_abnormal": False, "reference_low": 0, "reference_high": 3.3},
            ],
        },
        ensure_ascii=False,
    )


def _lab_batch_result():
    return json.dumps(
        {
            "batch": True,
            "count": 3,
            "queried": ["LDL", "ALT"],
            "by_name": {
                "LDL": {"count": 2, "items": [
                    {"name": "LDL", "value": 3.4, "unit": "mmol/L", "record_date": "2026-07-01",
                     "is_abnormal": True, "reference_low": 0, "reference_high": 3.3},
                    {"name": "LDL", "value": 3.1, "unit": "mmol/L", "record_date": "2026-01-01"},
                ]},
                "ALT": {"count": 1, "items": [
                    {"name": "ALT", "value": 22, "unit": "U/L", "record_date": "2026-07-01",
                     "is_abnormal": False},
                ]},
            },
            "truncated": False,
        },
        ensure_ascii=False,
    )


def _sleep_result():
    """analyze_sleep_quality dict (health_query dimension=sleep 的真实返回形状)。

    durations 全部为分钟整数 (见 models/daily_health 注释); quality_assessment 是服务端
    质量判定, builder 绝不消费。
    """
    return json.dumps(
        {
            "status": "success",
            "days_analyzed": 2,
            "average_sleep_score": 80.5,
            "average_sleep_duration_minutes": 442.5,
            "average_sleep_duration_hours": 7.4,
            "average_deep_sleep_minutes": 95.0,
            "quality_assessment": {"level": "良好", "summary": "整体睡眠质量良好"},
            "recommendations": ["保持规律作息"],
            "daily_data": [
                {"date": "2026-07-12", "sleep_score": 82, "total_sleep_duration": 445,
                 "deep_sleep_duration": 98, "rem_sleep_duration": 110, "awake_duration": 20},
                {"date": "2026-07-11", "sleep_score": 79, "total_sleep_duration": 440,
                 "deep_sleep_duration": 92, "rem_sleep_duration": 105, "awake_duration": 25},
            ],
        },
        ensure_ascii=False,
    )


def _diet_result():
    """DailyDietSummary dict (health_query dimension=diet 的真实返回形状)。

    meal_type 是 MealType str-enum → JSON 序列化为值 ("breakfast" 等);
    per-meal calories/protein 是 float (可能带 .0)。
    """
    return json.dumps(
        {
            "record_date": "2026-07-13",
            "total_calories": 830,
            "total_protein": 60.5,
            "total_carbs": 70.0,
            "total_fat": 30.0,
            "total_fiber": 12.0,
            "meals_count": 2,
            "meals": [
                {"record_date": "2026-07-13", "meal_type": "breakfast", "food_items": "燕麦粥, 水煮蛋",
                 "calories": 350.0, "protein": 18.0, "carbs": 40.0, "fat": 10.0},
                {"record_date": "2026-07-13", "meal_type": "lunch", "food_items": "鸡胸肉沙拉",
                 "calories": 480.0, "protein": 42.5, "carbs": 30.0, "fat": 20.0},
            ],
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# A. builder determinism — every cell traces to a tool-result field
# ---------------------------------------------------------------------------

def test_batch_cells_trace_to_fields():
    block = build_table_from_tool_call("health_query_batch", {}, _batch_result())
    assert block is not None
    assert block["type"] == "metric_table" and block["v"] == 1
    rows = block["rows"]
    # 3 valid rows: hrv, sleep (both have scalar value), + compare. diet(null) dropped.
    assert len(rows) == 3
    hrv = rows[0]
    assert hrv["metric"] == "HRV"
    assert hrv["value"] == "58 ms"          # value + unit, verbatim
    assert "近7天平均" in hrv["note"] and "7天数据" in hrv["note"]
    sleep = rows[1]
    assert sleep["value"] == "-5" and "略降" in sleep["note"]  # note field verbatim
    cmp_row = rows[2]
    assert cmp_row["value"] == "3 ms" and "差值" in cmp_row["metric"]


def test_batch_drops_null_value_rows_no_invention():
    """agg 省略/空数据/不可聚合 (value=None) → 不落行, 绝不编造单元格。"""
    result = json.dumps({"queries": [
        {"dimension": "diet", "days": 7, "agg": None, "value": None, "data": "x"},
        {"dimension": "hrv", "days": 7, "agg": "avg", "value": 60, "unit": "ms"},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query_batch", {}, result)
    assert block is not None
    assert len(block["rows"]) == 1
    assert block["rows"][0]["metric"] == "HRV" and block["rows"][0]["value"] == "60 ms"


def test_batch_all_null_builds_nothing():
    result = json.dumps({"queries": [
        {"dimension": "diet", "agg": None, "value": None},
        {"dimension": "medication", "agg": None, "value": None},
    ]}, ensure_ascii=False)
    assert build_table_from_tool_call("health_query_batch", {}, result) is None


def test_batch_relays_abnormal_flag_when_present():
    """Condition 2 (batch vitals): 工具结果若带 category/is_abnormal 旗标 → 领起说明列。

    R4: 只 relay 结果里已有的字段, 不发明阈值。旗标领先其他说明片段以提升 salience。
    """
    result = json.dumps({"queries": [
        {"dimension": "spo2", "days": 1, "agg": "min", "value": 84, "unit": "%",
         "n": 1, "is_abnormal": True, "category": "偏低"},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query_batch", {}, result)
    assert block is not None
    note = block["rows"][0]["note"]
    # 分级/异常旗标逐字透传, 且领起说明 (在 agg/天数说明之前)
    assert "偏低" in note and "异常" in note
    assert note.index("偏低") < note.index("最低")


def test_batch_no_flag_no_invented_status_adversarial():
    """对抗: 批查询不带 category/is_abnormal (可穿戴常态) → 说明列无编造的分级/异常字样。"""
    result = json.dumps({"queries": [
        {"dimension": "hrv", "days": 7, "agg": "avg", "value": 58, "unit": "ms", "n": 7},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query_batch", {}, result)
    assert block is not None
    assert "异常" not in block["rows"][0]["note"]  # 无旗标 → 不发明


def test_lab_single_history_table():
    block = build_table_from_tool_call("query_lab_indicators", {}, _lab_single_result())
    assert block is not None
    assert [c["key"] for c in block["columns"]] == ["metric", "value", "note"]
    assert len(block["rows"]) == 2
    r0 = block["rows"][0]
    assert r0["value"] == "3.4 mmol/L"          # value + unit
    assert "0–3.3" in r0["note"] and "异常" in r0["note"]  # reference + is_abnormal


def test_lab_batch_latest_per_indicator():
    block = build_table_from_tool_call("query_lab_indicators", {}, _lab_batch_result())
    assert block is not None
    metrics = {r["metric"]: r["value"] for r in block["rows"]}
    assert metrics["LDL"] == "3.4 mmol/L"       # latest item (items[0])
    assert metrics["ALT"] == "22 U/L"
    assert len(block["rows"]) == 2               # one row per queried indicator


def test_lab_items_without_value_skipped():
    result = json.dumps({"count": 1, "items": [
        {"name": "X", "value": None, "unit": "mg"},
    ]}, ensure_ascii=False)
    assert build_table_from_tool_call("query_lab_indicators", {}, result) is None


def test_weight_table_fat_column_kept_when_all_present():
    result = json.dumps([
        {"record_date": "2026-07-01", "weight": 70.5, "body_fat_percentage": 18.2},
        {"record_date": "2026-06-01", "weight": 71.0, "body_fat_percentage": 18.8},
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "weight"}, result)
    assert [c["key"] for c in block["columns"]] == ["date", "weight", "fat"]
    assert block["rows"][0] == {"date": "2026-07-01", "weight": "70.5 kg", "fat": "18.2 %"}


def test_weight_fat_column_dropped_when_partial():
    """任一行缺 body_fat → 整列丢弃 (绝不用占位值冒充数据)。"""
    result = json.dumps([
        {"record_date": "2026-07-01", "weight": 70.5, "body_fat_percentage": 18.2},
        {"record_date": "2026-06-01", "weight": 71.0, "body_fat_percentage": None},
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "weight"}, result)
    assert [c["key"] for c in block["columns"]] == ["date", "weight"]
    assert "fat" not in block["rows"][0]


def test_bp_table_with_pulse():
    result = json.dumps([
        {"record_date": "2026-07-01", "systolic": 120, "diastolic": 80, "pulse": 62},
        {"record_date": "2026-06-30", "systolic": 118, "diastolic": 78, "pulse": 60},
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result)
    assert [c["key"] for c in block["columns"]] == ["date", "bp", "pulse"]
    assert block["rows"][0] == {"date": "2026-07-01", "bp": "120/80 mmHg", "pulse": "62 bpm"}


def test_bp_row_missing_systolic_skipped():
    result = json.dumps([
        {"record_date": "2026-07-01", "systolic": None, "diastolic": 80},
    ], ensure_ascii=False)
    assert build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result) is None


def test_bp_status_column_relays_server_category_verbatim():
    """危险 affordance: 服务端 classify_blood_pressure 已算好的 `category` 逐字进"状态"列。

    Condition 2: builder 引用服务端分级, 绝不自行判定血压等级。用真实分级器输出
    (185/122→血压严重升高, 158/99→高血压2级) 逐字透传。
    """
    result = json.dumps([
        {"record_date": "2026-07-01", "systolic": 185, "diastolic": 122,
         "pulse": 88, "category": "血压严重升高"},
        {"record_date": "2026-06-30", "systolic": 158, "diastolic": 99,
         "pulse": 80, "category": "高血压2级"},
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result)
    assert block is not None
    assert [c["key"] for c in block["columns"]] == ["date", "bp", "pulse", "status"]
    # 服务端分级字符串逐字透传, builder 未改写/未重判
    assert block["rows"][0]["status"] == "血压严重升高"
    assert block["rows"][1]["status"] == "高血压2级"
    assert block["rows"][0]["bp"] == "185/122 mmHg"


def test_bp_status_column_absent_without_category_adversarial():
    """对抗: 工具结果不带 category → 绝不发明状态列 (builder 不自行判血压等级)。"""
    result = json.dumps([
        {"record_date": "2026-07-01", "systolic": 185, "diastolic": 122, "pulse": 88},
        {"record_date": "2026-06-30", "systolic": 158, "diastolic": 99, "pulse": 80},
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result)
    assert block is not None
    # 无 category → 保持存量形状, 无 "status" 列, 无编造分级
    assert [c["key"] for c in block["columns"]] == ["date", "bp", "pulse"]
    assert "status" not in block["rows"][0]


def test_bp_status_partial_category_still_column_but_blank_where_absent():
    """部分记录带 category → 加"状态"列; 缺 category 的行留空 (诚实空值, 非编造)。

    这里用一个**分级器永不产出**的合成字符串 (自定义分级ZZ) 证明 relay 的普适性:
    builder 不做白名单/校验, 忠实透传字段里出现的任意分级串 (来源若换/加档也不丢)。
    """
    result = json.dumps([
        {"record_date": "2026-07-01", "systolic": 185, "diastolic": 122, "category": "自定义分级ZZ"},
        {"record_date": "2026-06-30", "systolic": 118, "diastolic": 76},  # 无 category
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result)
    assert block is not None
    assert [c["key"] for c in block["columns"]] == ["date", "bp", "status"]
    assert block["rows"][0]["status"] == "自定义分级ZZ"  # 任意串逐字透传, 无白名单
    assert block["rows"][1]["status"] == ""  # 缺分级留空, 不借用上一行


def test_water_table():
    result = json.dumps(
        {"record_date": "2026-07-13", "total_amount": 1500, "target_amount": 2000, "records": []},
        ensure_ascii=False,
    )
    block = build_table_from_tool_call("health_query", {"dimension": "water"}, result)
    assert block["rows"] == [
        {"item": "今日饮水", "value": "1500 ml"},
        {"item": "目标", "value": "2000 ml"},
    ]


def test_water_missing_total_builds_nothing():
    result = json.dumps({"record_date": "2026-07-13", "records": []}, ensure_ascii=False)
    assert build_table_from_tool_call("health_query", {"dimension": "water"}, result) is None


# ---------------------------------------------------------------------------
# A1a. sleep — daily_data rows, verbatim, server-scored relay only
# ---------------------------------------------------------------------------

def test_sleep_real_shape_rows_verbatim():
    block = build_table_from_tool_call("health_query", {"dimension": "sleep"}, _sleep_result())
    assert block is not None
    assert block["type"] == "metric_table" and block["v"] == 1
    assert [c["key"] for c in block["columns"]] == ["date", "dur", "deep", "score"]
    assert len(block["rows"]) == 2
    # 每格逐字来自 daily_data 字段 (分钟单位, sleep_score 逐字)
    assert block["rows"][0] == {"date": "2026-07-12", "dur": "445 分钟",
                                "deep": "98 分钟", "score": "82"}
    assert block["rows"][1]["score"] == "79"


def test_sleep_no_quality_judgment_leaked():
    """R4: builder 只 relay daily_data raw 字段, 不碰 quality_assessment (服务端质量判定)。"""
    block = build_table_from_tool_call("health_query", {"dimension": "sleep"}, _sleep_result())
    blob = json.dumps(block, ensure_ascii=False)
    # quality_assessment 的判定词/键均不进卡片; 也不出现均值字段 (卡片只逐日 daily_data)
    assert "良好" not in blob and "quality" not in blob
    assert "average" not in blob


def test_sleep_no_data_builds_nothing():
    result = json.dumps(
        {"status": "no_data", "message": "没有足够的睡眠数据", "days_analyzed": 0},
        ensure_ascii=False,
    )
    assert build_table_from_tool_call("health_query", {"dimension": "sleep"}, result) is None


def test_sleep_deep_column_dropped_when_all_absent():
    """所有天都缺 deep_sleep_duration → 不建深睡列 (绝不占位)。"""
    result = json.dumps({"status": "success", "daily_data": [
        {"date": "2026-07-12", "sleep_score": 82, "total_sleep_duration": 445},
        {"date": "2026-07-11", "sleep_score": 79, "total_sleep_duration": 440},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "sleep"}, result)
    assert [c["key"] for c in block["columns"]] == ["date", "dur", "score"]
    assert "deep" not in block["rows"][0]


def test_sleep_partial_column_blank_where_absent():
    """部分天缺 deep → 列在, 缺的行留空 (诚实空值, 非借上一行)。"""
    result = json.dumps({"status": "success", "daily_data": [
        {"date": "2026-07-12", "sleep_score": 82, "total_sleep_duration": 445, "deep_sleep_duration": 98},
        {"date": "2026-07-11", "sleep_score": 79, "total_sleep_duration": 440},  # 无 deep
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "sleep"}, result)
    assert [c["key"] for c in block["columns"]] == ["date", "dur", "deep", "score"]
    assert block["rows"][0]["deep"] == "98 分钟"
    assert block["rows"][1]["deep"] == ""


def test_sleep_row_all_metrics_none_skipped():
    """对抗: daily_data 条目有 date 但所有指标 None → 跳过该行 (不落空行, 不编造)。"""
    result = json.dumps({"status": "success", "daily_data": [
        {"date": "2026-07-12", "sleep_score": None, "total_sleep_duration": None,
         "deep_sleep_duration": None},
        {"date": "2026-07-11", "sleep_score": 79, "total_sleep_duration": 440},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "sleep"}, result)
    assert len(block["rows"]) == 1
    assert block["rows"][0]["date"] == "2026-07-11"


def test_sleep_empty_daily_data_builds_nothing():
    result = json.dumps({"status": "success", "daily_data": []}, ensure_ascii=False)
    assert build_table_from_tool_call("health_query", {"dimension": "sleep"}, result) is None


# ---------------------------------------------------------------------------
# A1b. diet — DailyDietSummary meal rows, R4 no-invention on missing nutrients
# ---------------------------------------------------------------------------

def test_diet_real_shape_rows_verbatim():
    block = build_table_from_tool_call("health_query", {"dimension": "diet"}, _diet_result())
    assert block is not None
    assert [c["key"] for c in block["columns"]] == ["meal", "food", "cal", "pro"]
    assert len(block["rows"]) == 2
    # 餐次映射中文, 内容/热量/蛋白逐字 (整数浮点去 .0, 小数逐字)
    assert block["rows"][0] == {"meal": "早餐", "food": "燕麦粥, 水煮蛋",
                                "cal": "350 kcal", "pro": "18 g"}
    assert block["rows"][1] == {"meal": "午餐", "food": "鸡胸肉沙拉",
                                "cal": "480 kcal", "pro": "42.5 g"}


def test_diet_missing_calorie_no_fabrication():
    """对抗: 一餐未识别热量 (calories None) → 该格留空, 绝不编造/借总量。"""
    result = json.dumps({"record_date": "2026-07-13", "total_calories": 480,
                         "total_protein": 82.5, "meals": [
        {"meal_type": "lunch", "food_items": "鸡胸肉沙拉", "calories": None, "protein": 42.5},
        {"meal_type": "dinner", "food_items": "牛排", "calories": 480.0, "protein": 40.0},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "diet"}, result)
    # dinner 有 calories → 建热量列; lunch 该格空 (非 0/非编造), protein 逐字
    assert [c["key"] for c in block["columns"]] == ["meal", "food", "cal", "pro"]
    assert block["rows"][0]["cal"] == "" and block["rows"][0]["pro"] == "42.5 g"
    assert block["rows"][1]["cal"] == "480 kcal"


def test_diet_no_nutrient_columns_when_all_absent():
    """无一餐带 calories/protein → 只 餐次/内容 两列 (绝不补 0 冒充营养)。"""
    result = json.dumps({"record_date": "2026-07-13", "total_calories": 0, "total_protein": 0,
                         "meals": [
        {"meal_type": "snack", "food_items": "苹果"},
        {"meal_type": "extra", "food_items": "黑咖啡"},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "diet"}, result)
    assert [c["key"] for c in block["columns"]] == ["meal", "food"]
    assert block["rows"][0] == {"meal": "加餐", "food": "苹果"}


def test_diet_meal_without_food_skipped():
    """内容 (锚点字段) 空 → 跳过该餐行。"""
    result = json.dumps({"meals": [
        {"meal_type": "breakfast", "food_items": "", "calories": 100.0},
        {"meal_type": "lunch", "food_items": "米饭", "calories": 300.0},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "diet"}, result)
    assert len(block["rows"]) == 1
    assert block["rows"][0]["food"] == "米饭"


def test_diet_empty_meals_builds_nothing():
    result = json.dumps({"record_date": "2026-07-13", "total_calories": 0, "meals": []},
                        ensure_ascii=False)
    assert build_table_from_tool_call("health_query", {"dimension": "diet"}, result) is None


def test_diet_unknown_meal_type_passthrough():
    """未知 meal_type → 逐字透传 (无白名单丢弃, 与血压 category relay 同纪律)。"""
    result = json.dumps({"meals": [
        {"meal_type": "brunch", "food_items": "培根蛋", "calories": 400.0},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "diet"}, result)
    assert block["rows"][0]["meal"] == "brunch"


# ---------------------------------------------------------------------------
# A2. adversarial / fail-open
# ---------------------------------------------------------------------------

def test_error_string_builds_nothing():
    assert build_table_from_tool_call("health_query_batch", {}, "Error: 未知维度") is None


def test_unparseable_result_builds_nothing():
    assert build_table_from_tool_call("health_query_batch", {}, "让我查一下…（不是JSON）") is None


def test_truncated_list_suffix_recovered():
    """_api_get 会给超长 list 加 '...(仅显示前10条)' 尾注 → 剥掉后仍能解析。"""
    body = json.dumps([
        {"record_date": "2026-07-01", "systolic": 120, "diastolic": 80},
    ], ensure_ascii=False)
    result = body + "\n...(仅显示前10条)"
    block = build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result)
    assert block is not None and block["rows"][0]["bp"] == "120/80 mmHg"


def test_unknown_tool_builds_nothing():
    assert build_table_from_tool_call("health_record", {}, "{}") is None


def test_single_query_unknown_dimension_builds_nothing():
    """health_query 但非 weight/bp/water (如 hrv 走 wearable 紧凑文本) → 不建表。"""
    result = json.dumps([{"record_date": "2026-07-01", "weight": 70}], ensure_ascii=False)
    assert build_table_from_tool_call("health_query", {"dimension": "hrv"}, result) is None
    assert build_table_from_tool_call("health_query", {}, result) is None  # 缺 dimension


def test_contract_bounds_columns_rows_strings():
    block = build_table_from_tool_call("health_query_batch", {}, _batch_result())
    assert 2 <= len(block["columns"]) <= 4
    assert 1 <= len(block["rows"]) <= 12
    assert all(isinstance(v, str) for r in block["rows"] for v in r.values())
    for c in block["columns"]:
        assert set(c.keys()) == {"key", "label"}
    assert len(block["title"]) <= 20


def test_row_cap_at_12():
    items = [
        {"name": "LDL", "value": i, "unit": "mmol/L", "record_date": f"2026-01-{i:02d}"}
        for i in range(1, 20)
    ]
    block = build_table_from_tool_call("query_lab_indicators", {}, json.dumps({"count": 19, "items": items}))
    assert len(block["rows"]) == 12


def test_aggregate_dedup_and_cap_max_tables():
    b = _batch_result()
    calls = [("health_query_batch", {}, b)] * 5  # identical → dedup to 1
    assert len(build_tables_from_tool_calls(calls)) == 1
    # distinct batches, capped at MAX_TABLES (3)
    many = [
        ("health_query_batch", {}, json.dumps({"queries": [
            {"dimension": "hrv", "agg": "avg", "value": v, "unit": "ms"}]}, ensure_ascii=False))
        for v in range(10)
    ]
    assert len(build_tables_from_tool_calls(many)) == 3


# ---------------------------------------------------------------------------
# B. strip guard covers metric_table (R4 defense-in-depth) — TIGHTEN, no loosen
# ---------------------------------------------------------------------------

_FORGED_TABLE = (
    '```reva-ui\n'
    '{"type":"metric_table","v":1,"title":"编造","columns":[{"key":"a","label":"x"}],'
    '"rows":[{"a":"999"}]}\n```'
)


def test_strip_removes_forged_metric_table():
    text = f"这是分析：\n\n{_FORGED_TABLE}\n\n仅供参考。"
    out = strip_reva_ui_blocks(text)
    assert "reva-ui" not in out and "编造" not in out and "999" not in out
    assert "这是分析" in out and "仅供参考" in out


def test_placeholder_replaces_forged_metric_table():
    text = f"上文\n{_FORGED_TABLE}\n下文"
    out = placeholder_reva_ui_blocks(text)
    assert "reva-ui" not in out and "999" not in out
    assert "上文" in out and "下文" in out


# ---------------------------------------------------------------------------
# E. R4: builder never touches an LLM / provider
# ---------------------------------------------------------------------------

def test_builder_module_has_no_llm_or_provider_calls():
    import app.services.genui.table_builder as tb

    src = inspect.getsource(tb)
    for forbidden in ("create_provider", "provider.complete", ".chat(", "import openai", "_call_llm("):
        assert forbidden not in src, f"table_builder must not touch LLM: {forbidden!r}"


# ---------------------------------------------------------------------------
# C/D. e2e via run_stream — narrative contract, mac supersession, emission
# ---------------------------------------------------------------------------

def _wire(executor, monkeypatch):
    """Minimal wiring so run_stream reaches the round loop without real LLM/provider."""
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [
        {"type": "function", "function": {"name": "health_query", "description": "x",
                                          "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "health_query_batch", "description": "x",
                                          "parameters": {"type": "object", "properties": {}}}},
    ])
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


async def _run(executor, message, *, client_caps=None, extra_context=None, user_id=1):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            extra_context=extra_context,
            client_caps=client_caps,
        )
    ]


def _tokens(events):
    return "".join(
        e["data"].get("content", "") for e in events if e.get("event") == "token"
    )


def _exec_returns(result_str):
    """_execute_tool 是 async 方法 (被 await) → mock 必须是 async。"""
    async def _fake(name, args, tok):
        return result_str

    return _fake


_MAC_CTX = json.dumps({
    "client": "mac",
    "desktop_markdown_response_instruction": "必须用大 markdown 表格逐行列出所有数值",
})


def _batch_round_stream(captured):
    """round1 → health_query_batch tool_call; round2 → synthesis text."""
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        captured.append([m.get("content") for m in messages])
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "b1",
                "function": {"name": "health_query_batch",
                             "arguments": '{"queries":[{"dimension":"hrv","days":7,"agg":"avg"}]}'},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "结论：HRV 处于个人常态区间，继续保持。"}
            yield {"type": "finish", "finish_reason": "stop"}

    return fake_stream


@pytest.mark.asyncio
async def test_cap_on_injects_genui_contract_without_truncating_narrative_and_supersedes_mac(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    await _run(executor, "对比我这周和上周的 HRV", client_caps=[GENUI_TABLE_CAP],
               extra_context=_MAC_CTX, user_id=user.id)

    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "数据回答格式要求" in prompt
    assert "不超过 500 字" not in prompt
    assert "正文按问题完整回答" in prompt
    # mac 大表指令被覆盖: 声明了 cap → 不注入桌面端 markdown 表格强制指令
    assert "必须用大 markdown 表格逐行列出所有数值" not in prompt
    assert "桌面端回复格式要求" not in prompt


@pytest.mark.asyncio
async def test_cap_off_preserves_mac_instruction_no_contract(db, auth_user_and_headers, monkeypatch):
    """cap 缺失 → mac 指令原样注入, 不注入 GenUI 专属格式契约。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "对比我这周和上周的 HRV", client_caps=[],
                        extra_context=_MAC_CTX, user_id=user.id)

    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "必须用大 markdown 表格逐行列出所有数值" in prompt  # mac 指令保留
    assert "数据回答格式要求" not in prompt
    assert "不超过 500 字" not in prompt
    assert "reva-ui" not in _tokens(events)  # 零 emission


@pytest.mark.asyncio
async def test_cap_on_emits_metric_table_after_synthesis(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "对比我这周和上周的 HRV", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)

    # 叙事在前、卡片在后
    assert "结论：HRV" in rendered
    assert "```reva-ui" in rendered and '"type":"metric_table"' in rendered
    assert rendered.index("结论") < rendered.index("reva-ui")
    # 数值来自工具结果 (58 ms), 不来自 LLM 文本
    assert "58 ms" in rendered
    done = next(event["data"] for event in events if event.get("event") == "done")
    assert done["answer_evidence"] == {
        "version": "answer-evidence.v1",
        "summary": "本轮获得 3 条可核对数据",
        "basis": [
            {
                "id": "tool-1-row-1",
                "label": "HRV",
                "observation": "58 ms",
                "context": "近7天平均 · 7天数据",
                "source": "健康数据查询",
                "purpose": "用于评估恢复趋势",
            },
            {
                "id": "tool-1-row-2",
                "label": "睡眠评分",
                "observation": "-5",
                "context": "近7天趋势(首尾差) · 7天数据 · 略降",
                "source": "健康数据查询",
                "purpose": "用于评估睡眠与恢复状态",
            },
            {
                "id": "tool-1-row-3",
                "label": "对比(差值)",
                "observation": "3 ms",
                "source": "健康数据查询",
                "purpose": "用于回答本轮问题",
            },
        ],
        "limitations": [],
    }
    # 持久化的 assistant 消息也带 fence
    from app.models.agent_conversation import AgentMessage
    assistant = (
        db.query(AgentMessage).filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc()).first()
    )
    assert "```reva-ui" in (assistant.content or "")
    assert assistant.meta["answer_evidence"] == done["answer_evidence"]
    assert len(assistant.meta["answer_evidence_sha256"]) == 64


@pytest.mark.asyncio
async def test_available_but_unused_profile_data_is_not_reported_as_turn_evidence(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))
    monkeypatch.setattr(
        "app.services.agent_executor._inspect_user_data_sources",
        lambda *_args, **_kwargs: ["在服补剂 (10 种)", "主目标: 总体健康"],
    )

    events = await _run(
        executor,
        "对比我这周和上周的 HRV",
        client_caps=[GENUI_TABLE_CAP],
        user_id=user.id,
    )

    done = next(event["data"] for event in events if event.get("event") == "done")
    assert "在服补剂 (10 种)" not in done["sources_used"]
    assert "主目标: 总体健康" not in done["sources_used"]


def _sleep_round_stream(captured):
    """round1 → health_query(sleep) tool_call; round2 → synthesis text (新形状 e2e)。"""
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        captured.append([m.get("content") for m in messages])
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "s1",
                "function": {"name": "health_query", "arguments": '{"dimension":"sleep"}'},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "结论：你近两晚睡眠评分稳定在个人常态区间。"}
            yield {"type": "finish", "finish_reason": "stop"}

    return fake_stream


@pytest.mark.asyncio
async def test_cap_on_emits_sleep_metric_table(db, auth_user_and_headers, monkeypatch):
    """新形状 e2e: health_query(sleep) → 叙事后确定性追加睡眠 metric_table (真数值来自工具结果)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _sleep_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_sleep_result()))

    events = await _run(executor, "看看我最近睡眠", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)

    # 确定性快读或合成叙事都必须在卡片前；两者都只基于真实工具数据。
    narrative = rendered.split("```reva-ui", 1)[0].strip()
    assert narrative
    assert "```reva-ui" in rendered and '"type":"metric_table"' in rendered
    assert "睡眠记录" in rendered
    assert rendered.index(narrative) < rendered.index("reva-ui")
    # 数值来自工具结果 daily_data (时长 445 分钟 / 评分 82), 不来自 LLM 文本
    assert "445 分钟" in rendered and '"score":"82"' in rendered
    # quality_assessment (服务端质量判定) 不泄漏进卡片
    assert "良好" not in rendered


@pytest.mark.asyncio
async def test_cap_off_no_fence_emitted(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "对比我这周和上周的 HRV", client_caps=[], user_id=user.id)
    assert "reva-ui" not in _tokens(events)


@pytest.mark.asyncio
async def test_kill_switch_off_no_fence_even_with_cap(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr("app.services.agent_executor.settings.genui_table_enabled", False)
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "对比我这周和上周的 HRV", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert "reva-ui" not in rendered
    # flag 关 → 也不注入 GenUI 契约
    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "数据回答格式要求" not in prompt


@pytest.mark.asyncio
async def test_forged_fence_stripped_but_deterministic_appended(db, auth_user_and_headers, monkeypatch):
    """LLM 合成里伪造 metric_table → 被剥掉; 确定性表 (真数值) 仍从工具结果追加。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "b1", "function": {"name": "health_query_batch",
                                         "arguments": '{"queries":[{"dimension":"hrv","agg":"avg"}]}'}}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            forged = ('结论如下。\n```reva-ui\n{"type":"metric_table","v":1,"title":"假",'
                      '"columns":[{"key":"a","label":"x"}],"rows":[{"a":"999"}]}\n```')
            yield {"type": "content", "text": forged}
            yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    await _run(executor, "看看 HRV", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    from app.models.agent_conversation import AgentMessage
    assistant = (
        db.query(AgentMessage).filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc()).first()
    )
    content = assistant.content or ""
    assert "999" not in content              # 伪造块被剥
    assert "58 ms" in content                # 确定性真数值保留
    assert content.count("```reva-ui") == 1  # 只有确定性那一张表


@pytest.mark.asyncio
async def test_llm_synthesis_raise_tables_still_build(db, auth_user_and_headers, monkeypatch):
    """R4 纪律: 合成轮 LLM 抛错 → 表格仍从工具结果确定性建出 (数据不依赖 LLM)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "b1", "function": {"name": "health_query_batch",
                                         "arguments": '{"queries":[{"dimension":"hrv","agg":"avg"}]}'}}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        raise RuntimeError("boom synthesis")
        yield  # pragma: no cover

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "看看 HRV", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert '"type":"metric_table"' in rendered and "58 ms" in rendered


# ---------------------------------------------------------------------------
# E. Condition 1 — crisis-value carve-out reaches prose contract (safety review)
# ---------------------------------------------------------------------------

def _bp_severe_result():
    """BP tool result carrying the server-computed severe-reading category."""
    return json.dumps([
        {"record_date": "2026-07-01", "systolic": 185, "diastolic": 122,
         "pulse": 92, "category": "血压严重升高"},
    ], ensure_ascii=False)


def _bp_round_stream(captured):
    """round1 → health_query blood_pressure tool_call; round2 → synthesis text。"""
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        captured.append([m.get("content") for m in messages])
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "bp1",
                "function": {"name": "health_query",
                             "arguments": '{"dimension":"blood_pressure"}'},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "结论：血压严重升高，请先复测并按症状决定是否需要急诊。"}
            yield {"type": "finish", "finish_reason": "stop"}

    return fake_stream


# 安全例外的判别性片段 (仅本 carve-out 产出, 不会被 safety alert / mac 指令巧合命中)。
_CARVEOUT_MARKER = "必须在正文中明确说出具体数值"


@pytest.mark.asyncio
async def test_cap_on_severe_bp_injects_carveout(db, auth_user_and_headers, monkeypatch):
    """Condition 1: cap on + severe BP result → GenUI 契约携带"危急值必须复述"安全例外,
    且既有"不复述数值行"与"安全边界照常表达"两行未被削弱; BP 路径仍确定性出卡片。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _bp_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_bp_severe_result()))

    events = await _run(executor, "看看我的血压", client_caps=[GENUI_TABLE_CAP], user_id=user.id)

    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "数据回答格式要求" in prompt
    assert "不超过 500 字" not in prompt
    assert "正文按问题完整回答" in prompt
    assert _CARVEOUT_MARKER in prompt and "安全例外" in prompt        # 安全例外落进 prompt
    assert "血压严重升高" in prompt                                    # 例外示例用真实分级词
    # 既有边界不被削弱: 两行原样保留
    assert "绝不逐行复述表格中的数值行" in prompt
    assert "不确定性与安全边界照常表达" in prompt
    # "以系统标注为准"锚句在场 (防模型对系统判正常的数值自加危急判断)
    assert "以系统安全提示" in prompt and "不要给系统标注为正常的数值自行加危急判断" in prompt
    # BP 高分级结果确实经确定性建表路径出卡片 (卡片内 category relay 由 Condition 2 单测覆盖)
    assert '"type":"metric_table"' in _tokens(events)


@pytest.mark.asyncio
async def test_cap_off_no_carveout(db, auth_user_and_headers, monkeypatch):
    """对称: cap 缺失 → GenUI 契约整体不注入, 因此安全例外碎片也不存在。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _bp_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_bp_severe_result()))

    await _run(executor, "看看我的血压", client_caps=[], user_id=user.id)

    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "数据回答格式要求" not in prompt
    assert _CARVEOUT_MARKER not in prompt        # 契约缺失 → 无安全例外碎片
    # 工具结果本身会含服务端分级；这里只验证 cap 专属的格式契约未注入。
    assert "异常或需立即分流的数值" not in prompt


# ---------------------------------------------------------------------------
# F. diet_daily_summary 结构化卡 (汇总类卡结构化 v1) — emission 消费者级 e2e
#    证明: 接线真的触发、cap 门控生效、diet flag 关/cap 缺失 → 回退通用 metric_table。
# ---------------------------------------------------------------------------

def _diet_summary_result():
    """read_daily_diet 的 DailyDietSummary 形状 (逐餐 + 宏量合计)。"""
    return json.dumps({
        "record_date": "2026-07-16",
        "total_calories": 980, "total_protein": 55, "total_carbs": 66,
        "total_fat": 49, "total_fiber": 3, "meals_count": 2,
        "meals": [
            {"meal_type": "breakfast", "food_items": "山药小米粥·蒸蛋羹",
             "calories": 400, "protein": 23, "carbs": 38, "fat": 13, "fiber": 1},
            {"meal_type": "lunch", "food_items": "三文鱼鸡肉餐",
             "calories": 580, "protein": 32, "carbs": 28, "fat": 36, "fiber": 2},
        ],
    }, ensure_ascii=False)


def _diet_round_stream(captured):
    """round1 → health_query(diet) tool_call; round2 → synthesis text。"""
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        captured.append([m.get("content") for m in messages])
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "d1",
                "function": {"name": "health_query", "arguments": '{"dimension":"diet"}'},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "结论：今天蛋白质到位，脂肪略高。"}
            yield {"type": "finish", "finish_reason": "stop"}

    return fake_stream


@pytest.mark.asyncio
async def test_diet_cap_on_emits_diet_summary_card(db, auth_user_and_headers, monkeypatch):
    """diet cap 声明 → health_query(diet) 走结构化 diet_daily_summary 卡, 不落 metric_table;
    叙事在前、卡片在后; 卡片数值来自工具结果具名字段 (R4, 不来自 LLM)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _diet_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_diet_summary_result()))

    events = await _run(executor, "我今天吃了啥",
                        client_caps=[GENUI_TABLE_CAP, GENUI_DIET_SUMMARY_CAP], user_id=user.id)
    rendered = _tokens(events)

    assert "结论：今天蛋白质" in rendered
    assert "```reva-ui" in rendered and '"type":"diet_daily_summary"' in rendered
    assert '"type":"metric_table"' not in rendered          # diet 不再走通用表
    assert rendered.index("结论") < rendered.index("reva-ui")
    # 数值/文本来自工具结果具名字段 (fence 用 separators=(",",":"))
    assert '"calories":400' in rendered and "山药小米粥·蒸蛋羹" in rendered
    # 确定性派生观察落卡 (脂肪 49g/980kcal≈45%>35% → 脂肪偏高 caution)
    assert "脂肪偏高" in rendered
    # 持久化的 assistant 消息也带 diet fence
    from app.models.agent_conversation import AgentMessage
    assistant = (
        db.query(AgentMessage).filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc()).first()
    )
    assert '"type":"diet_daily_summary"' in (assistant.content or "")


@pytest.mark.asyncio
async def test_diet_cap_off_falls_back_to_metric_table(db, auth_user_and_headers, monkeypatch):
    """只有 table cap、diet cap 暗置 → diet 查询回退通用 metric_table (今日饮食), 不出结构化卡。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _diet_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_diet_summary_result()))

    events = await _run(executor, "我今天吃了啥", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert '"type":"metric_table"' in rendered and "今日饮食" in rendered
    assert "diet_daily_summary" not in rendered


@pytest.mark.asyncio
async def test_diet_kill_switch_off_falls_back_to_metric_table(db, auth_user_and_headers, monkeypatch):
    """diet flag 关 (即便声明 diet cap) → 不出结构化卡, 回退 metric_table (table cap 仍在)。"""
    user, _ = auth_user_and_headers
    monkeypatch.setattr(
        "app.services.agent_executor.settings.genui_diet_summary_enabled", False, raising=False)
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _diet_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_diet_summary_result()))

    events = await _run(executor, "我今天吃了啥",
                        client_caps=[GENUI_TABLE_CAP, GENUI_DIET_SUMMARY_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert "diet_daily_summary" not in rendered
    assert '"type":"metric_table"' in rendered


@pytest.mark.asyncio
async def test_diet_cap_only_emits_diet_summary_card(db, auth_user_and_headers, monkeypatch):
    """只声明 diet cap(无 table cap)→ diet 查询仍出结构化卡(证明 diet 路径不依赖 table cap)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _diet_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_diet_summary_result()))

    events = await _run(executor, "我今天吃了啥",
                        client_caps=[GENUI_DIET_SUMMARY_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert '"type":"diet_daily_summary"' in rendered
    assert '"type":"metric_table"' not in rendered
    # 契约版本必须是整数 1(移动端 parser 校验 v===1;字符串 "v1" 会被静默丢弃)
    assert '"v":1' in rendered and '"v":"v1"' not in rendered


@pytest.mark.asyncio
async def test_diet_cap_on_empty_meals_falls_through_no_card(db, auth_user_and_headers, monkeypatch):
    """diet 结果无餐次 → build 返回 None → 不出结构化卡;落回 _table_calls 但空饮食也无表 →
    纯散文(fail-open,既不出卡也不谎报)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    empty = json.dumps({"record_date": "2026-07-16", "total_calories": 0,
                        "meals_count": 0, "meals": []}, ensure_ascii=False)
    monkeypatch.setattr(executor, "_call_llm_stream", _diet_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(empty))

    events = await _run(executor, "我今天吃了啥",
                        client_caps=[GENUI_TABLE_CAP, GENUI_DIET_SUMMARY_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert "结论：今天蛋白质" in rendered      # 叙事仍在
    assert "reva-ui" not in rendered           # 无卡无表


@pytest.mark.asyncio
async def test_sleep_cap_on_emits_sleep_summary_card(db, auth_user_and_headers, monkeypatch):
    """sleep cap 声明 → health_query(sleep) 走结构化 sleep_summary 卡, 不落 metric_table;
    信封 v 整数 1(移动端 parser 校验 v===1);服务端 quality_assessment 不泄漏。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _sleep_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_sleep_result()))

    events = await _run(executor, "看看我最近睡眠",
                        client_caps=[GENUI_TABLE_CAP, GENUI_SLEEP_SUMMARY_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert '"type":"sleep_summary"' in rendered
    assert '"type":"metric_table"' not in rendered      # sleep 不再走通用表
    assert '"v":1' in rendered and '"v":"v1"' not in rendered
    assert "良好" not in rendered                        # quality_assessment 不泄漏


@pytest.mark.asyncio
async def test_sleep_cap_off_falls_back_to_metric_table(db, auth_user_and_headers, monkeypatch):
    """只 table cap、sleep cap 暗置 → sleep 查询回退通用 metric_table(睡眠记录), 不出结构化卡。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _sleep_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_sleep_result()))

    events = await _run(executor, "看看我最近睡眠", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert '"type":"metric_table"' in rendered and "睡眠记录" in rendered
    assert "sleep_summary" not in rendered
