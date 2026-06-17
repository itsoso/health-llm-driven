"""时点日程安全 seam(cut 5):把 SafetyGuardian 的 DDI/DSI 硬禁忌映射成「拒排 / 行警告」。

纯函数(只吃 meds 列表):由「待排的 meds 行」自身构最小 twin → 跑 DDI/DSI 规则 → 取 HIGH/CRITICAL
告警 → data_citation 里涉及的物质名 → 匹配回 meds 行,按 item 域分流:
  - supplement 侧 → forbidden_reasons(从时间轴移除,走告警);
  - medication 侧 → warnings(保留排程,行上标警告)。
R4 红线:处方药(domain=medication)**只 warn 永不 forbid**(不漏给药);drug×drug 两药都只 warn。
同源匹配:twin 的 active_meds/active_supplements 直接由 meds 派生,故名字匹配无跨表漂移。
"""
from typing import Dict, List, Tuple

from app.agents.safety_guardian.engine import evaluate_rules
from app.agents.safety_guardian.schema import Severity
from app.services.timing_adapter import _domain

_SEAM_CATEGORIES = {"ddi", "dsi"}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _flatten_citation_names(citation: dict) -> List[str]:
    out: List[str] = []
    for v in (citation or {}).values():
        if isinstance(v, (list, tuple)):
            out.extend(str(x) for x in v if isinstance(x, str))
    return out


def compute_seam(meds) -> Tuple[Dict[int, str], Dict[int, str]]:
    """返回 (forbidden_reasons={med_id: 理由}, warnings={med_id: 警告})。纯函数,无 DB。"""
    if not meds:
        return {}, {}
    from datetime import datetime, timezone

    from app.twin.schema import HealthTwin, TwinMeta

    # meta 仅供调试,不参与规则求解;用固定纪元保持纯函数确定性。
    twin = HealthTwin(meta=TwinMeta(user_id=0, generated_at=datetime(1970, 1, 1, tzinfo=timezone.utc)))
    twin.medication.active_meds = [{"name": getattr(m, "name", "") or ""} for m in meds if _domain(m) != "supplement"]
    twin.medication.has_any = bool(twin.medication.active_meds)
    twin.supplement.active_supplements = [{"name": getattr(m, "name", "") or ""} for m in meds if _domain(m) == "supplement"]

    alerts = [
        a for a in evaluate_rules(twin)
        if a.category in _SEAM_CATEGORIES and a.severity >= Severity.HIGH
    ]
    by_name = {_norm(getattr(m, "name", "")): m for m in meds if getattr(m, "name", None)}
    forbidden: Dict[int, str] = {}
    warnings: Dict[int, List[str]] = {}
    for a in alerts:
        for nm in _flatten_citation_names(a.data_citation):
            m = by_name.get(_norm(nm))
            if m is None or getattr(m, "id", None) is None:
                continue
            if _domain(m) == "supplement":
                forbidden[m.id] = a.title  # 补剂侧 → 拒排(R4 安全)
            else:
                warnings.setdefault(m.id, []).append(a.title)  # 处方药 → 只标警告,绝不拒排
    return forbidden, {mid: " / ".join(ts) for mid, ts in warnings.items()}
