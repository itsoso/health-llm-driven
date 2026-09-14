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
    r"(?:药|剂量|补剂|保健品|溃疡|胃镜|肠镜|检查|复查|随访|"
    r"鱼油|辅酶|红景天|维生素|叶酸|NAC|NMN|基因|MTHFR|"
    r"睡眠|REM|皮质醇|肾上腺素|服用|口服)", re.I,
)
# One unit vocabulary feeds both information-object projection and action
# matching. Gram units are shared with food, so unscoped 吃 and dose changes
# use only medication-specific measures/counts; explicit oral actions may use g.
_DOSE_MEASURE_UNIT = r"(?:mg|μg|ug|IU|单位|毫克|微克)"
_DOSE_COUNT_UNIT = r"(?:粒|片)"
_DOSE_FOOD_MASS_UNIT = r"(?:克|g)"
_DOSE_REGIMEN_UNIT = rf"(?:{_DOSE_MEASURE_UNIT}|{_DOSE_COUNT_UNIT})"
_DOSE_ORAL_UNIT = rf"(?:{_DOSE_REGIMEN_UNIT}|{_DOSE_FOOD_MASS_UNIT})"
_DOSE_NUMBER = r"[一二两三四五六七八九十百千\d]+(?:\.\d+)?"
_DOSE_ACTION = re.compile(
    r"(?:建议|应该|需要|可以|请|每天|每次)[^。；;!?！？\n]{0,24}"
    r"\d+(?:\.\d+)?\s*" + rf"(?:{_DOSE_MEASURE_UNIT}|{_DOSE_FOOD_MASS_UNIT})",
    re.I,
)
_SCHEDULE_CLAIM = re.compile(
    r"(?:(?:已经|已)?为你|已经|已)(?:成功)?(?:安排|预约|创建|设定|设置)(?:了)?[^。；;!?！？\n]{0,30}"
)

