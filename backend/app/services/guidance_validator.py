"""Guidance validator — R4 defense-in-depth for meal/movement guidance text.

The product hard rule (R4): the system only RECORDS / FOLLOWS-UP, it never
diagnoses / prescribes / adjusts. Eating "guidance" must stay OBSERVATIONAL /
post-hoc (e.g. "这餐约 450kcal / 今日蛋白还差 35g"), never a real-time imperative
dietary prescription ("别吃这个" / "每天吃 X 克" / "停止吃...").

This module is a *pure* function that HARD-STRIPS / flags imperative+quantitative
dietary tokens and imperative posture/training tokens from any LLM-generated
guidance string BEFORE it is returned to the client. It sits behind the
SafetyGuardian rules in ``rules/guidance_red_lines.py`` as a second layer:
the rules raise CRITICAL/HIGH alerts, this validator actually rewrites the text.

Fail-loud contract: callers MUST log/audit when ``flagged`` is True (the
returned ``violations`` list says what was stripped) — never silently alter the
text without recording it. Returns the sanitized string + structured metadata.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


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
    re.compile(rf"把[^。；;\n]{{0,12}}(?:提高|提升|增加|降|减|控制|限制)(?:到|至|在)?[^。；;\n]{{0,8}}{_QUANTITY}"),
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

_DIET_REDACTION = "[已移除非处方化建议]"
_MOVEMENT_SOFTENER = "(如有需要可在身体允许范围内自行调整, 不适请咨询医生)"


@dataclass
class GuidanceValidationResult:
    """Result of sanitizing one guidance string."""

    text: str
    flagged: bool = False
    violations: List[str] = field(default_factory=list)

    def to_audit(self) -> dict:
        return {"flagged": self.flagged, "violations": self.violations}


def _redact(text: str, pattern: re.Pattern, replacement: str, violations: List[str], kind: str) -> str:
    def _sub(m: re.Match) -> str:
        violations.append(f"{kind}: {m.group(0)}")
        return replacement

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

    return GuidanceValidationResult(
        text=out,
        flagged=bool(violations),
        violations=violations,
    )
