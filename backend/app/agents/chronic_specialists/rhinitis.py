"""
Rhinitis (过敏性鼻炎) Specialist。

输入：
- twin.behavioral.sneeze_count_today
- twin.behavioral.nasal_wash_count_today
- twin.chronic.rhinitis_today
- twin.environment.aqi / pollen / humidity
- twin.medication.active_meds（莫米松/西替利嗪等）

输出：
- 症状严重度分级
- 环境相关提示
- 药物依从性评估
- 下一步行动
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


def _rhinitis_severity(sneeze: int, wash: int) -> str:
    """简化症状严重度分级。"""
    if sneeze >= 20 or wash >= 4:
        return "severe"
    if sneeze >= 10 or wash >= 3:
        return "moderate"
    if sneeze >= 3 or wash >= 1:
        return "mild"
    return "stable"


# LPR 反流共现假说用:反流 / 上消化道酸相关指标关键词。
_REFLUX_INDICATORS = (
    "反流", "胃食管", "gerd", "lpr", "咽喉反流", "咽部异物", "烧心", "反酸", "嗳气", "胃溃疡",
)


def _acid_suppression_meds(twin: HealthTwin) -> List[str]:
    """在用的抑酸药(PPI/P-CAB)名单。复用 dsi 规则的单一关键词源(懒导入,避免循环 + 第三份副本)。"""
    try:
        from app.agents.safety_guardian.rules.dsi import _PCAB_KEYWORDS, _ppi_keywords

        kws = set(_ppi_keywords()) | set(_PCAB_KEYWORDS)
    except Exception:  # pragma: no cover - 退化到内置名单,不静默丢分支
        kws = {"伏诺拉生", "沃克", "vonoprazan", "奥美拉唑", "泮托拉唑", "雷贝拉唑", "兰索拉唑", "埃索美拉唑"}
    out: List[str] = []
    for m in (twin.medication.active_meds or []):
        name = m.get("name") or ""
        if name and any(k in name for k in kws):
            out.append(name)
    return out


def _reflux_indicator(twin: HealthTwin) -> Optional[str]:
    """从已登记病情 / 症状文本 / 慢病条件里找反流/上消化道酸相关指标;返回首个证据串(无→None)。"""
    def _hit(text: str) -> bool:
        low = (text or "").lower()
        return any(ind in (text or "") or ind in low for ind in _REFLUX_INDICATORS)

    for prl in (twin.acute.problem_red_lines or []):
        if _hit(prl.problem_name or ""):
            return f"已登记病情「{prl.problem_name}」"
    for txt in (twin.acute.symptom_texts_all or []):
        if _hit(txt or ""):
            return f"症状记录「{(txt or '')[:24]}」"
    for cond in (twin.chronic.active_conditions or []):
        if _hit(cond or ""):
            return f"慢病条件「{cond}」"
    return None


class RhinitisSpecialist:
    name = "rhinitis_specialist"
    category = "chronic"

    TRIGGER_KEYWORDS = {
        "鼻炎", "喷嚏", "鼻塞", "流鼻涕", "过敏性鼻炎", "花粉",
        "莫米松", "西替利嗪", "洗鼻",
        "rhinitis", "allergy", "pollen", "sneeze", "congestion",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "chronic" in intent.categories:
            return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 兜底：今天有鼻炎数据就参与
        if twin.behavioral.sneeze_count_today > 0 or twin.behavioral.nasal_wash_count_today > 0:
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            b = twin.behavioral
            env = twin.environment

            sneeze = b.sneeze_count_today or 0
            wash = b.nasal_wash_count_today or 0
            severity = _rhinitis_severity(sneeze, wash)

            findings: List[Dict[str, Any]] = []
            summary_parts: List[str] = []

            findings.append({
                "type": "symptom_severity",
                "severity": severity,
                "sneeze_count_today": sneeze,
                "nasal_wash_count_today": wash,
            })

            severity_zh = {
                "stable": "稳定",
                "mild": "轻度",
                "moderate": "中度",
                "severe": "重度",
            }[severity]
            summary_parts.append(f"鼻炎 {severity_zh}（喷嚏 {sneeze} / 洗鼻 {wash}）")

            # 环境相关
            env_parts = []
            if env.aqi is not None:
                env_parts.append(f"AQI {env.aqi}")
            if env.humidity_pct is not None:
                env_parts.append(f"湿度 {env.humidity_pct:.0f}%")
            env_ok = True
            if env.aqi is not None and env.aqi > 100:
                env_ok = False
                findings.append({
                    "type": "env_trigger",
                    "factor": "aqi",
                    "value": env.aqi,
                    "message": "空气质量差，PM2.5 会显著加重鼻炎症状。",
                    "action": "外出佩戴 N95 口罩；室内开启空气净化器；避免户外长时间停留。",
                })
            if env.humidity_pct is not None and env.humidity_pct > 75:
                env_ok = False
                findings.append({
                    "type": "env_trigger",
                    "factor": "humidity",
                    "value": env.humidity_pct,
                    "message": "湿度高有利于尘螨繁殖，可能加重过敏。",
                    "action": "卧室用除湿机将湿度控制在 40-60%；床上用品每 2 周 55°C 以上热水清洗。",
                })

            # 药物依从性
            active_meds = twin.medication.active_meds or []
            rhinitis_meds = [
                m for m in active_meds
                if any(k in (m.get("name") or "") for k in ["莫米松", "西替利嗪", "氯雷他定"])
            ]
            if rhinitis_meds and severity in ("moderate", "severe"):
                findings.append({
                    "type": "med_adherence",
                    "active_meds": [m.get("name") for m in rhinitis_meds],
                    "message": (
                        "有活跃症状期间，鼻喷糖皮质激素（莫米松）应每天固定使用 2-4 周"
                        "才能建立最佳效果，不要等症状出现才用。"
                    ),
                    "action": "今晚洗澡后固定使用鼻喷；如症状持续 > 1 周无改善，考虑加口服抗组胺药。",
                })

            # LPR 反流共现假说(锚点用户:伏诺拉生 + 胃溃疡 Hp- + 鼻症状)。
            # 仅在「有鼻症状 + 在用抑酸药 + 有反流/上消化道指标」三者共现时,提一条
            # **相关非因果、非诊断**的观察,交医生评估。不改 severity、不动莫米松依从、不给任何用药建议。
            if severity != "stable":
                acid_meds = _acid_suppression_meds(twin)
                reflux_ev = _reflux_indicator(twin) if acid_meds else None
                if acid_meds and reflux_ev:
                    findings.append({
                        "type": "reflux_hypothesis",
                        "confidence": "hypothesis",
                        # title 是 orchestrator 序列化器真正喂给 LLM 的字段(message 被丢弃),
                        # 故把「非诊断 / 相关非因果」的安全框架放进 title + summary,确保到达 LLM。
                        "title": "鼻症状与反流的相关性观察(相关非因果、非诊断,待医生评估)",
                        "acid_suppression_meds": acid_meds,
                        "evidence": reflux_ev,
                        "message": (
                            f"你在用抑酸药（{'、'.join(acid_meds)}）、有上消化道/反流相关记录"
                            f"（{reflux_ev}），同时有鼻部症状。咽喉反流(LPR)有时会刺激上气道、"
                            "表现出类似鼻炎的喷嚏/鼻塞——这只是一个**相关性观察、并非因果判断**,"
                            "也**不是诊断**。"
                        ),
                        "action": (
                            "下次复诊时,可以把鼻部症状和抑酸/反流治疗的时间关系一并讲给医生,"
                            "由医生判断是否需要从反流角度评估你的上气道症状。"
                        ),
                    })
                    summary_parts.append("鼻症状可能与反流相关(相关非因果、非诊断,待医生评估)")

            # 下一步行动
            actions: List[str] = []
            if severity == "severe":
                actions.append("今天避免花粉/尘螨暴露；全天佩戴口罩；增加洗鼻次数到 2-3 次。")
                actions.append("若症状影响睡眠或呼吸，考虑就诊耳鼻喉科评估是否需要加强方案。")
            elif severity == "moderate":
                actions.append("坚持每日鼻喷用药；晚上洗鼻一次；避免已知过敏原。")
            elif severity == "mild":
                actions.append("保持环境控制（空气净化器、除湿）；按需使用药物即可。")
            else:
                actions.append("症状稳定，维持当前方案。关注是否可以逐步减药。")

            for i, act in enumerate(actions, 1):
                findings.append({"type": "action", "order": i, "text": act})

            summary = " · ".join(summary_parts)
            if not env_ok:
                summary += " · 环境因素加重"

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "severity": severity,
                    "sneeze": sneeze,
                    "wash": wash,
                    "env_ok": env_ok,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[rhinitis_specialist] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"鼻炎评估失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
