"""小巴核心行为 battery runner — R3(确定性回归,CI 阻断)。

加载 evals/behavior/xiaoba_core.yaml,把每条 case 的 checks 断言到**确定性层**
(意图分类/确认档位/工具子集/卡片门控/兜底话术/remember 医疗硬闸/快路由上下文保留)。
零 LLM 零网络零写库 —— 与 evals/comparative/(LLM judge 评质量)分工,见 yaml 头注释。

R1(compaction)/R5(渐进披露)等改 prompt/路由的增量,翻 flag 前本文件必须全绿。
题库校验 fail-loud(quota 不符/未知 check type 直接抛),坏题库不静默跑。
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

BATTERY = Path(__file__).resolve().parents[1] / "evals" / "behavior" / "xiaoba_core.yaml"

_KNOWN_CHECKS = {
    "intake_intent", "confirm_tier", "fallback_shape",
    "remember_redirect", "owns_visualization", "fast_subset",
    "fast_context_retained", "prefer_fast_record",
}


def _load_battery() -> dict:
    data = yaml.safe_load(BATTERY.read_text(encoding="utf-8"))
    cases = data["cases"]
    # quota fail-loud(镜像 comparative/battery.py 的纪律)
    quota = data["meta"]["quota"]
    actual = Counter(c["family"] for c in cases)
    assert dict(actual) == dict(quota), f"家族配比漂移: yaml quota={quota}, 实际={dict(actual)}"
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "case id 重复"
    for c in cases:
        for chk in c["checks"]:
            assert chk["type"] in _KNOWN_CHECKS, f"{c['id']}: 未知 check type {chk['type']!r}"
    return data


_DATA = _load_battery()
_CASES = [(c["id"], c) for c in _DATA["cases"]]


def _tier_of(kind: str) -> str:
    """kind → 确认档位(读 agent_executor 活集合,与 ops registry 闸同源语义)。"""
    from app.services import agent_executor as ae
    if kind in ae._FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS:
        return "never_auto"
    if kind in ae._TYPED_ONLY_AUTO_CONFIRM_KINDS:
        return "typed_only"
    if kind in ae._FAST_RECORD_AUTO_CONFIRM_KINDS:
        return "auto"
    return "never_auto(fail-closed:不在任何集合)"


def _run_check(case_id: str, query: str, chk: dict) -> None:
    t = chk["type"]

    if t == "intake_intent":
        from app.services.intake_intent_classifier import classify_intake_intent
        got = classify_intake_intent(query).kind
        if "expect_any" in chk:
            assert got in chk["expect_any"], f"{case_id}: intent={got},期望 in {chk['expect_any']}"
        else:
            assert got == chk["expect"], f"{case_id}: intent={got},期望 {chk['expect']}"

    elif t == "confirm_tier":
        got = _tier_of(chk["kind"])
        assert got == chk["expect"], f"{case_id}: {chk['kind']} 档位={got},期望 {chk['expect']}"

    elif t == "fallback_shape":
        from app.services.agent_executor import _record_intent_needs_detail_message
        msg = _record_intent_needs_detail_message(query)
        for s in chk.get("must_contain", []):
            assert s in msg, f"{case_id}: 兜底话术缺 {s!r}: {msg}"
        for s in chk.get("must_not_contain", []):
            assert s not in msg, f"{case_id}: 兜底话术不该含 {s!r}(领域偏见回归): {msg}"

    elif t == "remember_redirect":
        from app.services.agent_executor import _remember_structured_medical_redirect
        got = _remember_structured_medical_redirect(chk["predicate"], chk["value"])
        if chk["expect"] == "blocked":
            assert got is not None and str(got).startswith("Error:"), (
                f"{case_id}: 结构化医疗数据未被 remember 硬闸拦截(fail-open 回归)")
        else:
            assert got is None, f"{case_id}: 良性属性被误拦(over-alarm 回归): {got}"

    elif t == "owns_visualization":
        from app.api.agent import _answer_owns_its_visualization
        got = _answer_owns_its_visualization(chk["answer"], chk.get("tools"))
        assert got is chk["expect"], (
            f"{case_id}: owns_visualization={got},期望 {chk['expect']}"
            f"(True=快照卡应抑制;False=卡照常)")

    elif t == "fast_subset":
        from app.services.tool_schema_registry import FAST_TURN_TOOL_NAMES
        assert list(FAST_TURN_TOOL_NAMES) == list(chk["expect"]), (
            f"{case_id}: fast 子集漂移 {FAST_TURN_TOOL_NAMES},期望 {chk['expect']}"
            "(变更须显式改 battery=有意决策)")

    elif t == "prefer_fast_record":
        # 复现 run_stream 的 _prefer_fast_record_model 门(四条排除),独立于模型选择。
        # expect=false 的否定用例:「别记录」不走 fast-record → 不被 R2 force 逼出记录。
        import app.services.agent_executor as ae
        got = (
            bool(ae._RECORD_INTENT_RE.search(query))
            and not bool(ae._ADVICE_OR_ANALYSIS_RE.search(query))
            and not bool(ae._RECORD_INTERROGATIVE_GUARD_RE.search(query))
            and not bool(ae._RECORD_NEGATION_GUARD_RE.search(query))
            and not ae._needs_reliable_tool_model(query)
        )
        assert got is chk["expect"], (
            f"{case_id}: prefer_fast_record={got},期望 {chk['expect']}"
            "(False=否定/疑问/分析→降级全模型,不被 R2 force 逼记)")

    elif t == "fast_context_retained":
        # 实现语义:上轮 assistant **提问**时,把它折进末条 user 消息
        # ([上一轮助手问我:…]\n我的回复:…),不保留独立 assistant 条
        # (弱模型适配器拒 [system, assistant, user] 序列)。battery 编码折叠语义。
        from app.services.agent_executor import _build_fast_record_messages
        prior = chk["prior_assistant"]
        msgs = [
            {"role": "user", "content": "早上好"},
            {"role": "assistant", "content": prior},
            {"role": "user", "content": query},
        ]
        out = _build_fast_record_messages(msgs)
        last = out[-1]
        content = str(last.get("content") or "")
        assert last.get("role") == "user", f"{case_id}: 末条必须是 user"
        assert prior[:8] in content, (
            f"{case_id}: 上轮助手提问未折入末条 user(跟进上下文回归): {content[:120]}")
        assert query in content, f"{case_id}: 当前输入丢失: {content[:120]}"


@pytest.mark.parametrize("case_id,case", _CASES, ids=[c[0] for c in _CASES])
def test_behavior_battery(case_id: str, case: dict) -> None:
    for chk in case["checks"]:
        _run_check(case_id, case.get("query", ""), chk)
