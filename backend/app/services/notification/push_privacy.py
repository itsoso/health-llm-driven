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
from typing import Optional, Tuple

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
