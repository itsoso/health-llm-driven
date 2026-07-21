"""推送隐私(AGENTS.md §5):锁屏可见文本不携带敏感健康标识。

iOS 默认在锁屏渲染推送 title/body,且 payload 途经 APNs(第三方)。
具体药名/补剂名/化验项目名/诊断名会向"能瞥到手机的人"泄露敏感健康属性
(药名可反推诊断:二甲双胍→糖尿病、舍曲林→抑郁症)。铁律:

- 推送 title/content 只到类别级(「用药提醒」「化验指标提醒」);
- 具体标识(medication_name / dosage / 补剂名 / 化验项 / 诊断)只进
  data payload,App 解锁后在应用内渲染;
- 用户自拟文本(SmartReminder、日历标题、自定义打卡名)推给本人设备可透传,
  但系统代成文案时不得把药名拼进可见文本。

新增推送生产者时必须遵守;违反 = 隐私 bug,不是文案风格问题。
"""
import logging
import re
from functools import lru_cache
from typing import Any, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

# Safety Guardian 里 title/message 结构性携带药名/化验项/诊断的规则类别 →
# 锁屏泛化文案用的类别级标签。vitals/cgm/symptoms/cardiac/training_load 等
# 急性类不在表内:数值/症状措辞是安全时效信息,按原文透传。
# (pgx 不标"基因"——提及基因本身也泄露用户做过基因检测。)
SENSITIVE_ALERT_CATEGORY_LABELS = {
    "ddi": "用药安全",
    "dsi": "用药与补剂安全",
    "pgx": "用药安全",
    "labs": "化验指标",
    "problem_red_lines": "健康状况",
}

# rule_id 命名约定是 "{category}.{name}"(如 ddi.warfarin_nsaid),
# 只有 rule_id 可用的上下文(如 ActionCard.source_id)按前缀判类别。
_SENSITIVE_RULE_PREFIXES = tuple(f"{c}." for c in SENSITIVE_ALERT_CATEGORY_LABELS)

_GENERIC_ALERT_CONTENT = "检测到需要你关注的安全事项,打开 App 查看详情与建议。"


def is_sensitive_alert(
    category: Optional[str] = None, rule_id: Optional[str] = None
) -> bool:
    """该告警的 title/message 是否结构性携带药名/化验项/诊断。"""
    if category and category in SENSITIVE_ALERT_CATEGORY_LABELS:
        return True
    if rule_id and str(rule_id).startswith(_SENSITIVE_RULE_PREFIXES):
        return True
    return False


def _category_label(category: Optional[str], rule_id: Optional[str]) -> str:
    if category and category in SENSITIVE_ALERT_CATEGORY_LABELS:
        return SENSITIVE_ALERT_CATEGORY_LABELS[category]
    rid = str(rule_id or "")
    for cat, label in SENSITIVE_ALERT_CATEGORY_LABELS.items():
        if rid.startswith(f"{cat}."):
            return label
    return "健康安全"


def safety_alert_push_text(alert) -> Tuple[str, str]:
    """Safety Guardian Alert → 锁屏可见 (title, content)。

    敏感类别(ddi/dsi/pgx/labs/problem_red_lines)→ 类别级泛化文案,
    完整 title/message 由 App 内 /safety 页渲染(data.rule_id 定位);
    其余类别按原文透传(content 截 120 字,与既有推送行为一致)。
    """
    category = getattr(alert, "category", None)
    rule_id = getattr(alert, "rule_id", None)
    if not is_sensitive_alert(category, rule_id):
        return f"⚠️ {alert.title}", (alert.message or "")[:120]

    label = _category_label(category, rule_id)
    severity_zh = getattr(getattr(alert, "severity", None), "label_zh", "注意")
    return f"⚠️ [{severity_zh}] {label}提醒", _GENERIC_ALERT_CONTENT


# ─────────────────── LLM 自由文本出口的确定性 backstop ───────────────────
#
# 确定性生产者(上面的类别泛化)之外,还有 LLM 自由生成的推送文案
# (agent_loop 主动通知 / 早安短稿 / 周聊稿 / 今日健康复盘)。LLM prompt 无法
# 硬保证不写药名,所以出口处用 drug_lexicon 派生的名称词集扫一遍:
# 命中 → 锁屏文案降级为泛化文案,原文只进 data payload / 应用内渲染。
#
# 判定是 TIGHTEN-only:扫描本身抛异常时 fail 到泛化文案(隐私侧 fail-closed),
# 推送永远照发(投递侧不因护栏故障丢消息)。

GENERIC_LLM_PUSH_TITLE = "健康管家提醒"
GENERIC_LLM_PUSH_CONTENT = "有一条为你准备的健康建议,点开查看。"

_SENSITIVE_PAYLOAD_KEYS = {
    "medication_name": "medication",
    "medicine_name": "medication",
    "drug_name": "medication",
    "dosage": "medication",
    "supplement_name": "supplement",
    "lab_name": "lab",
    "lab_item": "lab",
    "test_name": "lab",
    "diagnosis": "diagnosis",
    "diagnosis_name": "diagnosis",
    "condition_name": "diagnosis",
}

_SENSITIVE_CATEGORY_MARKERS = {
    "medication": "medication",
    "medicine": "medication",
    "drug": "medication",
    "supplement": "supplement",
    "lab": "lab",
    "medical_exam": "lab",
    "diagnosis": "diagnosis",
    "condition": "diagnosis",
}

