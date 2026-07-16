"""汇总卡族·睡眠 · sleep_summary composer 契约 + R4 测试。

契约字段必须与 mobile SleepSummaryCard 的 parse*(range_label/nights[date,score,duration_h,
deep_min]/averages/duration/observations)一字对齐 —— 跨界漂移 = 静默空卡。observations 必须
确定性 + factual(不判诊断、不消费 quality_assessment,守 R4)。信封 v 必须整数 1。
"""
from app.services.genui.sleep_summary import (
    build_sleep_summary,
    render_sleep_summary_block,
    SLEEP_SUMMARY_TYPE,
)
from app.services.atomic_capability_registry import (
    get_atomic_capability,
    validate_dynamic_view,
)


def _analysis():
    return {
        "status": "success",
        "days_analyzed": 3,
        "average_sleep_score": 80,
        "average_sleep_duration_minutes": 444,
        "average_sleep_duration_hours": 7.4,
        "average_deep_sleep_minutes": 95,
        "quality_assessment": {"level": "良好", "summary": "整体睡眠质量良好"},  # 绝不能被消费
        "recommendations": ["保持规律作息"],
        "daily_data": [
            {"date": "2026-07-12", "sleep_score": 82, "total_sleep_duration": 445,
             "deep_sleep_duration": 98, "rem_sleep_duration": 110, "awake_duration": 20},
            {"date": "2026-07-11", "sleep_score": 79, "total_sleep_duration": 440,
             "deep_sleep_duration": 92, "rem_sleep_duration": 105, "awake_duration": 25},
            {"date": "2026-07-10", "sleep_score": 78, "total_sleep_duration": 430,
             "deep_sleep_duration": 88, "rem_sleep_duration": 100, "awake_duration": 30},
        ],
    }


def test_descriptor_shape_matches_mobile_contract():
    d = build_sleep_summary(_analysis())
    assert d is not None
    assert d["type"] == SLEEP_SUMMARY_TYPE == "sleep_summary"
    assert d["v"] == 1  # 整数信封版本(移动端 parser 校验 v===1)
    data = d["data"]
    assert data["range_label"] == "近3天"
    # nights 最新在前,字段逐一对齐 mobile parseNights
    assert [n["date"] for n in data["nights"]] == ["2026-07-12", "2026-07-11", "2026-07-10"]
    n0 = data["nights"][0]
    assert set(n0) == {"date", "score", "duration_h", "deep_min"}
    assert n0["score"] == 82 and n0["duration_h"] == 7.4 and n0["deep_min"] == 98
    assert set(data["averages"]) == {"score", "duration_h", "deep_min"}
    assert data["duration"] == {"current_h": 7.4, "target_h": 8.0}
    for o in data["observations"]:
        assert set(o) == {"severity", "label", "detail"}
        assert o["severity"] in {"normal", "caution", "risk"}


def test_descriptor_golden_exact():
    """黄金样本:整个 descriptor 钉死,任一字段改名/重排/观察文案漂移即炸。"""
    assert build_sleep_summary(_analysis()) == {
        "type": "sleep_summary",
        "v": 1,
        "data": {
            "range_label": "近3天",
            "nights": [
                {"date": "2026-07-12", "score": 82, "duration_h": 7.4, "deep_min": 98},
                {"date": "2026-07-11", "score": 79, "duration_h": 7.3, "deep_min": 92},
                {"date": "2026-07-10", "score": 78, "duration_h": 7.2, "deep_min": 88},
            ],
            "averages": {"score": 80, "duration_h": 7.4, "deep_min": 95},
            "observations": [
                {"severity": "normal", "label": "睡眠时长充足", "detail": "平均 7.4h,一般建议 7–9h。"},
                {"severity": "normal", "label": "深睡充足", "detail": "平均 95 分钟。"},
                {"severity": "normal", "label": "睡眠评分", "detail": "近期平均 80(设备评分)。"},
            ],
            "duration": {"current_h": 7.4, "target_h": 8.0},
        },
    }


