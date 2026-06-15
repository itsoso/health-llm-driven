"""个性化红线 —— 用户已登记 HealthProblem 的 red_lines 命中症状即升级。

与 symptoms.py(全人群通用急症,关键词写死)互补:这层是**数据驱动**的,
把每个用户登记的具体病情红线(如胃溃疡的「黑便/呕血」)拿来匹配当前症状文本,
让安全网随病情个性化。

匹配:把 condition 按 / 、 , ; 等分隔符拆成关键词,任一关键词(≥2 字)
是症状文本子串即命中。无分隔符的短语型 condition(如「持续上腹痛进行性加重」)
整条即唯一关键词,casual 文本通常不会命中——这是有意的保守:漏判由通用急症规则兜底。

不做否定语义识别:「没有呕血」「担心会不会呕血」也会命中「呕血」。这是**有意偏严**
(宁可对已登记溃疡的用户多提醒一次就医,也不漏),不是 bug —— 见对应测试钉。

数据:twin.acute.problem_red_lines(builder 从 active HealthProblem 投影)
      × twin.acute.symptom_texts_all + illness_names(近 72h 症状)。

诚实边界:关键词匹配是兜底,会漏;不做诊断、不替代就医判断。命中给医嘱里的 action。
"""
import re
from typing import List

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin

_SPLIT = re.compile(r"[/、,，;；|]+")

# P0/P1 的红线命中 → CRITICAL(危及生命/需急诊);P2 → HIGH(需就医但非即刻)
_RISK_SEVERITY = {"P0": Severity.CRITICAL, "P1": Severity.CRITICAL, "P2": Severity.HIGH}


def _keywords(condition: str) -> List[str]:
    """condition → 候选关键词(按分隔符拆分;无分隔符时整条即唯一关键词),去重保序,过滤过短。"""
    seen, out = set(), []
    for p in (s.strip() for s in _SPLIT.split(condition)):
        if len(p) >= 2 and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _symptom_blob(twin: HealthTwin) -> str:
    parts = list(twin.acute.symptom_texts_all or [])
    parts += list(twin.acute.illness_names or [])
    parts += list(twin.acute.recent_symptoms or [])
    return " ".join(parts)


@register
def health_problem_red_line(twin: HealthTwin) -> List[Alert]:
    """用户登记健康问题的红线命中当前症状 → 按 problem 风险等级升级 + 给医嘱动作。"""
    red_lines = twin.acute.problem_red_lines or []
    if not red_lines:
        return []
    blob = _symptom_blob(twin)
    if not blob:
        return []

    alerts: List[Alert] = []
    for rl in red_lines:
        kws = _keywords(rl.condition)
        hit = next((k for k in kws if k in blob), None)
        if not hit:
            continue
        severity = _RISK_SEVERITY.get(rl.risk_level, Severity.CRITICAL)
        alerts.append(Alert(
            rule_id="problem_red_lines.health_problem_red_line",
            category="symptoms",
            severity=severity,
            title=f"{rl.problem_name} 红线触发",
            message=(
                f"你登记的「{rl.problem_name}」设有红线「{rl.condition}」,"
                f"近期症状记录命中「{hit}」。这是你和医生约定的升级信号,不要等待观察。"
            ),
            action=rl.action,
            data_citation={"condition": rl.condition, "matched": hit,
                           "problem": rl.problem_name},
            requires_medical_attention=True,
        ))
    return alerts
