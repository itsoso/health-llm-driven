"""Deterministic training-load metrics shared by Twin and Episode paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


# The 28-day window is the acute week plus the preceding three weeks. Require
# actual load in those prior weeks before publishing an injury-risk ratio.
ACWR_WINDOW_DAYS = 28
ACWR_REQUIRED_BASELINE_WEEKS = 3


@dataclass(frozen=True)
class AcwrAssessment:
    acute_load_7d: float
    chronic_load_28d: float
    raw_acwr: Optional[float]
    acwr: Optional[float]
    zone: str
    reliable: bool
    unavailable_reason: Optional[str]
    data_days: int
    baseline_active_days: int
    baseline_weeks_with_load: int
    oldest_load_age_days: Optional[int]


def assess_acwr(daily_loads_newest_first: Sequence[float]) -> AcwrAssessment:
    """Assess ACWR while withholding ratios without a chronic baseline.

    ``daily_loads_newest_first[0]`` is today's load. Negative or malformed
    values are treated as zero because they cannot represent training load.
    """

    loads: list[float] = []
    for raw in list(daily_loads_newest_first)[:ACWR_WINDOW_DAYS]:
        try:
            loads.append(max(0.0, float(raw or 0)))
        except (TypeError, ValueError):
            loads.append(0.0)
    loads.extend([0.0] * (ACWR_WINDOW_DAYS - len(loads)))

    acute_sum = sum(loads[:7])
    chronic_sum = sum(loads)
    acute_avg = acute_sum / 7
    chronic_avg = chronic_sum / ACWR_WINDOW_DAYS
    raw_acwr = round(acute_avg / chronic_avg, 2) if chronic_avg > 0 else None

    positive_indices = [i for i, value in enumerate(loads) if value > 0]
    baseline_active_days = sum(1 for value in loads[7:] if value > 0)
    baseline_weeks_with_load = sum(
        1
        for start in (7, 14, 21)
        if any(value > 0 for value in loads[start : start + 7])
    )
    oldest_load_age_days = max(positive_indices) if positive_indices else None

    unavailable_reason = None
    if acute_sum <= 0:
        unavailable_reason = "no_recent_training"
    elif baseline_weeks_with_load < ACWR_REQUIRED_BASELINE_WEEKS:
        unavailable_reason = "insufficient_chronic_baseline"

    reliable = unavailable_reason is None and raw_acwr is not None
    acwr = raw_acwr if reliable else None

    if acwr is None:
        zone = "unknown"
    elif acwr < 0.8:
        zone = "undertraining"
    elif acwr <= 1.3:
        zone = "optimal"
    elif acwr <= 1.5:
        zone = "danger"
    else:
        zone = "overtraining"

    return AcwrAssessment(
        acute_load_7d=round(acute_sum, 1),
        chronic_load_28d=round(chronic_sum, 1),
        raw_acwr=raw_acwr,
        acwr=acwr,
        zone=zone,
        reliable=reliable,
        unavailable_reason=unavailable_reason,
        data_days=len(positive_indices),
        baseline_active_days=baseline_active_days,
        baseline_weeks_with_load=baseline_weeks_with_load,
        oldest_load_age_days=oldest_load_age_days,
    )