def test_r4_never_consumes_quality_assessment_and_no_imperative():
    obs = build_sleep_summary(_analysis())["data"]["observations"]
    joined = " ".join(o["label"] + o["detail"] for o in obs)
    assert "良好" not in joined  # 服务端 quality_assessment 绝不泄漏进卡片
    for banned in ("必须", "务必", "一定要", "应该马上"):
        assert banned not in joined


def test_short_sleep_and_low_deep_flag_caution():
    a = _analysis()
    a["average_sleep_duration_hours"] = 5.8   # < 6.5 → 偏短
    a["average_deep_sleep_minutes"] = 40      # < 60 → 偏少
    labels = {o["label"]: o["severity"] for o in build_sleep_summary(a)["data"]["observations"]}
    assert labels.get("睡眠偏短") == "caution"
    assert labels.get("深睡偏少") == "caution"


def test_range_label_from_days_analyzed_and_single_night_is_recent_not_yesterday():
    # 单夜 → 「最近一晚」(不谎称昨晚,稀疏同步下可能是几天前)
    one = {"days_analyzed": 1, "daily_data": [
        {"date": "2026-07-09", "sleep_score": 80, "total_sleep_duration": 445}]}
    assert build_sleep_summary(one)["data"]["range_label"] == "最近一晚"
    # 标签用 days_analyzed(与 averages 窗口一致),即便展示夜数被 _MAX_NIGHTS 截断
    many = {"days_analyzed": 30, "average_sleep_duration_hours": 7.0,
            "daily_data": [{"date": f"2026-06-{d:02d}", "sleep_score": 80,
                            "total_sleep_duration": 420} for d in range(1, 13)]}
    out = build_sleep_summary(many)["data"]
    assert out["range_label"] == "近30天"
    assert len(out["nights"]) == 7  # 表只展示最近 7 夜,但标签反映真实 30 天窗口


def test_empty_daily_data_returns_none_fail_open():
    assert build_sleep_summary({"daily_data": []}) is None
    assert build_sleep_summary({}) is None
    assert build_sleep_summary(None) is None  # type: ignore[arg-type]


def test_zero_and_nan_metrics_degrade_not_crash():
    a = {
        "average_sleep_score": 0, "average_sleep_duration_hours": float("nan"),
        "average_deep_sleep_minutes": 0,
        "daily_data": [{"date": "2026-07-12", "sleep_score": float("inf"),
                        "total_sleep_duration": 445, "deep_sleep_duration": None}],
    }
    d = build_sleep_summary(a)
    assert d is not None
    block = render_sleep_summary_block(d)
    assert "NaN" not in block and "Infinity" not in block  # 合法 JSON
    n0 = d["data"]["nights"][0]
    assert n0["score"] is None and n0["deep_min"] is None  # inf/None → 缺值
    assert n0["duration_h"] == 7.4
    # 0 均值不出误导观察,nan 时长不建进度条
    assert "duration" not in d["data"]
    labels = {o["label"] for o in d["data"]["observations"]}
    assert not (labels & {"睡眠偏短", "睡眠时长充足", "深睡偏少", "深睡充足"})


def test_registered_capability_and_view_validates():
    cap = get_atomic_capability("sleep_summary")
    assert cap is not None
    assert cap.action_types == ("route.open",)
    assert cap.safety_boundary == "suggest_only"
    assert set(("range_label", "nights", "averages")).issubset(set(cap.data_required_fields))
    d = build_sleep_summary(_analysis())
    card = {"type": "sleep_summary", "surface": "mobile.chat", "data": d["data"]}
    view = {"sections": [{"cards": [card]}]}
    assert validate_dynamic_view(view) == []


def test_render_block_is_reva_ui_fence_with_integer_version():
    block = render_sleep_summary_block(build_sleep_summary(_analysis()))
    assert block.startswith("```reva-ui\n") and block.rstrip().endswith("```")
    assert '"type":"sleep_summary"' in block
    assert '"v":1' in block and '"v":"v1"' not in block  # 锁死整数版本契约
