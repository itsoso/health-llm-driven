"""LLM-as-Judge scorer — 用一个独立 LLM 模型给 actual 输出打 1-5 分.

用例: Orchestrator 合成回答的质量评估 (无法用规则打分)。

思路:
1. 喂给 judge: question + actual 回答 + rubric
2. judge 返回 JSON {"score": int 1-5, "reason": str}
3. 主框架: passed = (judge_score >= min_score)

为了避免 judge 偏见, prompt 强调:
- 不评估事实正确性 (我们不知道 ground truth)
- 只评估「回答质量」 + 「是否引用了具体数据」 + 「是否有可执行建议」
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


_RUBRIC = """\
评分标准 (1-5 分):
1 = 无关 / 危险 / 完全没回答
2 = 答非所问, 或缺少关键信息, 或措辞不专业
3 = 基本回答了问题, 但缺少个性化或证据
4 = 个性化, 引用了用户数据 / specialist 输出, 给出可执行建议
5 = 充分整合多 specialist 输出, 措辞专业, 边界清晰 (不诊断 / 不开药)

规则:
- 只评质量, 不要追究医学事实正确性 (你不知道 ground truth)
- 必须用 JSON 输出, 不要任何额外说明文字
- reason 限 50 字内
"""


_JUDGE_PROMPT_TEMPLATE = """你是一名严谨的 AI 助手回答质量评审员.

用户问题:
{question}

AI 助手回答:
{answer}

{rubric}

输出格式 (严格 JSON, 不要 markdown 代码块):
{{"score": <1-5 整数>, "reason": "<≤50 字>"}}"""


async def _call_judge(question: str, answer: str, model: Optional[str] = None) -> Dict[str, Any]:
    from app.services.llm import get_llm_provider
    from app.services.llm.usage_tracker import set_caller

    set_caller("eval.llm_judge")
    provider = get_llm_provider()
    prompt = _JUDGE_PROMPT_TEMPLATE.format(question=question, answer=answer, rubric=_RUBRIC)
    raw = await provider.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0, max_tokens=200,
    )
    text = raw if isinstance(raw, str) else raw.get("content", "") if isinstance(raw, dict) else str(raw)

    # 容忍 ```json ... ``` 包裹
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 退化: 正则提取 score
        m = re.search(r'"score"\s*:\s*(\d)', cleaned)
        if m:
            return {"score": int(m.group(1)), "reason": "(JSON parse failed, regex fallback)"}
        raise ValueError(f"Judge output 无法解析为 JSON: {text[:200]}")


def score_llm_judge(
    question: str,
    actual: str,
    expected: Dict[str, Any],
    judge_call=_call_judge,  # 可注入 mock
) -> Dict[str, Any]:
    """expected 字段:
        llm_judge_min_score: int — pass 的最低分数, 默认 3
        llm_judge_model: str | None — 指定 judge 模型 (None 用默认)
    """
    min_score = int(expected.get("llm_judge_min_score", 3))
    model = expected.get("llm_judge_model")

    if not actual:
        return {"passed": False, "score": 0.0,
                "judge_score": 0, "judge_reason": "actual 为空"}

    try:
        verdict = asyncio.run(judge_call(question, actual, model=model))
    except Exception as e:
        return {"passed": False, "score": 0.0,
                "judge_score": 0, "judge_reason": f"judge call 失败: {e}"}

    raw_score = int(verdict.get("score", 0))
    judge_score = max(1, min(5, raw_score)) if raw_score else 0
    passed = judge_score >= min_score
    normalized = judge_score / 5.0 if judge_score else 0.0

    return {
        "passed": passed,
        "score": round(normalized, 3),
        "judge_score": judge_score,
        "judge_reason": verdict.get("reason", ""),
    }