# These are bounded regression tripwires, not a medical-evidence verifier.
# Generic source names and model-authored claims of a doctor's approval cannot
# authorize advice. The sealed health_evidence verifier remains authoritative
# for admitted, applicable claims; a no-match here never proves medical safety.
_SUPPLEMENT_OR_MEDICINE = re.compile(
    rf"(?:药|剂量|补剂|保健品|鱼油|辅酶|红景天|维生素|叶酸|NAC|NMN|{_MED_DRUG_CLASS})", re.I,
)
_REGIMEN_ACTION = re.compile(
    r"(?:增加到|减少到|加到|减到|提高到|降低到|加倍|翻倍|停用|停药|加量|减量)|"
    r"(?:建议|应该|应当|请|必须|每天|每日|每次|早晚)[^。；;!?！？\n]{0,24}"
    r"(?:服用(?!时间)|补充(?!剂)|吃|停用|增加|减少|" + _DOSE_NUMBER + r"\s*" + _DOSE_REGIMEN_UNIT + r")",
    re.I,
)
_UNSCOPED_REGIMEN = re.compile(
    r"(?:建议|应该|应当|请|必须|每天|每日|每次)[^。；;!?！？\n]{0,16}"
    r"(?:服用|口服)[^。；;!?！？\n]{0,30}" + _DOSE_NUMBER + r"\s*" + _DOSE_ORAL_UNIT + r"|"
    # Complete administration predicates do not depend on distance from 请/建议.
    r"(?:服用|口服|服)\s*" + _DOSE_NUMBER + r"\s*" + _DOSE_ORAL_UNIT + r"|"
    r"(?:增加到|减少到|加到|减到|提高到|降低到)\s*"
    + _DOSE_NUMBER + r"\s*" + _DOSE_MEASURE_UNIT + r"|"
    r"(?:每天|每日|每次|早上|晚上|早晚|睡前|餐前|餐后|随餐)\s*(?:服用|口服)(?!时间)|"
    r"(?:早晚|每天|每日|每次|睡前)\s*(?:各)?\s*" + _DOSE_NUMBER + r"\s*" + _DOSE_REGIMEN_UNIT + r"|"
    r"(?:每天|每日|每次)\s*(?:增加到|减少到|加到|减到|提高到|降低到)\s*"
    + _DOSE_NUMBER + r"\s*" + _DOSE_REGIMEN_UNIT + r"|"
    # A terminal 吃 quantity is actionable anywhere in a clause. Requiring the
    # object boundary keeps named foods such as 两片全麦面包 out of this rule.
    r"吃\s*" + _DOSE_NUMBER + r"\s*" + _DOSE_REGIMEN_UNIT
    + r"(?=\s*(?:[，,。；;!?！？\n]|$|即可|就行))",
    re.I,
)
# 服用时间 is a field noun, not the administration verb 服用. Changing or
# assigning that field remains an action, including without a medicine name.
_INTAKE_TIME_ACTION = re.compile(
    r"(?:调整|修改|改变|指定|设置|安排)[^，,。；;!?！？\n]{0,12}服用时间|"
    r"服用时间\s*(?:改为|改到|调整为|调整到|设为|定在|安排在|提前到|推迟到|应为|应该为)|"
    r"(?:建议|应该|应当|必须)[^，,。；;!?！？\n]{0,12}服用时间\s*[:：为]\s*"
    r"(?:睡前|早上|晚上|早晚|餐前|餐后|随餐|\d{1,2}[:：点])"
)
# Explicit course changes are actionable even after a harmless clinician
# question. A duration/state description alone is not a treatment instruction.
_COURSE_OBJECT = r"(?:疗程|用药周期|服用周期|治疗周期)"
# Formatting separators are part of the matching view, not new semantic words.
_COURSE_GAP = r"[ \t\r*_`]*(?:\n[ \t\r*_`]*)?"
_COURSE_DURATION = _DOSE_NUMBER + _COURSE_GAP + r"(?:天|日|周|星期|个月|月)"
_COURSE_DURATION_ACTION = re.compile(
    _COURSE_OBJECT + _COURSE_GAP + r"[:：]?" + _COURSE_GAP
    + r"(?:改为|改成|调整为|调整到|设为|定为|变更为|延长到|延长至|延长为|缩短到|缩短至|缩短为)"
    + _COURSE_GAP + _COURSE_DURATION + r"|(?:延长|缩短)" + _COURSE_GAP + _COURSE_OBJECT
    + _COURSE_GAP + r"(?:到|至|为)" + _COURSE_GAP + _COURSE_DURATION
)
_FUTURE_DOSE_CHANGE = (
    r"(?:增加|减少|提高|降低|恢复|调整|补充|补|加|减|增|降|改|换|服用|服|吃|用)"
    r"(?:到|至|为|成)"
)
_FUTURE_DOSE_CONTINUATION = (
    r"(?:也|再|仍(?:然|旧)?|依(?:然|旧)|还(?:是)?|继续|维持|保持|接着|各|都|先|"
    r"要|需|照(?:旧|常|样)|是|为|在|按|开始|起|"
    r"共|总共|一共|固定|至少|最多|约|大约|大概|"
    + _MED_ADVISORY + r"|" + _MED_DOSE_VERB
    + r"|坚持|推荐|可(?:以)?|将|计划|准备|打算|改(?:用|服)|换(?:用|服)|"
    + _FUTURE_DOSE_CHANGE
    + r"|(?:口服|服用|服|吃|用)(?:上)?|补(?:充|服|上)?|添(?:加|上)?|"
    r"续(?:服|用|上|补)?|每天|每日|每次|早晚|"
    + _MED_TIMING + r"|随餐|(?:早|午|晚)餐(?:前|后))"
)
_FUTURE_DOSE_TIME = (
    r"(?:明天|明日|后天|后日|明早|明晨|明晚|今晚|之后|以后|后续|"
    r"下周|下星期|下次|下一次|下回|次日|翌日|今后|往后|接下来)"
)
# Detect clause structure, not a vocabulary of allowed connecting words. Count
# units need medical context below; an explicit food/document object takes
# precedence over context inherited from a preceding intake acknowledgement.
_FUTURE_DOSE_ACTION = re.compile(
    _FUTURE_DOSE_TIME
    + r"(?P<prefix>[^，,。；;!?！？]{0,48}?)"
    + r"(?P<quantity>" + _DOSE_NUMBER + _COURSE_GAP
    + r"(?P<unit>" + _DOSE_REGIMEN_UNIT + r"))"
    + r"(?P<object>[^，,。；;!?！？\n]{0,24})(?=[，,。；;!?！？\n]|$)",
    re.I,
)
# Only complete food nouns can disambiguate particle/slice counts. An unknown
# product, pronoun, dosage form, or appended instruction is not food evidence.
_EXPLICIT_COUNTED_FOOD = re.compile(
    r"(?:(?:全麦|黑麦|杂粮|多谷物|白)?面包|吐司|(?:红|绿|青|紫)?葡萄|"
    r"花生(?:米)?|玉米(?:粒)?|米粒|苹果|黄瓜|西红柿|番茄|"
    r"奶酪|芝士|饼干|火腿|土豆|马铃薯|胡萝卜)(?:即可|就行)?"
)

