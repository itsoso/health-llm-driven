"""
鼻炎趋势 API — 聚合 checkin（喷嚏/洗鼻）+ medication logs（莫米松/西替利嗪）的近期数据。

GET /api/v1/rhinitis-trend/me?days=7
"""

import logging
from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rhinitis-trend", tags=["rhinitis-trend"])

RHINITIS_MED_KEYWORDS = ["莫米松", "西替利嗪", "氯雷他定", "mometasone", "cetirizine"]


@router.get("/me")
def get_rhinitis_trend(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """
    返回最近 N 天的鼻炎趋势数据。

    每天一条：{date, sneeze, wash, meds: [{name, taken, time}]}
    """
    from app.models.health_checkin import HealthCheckin

    today = date.today()
    start = today - timedelta(days=days - 1)

    # 1. Checkin 数据（喷嚏/洗鼻）
    checkins = (
        db.query(HealthCheckin)
        .filter(
            HealthCheckin.user_id == current_user.id,
            HealthCheckin.checkin_date >= start,
            HealthCheckin.checkin_date <= today,
        )
        .order_by(HealthCheckin.checkin_date)
        .all()
    )
    checkin_map = {}
    for c in checkins:
        d = str(c.checkin_date)
        # 同一天可能有多条，取最大值
        existing = checkin_map.get(d, {})
        checkin_map[d] = {
            "sneeze": max(existing.get("sneeze", 0), c.sneeze_count or 0),
            "wash": max(existing.get("wash", 0), c.nasal_wash_count or 0),
        }

    # 2. Medication logs（鼻炎相关药物）
    med_map = {}  # date -> [{name, taken, time}]
    try:
        from app.models.medication import Medication, MedicationLog

        # 找出鼻炎相关药物 ID
        all_meds = (
            db.query(Medication)
            .filter(Medication.user_id == current_user.id, Medication.is_active == True)
            .all()
        )
        rhinitis_meds = [
            m for m in all_meds
            if any(kw.lower() in (m.name or "").lower() for kw in RHINITIS_MED_KEYWORDS)
        ]
        rhinitis_med_ids = {m.id: m.name for m in rhinitis_meds}

        if rhinitis_med_ids:
            logs = (
                db.query(MedicationLog)
                .filter(
                    MedicationLog.user_id == current_user.id,
                    MedicationLog.medication_id.in_(list(rhinitis_med_ids.keys())),
                    MedicationLog.taken_date >= start,
                    MedicationLog.taken_date <= today,
                )
                .all()
            )
            for log in logs:
                d = str(log.taken_date)
                if d not in med_map:
                    med_map[d] = []
                # 简化药名
                full_name = rhinitis_med_ids.get(log.medication_id, "")
                short = "莫米松" if "莫米松" in full_name else "西替利嗪" if "西替利嗪" in full_name else full_name.split(" ")[0]
                med_map[d].append({
                    "name": short,
                    "taken": log.status == "taken",
                    "time": str(log.taken_time) if log.taken_time else None,
                })
    except Exception as e:
        logger.warning(f"[rhinitis_trend] medication logs 查询失败: {e}")

    # 3. 组装每天的数据
    result = []
    for i in range(days):
        d = str(start + timedelta(days=i))
        c = checkin_map.get(d, {})
        result.append({
            "date": d,
            "sneeze": c.get("sneeze", 0),
            "wash": c.get("wash", 0),
            "meds": med_map.get(d, []),
        })

    # 4. 汇总统计
    total_sneeze = sum(r["sneeze"] for r in result)
    total_wash = sum(r["wash"] for r in result)
    med_days = sum(1 for r in result if any(m["taken"] for m in r["meds"]))

    return {
        "days": days,
        "start": str(start),
        "end": str(today),
        "daily": result,
        "summary": {
            "total_sneeze": total_sneeze,
            "total_wash": total_wash,
            "avg_sneeze": round(total_sneeze / days, 1),
            "avg_wash": round(total_wash / days, 1),
            "med_adherence_days": med_days,
            "med_adherence_pct": round(med_days / days * 100, 0) if days > 0 else 0,
        },
    }
