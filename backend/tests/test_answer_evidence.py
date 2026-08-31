from datetime import UTC, datetime
import json

from app.services.answer_evidence import (
    answer_evidence_sha256,
    build_answer_evidence,
    normalize_answer_evidence,
)
from app.services.health_evidence.contracts import (
    ContextBudget,
    ContextGap,
    EvidenceConflict,
    GapState,
    HealthIntentEnvelope,
    PersonalEvidenceItem,
    PersonalEvidencePacket,
    RiskLevel,
)


def test_builds_concrete_basis_from_executed_batch_results():
    result = json.dumps(
        {
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
                    "note": "略降",
                },
            ],
            "meta": {"executed": 2, "failed": 0},
        },
        ensure_ascii=False,
    )

    evidence = build_answer_evidence(
        tool_calls=[("health_query_batch", {}, result)],
    )

    assert evidence == {
        "version": "answer-evidence.v1",
        "summary": "本轮获得 2 条可核对数据",
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
        ],
        "limitations": [],
    }


def test_turns_no_data_into_an_honest_limitation():
    result = json.dumps(
        {
            "status": "no_data",
            "message": "没有足够的睡眠数据",
            "days_analyzed": 0,
        },
        ensure_ascii=False,
    )

    evidence = build_answer_evidence(
        tool_calls=[("health_query", {"dimension": "sleep", "days": 7}, result)],
    )

    assert evidence == {
        "version": "answer-evidence.v1",
        "summary": "本轮有 1 项数据限制",
        "basis": [],
        "limitations": [
            {
                "id": "tool-1-limitation",
                "title": "睡眠数据不足",
                "detail": "没有足够的睡眠数据",
                "handling": "未将缺失数据推断为正常；本次回答采用保守表达",
            }
        ],
    }


def test_nested_tool_payloads_are_never_rendered_as_answer_evidence():
    batch_result = json.dumps(
        {
            "queries": [{
                "dimension": "hrv",
                "value": {"private": "must-not-leak"},
                "unit": "ms",
            }],
        },
        ensure_ascii=False,
    )
    diet_result = json.dumps(
        {
            "meals": [{
                "meal_type": "lunch",
                "food_items": {"private": "must-not-leak"},
                "calories": 420,
            }],
        },
        ensure_ascii=False,
    )

    evidence = build_answer_evidence(
        tool_calls=[
            ("health_query_batch", {}, batch_result),
            ("health_query", {"dimension": "diet"}, diet_result),
        ],
    )

    assert evidence is None


def test_health_packet_only_exposes_selected_scalar_evidence():
    intent = HealthIntentEnvelope(
        query="昨晚睡得怎样，今天适合锻炼吗？",
        intent_id="health_advice.recovery.exercise",
        intent="recovery exercise advice",
        domain="movement",
        risk_level=RiskLevel.MEDIUM,
        requires_personal_context=True,
        requires_authority=True,
    )
    packet = PersonalEvidencePacket(
        generated_at=datetime(2026, 8, 31, tzinfo=UTC),
        intent=intent,
        mandatory_categories=("wearable", "medication"),
        evidence=(
            PersonalEvidenceItem(
                evidence_id="wearable.hrv.latest",
                category="wearable",
                kind="metric",
                label="HRV",
                value=31,
                unit="ms",
                observed_at="2026-08-31T07:55:00+08:00",
                freshness="current",
                reliability="high",
                source_kind="garmin",
            ),
            PersonalEvidenceItem(
                evidence_id="wearable.raw.payload",
                category="wearable",
                kind="payload",
                label="设备原始载荷",
                value={"private": "must-not-leak"},
                source_kind="garmin",
            ),
        ),
        gaps=(
            ContextGap(
                gap_id="medication.current",
                category="medication",
                state=GapState.ABSENT,
                detail="本轮没有当前用药记录",
            ),
        ),
        budget=ContextBudget(max_items=6, selected_items=2, truncated=False),
    )

    evidence = build_answer_evidence(personal_packet=packet)

    assert evidence is not None
    assert evidence["basis"] == [
        {
            "id": "wearable.hrv.latest",
            "label": "HRV",
            "observation": "31 ms",
            "source": "Garmin",
            "purpose": "用于评估恢复与活动承受度",
            "observed_at": "2026-08-31T07:55:00+08:00",
            "freshness": "current",
            "confidence": "high",
        }
    ]
    assert "must-not-leak" not in json.dumps(evidence, ensure_ascii=False)
    assert evidence["limitations"] == [
        {
            "id": "medication.current",
            "title": "用药信息缺失",
            "detail": "本轮没有当前用药记录",
            "handling": "未将缺失信息推断为正常或不存在",
        }
    ]