_EXPLICIT_COUNTED_DOCUMENT = re.compile(r"(?:检查影像|影像|病理切片|报告)")
_EXPLICIT_ADMINISTRATION = re.compile(r"(?:服用|口服|服(?:上)?|用药|给药|补服)")
_REGIMEN_CONTEXT = re.compile(
    r"(?:剂量|原量|加量|减量|增量|减药|服用|口服|补服|用药|给药)"
)


def _future_count_is_medical(match: re.Match, *, regimen_context: bool) -> bool:
    if match.group("unit").lower() not in {"粒", "片"}:
        return True
    prefix = re.sub(r"[\s*_`：:]+", "", match.group("prefix"))
    object_text = re.sub(r"[\s*_`]+", "", match.group("object"))
    local = prefix + object_text
    medical = bool(_SUPPLEMENT_OR_MEDICINE.search(local)
                   or re.search(_MED_DOSAGE_FORM, local)
                   or _EXPLICIT_ADMINISTRATION.search(local))
    if not medical:
        food_prefix = re.sub(_FUTURE_DOSE_CONTINUATION, "", prefix).strip("的")
        if (_EXPLICIT_COUNTED_FOOD.fullmatch(object_text)
            or (not object_text and _EXPLICIT_COUNTED_FOOD.fullmatch(food_prefix))
            or _EXPLICIT_COUNTED_DOCUMENT.search(local)):
            return False
    # Preserve the narrow legacy shorthand trigger, including bare quantity
    # questions. Arbitrary intervening words alone do not establish a regimen.
    bare_shorthand = re.fullmatch(r"(?:" + _FUTURE_DOSE_CONTINUATION + r"){0,8}", prefix)
    return bool(medical or regimen_context or _REGIMEN_CONTEXT.search(local) or bare_shorthand)


def _medical_sentence_view(text: str) -> str:
    """Keep a wrapped bounded medical action in one clause without changing output.

    Replace only newlines inside this bounded action grammar, preserving source
    offsets. A preceding negation on a separate line remains a separate clause;
    exact trusted clinician relays are compared against the original text.
    """
    view = list(text)
    for pattern in (_COURSE_DURATION_ACTION, _FUTURE_DOSE_ACTION):
        for match in pattern.finditer(text):
            for index in range(match.start(), match.end()):
                if view[index] == "\n":
                    view[index] = " "
    return "".join(view)


