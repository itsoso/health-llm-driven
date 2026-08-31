"""确定性查询直出 (Phase-2 rank2) 格式化器 + 覆盖判定的单元测试。

信任级不变量:
  - 读数**只**从真实 tool result 渲染, 绝不编造数字 (算错饮水总量 = 信任 bug)。
  - 缺数据 → 诚实「还没有记录」, 不谎报数字。
  - 未覆盖工具/维度、无法解析、带安全告警后缀 → deterministic_query_reply 返回 None
    (调用方 fail-open 回落合成轮)。
"""
import json

import pytest

from app.services import query_readouts as qr


def _tool_msg(tool_call_id: str, payload) -> dict:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _assistant_query(tool_call_id: str, dimension: str, **args) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": "health_query",
                "arguments": json.dumps({"dimension": dimension, **args}, ensure_ascii=False),
            },
        }],
    }


def _assistant_batch(tool_call_id: str, queries: list[dict]) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": "health_query_batch",
                "arguments": json.dumps({"queries": queries}, ensure_ascii=False),
            },
        }],
    }


# ──────────────────────── marker drift guard ────────────────────────

def test_safety_marker_matches_agent_executor_source():
    """安全告警后缀 marker 必须与 agent_executor 单一真源一致 (漂移 = 安全短路失守)。"""
    from app.services.agent_executor import SAFETY_WARNING_MARKER

    assert qr._SAFETY_WARNING_MARKER == SAFETY_WARNING_MARKER


# ──────────────────────── water ────────────────────────

def test_water_uses_server_total_amount():
    payload = {
        "record_date": "2026-07-12",
        "total_amount": 1500,
        "target_amount": 2000,
        "progress_percentage": 75.0,
        "records_count": 3,
        "records": [{"amount": 500}, {"amount": 500}, {"amount": 500}],
    }
    out = qr._format_water(json.dumps(payload))
    assert out == "今日饮水 1500ml,目标 2000ml(完成 75%)。"


def test_water_sums_records_when_total_absent():
    # total_amount 字段缺失时从真实记录求和 (对抗: 多条记录求和, 非编造)。
    payload = {
        "record_date": "2026-07-12",
        "target_amount": 2000,
        "records": [{"amount": 250}, {"amount": 300}, {"amount": 450}],
        "records_count": 3,
    }
    out = qr._format_water(json.dumps(payload))
    assert "1000ml" in out  # 250+300+450
    assert "编造" not in out


def test_water_unit_edge_string_and_float_amounts_sum_correctly():
    payload = {
        "target_amount": 2000,
        "records": [{"amount": "250ml"}, {"amount": 300.0}, {"amount": 200}],
        "records_count": 3,
    }
    out = qr._format_water(json.dumps(payload))
    assert "750ml" in out  # 250+300+200


def test_water_zero_records_is_honest_not_fabricated():
    payload = {"record_date": "2026-07-12", "total_amount": 0, "target_amount": 2000,
               "progress_percentage": 0, "records_count": 0, "records": []}
    out = qr._format_water(json.dumps(payload))
    assert out == "今天还没有喝水记录哦,记得及时补水。"
    assert "0ml" not in out


def test_water_truncated_json_falls_open():
    # _api_get 硬字符截断 → 解析不回 → None (绝不用半截数据)。
    truncated = '{"record_date": "2026-07-12", "total_amount": 1500, "records": [{"amo'
    assert qr._format_water(truncated) is None


def test_water_error_content_falls_open():
    assert qr._format_water("Error: API 返回 500") is None
    assert qr._format_water("[1, 2, 3]") is None  # 非 dict


# ──────────────────────── weight ────────────────────────

def test_weight_latest_with_downward_delta():
    records = [
        {"id": 9, "record_date": "2026-07-12", "weight": 70.2},
        {"id": 8, "record_date": "2026-07-10", "weight": 71.0},
    ]
    out = qr._format_weight(json.dumps(records))
    assert out == "最新体重 70.2kg(2026-07-12),较上次下降 0.8kg。"