def test_packet_marks_stale_low_confidence_conflicts_and_partial_loading():
    intent = HealthIntentEnvelope(
        query="今天适合锻炼吗？",
        intent_id="health_advice.recovery.exercise",
        intent="recovery exercise advice",
        domain="movement",
        risk_level=RiskLevel.MEDIUM,
        requires_personal_context=True,
        requires_authority=True,
    )
    packet = PersonalEvidencePacket(
        generated_at=datetime(2026, 8, 31, tzinfo=UTC),
        intent=intent,
        mandatory_categories=("wearable",),
        evidence=(
            PersonalEvidenceItem(
                evidence_id="wearable.hrv.latest",
                category="wearable",
                kind="metric",
                label="HRV",
                value=31,
                unit="ms",
                observed_at="2026-08-20T07:55:00+08:00",
                freshness="stale",
                reliability="low",
                source_kind="garmin",
            ),
        ),
        failed_partitions=("medication",),
        conflicts=(
            EvidenceConflict(
                conflict_id="wearable.hrv.conflict",
                category="wearable",
                trusted_source="garmin",
                outlier_source="manual",
                detail="private conflict payload must not be exposed",
            ),
        ),
        budget=ContextBudget(max_items=1, selected_items=1, truncated=True),
    )

    evidence = build_answer_evidence(personal_packet=packet)

    assert evidence is not None
    assert evidence["summary"] == "本轮获得 1 条可核对数据，3 项需注意"
    assert evidence["basis"][0]["freshness"] == "stale"
    assert evidence["basis"][0]["confidence"] == "low"
    assert evidence["limitations"] == [
        {
            "id": "wearable.hrv.latest-quality",
            "title": "HRV需谨慎解读",
            "detail": "数据时间较旧，且可信度有限",
            "handling": "未将该项作为当前确定状态；本次回答采用保守表达",
        },
        {
            "id": "wearable.hrv.conflict",
            "title": "可穿戴数据存在冲突",
            "detail": "不同来源的记录不一致",
            "handling": "未将冲突数据合并为确定结论",
        },
        {
            "id": "personal-context-availability",
            "title": "部分健康数据不可完整使用",
            "detail": "有 1 类数据未成功加载；本轮依据已按相关性筛选",
            "handling": "未加载或未展示的数据不作为本轮结论依据",
        },
    ]
    assert "private conflict payload" not in json.dumps(
        evidence,
        ensure_ascii=False,
    )


def test_normalizer_rejects_unknown_fields_and_hash_binds_projection():
    evidence = build_answer_evidence(
        tool_calls=[(
            "health_query_batch",
            {},
            json.dumps({
                "queries": [{
                    "dimension": "hrv",
                    "days": 7,
                    "agg": "avg",
                    "value": 58,
                    "unit": "ms",
                }],
            }),
        )],
    )
    assert evidence is not None
    digest = answer_evidence_sha256(evidence)
    assert len(digest) == 64
    assert normalize_answer_evidence(evidence) == evidence

    tampered = {**evidence, "private_prompt": "do not expose"}
    assert normalize_answer_evidence(tampered) is None
    assert answer_evidence_sha256(tampered) != digest
