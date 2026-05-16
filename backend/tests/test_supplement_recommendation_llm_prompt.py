from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

from app.services.supplement_recommendation_llm import SupplementRecommendationServiceLLM


def test_llm_supplement_prompt_uses_conservative_mthfr_language():
    """MTHFR 只能提示结合化验和专业意见, 不能生成确定性补剂指令."""
    service = SupplementRecommendationServiceLLM()
    captured: dict[str, str] = {}

    async def fake_analyze_with_prompt(system_prompt: str, user_prompt: str):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return json.dumps({
            "health_analysis": {},
            "recommendations": [],
            "timing_suggestions": {},
            "precautions": [],
            "overall_rating": {},
        })

    service.llm_analyzer = Mock()
    service.llm_analyzer.analyze_with_prompt = fake_analyze_with_prompt

    asyncio.run(service._generate_llm_recommendation(
        profile=None,
        health_data=None,
        workout_data=None,
        diet_data=None,
        supplement_status={},
        knowledge_results=[],
        debug_info=None,
        genetic_data=[{
            "gene": "MTHFR",
            "variant": "C677T",
            "genotype": "TT",
            "risk": "high",
            "category": "nutrition",
            "result": "叶酸代谢降低",
        }],
    ))

    prompt = captured["system_prompt"]
    assert "必须使用活性叶酸" not in prompt
    assert "直接影响补剂选择和剂量" not in prompt
    assert "结合同型半胱氨酸" in prompt
    assert "医生或营养师" in prompt