def test_weight_upward_delta():
    records = [
        {"record_date": "2026-07-12", "weight": 71.5},
        {"record_date": "2026-07-10", "weight": 71.0},
    ]
    out = qr._format_weight(json.dumps(records))
    assert "较上次上升 0.5kg" in out


def test_weight_flat_delta():
    records = [
        {"record_date": "2026-07-12", "weight": 70.0},
        {"record_date": "2026-07-10", "weight": 70.0},
    ]
    out = qr._format_weight(json.dumps(records))
    assert "与上次持平" in out


def test_weight_single_record_no_delta():
    out = qr._format_weight(json.dumps([{"record_date": "2026-07-12", "weight": 68.3}]))
    assert out == "最新体重 68.3kg(2026-07-12)。"


def test_weight_empty_is_honest():
    assert qr._format_weight("[]") == "还没有体重记录,记录一次就能看到变化趋势。"


def test_weight_non_list_falls_open():
    assert qr._format_weight(json.dumps({"weight": 70})) is None


# ──────────────────────── blood pressure ────────────────────────

def test_bp_latest_with_category_reference():
    records = [
        {"id": 5, "record_date": "2026-07-12", "systolic": 135, "diastolic": 88,
         "pulse": 72, "category": "高血压1级"},
        {"id": 4, "record_date": "2026-07-10", "systolic": 120, "diastolic": 80,
         "category": "正常偏高"},
    ]
    out = qr._format_blood_pressure(json.dumps(records))
    assert "最新血压 135/88 mmHg" in out
    assert "脉搏 72次/分" in out
    assert "高血压1级" in out  # 引用服务端 ACC/AHA category, 不新造
    assert "2026-07-12" in out


def test_bp_without_category_still_renders_numbers():
    records = [{"record_date": "2026-07-12", "systolic": 118, "diastolic": 76}]
    out = qr._format_blood_pressure(json.dumps(records))
    assert "最新血压 118/76 mmHg" in out
    assert "分级" not in out


def test_bp_empty_is_honest():
    assert qr._format_blood_pressure("[]") == "还没有血压记录。"


def test_bp_missing_systolic_falls_open():
    # systolic/diastolic 是渲染核心, 缺任一 → 无有效最新记录 → 诚实空。
    assert qr._format_blood_pressure(json.dumps([{"record_date": "2026-07-12", "diastolic": 80}])) == "还没有血压记录。"


def test_bp_severe_reading_defers_to_safety_guidance():
    records = [{"record_date": "2026-07-12", "systolic": 185, "diastolic": 85,
                "category": "血压严重升高"}]
    assert qr._format_blood_pressure(json.dumps(records)) is None


# ──────────────────────── sleep ────────────────────────

def _sleep_payload():
    return {
        "status": "success",
        "days_analyzed": 3,
        "average_sleep_duration_hours": 7.2,
        "average_sleep_duration_minutes": 432.0,
        "daily_data": [
            {"date": "2026-07-09", "sleep_score": 70, "total_sleep_duration": 400, "deep_sleep_duration": 70},
            {"date": "2026-07-11", "sleep_score": 82, "total_sleep_duration": 445, "deep_sleep_duration": 95},
            {"date": "2026-07-10", "sleep_score": 76, "total_sleep_duration": 420, "deep_sleep_duration": 80},
        ],
    }


def test_sleep_picks_latest_night_by_date_not_list_order():
    # daily_data 顺序被打乱, 必须按日期取最近一晚 (2026-07-11), 不能取 list[0]。
    out = qr._format_sleep(json.dumps(_sleep_payload()))
    assert out.startswith("2026-07-11 睡了 7小时25分钟")  # 445min = 7h25m
    assert "深睡 1小时35分钟" in out  # 95min
    assert "睡眠评分 82" in out
    assert "最近 3 晚平均 7.2 小时" in out


def test_sleep_no_data_status_is_honest():
    out = qr._format_sleep(json.dumps({"status": "no_data", "message": "没有足够的睡眠数据"}))
    assert out == "还没有足够的睡眠数据(可能设备未同步)。"


def test_sleep_empty_daily_falls_open():
    assert qr._format_sleep(json.dumps({"status": "success", "daily_data": []})) is None


