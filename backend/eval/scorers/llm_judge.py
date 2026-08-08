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
- 如果用户问题末尾包含 [硬性语义断言], 必须逐项独立判断 AI 回答是否满足；
  否定、不确定、疑问或仅提及某行动不能算满足肯定行动断言
- 明确健康条件触发的行动（如“若持续偏高则就医”）属于肯定的条件式行动，
  不要把它误判成“不确定是否行动”
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
{{"score": <1-5 整数>, "reason": "<≤50 字>", "assertions": {{"<断言ID>": <true|false>}}}}
没有硬性语义断言时 assertions 输出空对象。"""


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
    judge_call=None,  # 可注入 mock; None 表示 call-time 解析模块级 _call_judge
) -> Dict[str, Any]:
    """expected 字段:
        llm_judge_min_score: int — pass 的最低分数, 默认 3
        llm_judge_model: str | None — 指定 judge 模型 (None 用默认)
        llm_judge_assertions: dict[str, str] — 必须全部由 judge 明确判 true 的语义断言
    """
    # default=_call_judge 会在 def 时把函数对象固化, 让 monkeypatch
    # lj_mod._call_judge 失效 (CI 跑 orchestrator runner case 时炸过).
    # 推到 call-time 解析, 模块属性变化才能被吃到.
    if judge_call is None:
        judge_call = _call_judge

    min_score = int(expected.get("llm_judge_min_score", 3))
    model = expected.get("llm_judge_model")
    raw_assertions = expected.get("llm_judge_assertions") or {}
    assertions = {str(key): str(value) for key, value in raw_assertions.items()}

    if not actual:
        return {"passed": False, "score": 0.0,
                "judge_score": 0, "judge_reason": "actual 为空",
                "assertions": {}, "assertion_failures": list(assertions)}

    judge_question = question
    if assertions:
        assertion_contract = json.dumps(assertions, ensure_ascii=False, sort_keys=True)
        judge_question = (
            f"{question}\n\n[硬性语义断言]\n"
            "以下每项必须根据 AI 回答的实际语义独立判定 true/false；"
            "缺失或无法确认一律判 false。\n"
            f"{assertion_contract}"
        )

    try:
        verdict = asyncio.run(judge_call(judge_question, actual, model=model))
    except Exception as e:
        return {"passed": False, "score": 0.0,
                "judge_score": 0, "judge_reason": f"judge call 失败: {e}",
                "assertions": {}, "assertion_failures": list(assertions)}

    try:
        if not isinstance(verdict, dict):
            raise TypeError(f"expected object, got {type(verdict).__name__}")
        raw_score = int(verdict.get("score", 0))
    except (TypeError, ValueError, AttributeError) as e:
        return {
            "passed": False,
            "score": 0.0,
            "judge_score": 0,
            "judge_reason": f"judge verdict 无效: {e}",
            "assertions": {},
            "assertion_failures": list(assertions),
        }
    judge_score = max(1, min(5, raw_score)) if raw_score else 0
    verdict_assertions = verdict.get("assertions")
    if not isinstance(verdict_assertions, dict):
        verdict_assertions = {}
    assertion_results = {
        key: verdict_assertions.get(key) is True
        for key in assertions
    }
    assertion_failures = [
        key for key, assertion_passed in assertion_results.items()
        if not assertion_passed
    ]
    passed = judge_score >= min_score and not assertion_failures
    normalized = judge_score / 5.0 if judge_score else 0.0

    return {
        "passed": passed,
        "score": round(normalized, 3),
        "judge_score": judge_score,
        "judge_reason": verdict.get("reason", ""),
        "assertions": assertion_results,
        "assertion_failures": assertion_failures,
    }