_NEGATED_ASSERTION = re.compile(
    r"(?:不要|不能|不可|不得|请勿|切勿|无需|不必|不建议|不意味着|并不意味着|不能据此|不能仅凭)"
    r"[^，,。；;!?！？\n]{0,18}$"
)
_GENETIC_ABSOLUTE = re.compile(
    r"必须|只能|无法(?:利用|代谢)|不能(?:利用|代谢)|一定(?:需要|要|会)"
)
_MISSING_DATA_INFERENCE = re.compile(r"(?:推测|说明|意味着|表明|证明|所以|因此)[^，,。；;!?！？\n]{0,16}(?:不足|异常|缺乏|严重)")
_PERSONAL_HORMONE_CAUSE = re.compile(
    r"(?:皮质醇|肾上腺素)[^。；;!?！？\n]{0,20}(?:透支|代偿|掩盖)|"
    r"(?:皮质醇|肾上腺素)[^。；;!?！？\n]{0,12}(?:导致|造成|让你)"
)
_ADVICE_HOLD = "部分建议或推断缺少已核验证据，暂不提供执行方案。可与医生或药师核对依据及适用条件。"


def _has_asserted_match(
    pattern: re.Pattern, sentence: str, *, regimen_context: bool = False,
) -> bool:
    for match in pattern.finditer(sentence):
        if pattern is _FUTURE_DOSE_ACTION:
            if not _future_count_is_medical(match, regimen_context=regimen_context):
                continue
            # Only a negation preceding this quantity can negate its action.
            # "明天两粒不要加量" asserts a dose before the negative tail.
            quantity_prefix = re.split(
                r"[，,。；;!?！？\n]|但是|但|不过|然而|而是",
                sentence[:match.start("quantity")],
            )[-1]
            if _NEGATED_ASSERTION.search(re.sub(r"[*_`]+", "", quantity_prefix)):
                continue
        if pattern is _REGIMEN_ACTION and any(
            question.start("question") <= match.start()
            and match.end() <= question.end("question")
            for question in _CLINICIAN_ASSESSMENT_QUESTION.finditer(sentence)
        ):
            # This narrow decision question cannot authorize a dose, timing,
            # administration predicate, or a later second regimen action.
            continue
        prefix = re.split(r"[，,。；;!?！？\n]|但是|但|不过|然而|而是", sentence[:match.start()])[-1]
        # A negated recommendation can begin inside the matched action itself.
        if prefix.endswith("不") and match.group(0).startswith("建议"):
            continue
        if _NEGATED_ASSERTION.search(prefix):
            continue
        # "Cannot metabolize" is itself the genetic claim, not a prohibition.
        if pattern not in (_GENETIC_ABSOLUTE, _FUTURE_DOSE_ACTION) and _NEGATED_ASSERTION.search(match.group(0)):
            continue
        if pattern not in (_COURSE_DURATION_ACTION, _FUTURE_DOSE_ACTION) and re.search(
            r"(?:咨询|询问|请教)(?:医生|药师).{0,8}(?:是否|能否).{0,12}$", prefix,
        ):
            continue
        return True
    return False


# A request can ask for record fields rather than ingestion, with or without
# a colon. Require the complete field list before a clause boundary so a
# medicine appended to that list cannot be mistaken for a field-name object.
# Match only field-name objects; do not erase the surrounding sentence or an
# appended command. The original response is never rewritten by this view.
_RECORD_FIELD_OBJECT = (
    r"(?:补剂(?:的)?(?:真实|准确|具体)?名称|(?:补剂(?:的)?)?剂量|单位|"
    r"(?:实际)?服用时间|(?:午餐|加餐)(?:记录)?|当前症状|"
    r"睡眠(?:起止时间|入睡与醒来时间)|设备同步记录|"
    r"情绪和工作压力情况|情绪评分|(?:简单的)?情绪/压力评分)"
)
_RECORD_FIELD_REQUEST = re.compile(
    r"(?:补充|提供|补齐)\s*[:：]?\s*" + _RECORD_FIELD_OBJECT
    + r"(?:\s*(?:[/、+和及或]|[，,]\s*(?:以及|以及简单的)?)\s*"
    + _RECORD_FIELD_OBJECT + r")*"
    + r"(?=\s*(?:[。；;!?！？\n]|$))"
)


