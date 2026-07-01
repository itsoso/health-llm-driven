# -*- coding: utf-8 -*-
"""exam_explain_service —— LLM explanation 输出走宽松 JSON 解析回归。

钉:弱模型/中文语境常吐弯引号 key / 全角分隔符 / 裸 key,strict json.loads 直接抛 →
整个解释包静默掉 explanation=None(用户白等)。改走 lenient_loads 后这些可修复输出能解析;
真不可修复时仍 fail-soft 到 explanation=None(包其余部分照常返回)。
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.services.exam_explain_service import build_exam_explain
from tests.conftest import create_authenticated_user


def _exam_with_abnormal(db, user_id):
    exam = MedicalExam(
        user_id=user_id, exam_date=date(2026, 5, 1), exam_type="comprehensive",
    )
    db.add(exam)
    db.flush()
    db.add(MedicalExamItem(
        exam_id=exam.id, item_name="低密度脂蛋白", item_code="LDL",
        value=4.9, unit="mmol/L", reference_range="< 3.4", is_abnormal="high",
    ))
    db.commit()
    db.refresh(exam)
    return exam


def _mock_provider(raw_text):
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=raw_text)
    return provider


def test_explain_parses_smart_quote_json(db):
    """弯引号 key + 全角分隔符:strict json.loads 抛,lenient_loads 修复后填充 explanation。"""
    user, _ = create_authenticated_user(db)
    exam = _exam_with_abnormal(db, user.id)
    raw = '{“summary”：“LDL 偏高,注意饮食”，“actions”：[]，“recheck_window_days”：30}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)                        # 钉:旧的 raw json.loads 会炸
    with patch("app.services.llm.get_llm_provider", return_value=_mock_provider(raw)):
        out = build_exam_explain(db, user.id, exam.id)
    assert out is not None
    assert out["explanation"] is not None
    assert out["explanation"]["summary"].startswith("LDL 偏高")
    assert out["explanation"]["recheck_window_days"] == 30


def test_explain_bare_key_json(db):
    """裸 key(无引号):strict json.loads 拒,lenient_loads 补引号后解析。"""
    user, _ = create_authenticated_user(db)
    exam = _exam_with_abnormal(db, user.id)
    raw = '{summary: "复查指标", actions: [], recheck_window_days: 60}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    with patch("app.services.llm.get_llm_provider", return_value=_mock_provider(raw)):
        out = build_exam_explain(db, user.id, exam.id)
    assert out["explanation"] is not None
    assert out["explanation"]["summary"] == "复查指标"
    assert out["explanation"]["recheck_window_days"] == 60


def test_explain_happy_path_unchanged(db):
    """合法 JSON:走快路径,行为零变化。"""
    user, _ = create_authenticated_user(db)
    exam = _exam_with_abnormal(db, user.id)
    raw = json.dumps({"summary": "正常", "actions": [], "recheck_window_days": 90},
                     ensure_ascii=False)
    with patch("app.services.llm.get_llm_provider", return_value=_mock_provider(raw)):
        out = build_exam_explain(db, user.id, exam.id)
    assert out["explanation"]["summary"] == "正常"
    assert out["explanation"]["recheck_window_days"] == 90


def test_explain_unrepairable_stays_fail_soft(db):
    """真不可修复输出:explanation=None,但解释包其余部分照常返回(fail-soft 未变)。"""
    user, _ = create_authenticated_user(db)
    exam = _exam_with_abnormal(db, user.id)
    with patch("app.services.llm.get_llm_provider",
               return_value=_mock_provider("这报告看着还行,没法给 JSON")):
        out = build_exam_explain(db, user.id, exam.id)
    assert out is not None
    assert out["explanation"] is None          # fail-soft 保持
    assert len(out["abnormal_items"]) == 1     # 包其余部分完好
