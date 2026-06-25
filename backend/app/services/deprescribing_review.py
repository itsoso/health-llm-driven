"""多药梳理 / 减药候选评审(deprescribing review)。

盲点:系统结构天然偏"加"(原研药推荐/补剂建议),无"是否还都需要 / 能否精简"的梳理。
对多药人群(≥5 种),deprescribing 的健康收益不亚于加药(跌倒/认知/肝肾负荷/相互作用)。

⚠️ 安全红线(同 AGENTS.md / 世界观红线):**绝不说"停药/减量"**,只产出"减药**候选**"
+ 统一话术"请与医生/药师讨论是否可精简"。最终决策永远在医生。基于 Beers/STOPP 思路,
只标高把握、可查证的候选,不臆断。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.utils.timezone import get_china_today

POLYPHARMACY_THRESHOLD = 5
LONG_TERM_WEEKS = 8  # 长期抑酸/镇静 deprescribing 评估阈值

# 治疗类 → 关键词(同类多药=可能重复;某些类=长期 deprescribing 候选)
_CLASS_KEYWORDS: dict[str, list[str]] = {
    "抑酸药(PPI/P-CAB)": ["泮托拉唑", "奥美拉唑", "埃索美拉唑", "雷贝拉唑", "兰索拉唑",
                          "伏诺拉生", "沃克", "泮立苏", "潘妥洛克", "耐信", "波利特"],
    "他汀": ["他汀", "立普妥", "可定", "阿托伐", "瑞舒伐", "辛伐"],
    "苯二氮䓬/助眠": ["地西泮", "阿普唑仑", "劳拉西泮", "艾司唑仑", "唑吡坦", "佐匹克隆", "右佐匹克隆"],
    "抗组胺": ["西替利嗪", "氯雷他定", "地氯雷他定", "开瑞坦", "仙特明", "恩理思"],
    "促胃动力": ["伊托必利", "多潘立酮", "莫沙必利", "加斯清", "吗丁啉"],
}
# 长期使用属 deprescribing 候选的类(Beers/STOPP 思路)
_LONG_TERM_CANDIDATE = {"抑酸药(PPI/P-CAB)", "苯二氮䓬/助眠"}


def _classes_of(name: str) -> list[str]:
    n = (name or "").lower()
    return [cls for cls, kws in _CLASS_KEYWORDS.items() if any(k.lower() in n for k in kws)]


def review_medications(meds: list[dict[str, Any]], today: Optional[date] = None) -> dict[str, Any]:
    """meds: [{name, start_date(date|None), end_date(date|None)}]。返回减药候选(非建议)。

    全部 candidate 级,话术统一"请与医生讨论是否可精简"。
    """
    today = today or get_china_today()
    active = [m for m in meds if m.get("name")]
    flags: list[dict[str, Any]] = []

    # 1) 多药
    if len(active) >= POLYPHARMACY_THRESHOLD:
        flags.append({
            "code": "polypharmacy",
            "detail": f"当前在用 {len(active)} 种药(≥{POLYPHARMACY_THRESHOLD} 即多药)",
            "suggestion": "建议带齐所有在用药(含保健品)请医生/药师做一次用药梳理,看是否可精简。",
        })

    # 2) 同类重复
    by_class: dict[str, list[str]] = {}
    for m in active:
        for cls in _classes_of(m["name"]):
            by_class.setdefault(cls, []).append(m["name"])
    for cls, names in by_class.items():
        if len(names) >= 2:
            flags.append({
                "code": "duplicate_class",
                "detail": f"{cls} 同类 {len(names)} 种:{' / '.join(names)}",
                "suggestion": f"同类多药可能重复,请与医生确认 {cls} 是否需要保留这么多种。",
            })

    # 3) 长期 deprescribing 候选(抑酸/镇静 用满阈值周数)
    for m in active:
        classes = _classes_of(m["name"])
        cand = [c for c in classes if c in _LONG_TERM_CANDIDATE]
        if not cand:
            continue
        sd = m.get("start_date")
        if isinstance(sd, date):
            weeks = (today - sd).days / 7
            if weeks >= LONG_TERM_WEEKS:
                flags.append({
                    "code": "long_term_candidate",
                    "detail": f"{m['name']}({cand[0]})已用 {int(weeks)} 周(≥{LONG_TERM_WEEKS} 周)",
                    "suggestion": f"{cand[0]}长期使用是减药评估的重点(如 PPI 长期用与镁/B12 缺乏、"
                                  "镇静药与跌倒/认知相关)。请与医生评估是否仍需继续或可降阶。",
                })

    # 4) 过期仍 active(忘记停用)
    for m in active:
        ed = m.get("end_date")
        if isinstance(ed, date) and ed < today:
            flags.append({
                "code": "expired_still_active",
                "detail": f"{m['name']} 计划结束日 {ed.isoformat()} 已过,仍标在用",
                "suggestion": "若已停用,请在 App 里标记停用;若仍在用,请与医生确认是否延长疗程。",
            })

    return {
        "active_count": len(active),
        "is_polypharmacy": len(active) >= POLYPHARMACY_THRESHOLD,
        "flags": flags,
        "disclaimer": "以上为减药**候选**提示,非建议停药/减量;任何调整务必经医生决定。",
    }