# A question that explicitly leaves a decision to a clinician is not an
# instruction or a claimed clinician approval. Admit only this complete grammar;
# preserve all surrounding text so appended actions still reach the tripwires.
_ASSESSMENT_MEDICINE = r"(?:补剂|药物|药品|用药|维生素)(?:[/和或及、](?:补剂|药物|药品|用药|维生素))*"
_ASSESSMENT_DECISION = r"(?:继续|停用|调整|停药|加量|减量)(?:[、或和及](?:继续|停用|调整|停药|加量|减量))*"
_CLINICIAN_ASSESSMENT_QUESTION = re.compile(
    r"(?P<lead>^\s*|[，,]\s*)"
    r"(?P<question>" + _ASSESSMENT_MEDICINE + r"(?:是否|能否)(?:需要|可以)?" + _ASSESSMENT_DECISION
    + r"|(?:是否|能否)(?:需要|可以)?" + _ASSESSMENT_DECISION + _ASSESSMENT_MEDICINE
    + r"|(?:是否|能否)(?:需要|可以)?停药)"
    r"(?P<referral>[，,]\s*(?:应|需|需要|请|须)?由(?:医生|药师)(?:或(?:医生|药师))?"
    r"(?:结合(?:当前)?(?:症状|检查)(?:(?:和|及)(?:症状|检查))?)?(?:判断|评估|确认))"
    r"(?=\s*(?:[，,。；;!?！？\n]|$))"
)


_COMPLETED_INTAKE_ACKNOWLEDGEMENT = re.compile(
    r"(?P<prefix>^\s*(?:已|已经)记录\s*[:：]?\s*"
    r"(?:今天|昨天|昨日|昨晚|今早|刚才|此前)\s*)"
    r"(?:服用|口服|服)(?:了)?\s*" + _DOSE_NUMBER + r"\s*" + _DOSE_ORAL_UNIT,
    re.I,
)

# Handling a medicine's physical object is distinct from administering it.
# Require a complete finite action/object/purpose clause, never an arbitrary
# non-administration verb or a prefix that could swallow a later instruction.
_HANDLED_MEDICINE = (
    r"(?:药(?:物|品|片)?|(?:补剂|鱼油|辅酶(?:Q10)?|红景天|"
    r"(?:复合)?维生素(?:\s*[A-EK]\d{0,2})?|叶酸|NAC|NMN)"
    r"(?:软?胶囊|片剂|片)?|" + _MED_DRUG_CLASS + r"(?:片|胶囊)?|" + _MED_DOSAGE_FORM + r")"
)
_HANDLED_QUANTITY = _DOSE_NUMBER + r"\s*" + _DOSE_REGIMEN_UNIT + r"\s*" + _HANDLED_MEDICINE
_FUTURE_MEDICINE_HANDLING = re.compile(
    r"\s*" + _FUTURE_DOSE_TIME + r"\s*(?:"
    + r"把\s*" + _HANDLED_QUANTITY + r"(?:带|携带)给(?:医生|药师)核对|"
    + r"(?:带|携带)" + _HANDLED_QUANTITY + r"给(?:医生|药师)核对|"
    + r"(?:拍|拍摄)" + _HANDLED_QUANTITY + r"的?(?:包装)?(?:照片|图片)|"
    + r"(?:核对|查看)" + _HANDLED_QUANTITY + r"的?(?:包装标签|包装|标签|批号)"
    + r")[。；;]?\s*", re.I,
)


