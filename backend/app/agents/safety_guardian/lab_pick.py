"""化验异常项的顺序无关取值 —— labs 规则共用。

twin.labs.flagged_abnormal 是最新检查的**完整**异常集合(collector 按 record_date/id 倒序),
同日常有重复行(结构化导入 + 图片上传)和子串「影子项」(AST/ALT 比值、LDL-C/HDL-C、异型淋巴…)。
首个匹配取值会随列表内容/顺序漂移:加进更多同日行就可能换成影子项 → 告警降级。

pick_worst 的保证(加层不减层):
  1. 只看匹配项里**最新 exam_date** 那一天 —— 不拿更旧检查的更差值升级;
  2. 当天取**最差**数值(severity 越大越差)—— 同次检查加行只会维持或加重;
  3. 当天无数值 → 返回当天首个匹配(供计数/引用),与旧行为一致。
"""

from typing import Any, Callable, Dict, List, Optional


def as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def find_all(abnormals: List[Dict[str, Any]], name_keywords: List[str]) -> List[Dict[str, Any]]:
    """按中文/英文关键字(不区分大小写)找出全部匹配项, 保持原顺序。"""
    kws = [kw.lower() for kw in name_keywords]
    return [
        item for item in abnormals
        if any(kw in (item.get("item_name") or "").lower() for kw in kws)
    ]


def pick_worst(
    matches: List[Dict[str, Any]],
    severity: Callable[[float], float] = lambda v: v,
) -> Optional[Dict[str, Any]]:
    """最新 exam_date 当天、severity(value) 最大的匹配项; 见模块 docstring。"""
    if not matches:
        return None
    dates = [str(m["exam_date"]) for m in matches if m.get("exam_date") is not None]
    latest = max(dates) if dates else None
    # 无日期项(合成 twin / 旧缓存)保守并入最新组, 绝不因缺日期被丢
    same_day = [
        m for m in matches
        if m.get("exam_date") is None or str(m["exam_date"]) == latest
    ]
    numeric = [m for m in same_day if as_float(m.get("value")) is not None]
    if not numeric:
        return same_day[0]
    return max(numeric, key=lambda m: severity(as_float(m.get("value"))))

