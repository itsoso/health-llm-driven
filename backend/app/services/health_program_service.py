"""健康项目服务(第 4 个一等对象)。串 Problem→Protocol→outcome 的 8–12 周容器。"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.health_program import HealthProgram, PROGRAM_TYPES, PROGRAM_STATUS
from app.models.health_protocol import HealthProtocol
from app.models.health_problem import HealthProblem

logger = logging.getLogger(__name__)


def create_program(db: Session, user_id: int, data: Dict[str, Any]) -> HealthProgram:
    if data.get("program_type") not in PROGRAM_TYPES:
        raise ValueError(f"未知 program_type: {data.get('program_type')}")
    if data.get("status") and data["status"] not in PROGRAM_STATUS:
        raise ValueError(f"未知 status: {data['status']}")
    g = HealthProgram(
        user_id=user_id,
        name=data["name"],
        program_type=data["program_type"],
        status=data.get("status", "active"),
        problem_id=data.get("problem_id"),
        primary_metrics=data.get("primary_metrics"),
        secondary_metrics=data.get("secondary_metrics"),
        baseline=data.get("baseline"),
        target=data.get("target"),
        latest=data.get("latest"),
        started_on=data.get("started_on") or date.today(),
        target_end_on=data.get("target_end_on"),
        notes=data.get("notes"),
    )
    db.add(g); db.commit(); db.refresh(g)
    logger.info(f"[Program] 创建: user={user_id} type={g.program_type} name={g.name}")
    return g


def list_programs(db: Session, user_id: int, active_only: bool = True) -> List[HealthProgram]:
    q = db.query(HealthProgram).filter(HealthProgram.user_id == user_id)
    if active_only:
        q = q.filter(HealthProgram.status == "active")
    return q.order_by(HealthProgram.created_at.desc()).all()


def get_program(db: Session, program_id: int, user_id: int) -> Optional[HealthProgram]:
    return db.query(HealthProgram).filter(
        HealthProgram.id == program_id, HealthProgram.user_id == user_id
    ).first()


def set_status(db: Session, program_id: int, user_id: int, status: str) -> Optional[HealthProgram]:
    if status not in PROGRAM_STATUS:
        raise ValueError(f"未知 status: {status}")
    g = get_program(db, program_id, user_id)
    if not g:
        return None
    g.status = status
    db.commit(); db.refresh(g)
    return g


def attach_protocol(db: Session, program_id: int, protocol_id: int, user_id: int) -> bool:
    """把协议挂到项目下(set HealthProtocol.program_id)。两者都须属当前用户。"""
    g = get_program(db, program_id, user_id)
    if not g:
        raise ValueError("项目不存在")
    p = db.query(HealthProtocol).filter(
        HealthProtocol.id == protocol_id, HealthProtocol.user_id == user_id
    ).first()
    if not p:
        raise ValueError("协议不存在")
    p.program_id = program_id
    db.commit()
    return True


def _linked_protocols(db: Session, program_id: int, user_id: int) -> List[HealthProtocol]:
    return db.query(HealthProtocol).filter(
        HealthProtocol.program_id == program_id,
        HealthProtocol.user_id == user_id,
        HealthProtocol.status == "active",
    ).all()


def progress(db: Session, program_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """项目进度:绑定的协议清单 + 关联问题 + outcome(baseline→latest→target)。"""
    g = get_program(db, program_id, user_id)
    if not g:
        return None
    protos = _linked_protocols(db, program_id, user_id)
    problem = None
    if g.problem_id:
        pr = db.query(HealthProblem).filter(
            HealthProblem.id == g.problem_id, HealthProblem.user_id == user_id
        ).first()
        if pr:
            problem = {"id": pr.id, "name": pr.name, "risk_level": pr.risk_level,
                       "follow_up": pr.follow_up}
    return {
        "program": serialize_program(g),
        "protocols": [{"id": p.id, "domain": p.domain, "name": p.name, "status": p.status}
                      for p in protos],
        "protocol_count": len(protos),
        "problem": problem,
        "outcome": {"baseline": g.baseline, "latest": g.latest, "target": g.target,
                    "primary_metrics": g.primary_metrics},
    }


def create_from_problem(
    db: Session, user_id: int, problem_id: int,
    program_type: str, name: Optional[str] = None,
) -> HealthProgram:
    """从一条 HealthProblem 起一个管理它的 Program(如 胃溃疡→愈合/代谢 program)。"""
    pr = db.query(HealthProblem).filter(
        HealthProblem.id == problem_id, HealthProblem.user_id == user_id
    ).first()
    if not pr:
        raise ValueError("问题不存在")
    return create_program(db, user_id, {
        "name": name or f"{pr.name} 管理项目",
        "program_type": program_type,
        "problem_id": pr.id,
    })


def serialize_program(g: HealthProgram) -> Dict[str, Any]:
    return {
        "id": g.id, "name": g.name, "program_type": g.program_type, "status": g.status,
        "problem_id": g.problem_id,
        "primary_metrics": g.primary_metrics, "secondary_metrics": g.secondary_metrics,
        "baseline": g.baseline, "target": g.target, "latest": g.latest,
        "started_on": str(g.started_on) if g.started_on else None,
        "target_end_on": str(g.target_end_on) if g.target_end_on else None,
        "notes": g.notes,
    }