_CENTRAL_GENERIC_TEXT = {
    "medication": ("用药提醒", "有一项用药事项需要你处理，打开 App 查看详情。"),
    "supplement": ("补剂提醒", "有一项补剂事项需要你处理，打开 App 查看详情。"),
    "lab": ("化验指标提醒", "有一项化验指标需要你关注，打开 App 查看详情。"),
    "diagnosis": ("健康事项提醒", "有一项健康事项需要你关注，打开 App 查看详情。"),
    "generic": (GENERIC_LLM_PUSH_TITLE, GENERIC_LLM_PUSH_CONTENT),
}

# 不点名具体药也能反推诊断的**治疗类别词**(对抗复审 2026-07-12 补):
# 「记得吃抗抑郁药」不含药名,但向锁屏泄露 Tier-5 心理健康域;化疗/HIV 同理。
# 只收诊断指向强的类别;「降压药」不收(vitals 血压数值本就按时效安全信息透传,
# 类别词不额外泄露)。已知可接受 fp:净化疗法⊃化疗、开放疗法⊃放疗(极罕见,
# 代价只是降级成泛化文案,推送仍送达 —— TIGHTEN 方向)。
_DIAGNOSIS_REVEALING_CLASS_TERMS = frozenset({
    "抗抑郁", "抗焦虑", "抗精神病", "精神科", "安眠药", "助眠药",
    "降糖药", "抗癫痫", "化疗", "放疗", "抗艾", "hiv", "抗逆转录", "避孕药",
})


@lru_cache(maxsize=1)
def _sensitive_name_re() -> "re.Pattern[str]":
    """把名称词集编成一条 alternation 正则。

    ASCII 词边缘加 (?<![a-z0-9]) / (?![a-z0-9]) 锚点 —— 自由文本裸子串会误配
    (历史教训 iron⊂environment / pril⊂April;那批词已在 lexicon 去歧义名单里,
    锚点兜的是剩余 ASCII 词,如 b12 不应命中工单号 AB123)。ASCII 尾词允许可选
    复数 s(statins/opioids 不因锚点漏检)。CJK 无词边界,子串即匹配(歧义 CJK
    短词同样已被 lexicon 剔除)。长词优先,避免 alternation 短词抢先截断。
    """
    from app.services.drug_lexicon import sensitive_name_free_text_terms

    terms = sensitive_name_free_text_terms() | _DIAGNOSIS_REVEALING_CLASS_TERMS
    parts = []
    for term in sorted(terms, key=len, reverse=True):
        pat = re.escape(term)
        if term[0].isascii():
            pat = r"(?<![a-z0-9])" + pat
        if term[-1].isascii():
            pat = pat + r"s?(?![a-z0-9])"
        parts.append(pat)
    return re.compile("|".join(parts), re.IGNORECASE)


def contains_sensitive_name(text: Optional[str]) -> bool:
    """自由文本是否点名了药/补剂(锁屏不可见的判定,大小写不敏感)。"""
    if not text:
        return False
    return bool(_sensitive_name_re().search(str(text)))


def _payload_privacy_kind(data: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not data:
        return None

    normalized_keys = {str(key).lower() for key in data}
    for key, kind in _SENSITIVE_PAYLOAD_KEYS.items():
        if key in normalized_keys:
            return kind

    category = str(data.get("category") or data.get("type") or "").lower()
    for marker, kind in _SENSITIVE_CATEGORY_MARKERS.items():
        if marker in category:
            return kind

    rule_id = str(data.get("rule_id") or "")
    if is_sensitive_alert(rule_id=rule_id):
        return "lab" if rule_id.startswith("labs.") else "medication"
    return None


def lock_screen_privacy_backstop(
    *,
    notification_type: str,
    title: Optional[str],
    content: Optional[str],
    data: Optional[Mapping[str, Any]],
) -> Tuple[str, str, bool]:
    """Final lock-screen privacy guard used by the shared push choke point.

    This is intentionally independent from producer-specific helpers. A new or
    legacy producer cannot leak medication, supplement, lab, or diagnosis text
    merely because it forgot to call its local privacy helper. Acute vital and
    symptom alerts remain unchanged unless their free text names a sensitive
    drug/supplement.
    """
    visible_title = str(title or "")
    visible_content = str(content or "")
    try:
        kind = _payload_privacy_kind(data)
        if kind is None and (
            contains_sensitive_name(visible_title)
            or contains_sensitive_name(visible_content)
        ):
            kind = "generic"
    except Exception:
        logger.warning("[push_privacy] central privacy scan failed; using generic text", exc_info=True)
        kind = "generic"

    if kind is None:
        return visible_title, visible_content, False
    safe_title, safe_content = _CENTRAL_GENERIC_TEXT[kind]
    return safe_title, safe_content, True


def llm_push_backstop(
    title: Optional[str],
    content: Optional[str],
    *,
    generic_title: Optional[str] = None,
    generic_content: str = GENERIC_LLM_PUSH_CONTENT,
) -> Tuple[str, str, bool]:
    """LLM 生成的推送文案出口守门:返回 (锁屏 title, 锁屏 content, 是否泛化)。

    title 或 content 任一命中 → 两者一起换成泛化文案(药名可能只在其一)。
    generic_title=None 表示 title 是确定性常量(如「🌅 早安」),命中时保留原 title。
    扫描异常 → 按命中处理(隐私 fail-closed),绝不 raise(投递不因护栏故障中断)。

    调用方责任:在**截断前**的全文上调用本函数(截断可能把药名切半逃过扫描),
    命中时把原文放 data payload 或让 App 内页面重取,不得再拼回可见文案。
    """
    title = title or ""
    content = content or ""
    try:
        hit = contains_sensitive_name(title) or contains_sensitive_name(content)
    except Exception:
        logger.warning("[push_privacy] LLM 文案扫描失败,fail-closed 泛化", exc_info=True)
        hit = True
    if not hit:
        return title, content, False
    return (generic_title if generic_title is not None else title), generic_content, True