def test_sleep_single_night_no_average_line():
    payload = {
        "status": "success",
        "days_analyzed": 1,
        "daily_data": [{"date": "2026-07-11", "total_sleep_duration": 480, "deep_sleep_duration": 90}],
    }
    out = qr._format_sleep(json.dumps(payload))
    assert "睡了 8小时" in out
    assert "平均" not in out


# ──────────────────────── activity / steps ────────────────────────

_ACTIVITY_TEXT = (
    "可穿戴 daily 数据 (最近 3 天, 多源按设备优先级合并): 数据源: garmin。\n"
    "- 2026-07-11: 步数 8500, 静息心率 55bpm, 活动分钟 42min, 总消耗 2200kcal\n"
    "- 2026-07-10: 步数 12000, 静息心率 54bpm\n"
    "- 2026-07-09: 步数 6000"
)


def test_activity_extracts_latest_day_steps():
    out = qr._format_activity(_ACTIVITY_TEXT)
    assert out.startswith("2026-07-11 步数 8500步")  # 最近一天 (输出倒序, 首行)
    assert "活动 42分钟" in out
    assert "消耗 2200kcal" in out
    assert "12000" not in out  # 不把更早一天的步数混进来


def test_activity_no_data_is_honest():
    text = "未找到可穿戴(Garmin/Apple Watch/RingConn)数据 (最近 7 天内)。可能设备未同步"
    out = qr._format_activity(text)
    assert "还没有可穿戴设备" in out


def test_activity_unparseable_falls_open():
    assert qr._format_activity("一些无法解析的文本没有步数字段") is None
    assert qr._format_activity("Error: 查询可穿戴数据失败") is None


# ──────────────────────── deterministic_query_reply (coverage) ────────────────────────

def test_single_covered_water_query_yields_reply():
    messages = [
        {"role": "user", "content": "今天喝了多少水"},
        _assistant_query("c1", "water"),
        _tool_msg("c1", {"total_amount": 1200, "target_amount": 2000,
                         "progress_percentage": 60.0, "records_count": 2,
                         "records": [{"amount": 600}, {"amount": 600}]}),
    ]
    out = qr.deterministic_query_reply(messages)
    assert out == "今日饮水 1200ml,目标 2000ml(完成 60%)。"


def test_multiple_covered_queries_are_joined():
    messages = [
        _assistant_query("c1", "water"),
        _tool_msg("c1", {"total_amount": 1000, "target_amount": 2000, "records_count": 1,
                         "records": [{"amount": 1000}]}),
        _assistant_query("c2", "weight"),
        _tool_msg("c2", [{"record_date": "2026-07-12", "weight": 70.0}]),
    ]
    out = qr.deterministic_query_reply(messages)
    assert "今日饮水 1000ml" in out
    assert "最新体重 70kg" in out


def test_batch_scalar_queries_render_grounded_readouts():
    messages = [
        _assistant_batch("batch-1", [
            {"dimension": "hrv", "days": 7, "agg": "avg"},
            {"dimension": "sleep", "days": 7, "agg": "trend"},
        ]),
        _tool_msg("batch-1", {
            "queries": [
                {
                    "dimension": "hrv",
                    "days": 7,
                    "agg": "avg",
                    "value": 58,
                    "unit": "ms",
                    "n": 7,
                },
                {
                    "dimension": "sleep",
                    "days": 7,
                    "agg": "trend",
                    "value": -5,
                    "n": 7,
                },
            ],
            "meta": {"executed": 2, "failed": 0},
        }),
    ]

    assert qr.deterministic_query_reply(messages) == (
        "近7天 HRV 平均值 58 ms。\n\n"
        "近7天 睡眠评分 较首个数据点下降 5 分。"
    )


