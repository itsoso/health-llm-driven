from app.services.agent_processing_summary import build_processing_summary
from app.services.agent_output_quality import needs_input_clarification


def test_incomplete_utterance_requires_clarification_instead_of_prior_intent():
    assert needs_input_clarification("嗯") is True
    assert needs_input_clarification("查一下最近七天睡眠") is False


def test_processing_summary_reports_evidence_density_without_raw_rows():
    summary = build_processing_summary(
        "get_sleep_data",
        {"days": 7},
        '[{"sleep_score": 80}, {"sleep_score": 82}]',
        success=True,
    )

    assert summary == {
        "source": "睡眠记录",
        "time_range": "最近 7 天",
        "row_count": 2,
        "availability": "available",
        "failure_reason": None,
        "next_action": "基于已取得的证据继续分析",
    }
    assert "sleep_score" not in str(summary)


def test_processing_summary_explains_failure_and_next_action():
    summary = build_processing_summary(
        "health_query",
        {},
        "Error: timeout",
        success=False,
    )

    assert summary["availability"] == "unavailable"
    assert summary["failure_reason"] == "数据源响应超时"
    assert summary["next_action"]
