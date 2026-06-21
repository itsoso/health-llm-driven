"""R4 红线 —— AI 生成指导/总结文本里的越界处方拦截。

产品硬规则 R4:系统只 RECORD / FOLLOW-UP, 绝不 diagnose / prescribe / adjust。
餐食监控等场景里 LLM 合成的"指导/总结"必须停留在 OBSERVATIONAL / 事后描述
(如「这餐约 450kcal / 今日蛋白还差 35g」),绝不能变成实时命令式饮食处方
(「别吃这个」「每天吃 X 克」)或命令式体态/训练指令(「立刻放慢」「必须做满 N 组」)。

与其它 rules 不同:这两条不看生理指标,而是扫描
``twin.acute.pending_guidance_texts`` —— 由 guidance 校验路径(餐食 finish 等)
临时塞入的候选文本。builder 永不填充该字段, 因此存量 safety 评估路径行为零变化。

这是 ``services/guidance_validator.py`` (真正改写文本的 token 级护栏) 背后的
**规则层**:validator 负责 strip/soften, 这两条规则负责升级成可审计的 Alert。
正则与 validator 共享 (single source), 避免两处漂移。

诚实边界:正则匹配是兜底, 会有漏判;对话层 prompt 红线清单做自由文本兜底。
"""
from typing import List, Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.services.guidance_validator import (
    _IMPERATIVE_DIET,
    _IMPERATIVE_MOVEMENT,
    _PRESCRIPTIVE_QTY,
)
from app.twin.schema import HealthTwin


def _guidance_blob(twin: HealthTwin) -> str:
    texts = getattr(twin.acute, "pending_guidance_texts", None) or []
    return "\n".join(t for t in texts if t)


def _matches(blob: str, patterns) -> List[str]:
    hits: List[str] = []
    for pat in patterns:
        for m in pat.finditer(blob):
            hits.append(m.group(0))
    return hits


@register
def diet_prescription_red_line(twin: HealthTwin) -> Optional[Alert]:
    """AI 指导文本含量化/命令式饮食处方(「别吃」「每天吃…克」「避免…+数量」)→ CRITICAL。

    R4 越界:系统给出"每天吃 50g 坚果"/"别吃米饭"这类处方,是把记录工具讲成医生。
    命中即 CRITICAL,调用方必须 block/strip(validator 已物理改写,本规则使其可审计)。
    """
    blob = _guidance_blob(twin)
    if not blob:
        return None
    hits = _matches(blob, _PRESCRIPTIVE_QTY) + _matches(blob, _IMPERATIVE_DIET)
    if not hits:
        return None
    return Alert(
        rule_id="guidance_red_lines.diet_prescription_red_line",
        category="guidance",
        severity=Severity.CRITICAL,
        title="AI 指导越界:量化/命令式饮食处方",
        message=(
            "生成的指导文本里出现了量化或命令式饮食处方(如「每天吃…克」「别吃…」),"
            "这违反 R4——系统只做观察性记录与事后跟进, 不开具饮食处方。该内容已被拦截/移除。"
        ),
        action="改用观察性表述(如「这餐约 X kcal / 今日蛋白还差 Yg, 可考虑…」);"
               "具体份量/禁忌请由用户与医生或营养师确认。",
        data_citation={"matched": hits[:8]},
        requires_medical_attention=False,
    )


@register
def movement_imperative_red_line(twin: HealthTwin) -> Optional[Alert]:
    """AI 指导文本含命令式体态/训练指令(「立刻放慢」「必须做满 N 组」)→ HIGH。

    实时命令式运动处方同样越 R4 界, 但风险低于饮食处方(降为 HIGH):
    软化措辞 + 若涉医学情形建议咨询医生, 而非硬性命令。
    """
    blob = _guidance_blob(twin)
    if not blob:
        return None
    hits = _matches(blob, _IMPERATIVE_MOVEMENT)
    if not hits:
        return None
    return Alert(
        rule_id="guidance_red_lines.movement_imperative_red_line",
        category="guidance",
        severity=Severity.HIGH,
        title="AI 指导越界:命令式体态/训练指令",
        message=(
            "生成的指导文本里出现了命令式体态/训练指令(如「立刻放慢」「必须做满 N 组」),"
            "实时命令式运动处方超出 R4 范围。该内容已被软化为非命令式建议。"
        ),
        action="改用非命令式表述(如「如有需要可在身体允许范围内自行调整」);"
               "若存在伤痛或医学限制, 建议咨询医生或康复师后再调整强度。",
        data_citation={"matched": hits[:8]},
        requires_medical_attention=False,
    )
