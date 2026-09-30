# -*- coding: utf-8 -*-
"""Deterministic numeric floor for acute vital readings stated in user text.

A turn such as "记一下血压185/115" reads like a casual record, but the value is
in the SafetyGuardian acute range. Routing must not hand it to the fast model
and compact record prompt, so ``classify_answer_task_tier`` and the fast-route
gate consult this parser first. Thresholds mirror the acute SafetyGuardian
vitals/CGM rules; the floor only ever tightens routing (never loosens it) and
does not replace the post-write SafetyGuardian evaluation.

Parsing is keyword-anchored: a number counts only when it follows a vital-sign
keyword within the same clause, so dates ("9/30"), step counts and weights are
not misread as blood pressure.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Gap between a keyword and its value: no digits, no clause terminators.
_GAP = r"[^\d。；;!?！？\n]{0,8}"

# 血压计 / 血压仪 are devices, not readings.
_BP_KEYWORD = r"(?:血压(?![计仪])|(?<![a-z])bp)"
_BP_PAIR_RE = re.compile(
    rf"{_BP_KEYWORD}{_GAP}(\d{{2,3}})\s*(?:/|-|,|、|\s)\s*(\d{{2,3}})(?!\d)"
)
_BP_MMHG_PAIR_RE = re.compile(r"(?<!\d)(\d{2,3})\s*/\s*(\d{2,3})\s*mm\s*hg")
_BP_SYSTOLIC_RE = re.compile(rf"(?:收缩压|高压){_GAP}(\d{{2,3}})(?!\d)")
_BP_DIASTOLIC_RE = re.compile(rf"(?:舒张压|低压){_GAP}(\d{{2,3}})(?!\d)")

_SPO2_RE = re.compile(rf"(?:血氧饱和度|氧饱和度|血氧|spo2){_GAP}(\d{{2,3}})(?!\d)")

_HR_RE = re.compile(rf"(?:静息心率|心率|脉搏|心跳){_GAP}(\d{{2,3}})(?!\d)")
_NEGATION_PREFIXES = ("没有", "没", "未", "不")
_EXERCISE_CONTEXT = (
    "运动", "跑", "骑", "训练", "健身", "游泳", "爬", "登山", "锻炼",
    "最大", "峰值", "最高", "比赛", "冲刺", "间歇", "hiit",
)

_GLUCOSE_RE = re.compile(
    rf"血糖{_GAP}(\d{{1,3}}(?:\.\d+)?)\s*(mmol/?l|mg/?dl)?"
)
_TEMPERATURE_RE = re.compile(
    rf"(?:体温|发烧|发热|烧到){_GAP}(\d{{2}}(?:\.\d+)?)(?!\d)"
)

# SafetyGuardian vitals.bp_severe_reading
_BP_SEVERE_SYSTOLIC = 180
_BP_SEVERE_DIASTOLIC = 120
# vitals.spo2_* (< 88 CRITICAL, 88-92 mild): floor below 90.
_SPO2_LOW = 90
# vitals.rhr_bradycardia (< 40); resting tachycardia well above the 100 rule.
_HR_LOW = 40
_HR_HIGH_AT_REST = 130
# cgm severe hypoglycaemia (< 54 mg/dL ≈ 3.0 mmol/L); hyperglycaemic crisis screen.
_GLUCOSE_LOW_MMOL = 3.0
_GLUCOSE_HIGH_MMOL = 16.7
_GLUCOSE_LOW_MG = 54
_GLUCOSE_HIGH_MG = 300
_TEMP_HIGH = 39.5
_TEMP_LOW = 35.0


def _normalized(text: Optional[str]) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def _plausible_bp(systolic: int, diastolic: int) -> bool:
    return 50 <= systolic <= 300 and 30 <= diastolic <= 200 and systolic > diastolic


def _bp_severe(text: str) -> bool:
    for pattern in (_BP_PAIR_RE, _BP_MMHG_PAIR_RE):
        for match in pattern.finditer(text):
            systolic, diastolic = int(match.group(1)), int(match.group(2))
            if not _plausible_bp(systolic, diastolic):
                continue
            if systolic >= _BP_SEVERE_SYSTOLIC or diastolic >= _BP_SEVERE_DIASTOLIC:
                return True
    if any(
        int(m.group(1)) >= _BP_SEVERE_SYSTOLIC for m in _BP_SYSTOLIC_RE.finditer(text)
    ):
        return True
    return any(
        int(m.group(1)) >= _BP_SEVERE_DIASTOLIC for m in _BP_DIASTOLIC_RE.finditer(text)
    )


def _spo2_low(text: str) -> bool:
    return any(int(m.group(1)) < _SPO2_LOW for m in _SPO2_RE.finditer(text))


def _in_exercise_context(text: str) -> bool:
    """Exercise wording that is not negated ("没运动" is rest, not exercise)."""
    for marker in _EXERCISE_CONTEXT:
        for match in re.finditer(re.escape(marker), text):
            prefix = text[max(0, match.start() - 2):match.start()]
            if not any(prefix.endswith(neg) for neg in _NEGATION_PREFIXES):
                return True
    return False


def _hr_extreme(text: str) -> bool:
    exercise = _in_exercise_context(text)
    for match in _HR_RE.finditer(text):
        value = int(match.group(1))
        if value < _HR_LOW:
            return True
        if value >= _HR_HIGH_AT_REST and not exercise:
            return True
    return False


def _glucose_extreme(text: str) -> bool:
    for match in _GLUCOSE_RE.finditer(text):
        value = float(match.group(1))
        unit = match.group(2) or ("mmol/l" if value <= 35 else "mg/dl")
        if unit.startswith("mmol"):
            if value <= _GLUCOSE_LOW_MMOL or value >= _GLUCOSE_HIGH_MMOL:
                return True
        elif value < _GLUCOSE_LOW_MG or value >= _GLUCOSE_HIGH_MG:
            return True
    return False


def _temperature_extreme(text: str) -> bool:
    for match in _TEMPERATURE_RE.finditer(text):
        value = float(match.group(1))
        if 30 <= value <= 45 and (value >= _TEMP_HIGH or value < _TEMP_LOW):
            return True
    return False


_CHECKS = (
    ("bp_severe", _bp_severe),
    ("spo2_low", _spo2_low),
    ("hr_extreme", _hr_extreme),
    ("glucose_extreme", _glucose_extreme),
    ("temperature_extreme", _temperature_extreme),
)


def acute_vital_reading(message: Optional[str]) -> Optional[str]:
    """Return the acute-vital reason label when the text states one, else None."""
    text = _normalized(message)
    if not text or not any(ch.isdigit() for ch in text):
        return None
    for label, check in _CHECKS:
        if check(text):
            return label
    return None
