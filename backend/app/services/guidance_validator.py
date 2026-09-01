"""Guidance validator — R4 defense-in-depth for meal/movement guidance text.

The product hard rule (R4): the system only RECORDS / FOLLOWS-UP, it never
diagnoses / prescribes / adjusts. Eating "guidance" must stay OBSERVATIONAL /
post-hoc (e.g. "这餐约 450kcal / 今日蛋白还差 35g"), never a real-time imperative
dietary prescription ("别吃这个" / "每天吃 X 克" / "停止吃...").

This module is a *pure* function that HARD-STRIPS / flags imperative+quantitative
dietary tokens, imperative posture/training tokens, and (ships-disabled) pseudo-
prescriptive medication-timing wording from any LLM-generated guidance string
BEFORE it is returned to the client. It sits behind the SafetyGuardian rules in
``rules/guidance_red_lines.py`` as a second layer: the rules raise CRITICAL/HIGH
alerts, this validator actually rewrites the text.

Three families:
  1. Quantified/imperative DIET prescriptions → REDACT to a neutral placeholder.
  2. Imperative MOVEMENT commands → SOFTEN to a non-imperative, see-a-clinician note.
  3. Pseudo-prescriptive MEDICATION-TIMING ("每8小时服用一次", "建议睡前使用鼻喷剂",
     "漏服后6小时补服/超12小时跳过", "第N周停/减药") → SOFTEN to "遵医嘱/药师/说明书".
     Gated behind ``settings.med_timing_softening`` (default False = ships-disabled;
     zero behaviour change until an eval arm validates the false-positive rate).
     Negative guards (relaying a drug label / doctor's order / a negated warning)
     are always on and never widen with the flag.

Fail-loud contract: callers MUST log/audit when ``flagged`` is True (the
returned ``violations`` list says what was stripped) — never silently alter the
text without recording it. Returns the sanitized string + structured metadata.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Sequence


# ── 量化 + 命令式饮食处方 (R4 越界) ────────────────────────────────
# 命中即把整句替换成中性占位, 因为这是"系统不该说的话"。
# 例: "每天吃 50 克坚果", "别吃米饭", "停止吃糖", "避免摄入 200g 碳水", "禁止喝酒"
#     "Eat 50g of nuts every day", "Don't eat rice", "Avoid carbs",
#     "请减少米饭的摄入", "应当控制碳水摄入量"
_QUANTITY = r"\d+(?:\.\d+)?\s*(?:克|g|毫克|mg|份|个|两|斤|ml|毫升|卡|kcal|大卡)"
# 英文数量 (剂量/份量) — diet quantity tokens
_QUANTITY_EN = r"\d+(?:\.\d+)?\s*(?:g|mg|kg|kcal|cals?|calories|oz|servings?|grams?)"

# 中文饮食名词 (软祈使无数量也越界用) — diet noun anchors
_DIET_NOUN_ZH = (
    r"(?:碳水|糖(?:分|类)?|主食|米饭|面(?:条|食)?|脂肪|油|蛋白质?|热量|卡路里|"
    r"高糖食物|高脂食物|高盐|盐分?|零食|饮料|酒(?:精)?|甜食|淀粉|red\s*meat|红肉|奶|乳制品)"
)

# 命令式动词 (祈使) — 直接命令用户吃/不吃
_IMPERATIVE_EAT = (
    r"别吃", r"不要吃", r"不能吃", r"禁止吃", r"停止吃", r"戒掉",
    r"别喝", r"不要喝", r"不能喝", r"禁止喝", r"停止喝",
    r"必须吃", r"一定要吃", r"务必吃", r"应该吃", r"得吃",
)

# 量化处方型: "每天吃/补/摄入 + 数量" / "每餐 + 数量"
_PRESCRIPTIVE_QTY = [
    re.compile(rf"每(?:天|日|餐|顿)[^。；;\n]{{0,6}}(?:吃|补|摄入|喝|服用|加|减)[^。；;\n]{{0,8}}{_QUANTITY}"),
    re.compile(rf"(?:吃|补|摄入|喝|服用)[^。；;\n]{{0,6}}{_QUANTITY}[^。；;\n]{{0,4}}(?:每(?:天|日|餐|顿))"),
    re.compile(rf"(?:避免|限制|控制|减少)[^。；;\n]{{0,8}}{_QUANTITY}"),
    # 中文软祈使: "把蛋白质提高到每天120克" / "下一餐请勿摄入超过50克脂肪" / "降到X克"
    # council #12: the old fixed {0,12} gap between "把" and the verb missed longer
    # noun phrases ("把你的身体状态允许的蛋白量逐步提升至120克", gap > 12). Widen the
    # lead-in to {0,40} (lazy) and require an explicit 到/至/到达-style target marker
    # so observational text ("今日蛋白还差35g" — no "把") stays clean.
    re.compile(
        rf"把[^。；;!?！？\n]{{0,40}}?(?:提高|提升|增加|降低?|减少?|控制|限制)"
        rf"(?:到|至|在)[^。；;!?！？\n]{{0,10}}?{_QUANTITY}"
    ),
    re.compile(rf"(?:请勿|不得|不要|别)[^。；;\n]{{0,8}}(?:摄入|吃|喝|超过)[^。；;\n]{{0,8}}{_QUANTITY}"),
    # 英文量化处方: "Eat 50g of nuts", "consume 200g protein", "limit intake to 500 calories"
    re.compile(
        rf"(?i:\b(?:eat|consume|take|have|add|cut|reduce|limit|increase)\b)"
        rf"[^.;\n]{{0,30}}{_QUANTITY_EN}"
    ),
    re.compile(
        rf"(?i:\b(?:limit|cut|reduce|keep)\b)[^.;\n]{{0,20}}"
        rf"(?i:\bto\b)[^.;\n]{{0,8}}{_QUANTITY_EN}"
    ),
]

# 命令式吃/不吃 (带或不带数量都算越界)
_IMPERATIVE_DIET = [re.compile(p) for p in _IMPERATIVE_EAT] + [
    # 中文软祈使 + 饮食名词 (无数量也越界): "请减少米饭的摄入", "应当控制碳水",
    # "建议你避免高糖食物", "少吃甜食", "多吃蛋白质"
    re.compile(rf"(?:避免|限制|控制|减少|戒|少吃|多吃|忌口?|请勿)[^。；;\n]{{0,6}}{_DIET_NOUN_ZH}"),
    re.compile(rf"(?:应当|应该|建议你?|请|需要|务必|一定要)[^。；;\n]{{0,6}}(?:避免|限制|控制|减少|戒|少吃|多吃)[^。；;\n]{{0,6}}{_DIET_NOUN_ZH}"),
    re.compile(rf"(?:不要|别|请勿|不得|不能)[^。；;\n]{{0,4}}(?:吃|喝|摄入)[^。；;\n]{{0,6}}{_DIET_NOUN_ZH}"),
    # 英文祈使饮食命令: "Don't eat rice", "Avoid carbs", "Stop eating sugar",
    # "You must consume 200g protein" 已被 _PRESCRIPTIVE_QTY 接住, 此处接无数量的
    re.compile(
        r"(?i:\b(?:don'?t|do not|avoid|stop|never|quit|cut out)\b)"
        r"[^.;\n]{0,20}"
        r"(?i:\b(?:eat|eating|consume|consuming|drink|drinking|carbs?|carbohydrates?|sugar|rice|"
        r"protein|fat|salt|sodium|snacks?|alcohol|dairy|gluten|bread|red\s*meat)\b)"
    ),
    re.compile(
        r"(?i:\byou must\b)[^.;\n]{0,12}"
        r"(?i:\b(?:eat|consume|drink|avoid|cut|reduce|limit)\b)"
    ),
]

# ── 命令式体态 / 训练指令 (实时祈使运动处方) ──────────────────────
# 例: "立刻放慢", "马上停下", "必须做满 3 组", "现在加速到 X"
#     "Slow down immediately", "You must do 3 sets", "赶紧慢下来", "你需要做满5组深蹲"
_IMPERATIVE_MOVEMENT = [
    re.compile(r"(?:立刻|立即|马上|现在就|赶紧|赶快)[^。；;\n]{0,6}(?:放慢|慢下来|加快|加速|停下|停止|改成|换成|调整)"),
    re.compile(r"必须做(?:满)?\s*\d+\s*(?:组|个|次|分钟|km|公里)"),
    re.compile(r"(?:一定要|务必|得|需要)[^。；;\n]{0,4}(?:做满|完成|坚持)[^。；;\n]{0,4}\d+\s*(?:组|个|次|分钟)"),
    # 英文祈使训练/体态命令
    re.compile(r"(?i:\b(?:slow down|speed up|stop|halt)\b)\s+(?i:\b(?:immediately|now|right now)\b)"),
    re.compile(r"(?i:\byou must\b)\s+(?i:\b(?:do|complete|finish|perform)\b)\s*\d+\s*(?i:\b(?:sets?|reps?|minutes?|min)\b)"),
    re.compile(r"(?i:\bmust\s+(?:do|complete|finish|perform)\b)\s*\d+\s*(?i:\b(?:sets?|reps?)\b)"),
]

# ── 拟处方用药时序措辞 (pseudo-prescriptive medication timing) ─────────
# R4 越界:系统主动开口给"具体服药间隔/时点/漏服窗/疗程调整"——像在开药, 而非
# 观察记录。命中动作 = SOFTEN(改写为"遵医嘱/药师/说明书"), 不整段拦截。
# 例(评测实锤漏杀): "6小时内可补服,超过12小时跳过" / "建议睡前使用鼻喷剂"
# 命中锚点(缺一不构成越界, 靠组合避免误伤食物量词/吸收科普):
#   剂型 / 具体药名药类 / 服药动词 / 时序 / 间隔 / 漏服窗 / 第N周疗程调整。
# 负向守卫(始终生效, 与开关无关): 转述说明书/医嘱/药师/临床指南(label-fact) 或
# 否定祈使("不要自行每8小时加一次") 不软化——那是科普/转述/告诫, 不是系统开处方。
_MED_DOSAGE_FORM = (
    r"(?:鼻喷剂|喷剂|滴剂|滴眼液|眼药水|栓剂|贴片|口服液|片剂|胶囊|颗粒|"
    r"含片|糖浆|软膏|乳膏|针剂|注射液?|吸入剂|气雾剂|药膏)"
)
# 具体药名/药类 — 自包含小集(不引外部词库, 避免与并发 session 的 drug_lexicon 撞地盘)
_MED_DRUG_CLASS = (
    r"(?:PPI|P-CAB|他汀|降压药|抗凝药|华法林|阿司匹林|二甲双胍|胰岛素|"
    r"奥美拉唑|雷贝拉唑|布洛芬|SSRI|抗生素|激素|沙丁胺醇|氯雷他定|地氯雷他定)"
)
# 服药动词 — 只认 服/吃/用/停/减/换/加(次), 与"食物量词/吸收"科普区分
_MED_DOSE_VERB = r"(?:服用|服|吃|用|停|减量?|换|加(?:一次|次)?)"
# 命令/建议动词 — 系统主动开口("建议…""每次…")
_MED_ADVISORY = r"(?:建议|应该?|应当|需要|请|务必|一定要|最好|记得|每次)"
# 时序锚点 — 睡前/饭前饭后/餐前餐后/空腹/晨起
_MED_TIMING = r"(?:睡前|饭前|饭后|餐前|餐后|空腹|晨起|睡觉前|临睡前|早晚)"
# 间隔锚点 — 每/隔/间隔 N 小时
_MED_INTERVAL = r"(?:每|隔|间隔)\s*\d+\s*(?:小时|个小时|h|钟头)"
# 漏服时间窗规则 — "6小时内可补服"/"超过12小时跳过"/"漏服后…小时"
_MED_MISSED_DOSE = (
    r"(?:漏服|忘(?:记|了)?(?:服|吃)|错过)[^。；;!?！？\n]{0,10}?\d+\s*(?:小时|个小时|h)"
    r"|\d+\s*(?:小时|个小时|h)[^。；;!?！？\n]{0,6}?(?:内|后)[^。；;!?！？\n]{0,6}?(?:可)?补服"
    r"|(?:超过|超出)\s*\d+\s*(?:小时|个小时|h)[^。；;!?！？\n]{0,6}?(?:跳过|不(?:用|要|需)?补|别补)"
)
# 第 N 周/天 停/减/换/加 药 — 疗程调整
_MED_COURSE_ADJUST = (
    r"第\s*\d+\s*(?:周|天|日|个月|月)[^。；;!?！？\n]{0,8}?"
    r"(?:停药?|减药|减量|换药|加量|加药|停用)"
)

_MED_TIMING_PATTERNS = [
    # A. 间隔服药: "每8小时服用" (间隔 + 服药动词)
    re.compile(rf"{_MED_INTERVAL}[^。；;!?！？\n]{{0,8}}?{_MED_DOSE_VERB}"),
    # B. advisory + 时序 + (动词|剂型|药名): "建议睡前使用鼻喷剂" / "建议餐前30分钟服用他汀"
    re.compile(
        rf"{_MED_ADVISORY}[^。；;!?！？\n]{{0,6}}?{_MED_TIMING}"
        rf"[^。；;!?！？\n]{{0,8}}?(?:{_MED_DOSE_VERB}|{_MED_DOSAGE_FORM}|{_MED_DRUG_CLASS})"
    ),
    # C. 时序 + 剂型/药名 + 服药动词: "睡前他汀服用"
    re.compile(
        rf"{_MED_TIMING}[^。；;!?！？\n]{{0,6}}?(?:{_MED_DOSAGE_FORM}|{_MED_DRUG_CLASS})"
        rf"[^。；;!?！？\n]{{0,4}}?{_MED_DOSE_VERB}"
    ),
    # C2. 时序 + 服药动词 + 剂型/药名: "睡前用一次鼻喷剂"(动词在剂型前)
    re.compile(
        rf"{_MED_TIMING}[^。；;!?！？\n]{{0,6}}?{_MED_DOSE_VERB}"
        rf"[^。；;!?！？\n]{{0,8}}?(?:{_MED_DOSAGE_FORM}|{_MED_DRUG_CLASS})"
    ),
    # D. 漏服时间窗规则
    re.compile(_MED_MISSED_DOSE),
    # E. 第 N 周疗程调整
    re.compile(_MED_COURSE_ADJUST),
]

# 负向守卫:同一 clause 内含转述/医嘱/说明书标记 → 转述科普, 不软化。
_MED_LABEL_FACT = re.compile(
    r"(?:说明书|公开资料|医嘱|医生(?:开|说|建议|叮嘱)|药师(?:说|建议)|"
    r"处方(?:上|里|写)?|临床(?:研究|指南)|文献|资料显示|参考资料|药品标签|标签上|适应症)"
)
# 否定祈使前缀:命中片段前(同 clause, ≤12 字)有否定 → 告诫而非开处方, 不软化。
_MED_NEG_PREFIX = re.compile(r"(?:不要|不能|别|请勿|不得|无需|不必|切勿|勿)")
_SENTENCE_BOUNDARY = "。；;!?！？\n"

_DIET_REDACTION = "[已移除非处方化建议]"
_MOVEMENT_SOFTENER = "(如有需要可在身体允许范围内自行调整, 不适请咨询医生)"
_MED_TIMING_SOFTENER = "(具体服用间隔/时点请遵医嘱、药师或药品说明书)"


def _clause_around(blob: str, start: int, end: int) -> str:
    """The sentence-level clause containing ``blob[start:end]`` (for guard checks)."""
    left = max((blob.rfind(c, 0, start) for c in _SENTENCE_BOUNDARY), default=-1)
    rights = [blob.find(c, end) for c in _SENTENCE_BOUNDARY]
    rights = [r for r in rights if r != -1]
    right = min(rights) if rights else len(blob)
    return blob[left + 1: right]


def _med_timing_guarded(blob: str, m: re.Match) -> bool:
    """True → this med-timing match is a RELAY / NEGATION, NOT a system prescription,
    so it must be left untouched. Fail-closed default is to soften (return False);
    only explicit label-fact / negation cues suppress."""
    clause = _clause_around(blob, m.start(), m.end())
    if _MED_LABEL_FACT.search(clause):
        return True
    # negation must sit in the same clause, immediately before the match (≤12 chars)
    window = blob[max(0, m.start() - 12): m.start()]
    parts = re.split(rf"[{_SENTENCE_BOUNDARY}]", window)
    if _MED_NEG_PREFIX.search(parts[-1]):
        return True
    return False


@dataclass
class GuidanceValidationResult:
    """Result of sanitizing one guidance string."""

    text: str
    flagged: bool = False
    violations: List[str] = field(default_factory=list)

    def to_audit(self) -> dict:
        return {"flagged": self.flagged, "violations": self.violations}


_SENSITIVE_MEDICAL_TOPIC = re.compile(
    r"(?:药|用药|停药|换药|剂量|补剂|保健品|溃疡|胃镜|肠镜|检查|复查|随访)"
)
_DOSE_ACTION = re.compile(
    r"(?:建议|应该|需要|可以|请|每天|每次)[^。；;!?！？\n]{0,24}"
    r"\d+(?:\.\d+)?\s*(?:mg|μg|ug|IU|单位|毫克|微克|克)"
)
_SCHEDULE_CLAIM = re.compile(
    r"(?:(?:已经|已)?为你|已经|已)(?:成功)?(?:安排|预约|创建|设定|设置)(?:了)?[^。；;!?！？\n]{0,30}"
)


def requires_medical_evidence_boundary(text: str) -> bool:
    """Whether the turn must be buffered until medical provenance checks finish."""
    return bool(_SENSITIVE_MEDICAL_TOPIC.search(text or ""))


def build_confirmable_health_fact_draft(text: str) -> dict | None:
    """Recognize narrow natural-language facts without authorizing a write."""
    raw = unicodedata.normalize("NFKC", text or "").strip()
    if any(marker in raw for marker in ("?", "？", "怎么", "为什么", "为何", "影响", "分析")):
        return None
    facts: list[dict[str, str]] = []
    caffeine = re.search(
        r"(?:咖啡因|咖啡)[^。；;!?！？\n]{0,12}?(\d+(?:\.\d+)?)\s*(mg|毫克)", raw, re.I
    )
    if caffeine:
        facts.append({"type": "caffeine_intake", "value": caffeine.group(1), "unit": "mg"})
    sleep = re.search(
        r"(?:昨晚|今晚|今天)?\s*(\d{1,2})(?:[:：点时](\d{1,2})?)?\s*(?:左右)?(?:入睡|睡着)", raw
    )
    if sleep:
        hour = int(sleep.group(1))
        minute = int(sleep.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            facts.append({"type": "sleep_onset", "value": f"{hour:02d}:{minute:02d}", "unit": "local_time"})
    if not facts:
        return None
    return {
        "status": "draft",
        "facts": facts,
        "requires_confirmation": True,
        "authorized_write": False,
    }


def enforce_medical_evidence_boundaries(
    text: str,
    *,
    evidence_sources: Sequence[str] = (),
    has_clinician_instruction: bool = False,
    verified_write_receipt: bool = False,
) -> GuidanceValidationResult:
    """Label sensitive medical claims and remove unauthorized action certainty."""
    if not text or not _SENSITIVE_MEDICAL_TOPIC.search(text):
        return GuidanceValidationResult(text=text or "")
    violations: list[str] = []
    out = text
    if not has_clinician_instruction:
        out = _redact(
            out,
            _DOSE_ACTION,
            "[具体药物或补剂剂量需由医生确认]",
            violations,
            "unverified_dose_action",
        )
    if not verified_write_receipt and not has_clinician_instruction:
        out = _redact(
            out,
            _SCHEDULE_CLAIM,
            "[尚无验证写入回执]",
            violations,
            "unverified_schedule_claim",
        )
    labels = ["用户陈述"]
    if evidence_sources:
        labels.append("已检索证据")
    labels.append("模型推断")
    if has_clinician_instruction:
        labels.append("医生确认指示")
    boundary = "信息来源：" + "、".join(labels) + "。"
    if not out.startswith("信息来源："):
        out = boundary + "\n" + out
    return GuidanceValidationResult(out, bool(violations), violations)


def _redact(text: str, pattern: re.Pattern, replacement: str, violations: List[str], kind: str) -> str:
    def _sub(m: re.Match) -> str:
        violations.append(f"{kind}: {m.group(0)}")
        return replacement

    return pattern.sub(_sub, text)


def _soften_med_timing(text: str, pattern: re.Pattern, violations: List[str]) -> str:
    """Soften pseudo-prescriptive med-timing matches, skipping relay/negation
    matches (label-fact / doctor-order / negated imperative) which are science
    communication, not the system prescribing. ``text`` is the FULL string so the
    guards can inspect the surrounding clause."""

    def _sub(m: re.Match) -> str:
        if _med_timing_guarded(text, m):
            return m.group(0)  # relay/negation — leave untouched
        violations.append(f"med_timing: {m.group(0)}")
        return _MED_TIMING_SOFTENER

    return pattern.sub(_sub, text)


def sanitize_guidance(text: str) -> GuidanceValidationResult:
    """Strip imperative+quantitative dietary tokens and imperative posture/training
    tokens from a guidance string.

    - Quantified/imperative DIET prescriptions ("每天吃 50g 坚果", "别吃米饭",
      "避免摄入 200g 碳水") → replaced with a neutral redaction placeholder.
    - Imperative MOVEMENT commands ("立刻放慢", "必须做满 3 组") → softened with a
      non-imperative, see-a-clinician note instead of a bare command.

    Observational wording ("这餐约 450kcal", "今日蛋白还差 35g", "建议/可以考虑...")
    is left untouched.

    Returns a ``GuidanceValidationResult``. When ``flagged`` is True the caller
    MUST record ``violations`` in the audit log — never silently alter text.
    """
    if not text:
        return GuidanceValidationResult(text=text or "", flagged=False, violations=[])

    violations: List[str] = []
    out = text

    for pat in _PRESCRIPTIVE_QTY:
        out = _redact(out, pat, _DIET_REDACTION, violations, "diet_prescription")
    for pat in _IMPERATIVE_DIET:
        out = _redact(out, pat, _DIET_REDACTION, violations, "diet_imperative")
    for pat in _IMPERATIVE_MOVEMENT:
        out = _redact(out, pat, _MOVEMENT_SOFTENER, violations, "movement_imperative")

    # 第三家族(ships-disabled): 拟处方用药时序措辞软化。开关关时零行为变更。
    # 负向 label-fact/否定守卫在 _soften_med_timing 内部, 与开关无关(不放宽)。
    if _med_timing_enabled():
        for pat in _MED_TIMING_PATTERNS:
            out = _soften_med_timing(out, pat, violations)

    return GuidanceValidationResult(
        text=out,
        flagged=bool(violations),
        violations=violations,
    )


def _med_timing_enabled() -> bool:
    """Read the ships-disabled flag at call time (so tests can flip it via
    ``settings``/monkeypatch without re-importing the module)."""
    try:
        from app.config import settings

        return bool(getattr(settings, "med_timing_softening", False))
    except Exception:  # pragma: no cover — config import must not break sanitization
        return False
