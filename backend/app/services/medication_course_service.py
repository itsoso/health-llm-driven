"""用药疗程 → 复查闭环。

盘点缺口:Medication.end_date 存在但无任何"疗程结束→复查"机制;illness_episode
(如胃溃疡)与 ActionCard/复查日历隔离。本模块:扫即将结束的疗程,按药类给出
**该做的复查**(高把握映射,如 PPI/P-CAB/胃黏膜保护剂 → 胃镜复查),并物化为
ReviewSchedule(复查日历)。对话注入让三端都能提醒。

边界:复查建议="提示",最终由医生定;映射只放高把握项,其余给通用"疗程结束复诊"。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.family_health import ReviewSchedule
from app.models.medication import Medication
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)


# 关键词(规范化小写无空格命中)→ 复查项。仅高把握。
# 每项: (item_name, department, category)
_FOLLOWUP_RULES: list[tuple[list[str], tuple[str, str, str]]] = [
    # 抑酸/胃黏膜保护 → 溃疡/胃炎疗程后胃镜复查
    (["泮托拉唑", "奥美拉唑", "埃索美拉唑", "雷贝拉唑", "兰索拉唑", "伏诺拉生", "沃克",
      "泮立苏", "潘妥洛克", "替普瑞酮", "施维舒", "瑞巴派特", "膜固思达"],
     ("胃镜复查", "消化内科", "specialist")),
    # 他汀 → 血脂 + 肝酶复查
    (["他汀", "立普妥", "可定", "阿托伐", "瑞舒伐", "辛伐"],
     ("血脂 + 肝酶复查", "心血管内科", "blood")),
    # 甲状腺素 → 甲功复查
    (["左甲状腺素", "优甲乐"], ("甲状腺功能复查", "内分泌科", "blood")),
]


def _norm(name: str) -> str:
    return (name or "").lower().replace(" ", "")


def _followup_for(med_name: str) -> Optional[tuple[str, str, str]]:
    n = _norm(med_name)
    for kws, fu in _FOLLOWUP_RULES:
        if any(_norm(k) in n for k in kws):
            return fu
    return None


def upcoming_course_completions(db: Session, user_id: int, within_days: int = 45) -> list[dict[str, Any]]:
    """即将结束(end_date 在未来 within_days 内)的在用药 + 建议复查。

    无 end_date / 已过期太久的不算。按 end_date 升序。
    """
    today = get_china_today()  # 京历(Asia/Shanghai)边界,与全局一致;原 date.today() 随 runner OS tz 漂
    horizon = today + timedelta(days=within_days)
    meds = (
        db.query(Medication)
        .filter(
            Medication.user_id == user_id,
            Medication.is_active == True,  # noqa: E712
            Medication.end_date.isnot(None),
            Medication.end_date >= today,
            Medication.end_date <= horizon,
        )
        .order_by(Medication.end_date.asc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for m in meds:
        fu = _followup_for(m.name)
        out.append({
            "medication": m.name,
            "end_date": m.end_date.isoformat(),
            "days_left": (m.end_date - today).days,
            "followup": (
                {"item_name": fu[0], "department": fu[1], "category": fu[2]} if fu else None
            ),
        })
    return out


def users_with_upcoming_completions(db: Session, within_days: int = 45) -> list[int]:
    """有在用药且 end_date 落在未来 within_days 内的用户 id(去重)。

    供每日物化任务做「活跃用户」预筛,避免空扫全体用户。窗口与
    upcoming_course_completions / ensure_review_schedules 共用同一 get_china_today 边界,
    保证预筛集与逐人物化看到的是同一个「今天」(京历 Asia/Shanghai)。
    """
    today = get_china_today()
    horizon = today + timedelta(days=within_days)
    rows = (
        db.query(Medication.user_id)
        .filter(
            Medication.is_active == True,  # noqa: E712
            Medication.end_date.isnot(None),
            Medication.end_date >= today,
            Medication.end_date <= horizon,
        )
        .distinct()
        .all()
    )
    return [uid for (uid,) in rows]


def ensure_review_schedules(db: Session, user_id: int, within_days: int = 45) -> dict[str, int]:
    """为有明确复查项的即将结束疗程物化 ReviewSchedule(复查日历)。

    幂等:同 (user_id, item_name, next_due_date) 已存在则不重复建。
    next_due_date = 疗程结束日。返回 {created, skipped}。
    """
    items = upcoming_course_completions(db, user_id, within_days)
    created = skipped = 0
    for it in items:
        fu = it["followup"]
        if not fu:
            continue
        due = date.fromisoformat(it["end_date"])
        exists = (
            db.query(ReviewSchedule)
            .filter(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.item_name == fu["item_name"],
                ReviewSchedule.next_due_date == due,
            )
            .first()
        )
        if exists:
            skipped += 1
            continue
        db.add(ReviewSchedule(
            user_id=user_id,
            item_name=fu["item_name"],
            category=fu["category"],
            department=fu["department"],
            next_due_date=due,
            priority="high",
            status="pending",
            notes=f"{it['medication']} 疗程({it['end_date']} 结束)后建议复查;以医生意见为准。",
        ))
        created += 1
    if created:
        db.commit()
    return {"created": created, "skipped": skipped}


def course_prompt_blob(db: Session, user_id: int, within_days: int = 45) -> str:
    """注入 agent 的紧凑文本;无即将结束疗程返回空串。"""
    items = upcoming_course_completions(db, user_id, within_days)
    if not items:
        return ""
    lines = []
    for it in items:
        fu = it["followup"]
        tail = f" → 届时建议{fu['item_name']}({fu['department']})" if fu else " → 届时复诊评估是否继续"
        lines.append(f"- {it['medication']}:还有 {it['days_left']} 天({it['end_date']})结束{tail}")
    return ("【用药疗程提醒(相关时提及;复查为提示,以医生为准)】\n" + "\n".join(lines))
