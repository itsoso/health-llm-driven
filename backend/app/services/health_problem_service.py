"""医学问题登记服务(R13)。CRUD + 到期随访投影 + 升级判断雏形。

不替代医生:系统只登记、随访、到期/红线提示;不诊断、不开方。
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.health_problem import HealthProblem, RISK_LEVELS, PROBLEM_STATUS
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)


def create_problem(db: Session, user_id: int, data: Dict[str, Any]) -> HealthProblem:
    if data.get("risk_level") and data["risk_level"] not in RISK_LEVELS:
        raise ValueError(f"未知 risk_level: {data['risk_level']}")
    if data.get("status") and data["status"] not in PROBLEM_STATUS:
        raise ValueError(f"未知 status: {data['status']}")
    p = HealthProblem(
        user_id=user_id,
        name=data["name"],
        risk_level=data.get("risk_level", "P1"),
        status=data.get("status", "active"),
        diagnosis=data.get("diagnosis"),
        risk_stratification=data.get("risk_stratification"),
        red_lines=data.get("red_lines"),
        responsible=data.get("responsible"),
        follow_up=data.get("follow_up"),
        escalation_path=data.get("escalation_path"),
        evidence_tier=data.get("evidence_tier"),
        notes=data.get("notes"),
    )
    db.add(p); db.commit(); db.refresh(p)
    logger.info(f"[Problem] 登记: user={user_id} name={p.name} risk={p.risk_level}")
    return p


def list_problems(db: Session, user_id: int, active_only: bool = True) -> List[HealthProblem]:
    q = db.query(HealthProblem).filter(HealthProblem.user_id == user_id)
    if active_only:
        q = q.filter(HealthProblem.status != "resolved")
    # P0 在前(医学优先级压过其他)
    return sorted(q.all(), key=lambda p: (p.risk_level or "P9", p.id))


def get_problem(db: Session, problem_id: int, user_id: int) -> Optional[HealthProblem]:
    return db.query(HealthProblem).filter(
        HealthProblem.id == problem_id, HealthProblem.user_id == user_id
    ).first()


def set_status(db: Session, problem_id: int, user_id: int, status: str) -> Optional[HealthProblem]:
    if status not in PROBLEM_STATUS:
        raise ValueError(f"未知 status: {status}")
    p = get_problem(db, problem_id, user_id)
    if not p:
        return None
    p.status = status
    db.commit(); db.refresh(p)
    return p


def due_followups(db: Session, user_id: int, within_days: int = 45) -> List[Dict[str, Any]]:
    """到期/即将到期的随访(follow_up.next_due ≤ today+within_days)→ 投影成议程/提醒源。

    today 按用户本地时区(UserProfile.timezone,缺省回退中国时区)取,使「逾期/N 天内到期」
    的判定落在用户自己的日历日边界上。
    """
    today = get_user_today(db, user_id)
    cutoff = today + timedelta(days=within_days)
    out: List[Dict[str, Any]] = []
    for p in list_problems(db, user_id, active_only=True):
        fu = p.follow_up or {}
        nd = fu.get("next_due")
        if not nd:
            continue
        try:
            due = date.fromisoformat(str(nd))
        except (ValueError, TypeError):
            continue
        if due <= cutoff:
            out.append({
                "problem_id": p.id, "name": p.name, "risk_level": p.risk_level,
                "next_due": str(due), "overdue": due < today,
                "what_to_check": fu.get("what_to_check"),
                "responsible": p.responsible,
            })
    return sorted(out, key=lambda x: x["next_due"])


def serialize_problem(p: HealthProblem) -> Dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "risk_level": p.risk_level, "status": p.status,
        "diagnosis": p.diagnosis, "risk_stratification": p.risk_stratification,
        "red_lines": p.red_lines, "responsible": p.responsible, "follow_up": p.follow_up,
        "escalation_path": p.escalation_path, "evidence_tier": p.evidence_tier, "notes": p.notes,
    }


# ── seed:锚点用户真实病理(浙大一院 Y2026044477,活检 HP-)──────────
def create_gastric_ulcer_hp_negative(db: Session, user_id: int) -> HealthProblem:
    """从用户病理报告登记胃溃疡(Hp 阴性)。复查随访按医嘱「短期治疗后复查」。"""
    return create_problem(db, user_id, {
        "name": "胃溃疡(Hp 阴性,胃窦后壁)",
        "risk_level": "P1",
        "status": "active",
        "diagnosis": {
            "分型": "黏膜慢性轻度炎伴糜烂,小片炎性坏死渗出物",
            "hp_status": "negative",
            "证据": "胃镜活检 病理号 Y2026044477(浙大一院国际保健中心,2026-06-11)",
            "evidence_grade": "A",
        },
        "red_lines": [
            {"condition": "黑便/呕血", "action": "立即就医/急诊"},
            {"condition": "持续上腹痛进行性加重", "action": "消化内科复诊"},
            {"condition": "无诱因体重骤降", "action": "消化内科评估"},
        ],
        "responsible": "浙大一院 国际保健中心(初诊 程会贤 / 复诊 杜薇)",
        "follow_up": {
            "last_checkup": "2026-06-11",
            "cadence": "短期治疗后复查(医嘱)",
            "next_due": "2026-08-11",   # 约 8 周后复查胃镜/活检(可按医生调整)
            "what_to_check": "复查胃镜/活检确认愈合;去除诱因(NSAID/酒精/应激)",
        },
        "escalation_path": "复查到期/红线命中 → 消化内科;Hp- 不需根除,PPI 愈合疗程为准(以医生为准)",
        "evidence_tier": "A",
        "notes": "Hp 阴性 → 用药走 PPI 愈合模板(gu_ppi_healing_8w),非根除四联。",
    })
