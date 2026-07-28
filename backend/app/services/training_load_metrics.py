"""Deterministic training-load metrics shared by Twin and Episode paths."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence


ACWR_WINDOW_DAYS = 28
ACWR_REQUIRED_BASELINE_WEEKS = 3
ACWR_MIN_ACUTE_OBSERVED_DAYS = 5
ACWR_MIN_BASELINE_OBSERVED_DAYS = 18
ACWR_MIN_BASELINE_ACTIVE_DAYS = 2
ACWR_MIN_BASELINE_ACTIVE_WEEKS = 2
ACWR_MIN_BASELINE_LOAD_21D = 30.0


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
    baseline_load_21d: float
    acute_observed_days: int
    baseline_observed_days: int
    oldest_load_age_days: Optional[int]


def assess_acwr(
    daily_loads_newest_first: Sequence[float],
    *,
    observed_days_newest_first: Optional[Sequence[bool]] = None,
) -> AcwrAssessment:
    """Assess ACWR while withholding ratios without a chronic baseline.

    ``daily_loads_newest_first[0]`` is today's load. Negative or malformed
    values cannot represent training load. When an observation mask is
    supplied, zero-load days are distinguishable from missing sync days.
    """

    loads: list[float] = []
    invalid_load_data = False
    for raw in list(daily_loads_newest_first)[:ACWR_WINDOW_DAYS]:
        try:
            value = float(raw or 0)
        except (TypeError, ValueError):
            value = 0.0
            invalid_load_data = True
        if not math.isfinite(value) or value < 0:
            value = 0.0
            invalid_load_data = True
        loads.append(value)
    loads.extend([0.0] * (ACWR_WINDOW_DAYS - len(loads)))

    observed_supplied = observed_days_newest_first is not None
    if observed_supplied:
        observed = [
            bool(value)
            for value in list(observed_days_newest_first or [])[:ACWR_WINDOW_DAYS]
        ]
        observed.extend([False] * (ACWR_WINDOW_DAYS - len(observed)))
        # A persisted workout is itself proof that the day was observed.
        observed = [seen or load > 0 for seen, load in zip(observed, loads)]
    else:
        observed = [load > 0 for load in loads]

    acute_sum = sum(loads[:7])
    chronic_sum = sum(loads)
    acute_avg = acute_sum / 7
    chronic_avg = chronic_sum / ACWR_WINDOW_DAYS
    raw_acwr = (
        round(acute_avg / chronic_avg, 2)
        if chronic_avg > 0 and not invalid_load_data
        else None
    )

    positive_indices = [i for i, value in enumerate(loads) if value > 0]
    baseline_active_days = sum(1 for value in loads[7:] if value > 0)
    baseline_load_21d = sum(loads[7:])
    baseline_weeks_with_load = sum(
        1
        for start in (7, 14, 21)
        if any(value > 0 for value in loads[start : start + 7])
    )
    acute_observed_days = sum(1 for value in observed[:7] if value)
    baseline_observed_days = sum(1 for value in observed[7:] if value)
    oldest_load_age_days = max(positive_indices) if positive_indices else None

    unavailable_reason = None
    if invalid_load_data:
        unavailable_reason = "invalid_training_load_data"
    elif acute_sum <= 0:
        unavailable_reason = "no_recent_training"
    elif observed_supplied and (
        acute_observed_days < ACWR_MIN_ACUTE_OBSERVED_DAYS
        or baseline_observed_days < ACWR_MIN_BASELINE_OBSERVED_DAYS
    ):
        unavailable_reason = "insufficient_data_coverage"
    elif observed_supplied and (
        baseline_active_days < ACWR_MIN_BASELINE_ACTIVE_DAYS
        or baseline_weeks_with_load < ACWR_MIN_BASELINE_ACTIVE_WEEKS
        or baseline_load_21d < ACWR_MIN_BASELINE_LOAD_21D
    ):
        unavailable_reason = "insufficient_chronic_baseline"
    elif (
        not observed_supplied
        and (
            baseline_weeks_with_load < ACWR_REQUIRED_BASELINE_WEEKS
            or baseline_load_21d < ACWR_MIN_BASELINE_LOAD_21D
        )
    ):
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
        baseline_load_21d=round(baseline_load_21d, 1),
        acute_observed_days=acute_observed_days,
        baseline_observed_days=baseline_observed_days,
        oldest_load_age_days=oldest_load_age_days,
    )
