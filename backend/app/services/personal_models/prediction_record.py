"""Helpers for attaching PersonalPrediction snapshots to execution events."""

from __future__ import annotations

from typing import Any, Dict

BOUNDARY_TEXT = "预测记录仅用于后续观察性复盘, 不证明单个行动造成指标变化, 不替代医生诊断、处方或治疗。"

_CONTEXT_KEYS = (
    "id",
    "prediction_type",
    "metric",
    "domain",
    "horizon_days",
    "baseline",
    "unit",
    "expected_signal",
    "confidence",
    "uncertainty",
    "evidence_tier",
    "source_model",
    "model_version",
    "claim_boundary",
    "requires_clinician",
    "review_hint",
)


def prediction_context_for_attachment(prediction: Dict[str, Any]) -> Dict[str, Any] | None:
    """Return the stable subset safe to carry on Agenda/Daily Plan actions."""
    if not isinstance(prediction, dict):
        return None
    if not prediction.get("id") or not prediction.get("metric"):
        return None
    expected_signal = prediction.get("expected_signal")
    if not isinstance(expected_signal, dict):
        return None

    context = {key: prediction[key] for key in _CONTEXT_KEYS if key in prediction}
    context.setdefault("claim_boundary", BOUNDARY_TEXT)
    return context


def prediction_record_from_context(
    prediction: Dict[str, Any] | None,
    *,
    attached_to: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Normalize a carried prediction context into an execution snapshot record."""
    context = prediction_context_for_attachment(prediction or {})
    if context is None:
        return None

    expected_signal = dict(context["expected_signal"])
    expected_signal.setdefault("metric", context["metric"])
    record = dict(context)
    record["expected_signal"] = expected_signal
    record["source"] = (
        prediction.get("source")
        or context.get("source_model")
        or context.get("model_version")
        or "personal_prediction"
    )
    record["attached_to"] = {
        "object_type": str(attached_to.get("object_type") or "unknown"),
        "object_id": str(attached_to.get("object_id") or "unknown"),
    }
    record["attachment_version"] = "prediction_record_attachment_v1"
    return record


def attach_prediction_record_to_snapshot(
    snapshot: Dict[str, Any],
    *,
    object_type: str,
    object_id: str,
) -> Dict[str, Any]:
    """Attach prediction_record when a snapshot carries a PersonalPrediction context."""
    out = dict(snapshot)
    if isinstance(out.get("prediction_record"), dict):
        source = out["prediction_record"]
    elif isinstance(out.get("personal_prediction_context"), dict):
        source = out["personal_prediction_context"]
    else:
        trajectory = out.get("trajectory_context")
        source = (
            trajectory.get("personal_prediction_context")
            if isinstance(trajectory, dict) and isinstance(trajectory.get("personal_prediction_context"), dict)
            else None
        )
    record = prediction_record_from_context(
        source,
        attached_to={"object_type": object_type, "object_id": object_id},
    )
    if record:
        out["prediction_record"] = record
    return out
