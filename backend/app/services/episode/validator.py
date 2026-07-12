"""v3 Output Validator — MVP 只做前 3 项 (规则, 无 LLM).

六项职责 (MVP 前 3 项, 其余 TODO):
1. Schema 校验 — Pydantic strict (已由 planner 输出的 Pydantic 模型保证)
2. 黑名单拦截 — regex 禁词
3. Disclaimer 注入 — 命中灰/黑名单 → 自动附 disclaimer + 转介

4-6 留到 v2: evidence_id 校验 / 数值范围校验 / 医疗越界 LLM Critic.

v3 cross-cutting: validate_text() 给 orchestrator / agent_executor 等所有
LLM 终态文本输出统一过一遍 (不只是 ActionGraph). 这是 v3 "Safety as
cross-cutting concern" 的落地: SafetyGuardian specialist 仍跑结构化规则,
此处补上"任意 LLM 自由文本"维度.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List

from app.services.episode.protocol_registry import ProtocolAction

logger = logging.getLogger(__name__)


# v3 黑名单: 诊断/处方/药物剂量调整 (General Wellness 红线).
# 2026-07-12 修 (prod 误杀): 术语匹配后先做"否定/转诊先判" —— 综合分析合成里的
# 边界话术 ("请勿自行停药" / "不构成诊断" / "就医确诊") 曾被无上下文子串匹配
# 整篇替换成拒答模板, 白烧 45-85s 的 specialist + LLM 产出。
# 只有真处方式/裁决式使用才算命中; 命中后按句遮蔽而非整篇拒答 (见 validate_text).
_BLACKLIST_TERM_RE = re.compile(
    r"(胰岛素调整|降压药剂量|推荐剂量|服药剂量|诊断|处方|停药|确诊|治愈|"
    r"加药|减药|换药|mg\s*[/／]\s*kg)",
    re.IGNORECASE,
)

# 否定/转诊语境判定 (fail-closed 设计):
# - 只看术语**前文**, 后文一律不洗白 —— "建议停药后咨询医生" 是真处方,
#   后半句的"咨询医生"不能救它 (疑问词是唯一例外, 见 _QUESTION_PRE)。
# - 前文窗口不跨 clause 边界 (句读/逗号/分号/换行) —— "请勿犹豫，立即停药"
#   的否定被逗号切断, 仍算命中。
# - 顿号 (、) 与连词**不是**边界 —— "请勿自行停药、加药或换药" 的否定
#   要传播到整个列举。
_CLAUSE_BOUNDARY_CHARS = "。！？!?；;，,\n"
_PRE_WINDOW = 24

# 否定 token (无条件洗白): 前文窗口内任意位置出现即视为边界话术。
# 不得/不能/不可 排除 "不得不停药" (双重否定 = 肯定, 仍算命中);
# 不要 排除 "要不要" (疑问, 走 _QUESTION_PRE 的带转诊路径, 评审阻断#1)。
_NEGATION_PRE = re.compile(
    r"(请勿|切勿|(?<!要)不要|不得(?!不)|不能(?!不)|不可(?!不)|不应|不宜|不建议|不会|"
    r"不构成|不提供|不属于|不代表|并非|不是|无法|难以|禁止|避免)"
)
# 单字否定: 只认**紧邻**术语前一个字 ("非处方" / "未确诊"), 避免
# "非常建议停药" 这类含"非"字的误洗白。
_SAFE_PRE_ADJACENT_CHARS = "非勿别未莫"

# 疑问 token: **必须**同句后文出现医方转诊词才洗白 (2026-07-12 安全评审阻断#1:
# "你要不要停药看看效果" 是无医生参与的停药建议, 裸疑问词不能洗白)。
_QUESTION_PRE = re.compile(r"(是否|要不要|能否|可否)")

# 转诊名词分级 (2026-07-12 安全评审阻断#2: "医生让你把降压药剂量加倍" 是
# 转述具体处方指令, 裸转诊名词不能洗白处方/剂量类术语):
# - 诊断类术语 (诊断/确诊/处方名词本身): 裸转诊名词即可洗白 ——
#   "就医确诊" / "医生诊断" / "医生开的处方" 都是转诊/归属语境。
# - 处方/剂量类术语 (停药/加药/…/推荐剂量/mg/kg): 必须"指导语境"动词锚定
#   ("在医生指导下停药" / "遵医嘱" / "由医生决定"), 排除转述指令
#   ("医生让你…" / "药师说你可以…")。
_DIAGNOSTIC_CLASS_TERMS = ("诊断", "确诊", "处方")
_BARE_REFERRAL_PRE = re.compile(r"(医生|医师|医嘱|就医|门诊|医院|药师)")
_GUIDED_REFERRAL_PRE = re.compile(
    r"(遵医嘱|遵照医嘱|按医嘱|"
    r"(?:在|经|由|与|和|跟)[^。！？!?；;，,\n]{0,8}(?:医生|医师|药师|医院|门诊|专科)"
    r"[^。！？!?；;，,\n]{0,6}(?:指导|同意|评估|确认|监督|商量|讨论|沟通|批准|决定|判断|安排))"
)
# 指导语境必须**直接管辖术语** (2026-07-12 复审残留阻断): consult 短语与术语
# 之间只允许短连接尾 (下/后/再/之后/是否…), 一旦夹进"交付标记"(把/让/给/我/
# 你/建议/直接/可以/自行…) 说明 consult 只是铺垫、术语是助理另行下达的指令
# ("跟医生沟通后**把降压药剂量加倍**"), 不洗白。尾长 >8 一律不洗白 (fail-closed)。
#
# 已知残留 (三轮安全评审论证后**接受**, 勿轻动): "consult + 紧迫情态词
# (立刻/务必/赶紧/需要…) + 裸指令" (如 "经医生评估后应立刻停药") 仍会洗白。
# **不要**把这些情态词加进 _DELIVERY_MARKERS —— "由医生决定是否需要立刻停药"
# 这类合法转诊句同样含它们, 加了会退回 prod 误杀 (有护栏测试钉死)。子串层
# 不可无损收紧; 靠 reason=guided_referral 洗白遥测监控, 真在 prod 命中
# 交付式违规再考虑成分级解析。
_GUIDED_TAIL_MAX = 8
_DELIVERY_MARKERS = re.compile(
    r"[把让给我你就先请]|建议|直接|立即|现在|可以|自行|马上|尽快|记得"
)

# 名词化 + 后置转诊: "任何加药、减药或换药的决定, 都必须由医生做出。"
# 术语后必须紧跟**名词化头** (允许顿号/连词列举传播), 且同句后文出现医方词
# 才放行。名词化头收窄到决策类名词 —— "的同时"/"后" 这类连接用法不满足,
# 所以裸指令 ("停药后咨询医生" / "建议停药的同时告知医生") 仍拦截。
_NOMINAL_AFTER = re.compile(
    r"^(?:[、/]|或|和|及|以及|停药|加药|减药|换药)*"
    r"(?:的(?:决定|时机|方案|问题|选择|与否|事宜|安排|必要性)|"
    r"与否|时机|方案|决定|问题|事宜)"
)
_DEFERRAL_AFTER = re.compile(r"(医生|医师|医嘱|就医|门诊|医院|药师)")


def _pre_clause_context(text: str, pos: int) -> str:
    """取 pos 前同一 clause 内、最多 _PRE_WINDOW 字的前文."""
    lo = max(0, pos - _PRE_WINDOW)
    i = pos - 1
    while i >= lo and text[i] not in _CLAUSE_BOUNDARY_CHARS:
        i -= 1
    return text[i + 1: pos]


def _same_sentence_after(text: str, pos: int) -> str:
    """取 pos 之后到句末 (。！？!?\\n) 的文本 —— 跨逗号, 不跨句."""
    end = pos
    n = len(text)
    while end < n and text[end] not in "。！？!?\n":
        end += 1
    return text[pos:end]


def _cleared_reason(text: str, m: "re.Match[str]") -> str | None:
    """术语 m 若处于边界话术语境, 返回洗白原因 (审计用); 否则 None (= 真命中)."""
    term = m.group(0).lower()
    pre = _pre_clause_context(text, m.start())
    after = _same_sentence_after(text, m.end())

    if pre:
        if _NEGATION_PRE.search(pre):
            return "negation_pre"
        if pre[-1] in _SAFE_PRE_ADJACENT_CHARS:
            return "adjacent_negation"
        # 疑问词: 必须同句后文有医方转诊词 (评审阻断#1)
        if _QUESTION_PRE.search(pre) and _DEFERRAL_AFTER.search(after):
            return "question_with_deferral"
        # 裸转诊名词只洗白诊断类术语 (评审阻断#2)
        if term in _DIAGNOSTIC_CLASS_TERMS and _BARE_REFERRAL_PRE.search(pre):
            return "bare_referral_diagnostic"
        # 处方/剂量类术语: 指导语境动词锚定的转诊才洗白, 且 consult 短语必须
        # 直接管辖术语 —— 取**最靠近术语**的 consult 匹配, 其后的尾巴只能是
        # 短连接词, 出现交付标记或过长即视为另行下达的指令 (复审残留阻断)
        guided_last = None
        for g in _GUIDED_REFERRAL_PRE.finditer(pre):
            guided_last = g
        if guided_last is not None:
            tail = pre[guided_last.end():]
            if len(tail) <= _GUIDED_TAIL_MAX and not _DELIVERY_MARKERS.search(tail):
                return "guided_referral"

    if _NOMINAL_AFTER.match(after) and _DEFERRAL_AFTER.search(after):
        return "nominal_with_deferral"
    return None


def _find_blacklist_hits(text: str) -> List["re.Match[str]"]:
    """黑名单术语匹配 + 否定/转诊先判. 只返回真处方式/裁决式命中."""
    hits: List["re.Match[str]"] = []
    for m in _BLACKLIST_TERM_RE.finditer(text):
        reason = _cleared_reason(text, m)
        if reason:
            # 洗白遥测 (评审建议#3): prod 复盘洗白是否过宽的依据
            logger.debug(
                "[validator.text] 黑名单术语被洗白 term=%r reason=%s context=%r",
                m.group(0), reason,
                text[max(0, m.start() - 12): m.end() + 8],
            )
            continue
        hits.append(m)
    return hits


# 灰名单: 涉医/涉药关键词 → 不阻断, 但触发 disclaimer
_GRAYLIST_KEYWORDS = ("药", "补剂", "痛", "症状", "剂量", "副作用", "病")

_DISCLAIMER = "温馨提示: 以上建议仅为运动恢复参考, 非医疗处方. 如症状持续或加重, 请咨询医生."

# 文本被硬拦截后, 替换为安全兜底 (避免泄露原 LLM 输出)
_BLOCKED_FALLBACK = (
    "这个问题涉及具体医疗判断, 已超出我作为健康助理的安全边界. "
    "请咨询您的主治医生或拨打 12320 卫生热线."
)

# 句级遮蔽占位符: 命中句被移除时用户可见的提示 (fail-loud, 不静默吞句).
_REDACTED_PLACEHOLDER = "〔此处一句涉及需由医生判断的内容, 已由安全护栏略去〕"
# 遮蔽后剩余有效内容低于此字数 → 退回整篇拒答模板 (短文本/全篇越界时保持旧行为).
_MIN_KEPT_CHARS = 30
# 句终结符 (逗号/分号不终结句 —— 命中长逗号链时整句遮蔽, fail-closed).
_SENTENCE_TERMINATORS = "。！？!?\n"


def _redact_hit_sentences(
    text: str, hits: List["re.Match[str]"]
) -> tuple[str, int, int]:
    """把含真命中的句子替换为占位符, 保留其余句子.

    返回 (redacted_text, redacted_sentence_count, kept_content_chars).
    句 = 以 。！？!?\\n 终结的片段; 保留句尾换行以免破坏 markdown 结构.
    """
    hit_positions = [m.start() for m in hits]
    out_parts: List[str] = []
    redacted_count = 0
    kept_chars = 0
    idx = 0
    n = len(text)
    while idx < n:
        end = idx
        while end < n and text[end] not in _SENTENCE_TERMINATORS:
            end += 1
        if end < n:
            end += 1  # 含终结符
        sentence = text[idx:end]
        if any(idx <= p < end for p in hit_positions):
            redacted_count += 1
            trail = "\n" if sentence.endswith("\n") else ""
            out_parts.append(_REDACTED_PLACEHOLDER + trail)
        else:
            out_parts.append(sentence)
            kept_chars += len(sentence.strip())
        idx = end
    return "".join(out_parts), redacted_count, kept_chars


@dataclass
class ValidationResult:
    ok: bool
    blocked_actions: List[int] = field(default_factory=list)  # action index 列表
    disclaimer: str = ""
    notes: List[str] = field(default_factory=list)


@dataclass
class TextValidationResult:
    """validate_text() 的结果. 调用方根据 action 字段决定如何处理:
    - 'pass': 原文直接用
    - 'append_disclaimer': 原文末尾 + '\n\n' + disclaimer
    - 'replace': safe_text 已是替换后的最终文本 (硬拦截) —— 句级遮蔽版原文,
      或剩余内容不足时的整篇 _BLOCKED_FALLBACK; 两种情况均已附 disclaimer
    """
    ok: bool                # False = 命中黑名单, 必须替换
    action: str             # 'pass' | 'append_disclaimer' | 'replace'
    safe_text: str          # 已经处理过的最终安全文本 (调用方直接用)
    disclaimer: str = ""    # 非空 → 客户端需展示
    matched_terms: List[str] = field(default_factory=list)  # 命中的禁/灰名词, 审计用


def validate_actions(actions: List[ProtocolAction]) -> ValidationResult:
    """对 ActionGraph 做黑名单 + disclaimer 判定.

    返回:
      ok=True 不代表无 disclaimer, 只代表没触发硬拦截.
    """
    result = ValidationResult(ok=True)
    needs_disclaimer = False

    for idx, a in enumerate(actions):
        text = " ".join(filter(None, [a.title, a.body or ""]))
        if _find_blacklist_hits(text):
            result.blocked_actions.append(idx)
            result.notes.append(
                f"action[{idx}] '{a.template_id}' 命中黑名单, 阻断输出"
            )
            logger.warning("Validator 拦截 action %s: %s", a.template_id, text[:80])
            needs_disclaimer = True

        # 灰名单: 涉医/涉药关键词 → 不阻断, 但触发 disclaimer
        if any(kw in text for kw in _GRAYLIST_KEYWORDS):
            needs_disclaimer = True

    if result.blocked_actions:
        result.ok = False

    if needs_disclaimer:
        result.disclaimer = _DISCLAIMER

    return result


def validate_text(text: str) -> TextValidationResult:
    """v3 cross-cutting: 给任意 LLM 自由文本做安全校验.

    设计取舍 (2026-07-12 修 prod 误杀后):
    - 黑名单术语先做否定/转诊先判 —— 边界话术 ("请勿自行停药" / "不构成诊断"
      / "就医确诊") 不算命中, 原文保留 (灰名单仍会补 disclaimer).
    - 真命中 → **句级遮蔽**: 只把命中句替换为占位符, 其余合成保留.
      遮蔽后剩余 < _MIN_KEPT_CHARS → 退回整篇拒答模板 (短文本/全篇越界).
      违规句本身绝不泄露 (整句移除, 非 token 级软化).
    - 灰名单命中 → 保留原文 + 末尾 disclaimer (不影响主信息).
    - 都不命中 → 原文直传 (零开销).

    空字符串 / None 直接 pass (上游 LLM 失败的兜底, 不在本层处理).
    """
    if not text or not text.strip():
        return TextValidationResult(ok=True, action="pass", safe_text=text or "")

    matched: List[str] = []

    # 黑名单 = 硬拦截 (否定/转诊先判后仍命中的才算)
    hits = _find_blacklist_hits(text)
    if hits:
        matched.extend(sorted({m.group(0) for m in hits}))
        redacted_text, redacted_count, kept_chars = _redact_hit_sentences(text, hits)
        if kept_chars < _MIN_KEPT_CHARS:
            safe = f"{_BLOCKED_FALLBACK}\n\n{_DISCLAIMER}"
            logger.warning(
                "[validator.text] 黑名单拦截(整篇替换) terms=%s kept_chars=%d text_head=%r",
                matched[:3], kept_chars, text[:80],
            )
        else:
            safe = f"{redacted_text.rstrip()}\n\n{_DISCLAIMER}"
            logger.warning(
                "[validator.text] 黑名单拦截(句级遮蔽 %d 句) terms=%s text_head=%r",
                redacted_count, matched[:3], text[:80],
            )
        return TextValidationResult(
            ok=False, action="replace",
            safe_text=safe, disclaimer=_DISCLAIMER,
            matched_terms=matched,
        )

    # 灰名单 = 加 disclaimer
    gray_hits = [kw for kw in _GRAYLIST_KEYWORDS if kw in text]
    if gray_hits:
        matched.extend(gray_hits)
        return TextValidationResult(
            ok=True, action="append_disclaimer",
            safe_text=f"{text}\n\n{_DISCLAIMER}",
            disclaimer=_DISCLAIMER,
            matched_terms=matched,
        )

    return TextValidationResult(ok=True, action="pass", safe_text=text)