def test_batch_sensitive_or_partial_results_fall_open():
    for payload in (
        {
            "queries": [{
                "dimension": "spo2",
                "days": 7,
                "agg": "avg",
                "value": 93,
                "unit": "%",
                "n": 7,
            }],
            "meta": {"executed": 1, "failed": 0},
        },
        {
            "queries": [{
                "dimension": "hrv",
                "days": 7,
                "agg": "avg",
                "value": None,
                "error": "数据查询失败",
            }],
            "meta": {"executed": 1, "failed": 1},
        },
    ):
        messages = [
            _assistant_batch("batch-1", [{
                "dimension": payload["queries"][0]["dimension"],
                "days": 7,
                "agg": "avg",
            }]),
            _tool_msg("batch-1", payload),
        ]

        assert qr.deterministic_query_reply(messages) is None


def test_preplanned_batch_query_is_narrow_and_low_risk():
    assert qr.preplanned_batch_query_args("查一下最近7天的HRV和睡眠平均值") == {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "avg"},
            {"dimension": "sleep", "days": 7, "agg": "avg"},
        ],
    }
    assert qr.preplanned_batch_query_args("列出近两周步数和身体电量的最高值") == {
        "queries": [
            {"dimension": "activity", "days": 14, "agg": "max"},
            {"dimension": "body_battery", "days": 14, "agg": "max"},
        ],
    }
    assert qr.preplanned_batch_query_args("查询近3周的HRV和睡眠趋势") == {
        "queries": [
            {"dimension": "hrv", "days": 21, "agg": "trend"},
            {"dimension": "sleep", "days": 21, "agg": "trend"},
        ],
    }

    assert qr.preplanned_batch_query_args("查一下最近7天的HRV和睡眠数据") == {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": None},
            {"dimension": "sleep", "days": 7, "agg": None},
        ],
    }
    assert qr.preplanned_batch_query_args("列出近两周的步数和身体电量") == {
        "queries": [
            {"dimension": "activity", "days": 14, "agg": None},
            {"dimension": "body_battery", "days": 14, "agg": None},
        ],
    }
    assert qr.preplanned_batch_query_args("分析最近7天的HRV和睡眠") is None
    assert qr.preplanned_batch_query_args("查最近7天的HRV、睡眠和血氧") is None
    assert qr.preplanned_batch_query_args("查最近120天的HRV和睡眠") is None
    assert qr.preplanned_batch_query_args("查最近7天的HRV") is None
    assert qr.preplanned_batch_query_args("不要查HRV和睡眠数据") is None
    assert qr.preplanned_batch_query_args("你能查询HRV和睡眠数据吗") is None
    assert qr.preplanned_batch_query_args("查昨天的HRV和睡眠") is None
    assert qr.preplanned_batch_query_args("查过去24小时的HRV和睡眠") is None


def test_batch_sparse_window_falls_open_instead_of_claiming_full_window():
    messages = [
        _assistant_batch("batch-1", [
            {"dimension": "hrv", "days": 90, "agg": "trend"},
            {"dimension": "sleep", "days": 90, "agg": "avg"},
        ]),
        _tool_msg("batch-1", {
            "queries": [
                {
                    "dimension": "hrv",
                    "days": 90,
                    "agg": "trend",
                    "value": -12,
                    "unit": "ms",
                    "n": 2,
                },
                {
                    "dimension": "sleep",
                    "days": 90,
                    "agg": "avg",
                    "value": 76,
                    "n": 1,
                },
            ],
            "meta": {"executed": 2, "failed": 0},
        }),
    ]

    assert qr.deterministic_query_reply(messages) is None


@pytest.mark.parametrize(
    ("dimension", "value"),
    (("sleep", 120), ("hrv", float("inf")), ("activity", -1)),
)
def test_batch_nonfinite_or_impossible_scalar_falls_open(dimension, value):
    messages = [
        _assistant_batch("batch-1", [
            {"dimension": dimension, "days": 7, "agg": "avg"},
        ]),
        _tool_msg("batch-1", {
            "queries": [{
                "dimension": dimension,
                "days": 7,
                "agg": "avg",
                "value": value,
                "n": 7,
            }],
            "meta": {"executed": 1, "failed": 0},
        }),
    ]

    assert qr.deterministic_query_reply(messages) is None