# Full-clause directed questions ask for information. The complete grammar is
# deliberately narrower than arbitrary model-authored questions or suggestions.
_DIRECTED_FUTURE_DOSE_QUESTION = re.compile(
    r"\s*(?:请确认|请告诉我|能否告诉我|我想确认)\s*" + _FUTURE_DOSE_TIME
    + r"(?:的?剂量)?\s*(?:是否|是不是)(?:" + _FUTURE_DOSE_CONTINUATION + r"\s*){0,8}"
    + _DOSE_NUMBER + r"\s*" + _DOSE_ORAL_UNIT
    + r"\s*(?:药物|药品|" + _SUPPLEMENT_OR_MEDICINE.pattern + r"|" + _MED_DOSAGE_FORM + r")?"
    + r"\s*[?？]\s*", re.I,
)


def _sentence_has_regimen_context(sentence: str) -> bool:
    normalized = _medical_assertion_matching_text(sentence)
    completed = (_COMPLETED_INTAKE_ACKNOWLEDGEMENT.match(normalized)
                 and not normalized.rstrip().endswith(("?", "？")))
    clinician = (re.search(r"(?:医生|药师)[^。；;!?！？\n]{0,24}(?:判断|评估|确认)", normalized)
                 and (_SUPPLEMENT_OR_MEDICINE.search(normalized)
                      or re.search(_COURSE_OBJECT, normalized)))
    return bool(completed or clinician)


def _regimen_assertion_text(sentence: str) -> str:
    """Separate data-field nouns and a directed question from actual actions.

    Never exempt an entire greedy action match: a second instruction must still
    be checked, including nonnumeric timing instructions after a question.
    """
    if _FUTURE_MEDICINE_HANDLING.fullmatch(sentence):
        return "待核对的药品实物信息。"
    if _DIRECTED_FUTURE_DOSE_QUESTION.fullmatch(sentence):
        return "待确认的用药记录？"
    if not sentence.rstrip().endswith(("?", "？")):
        # A completed, dated intake acknowledgement is not a new prescription.
        # Project only that intake predicate; its object and every appended
        # dose, schedule, or course action still reach the existing tripwires.
        sentence = _COMPLETED_INTAKE_ACKNOWLEDGEMENT.sub(
            r"\g<prefix>既有摄入量", sentence,
        )
    sentence = re.sub(
        r"(^\s*(?:请告诉我|能否告诉我|(?:我)?(?:想确认|不知道|不清楚|无法确认|未能确认|未核实))(?:你)?(?:是否|能否))"
        r"(?:(?:每天|每日|每次|早上|晚上|早晚|睡前|餐前|餐后|随餐)\s*)?(?:服用|口服|吃)"
        r"(?:\s*" + _DOSE_NUMBER + r"\s*" + _DOSE_ORAL_UNIT + r")?"
        r"(?=\s*(?:[，,。；;!?！？\n]|$))",
        r"\1有该用药记录", sentence, flags=re.I,
    )
    sentence = _RECORD_FIELD_REQUEST.sub(
        lambda match: match.group(0).replace("补充", "提供", 1).replace("服用时间", "用药时间"),
        sentence,
    )
    # Only a request to supply a field is neutral. "调整服用时间" is still
    # an action and must retain the original tripwire.
    projected = re.sub(
        r"服用(?=时间(?:\*\*)?\s*(?:补上|补齐)(?:[，,。；;!?！？\n]|$))",
        "用药", sentence,
    )
    projected = re.sub(
        r"(^\s*请告诉我[^。；;!?！？\n]{0,40})服用(?=时间[。；;!?！？\n]*$)",
        r"\1用药", projected,
    )
    def existing_quantity(match: re.Match) -> str:
        prefix = re.split(
            r"[，,。；;!?！？\n]|但是|但|不过|然而|而是", projected[:match.start()]
        )[-1]
        if re.search(
            r"(?:不知道|不清楚|无法确认|无法还原|未能确认)"
            r"[^，,。；;!?！？\n]{0,45}$", prefix,
        ):
            # Replace only the unknown quantity object, never its surrounding
            # sentence: an appended dose/timing instruction remains visible.
            return "既有用药数量信息"
        return match.group(0)

    projected = re.sub(
        r"(?:每天|每日|每次)(?:吃|服用)(?:了)?(?:多少种|几种|几粒|几片|多少)",
        existing_quantity, projected,
    )
    inquiry = re.search(r"(?:每天|每日|每次)?(?:什么时间|何时)(?:吃|服用)", projected)
    directed = re.match(
        r"^\s*(?:要评估[，,]\s*)?(?:请告诉我|我需要你(?:直接)?告诉我)", projected
    )
    if inquiry is not None and directed is not None:
        remainder = projected[inquiry.end():]
        if not re.search(r"服用|口服|补充|吃|停用|停药|加量|减量|增加到|减少到", remainder):
            return projected[:inquiry.start()] + "既有用药信息" + remainder
    return projected


