"""rank11: 深报告并行分专家段落合成 + 确定性拼接。

深分析合成本是一次串行强模型大 decode(单 `_call_llm` 吃掉全部 specialist findings →
p50 30-40s decode @ 12-13 tok/s)。findings 天然 per-specialist,确定性专家层早已并行,
只有 LLM 叙事被串行化。本模块把叙事也并行化:`asyncio.gather` N 个小强模型段落调用
(每段一个专家 finding + twin blob + 全局仲裁判词 + 严格段落契约),按严重度确定性拼接
(safety first),墙钟取 max-of-sections 而非 sum。

**安全不变量(加层不减层)**:本模块**不做任何安全裁决**。拼接产物由调用方(orchestrator)
过与 mega-synthesis **同一条** `_strip_llm_reva_ui` + `_safety_wrap`/`validate_text` 出站
护栏(套在**拼接整体**上,任一段落越界 → 整篇同样被句级遮蔽 + disclaimer)。

**只对报告形深分析启用**(`report_shaped`:≥2 substantive findings 且非 lite/siri)。SoT-R
教训:对话形短答用分段会劣化连贯性,故 gate 收窄到报告形。

Flag `settings.orchestrator_parallel_synthesis`: 'off' | 'shadow' | 'on'(见 `resolve_mode`)。
拼接是纯确定性(无 LLM);段落契约由 prompt 约束,greeting 由 `strip_section_greeting`
确定性剥离,跨段引用(「如上所述」)prompt-discouraged 但容忍(不做危险的中段裁剪)。
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from app.orchestrator.schema import SpecialistFinding
from app.twin.formatter import twin_to_prompt_blob
from app.twin.schema import HealthTwin

# 分段上限:cap 段并行 LLM 调用,超出的低优先 finding 并成一段「其他观察」。
# 5 是成本/收益折中(N× prefill,见 rank3 显式缓存 gate)。
DEFAULT_SECTION_CAP = 5

# specialist_name → 中文段落标题。覆盖全部注册 specialist;缺省回落到原名。
_SPECIALIST_CN: Dict[str, str] = {
    "safety_guardian": "安全",
    "recovery_coach": "恢复",
    "fuel_strategist": "营养",
    "movement_coach": "运动",
    "mental_health_companion": "心理",
    "hypertension_specialist": "血压",
    "metabolic_specialist": "代谢",
    "rhinitis_specialist": "鼻炎",
    "knowledge_librarian": "知识",
    "longitudinal_analyst": "趋势",
    "supplement_advisor": "补剂",
    "longevity_specialist": "抗衰",
    "cross_source_validator": "数据一致性",
}

# 严重度 → 数值(英文 label + safety_guardian 的 label_zh 都覆盖)。
_SEVERITY_NUM: Dict[str, int] = {
    "critical": 4, "emergency": 4, "red": 4, "severe": 4, "紧急": 4,
    "high": 3, "警告": 3,
    "medium": 2, "moderate": 2, "注意": 2,
    "low": 1, "关注": 1,
    "info": 0, "提示": 0,
}

# safety_guardian 段落恒排第一(急性红线优先播报),即便本次它只有 medium。
_SAFETY_FLOOR_BOOST = 10

_MERGED_LABEL = "其他观察"


def resolve_mode(raw: Any) -> str:
    """归一化 flag 值。未知值 fail-closed 归到 'off'。"""
    mode = str(raw or "off").strip().lower()
    return mode if mode in ("off", "shadow", "on") else "off"


# 段落调用思考控制的合法档 + 'budget512' 的封顶值。
SECTION_THINKING_MODES = ("off", "budget512", "on")
_SECTION_THINKING_BUDGET = 512


def resolve_section_thinking(raw: Any) -> str:
    """归一化段落思考档(见 settings.parallel_synthesis_section_thinking)。

    'off' = 关思考(本候选默认)、'budget512' = 封顶 512、'on' = 不加控制(存量行为)。
    未知/非法值 fail-closed 归到 'on'(= 不动思考,对存量段落零行为变更);仅当 config 显式
    落在合法档时才会真正给段落调用加思考控制。
    """
    mode = str(raw or "").strip().lower()
    return mode if mode in SECTION_THINKING_MODES else "on"


def _lookup_model_entry(model_name: Any):
    """按 model 字符串反查 ModelEntry(匹配 entry.model 或 entry.id)。fail-closed → None。

    镜像 openai_provider._model_supports_explicit_cache 的反查模式:观测/门控层绝不抛,
    查不到即返回 None(调用方据此不加任何控制,payload 逐字节不变)。
    """
    if not model_name:
        return None
    try:
        from app.services.llm.model_registry import MODELS

        for entry in MODELS:
            if entry.model == model_name or entry.id == model_name:
                return entry
    except Exception:  # noqa: BLE001 — 查不到注册表宁可不加控制(纯降级)
        return None
    return None


def build_section_llm_kwargs(model_name: Any, ctrl: Dict[str, Any]) -> Dict[str, Any]:
    """构造**段落**调用要透传给 provider.chat 的思考/缓存控制 kwargs(纯函数,registry 门控)。

    ctrl = {"thinking": <'off'|'budget512'|'on'>, "cache": <bool>}(orchestrator 从 settings
    算出后经 _section_synthesis_ctx 传入)。门控与 provider 侧 fail-closed 一致:
      - 思考控制:仅当本次实际调用的 model 的 ModelEntry.supports_thinking_budget=True 才加
        (探针验证过的 qwen 系,如 qwen3.7-max);'off'→enable_thinking=False、
        'budget512'→thinking_budget=512、'on'→不加。非支持/未知 model → 不加(免端点 400)。
      - 显式缓存:仅当 ctrl['cache'] 且 model.supports_explicit_cache=True 才置
        prompt_cache_markers=True(默认布局 = 前导 system 断点;provider 侧 _maybe_mark_prompt_cache
        再按本次真实 model 复核一次,不支持则 strip → 覆盖 primary + 任何 failover)。

    未查到 model(failover 到未注册/非 qwen provider,如 openai vision)→ 返回 {} → 段落 payload
    与存量逐字节相同。MEGA 路径永不进本函数(orchestrator 只对段落调用 set ctx)。
    """
    out: Dict[str, Any] = {}
    entry = _lookup_model_entry(model_name)
    if entry is None:
        return out
    thinking = str(ctrl.get("thinking") or "on")
    if getattr(entry, "supports_thinking_budget", False):
        if thinking == "off":
            out["enable_thinking"] = False
        elif thinking == "budget512":
            out["thinking_budget"] = _SECTION_THINKING_BUDGET
        # 'on' → 不加(思考照旧)
    if ctrl.get("cache") and getattr(entry, "supports_explicit_cache", False):
        out["prompt_cache_markers"] = True
    return out


def specialist_cn_label(name: str) -> str:
    key = (name or "").strip().lower()
    return _SPECIALIST_CN.get(key, name or "分析")


def is_substantive(finding: SpecialistFinding) -> bool:
    """有一句话概括,或有任何结构化 finding item → 值得单独成段。"""
    if (getattr(finding, "summary", "") or "").strip():
        return True
    return bool(getattr(finding, "findings", None))


def finding_severity_rank(finding: SpecialistFinding) -> int:
    """段落排序键:段内 item 最高严重度 + safety 段 floor boost。"""
    best = 0
    for item in getattr(finding, "findings", None) or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("severity_label") or item.get("severity") or "").strip().lower()
        best = max(best, _SEVERITY_NUM.get(label, 0))
    name = (getattr(finding, "specialist_name", "") or "").lower()
    category = (getattr(finding, "category", "") or "").lower()
    if "safety" in name or category == "safety":
        best += _SAFETY_FLOOR_BOOST
    return best


def report_shaped(lite_mode: bool, findings: List[SpecialistFinding], source: Any = None) -> bool:
    """gate:报告形深分析才启用分段(≥2 substantive findings 且非 lite/siri)。"""
    if lite_mode:
        return False
    if source == "siri":
        return False
    substantive = [f for f in findings if is_substantive(f)]
    return len(substantive) >= 2


@dataclass
class SectionSpec:
    """一个段落的输入:1 个专家 finding(或并段时多个)+ 中文标题 + 排序严重度。"""

    findings: List[SpecialistFinding]
    label: str
    severity: int
    merged: bool = False


def select_sections(
    findings: List[SpecialistFinding], *, cap: int = DEFAULT_SECTION_CAP
) -> List[SectionSpec]:
    """按严重度(safety first)选 top-(cap-1) 段,余下并成一段「其他观察」。

    ≤cap 个 substantive finding → 每个独立成段;严格降序(严重度高在前),
    同严重度保持原注册顺序(稳定)。
    """
    substantive = [f for f in findings if is_substantive(f)]
    ranked = [
        f
        for _, f in sorted(
            enumerate(substantive),
            key=lambda pair: (-finding_severity_rank(pair[1]), pair[0]),
        )
    ]

    if len(ranked) <= cap:
        return [
            SectionSpec([f], specialist_cn_label(f.specialist_name), finding_severity_rank(f))
            for f in ranked
        ]

    top = ranked[: cap - 1]
    rest = ranked[cap - 1:]
    specs = [
        SectionSpec([f], specialist_cn_label(f.specialist_name), finding_severity_rank(f))
        for f in top
    ]
    merged_sev = min((finding_severity_rank(f) for f in rest), default=0)
    specs.append(SectionSpec(list(rest), _MERGED_LABEL, merged_sev, merged=True))
    return specs


def _format_finding_for_section(finding: SpecialistFinding) -> List[str]:
    """单个 finding 的裁决文本(与 mega _build_synthesis_prompt 的 findings_text 同构)。

    携带 support_status / evidence_refs 证据契约,保住 R4 证据优先信号。
    """
    parts: List[str] = [f"【{finding.specialist_name}】{finding.summary}"]
    refs = list(finding.evidence_refs or [])
    support_status = "supported" if refs else "model_inference"
    evidence_ref_text = ",".join(refs) if refs else "none"
    parts.append(f"  证据契约: support_status={support_status}; evidence_refs={evidence_ref_text}")
    for idx, item in enumerate(finding.findings or [], 1):
        if not isinstance(item, dict):
            continue
        sev = item.get("severity_label", "")
        title = item.get("title", "")
        action = item.get("action") or ""
        line = f"  {idx}. [{sev}] {title}"
        if action:
            line += f" → {action}"
        item_refs = item.get("evidence_refs")
        if isinstance(item_refs, list) and item_refs:
            line += f" (evidence_refs={','.join(str(r) for r in item_refs)})"
        parts.append(line)
    return parts


# 段落 system 契约:结论先行、无问候/结束/标题、无跨段引用、不编数字、data_gap 不填空、
# 硬约束不软化、证据分级、显式归因、遵守仲裁判词。是 mega 硬规则的段落投影。
_SECTION_SYSTEM_TEMPLATE = (
    "你是健康助理的分项分析师,本次只负责【{label}】这**一个**专家维度的表述。\n"
    "严格契约:\n"
    "1. **结论先行**: 第一句直接给该维度的结论。\n"
    "2. **不超过 180 字**, 简洁, 只讲这一个维度。\n"
    "3. **不写问候语、不写开场白、不写结束语、不写标题/井号** —— 拼接层会加标题, 你只写正文。\n"
    "4. **不引用其它段落**: 禁止出现'如上所述/前面提到/综上/另外还有'等跨段指代 —— 你只看到本段材料。\n"
    "5. **不编数字/规则名**: 只用下方裁决材料里的事实; 没有的数据直说'暂无相关数据'。\n"
    "6. **数据缺口不填空**: 材料出现 type=data_gap 或 data_gap=True 时, 不得对该指标做任何数值/状态"
    "描述, 只说缺什么、请补什么。\n"
    "7. **硬约束不软化**: 材料含 'rest/停/禁/避免/不宜/暂停/过载/超载/hard_block' 等禁止类结论时, "
    "不得给'可轻度/替代/少量/Z1 30min'等软化版, 必须给一致结论。\n"
    "8. **证据分级**: support_status=model_inference 或 evidence_refs=none 的建议只能作模型推断, "
    "用'目前证据不足, 先作为尝试'降级表达, 不得压过有证据的相反建议。\n"
    "9. **显式归因**: 用到用户差异化数据(基因/化验/在服药物/历史症状/长期趋势/可穿戴日读数)时, "
    "在该句后用括号标注来源(如 '(基于你的 MTHFR C677T 杂合)' / '(参照你近期 HbA1c 5.8)')。\n"
    "10. **服从仲裁**: 若下方出现'冲突仲裁判词', 本段结论必须与判词一致, 不得给相反或软化建议。"
)


def build_section_prompt(
    spec: SectionSpec, query: str, twin_blob: str, arb_block: str = ""
) -> Tuple[str, str]:
    """确定性构造 (section_system, section_user)。无 LLM。"""
    system_prompt = _SECTION_SYSTEM_TEMPLATE.format(label=spec.label)

    findings_lines: List[str] = []
    for finding in spec.findings:
        findings_lines.extend(_format_finding_for_section(finding))
    findings_text = "\n".join(findings_lines) or "(无 specialist 输出)"

    user_parts = [
        f"【本段专家维度】{spec.label}",
        f"【用户原始问题】\n{query}",
        f"【用户当前健康快照】\n{twin_blob or '(数据暂缺)'}",
        f"【本段专家裁决】\n{findings_text}",
    ]
    if arb_block:
        user_parts.append(
            "【冲突仲裁判词(全局,本段必须遵守,不得给相反建议)】\n" + arb_block
        )
    user_parts.append(f"请只就【{spec.label}】这一个维度, 写一段结论先行的分析。")
    return system_prompt, "\n\n".join(user_parts)


_GREETING_HEAD_RE = re.compile(
    r"^\s*(?:你好呀|您好呀|你好|您好|嗨+|哈喽|哈啰|hi|hello|hey)", re.IGNORECASE
)
# 剥问候词后, 吃掉紧邻的标点/填充(逗号/顿号/感叹/句号/波浪/空白)。
_GREETING_TRAIL_CHARS = "，,、!！~。.；;： 　\t"


def strip_section_greeting(text: str) -> str:
    """确定性剥掉段落开头的问候词 + 紧邻标点(段落契约禁止问候,但弱模型偶尔仍写)。

    只剥**开头的问候词本身**(你好/您好/hi/hello/…)与其后紧邻的分隔标点, 保留正文。
    不以问候词开头 → 原样(只 strip 首尾空白)。跨段引用(如上所述)/寒暄填充不在此处理:
    prompt-discouraged 但容忍(中段裁剪有语义风险, 宁可保留)。
    """
    if not text:
        return ""
    stripped = text.lstrip()
    match = _GREETING_HEAD_RE.match(stripped)
    if not match:
        return text.strip()
    return stripped[match.end():].lstrip(_GREETING_TRAIL_CHARS)


# 确定性拼接:开场(仅在有仲裁判词时)+ 每段 ## 标题 + 段落正文 + 结束边界。
_OPENING_WITH_ARBITRATION = (
    "说明: 下方分项分析已按各专家严重度排序(安全优先); 专家意见冲突处以仲裁结论为准。"
)
_CLOSING_BOUNDARY = "注: 以上为分项分析, 不构成诊断; 如有持续或加重的症状请及时就医。"


def stitch(rendered_sections: List[Tuple[str, str]], arb_block: str = "") -> str:
    """确定性拼接(纯字符串, 无 LLM)。

    rendered_sections: [(中文标题, 段落正文), ...](已按严重度排序 + greeting 剥离)。
    """
    if not rendered_sections:
        return ""
    blocks: List[str] = []
    if arb_block:
        blocks.append(_OPENING_WITH_ARBITRATION)
    for label, body in rendered_sections:
        body_text = (body or "").strip()
        if not body_text:
            continue
        blocks.append(f"## {label}\n\n{body_text}")
    if not blocks or (arb_block and len(blocks) == 1):
        # 只有开场没有任何段落正文 → 视为空(交回上层走 mega/兜底)。
        return ""
    blocks.append(_CLOSING_BOUNDARY)
    return "\n\n".join(blocks)


SectionCallLLM = Callable[[str, str], Awaitable[str]]


async def run_parallel_sectioned(
    *,
    call_llm: SectionCallLLM,
    query: str,
    twin: HealthTwin,
    findings: List[SpecialistFinding],
    arb_block: str = "",
    cap: int = DEFAULT_SECTION_CAP,
) -> Tuple[str, Dict[str, Any]]:
    """并行分段合成 + 确定性拼接。返回 (拼接文本, meta)。

    - `call_llm`: 注入的段落 LLM 调用(orchestrator 传 `_call_llm`;测试注入 fake)。
      走与 mega **同一条** provider 路径(失败 failover / provider 偏好 / 显式缓存标记
      的门控逻辑一致)。
    - **fail-soft**: 单段落调用异常/空 → 丢弃该段, 其余照拼(不抛)。全部失败 → 返回 ("", meta),
      上层据此回落 mega/兜底。
    - **本函数不做安全裁决**: 返回的拼接文本必须由调用方过 `_safety_wrap`(加层不减层)。
    """
    t_start = time.monotonic()
    twin_blob = twin_to_prompt_blob(twin)
    specs = select_sections(findings, cap=cap)
    prompts = [build_section_prompt(spec, query, twin_blob, arb_block) for spec in specs]

    t_llm = time.monotonic()
    results = await asyncio.gather(
        *(call_llm(system_prompt, user_prompt) for system_prompt, user_prompt in prompts),
        return_exceptions=True,
    )
    section_wall_ms = int((time.monotonic() - t_llm) * 1000)

    rendered: List[Tuple[str, str]] = []
    failed = 0
    for spec, result in zip(specs, results):
        if isinstance(result, BaseException) or not isinstance(result, str) or not result.strip():
            failed += 1
            continue
        rendered.append((spec.label, strip_section_greeting(result)))

    text = stitch(rendered, arb_block)
    meta: Dict[str, Any] = {
        "sections": len(rendered),
        "sections_planned": len(specs),
        "sections_failed": failed,
        "section_wall_ms": section_wall_ms,
        "wall_ms": int((time.monotonic() - t_start) * 1000),
        "labels": [label for label, _ in rendered],
        "cap": cap,
    }
    return text, meta