def test_deterministic_reply_only_considers_current_turn_tools():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "old-write",
                "type": "function",
                "function": {"name": "health_record", "arguments": "{}"},
            }],
        },
        _tool_msg("old-write", {"id": 1}),
        {"role": "user", "content": "查最近7天的HRV和睡眠"},
        _assistant_batch("batch-1", [
            {"dimension": "hrv", "days": 7, "agg": "avg"},
            {"dimension": "sleep", "days": 7, "agg": "avg"},
        ]),
        _tool_msg("batch-1", {
            "queries": [
                {"dimension": "hrv", "days": 7, "agg": "avg", "value": 58, "n": 7},
                {"dimension": "sleep", "days": 7, "agg": "avg", "value": 76, "n": 7},
            ],
            "meta": {"executed": 2, "failed": 0},
        }),
    ]

    assert qr.deterministic_query_reply(messages) == (
        "近7天 HRV 平均值 58 ms。\n\n"
        "近7天 睡眠评分 平均值 76 分。"
    )


def test_bp_alias_dimension_normalizes_and_covers():
    # 模型传 dimension="血压" → 归一到 blood_pressure → 覆盖。
    messages = [
        _assistant_query("c1", "血压"),
        _tool_msg("c1", [{"record_date": "2026-07-12", "systolic": 120, "diastolic": 78,
                          "category": "正常偏高"}]),
    ]
    out = qr.deterministic_query_reply(messages)
    assert "最新血压 120/78 mmHg" in out


def test_safety_suffix_present_falls_open():
    # 不变量 3: 任一 tool result 带安全告警后缀 → 绝不短路 (安全文本须进强模型答案)。
    warned = {"total_amount": 1000, "target_amount": 2000, "records_count": 1,
              "records": [{"amount": 1000}]}
    content = json.dumps(warned, ensure_ascii=False) + qr._SAFETY_WARNING_MARKER + " 夜间血氧偏低"
    messages = [_assistant_query("c1", "water"), {"role": "tool", "tool_call_id": "c1", "content": content}]
    assert qr.deterministic_query_reply(messages) is None


def test_uncovered_dimension_falls_open():
    messages = [
        _assistant_query("c1", "genetic"),
        _tool_msg("c1", [{"gene_name": "MTHFR", "genotype": "CT"}]),
    ]
    assert qr.deterministic_query_reply(messages) is None


def test_mixed_covered_and_uncovered_falls_open():
    # 一个覆盖 + 一个未覆盖 → 整体 fall-open (全覆盖才短路)。
    messages = [
        _assistant_query("c1", "water"),
        _tool_msg("c1", {"total_amount": 1000, "target_amount": 2000, "records_count": 1,
                         "records": [{"amount": 1000}]}),
        _assistant_query("c2", "genetic"),
        _tool_msg("c2", [{"gene_name": "APOE"}]),
    ]
    assert qr.deterministic_query_reply(messages) is None


def test_non_query_tool_falls_open():
    # 不变量 4: 写工具在场 → 绝不短路 (查询回合绝不谎报/执行写操作的门不受影响)。
    messages = [{
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "c1", "type": "function",
                        "function": {"name": "health_record",
                                     "arguments": json.dumps({"record_type": "water"})}}],
    }, _tool_msg("c1", {"id": 1, "message": "已记录饮水 500ml"})]
    assert qr.deterministic_query_reply(messages) is None


def test_no_tool_calls_returns_none():
    assert qr.deterministic_query_reply([{"role": "user", "content": "你好"}]) is None
    assert qr.deterministic_query_reply([]) is None


def test_unparseable_result_content_falls_open():
    # health_query 覆盖维度, 但结果被截断解析不回 → fall-open。
    messages = [
        _assistant_query("c1", "weight"),
        {"role": "tool", "tool_call_id": "c1", "content": '[{"record_date":"2026-07-12","weig'},
    ]
    assert qr.deterministic_query_reply(messages) is None


def test_missing_result_for_call_falls_open():
    # tool_call 没有对应 tool result (配对不上) → 保守 fall-open。
    messages = [_assistant_query("c1", "water")]
    assert qr.deterministic_query_reply(messages) is None