def _medical_assertion_matching_text(text: str) -> str:
    """Use the same matching view at the early gate and per-sentence guard.

    Normalize typography and bounded list markers only for matching. Keep the
    original text for output and exact independently trusted clinician relays.
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    return re.sub(
        r"(^|[。；;!?！？\n])[^\S\n]*"
        r"(?:[-*+•][^\S\n]+|(?:\d+[.)、]|\(\d+\))[^\S\n]*)",
        r"\1", normalized,
    )


def _unsupported_advice_reasons(
    sentence: str, *, inherited_regimen_context: bool = False,
) -> list[str]:
    """Only emit stable codes; never put health text into audit metadata."""
    normalized = _medical_assertion_matching_text(sentence)
    reasons: list[str] = []
    assertion = _regimen_assertion_text(normalized)
    if (_has_asserted_match(_UNSCOPED_REGIMEN, assertion)
        or _has_asserted_match(_COURSE_DURATION_ACTION, normalized)
        or _has_asserted_match(
            _FUTURE_DOSE_ACTION, assertion,
            regimen_context=inherited_regimen_context or _sentence_has_regimen_context(normalized),
        )
        or _has_asserted_match(_INTAKE_TIME_ACTION, assertion)
        or (_SUPPLEMENT_OR_MEDICINE.search(normalized) and (
        _has_asserted_match(_DOSE_ACTION, assertion)
        or _has_asserted_match(_REGIMEN_ACTION, assertion)
    ))):
        reasons.append("unverified_dose_action")
    if re.search(r"基因|MTHFR", normalized, re.I) and _has_asserted_match(_GENETIC_ABSOLUTE, normalized):
        reasons.append("genetic_absolute_action")
    if re.search(r"数据缺失|没有数据|未同步|未记录", normalized) and _has_asserted_match(_MISSING_DATA_INFERENCE, normalized):
        reasons.append("missing_data_inference")
    if "你" in normalized and _has_asserted_match(_PERSONAL_HORMONE_CAUSE, normalized):
        reasons.append("unsupported_personal_causality")
    return reasons


def requires_medical_evidence_boundary(text: str) -> bool:
    """Whether the turn must be buffered until medical provenance checks finish."""
    normalized = _medical_assertion_matching_text(text)
    return bool(_SENSITIVE_MEDICAL_TOPIC.search(normalized) or _UNSCOPED_REGIMEN.search(normalized)
                or _COURSE_DURATION_ACTION.search(normalized) or _FUTURE_DOSE_ACTION.search(normalized))


def build_confirmable_health_fact_draft(text: str) -> dict | None:
    """Recognize narrow natural-language facts without authorizing a write."""
    raw = unicodedata.normalize("NFKC", text or "").strip()
    if any(marker in raw for marker in ("?", "？", "怎么", "为什么", "为何", "影响", "分析")):
        return None
    # Explicit mutations must continue through the normal tool path so
    # validation, authorization, independent outcomes and durable receipts stay
    # authoritative.  This shortcut is only for uncommanded facts that need a
    # confirmation prompt before any write is proposed.
    if any(marker in raw for marker in ("记录", "保存", "写入", "添加", "同步")):
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
    trusted_clinician_instructions: Sequence[str] = (),
    trusted_write_summary: str = "",
    trusted_fact_summary: str = "",
    model_generated: bool = True,
) -> GuidanceValidationResult:
    """Withhold known unsupported advice, without claiming medical verification.

    ``trusted_clinician_instructions`` must contain exact text from instructions
    independently verified by the caller for this authenticated user. Never fill
    it from the generated response, user assertion, or an intent classifier.
    Only exact sentence relays qualify; changed doses and appended advice do not.
    ``has_clinician_instruction`` alone is context, never authorization.
    Trusted summaries must be rendered independently from verified tool facts
    or durable receipts, never extracted from model-authored completion claims.
    A receipt boolean alone cannot identify which generated claim is true.
    """
    if not text or not requires_medical_evidence_boundary(text):
        return GuidanceValidationResult(text=text or "")
    violations: list[str] = []
    trusted = {item.strip() for item in trusted_clinician_instructions if item.strip()}
    out_parts: list[str] = []
    trusted_relays: list[str] = []
    relayed_instruction = False
    inherited_regimen_context = False
    for match in re.finditer(r"[^。；;!?！？\n]+[。；;!?！？\n]*|[。；;!?！？\n]+", _medical_sentence_view(text)):
        sentence = text[match.start():match.end()]
        is_trusted = has_clinician_instruction and sentence.strip() in trusted
        relayed_instruction = relayed_instruction or is_trusted
        reasons = [] if is_trusted else _unsupported_advice_reasons(
            sentence, inherited_regimen_context=inherited_regimen_context,
        )
        inherited_regimen_context = _sentence_has_regimen_context(sentence)
        unverified_schedule = any(
            not (verified_write_receipt and claim.group(0).strip() in trusted_write_summary)
            for claim in _SCHEDULE_CLAIM.finditer(sentence)
        )
        if unverified_schedule:
            violations.append("unverified_schedule_claim")
            # Strip only the unverified operation from an independently trusted
            # clinician relay; its exact admitted instruction remains available.
            sentence = _SCHEDULE_CLAIM.sub("", sentence)
            sentence = re.sub(r"[，,]\s*([。；;!?！？])", r"\1", sentence)
        if reasons:
            violations.extend(reasons)
        elif is_trusted and sentence.strip():
            trusted_relays.append(sentence.strip())
        out_parts.append(sentence)
    out = "".join(out_parts)
    if violations:
        # Sentence replacement leaves table headers, dangling lists and repeated
        # placeholders. Withhold the untrusted document as a whole, retaining
        # only independently verified material in a complete short answer.
        safe_parts = list(dict.fromkeys(trusted_relays))
        for summary, is_receipt in ((trusted_fact_summary, False), (trusted_write_summary, True)):
            if not summary.strip() or (is_receipt and not verified_write_receipt):
                continue
            summary_reasons = _unsupported_advice_reasons(summary)
            if summary_reasons:
                violations.extend(summary_reasons)
                continue
            if not is_receipt and _SCHEDULE_CLAIM.search(summary):
                violations.append("unverified_schedule_claim")
                continue
            safe_parts.append(summary.strip())
        if any(reason != "unverified_schedule_claim" for reason in violations):
            safe_parts.append(_ADVICE_HOLD)
        if "unverified_schedule_claim" in violations:
            safe_parts.append("相关安排尚无已核验的完成回执，不能确认已经完成。")
        out = "\n\n".join(dict.fromkeys(safe_parts))
    # Provenance affects the label only; deterministic output keeps every check.
    labels = ["用户陈述"] if model_generated else ["工具读取结果"]
    if evidence_sources:
        labels.append("已检索证据（未逐句核验）")
    if model_generated:
        labels.append("模型推断")
    if relayed_instruction:
        labels.append("医生确认指示")
    boundary = "信息来源：" + "、".join(labels) + "。"
    if not out.startswith("信息来源："):
        out = boundary + "\n" + out
    return GuidanceValidationResult(out, bool(violations), list(dict.fromkeys(violations)))


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
