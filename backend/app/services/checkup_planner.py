"""R7 体检 / 专项筛查规划器 —— 按年龄·性别生成**人群筛查**复查项,物化成 ReviewSchedule。

定位与安全边界(与 ② course-review 已上线的提示性复查物化同一安全信封,非处方/非诊断):
- 只产出**人群层面、循证充分**的筛查建议(结直肠癌、血脂、血糖、上消化道、女性宫颈/乳腺、男性 PSA),
  每条带「以医生意见为准」+ priority=normal,**advisory-only**。
- **不内嵌按具体病灶分期的临床判定**(TI-RADS / Fleischner / NAFLD 分期)——那是临床锚定的
  `HealthProblem.follow_up` 的活;本规划器只补「用户还没登记成 HealthProblem 的、按年龄性别该做的通用筛查」。
- 物化成 `ReviewSchedule`,由**已上线**的 agenda 投影 + 器官 token 去重消费(本模块不碰 agenda_service):
  若用户已有同器官 HealthProblem(如胃溃疡),agenda 去重会自动抑制重复的胃镜筛查项。
- R4/R7 合规:系统不开方、不下诊断、不替代医生;数字阈值仅作筛查触发年龄,具体项目与时机交医生。
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.family_health import ReviewSchedule
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)

_DOCTOR_BOUNDARY = "属人群通用筛查建议,具体筛查项目、方式与时机请以医生意见为准。"
# 首次物化的到期日提前量:必须 ≤ agenda 默认投影窗(followup_within_days=14),否则新建项
# 落窗外、十几天内在议程上完全不可见(对抗评审实证的 BLOCKING)。7 天=可见 + 一周排期缓冲;
# priority=normal 保持不抢眼,不构成过度医疗化。
_LEAD_DAYS = 7

# 人群筛查规则:年龄/性别驱动、循证充分、China-context。sexes=None 不分性别;min/max_age 含边界。
# 数字仅为「该考虑筛查的年龄」,非诊断阈值;争议项(PSA)措辞强制 advisory。
_SCREENING_RULES: List[Dict[str, Any]] = [
    {"item": "血脂四项", "category": "blood", "department": "心血管内科",
     "min_age": 40, "max_age": None, "sexes": None, "interval_months": 12,
     "rationale": "40 岁以上建议每年查血脂以评估心血管风险"},
    {"item": "空腹血糖 / 糖化血红蛋白", "category": "blood", "department": "内分泌科",
     "min_age": 40, "max_age": None, "sexes": None, "interval_months": 12,
     "rationale": "40 岁以上建议每年查血糖以筛查糖尿病"},
    {"item": "结直肠癌筛查(肠镜或便潜血)", "category": "specialist", "department": "消化内科",
     "min_age": 45, "max_age": 75, "sexes": None, "interval_months": 120,
     "rationale": "45 岁起建议结直肠癌筛查(肠镜约每 10 年,或便潜血每年)"},
    {"item": "上消化道内镜(胃镜)", "category": "specialist", "department": "消化内科",
     "min_age": 40, "max_age": None, "sexes": None, "interval_months": 36,
     "rationale": "中国为胃癌高发区,40 岁以上(尤其幽门螺杆菌或胃病史者)建议胃镜筛查"},
    {"item": "宫颈癌筛查(HPV / TCT)", "category": "specialist", "department": "妇科",
     "min_age": 21, "max_age": 65, "sexes": {"female"}, "interval_months": 36,
     "rationale": "21–65 岁女性建议宫颈癌筛查(HPV/TCT 约每 3–5 年)"},
    {"item": "乳腺筛查(钼靶或超声)", "category": "imaging", "department": "乳腺科",
     "min_age": 40, "max_age": None, "sexes": {"female"}, "interval_months": 12,
     "rationale": "40 岁以上女性建议每 1–2 年乳腺筛查"},
    {"item": "前列腺癌筛查(PSA,需与医生讨论利弊)", "category": "blood", "department": "泌尿外科",
     "min_age": 50, "max_age": None, "sexes": {"male"}, "interval_months": 12,
     "rationale": "50 岁以上男性可与医生讨论是否做 PSA 筛查(需权衡早诊获益与过度诊断风险)"},
]


def _norm_gender(g: Any) -> Optional[str]:
    if not g:
        return None
    s = str(g).strip().lower()
    if s in ("male", "m", "男"):
        return "male"
    if s in ("female", "f", "女"):
        return "female"
    return None


def _user_age_sex(db: Session, user_id: int) -> Tuple[Optional[int], Optional[str]]:
    """从 UserProfile(优先)/ User 读出生日期·性别,算北京日历年龄。缺出生日期 → age=None。"""
    from app.models.user import User
    from app.models.user_profile import UserProfile

    bd = gender = None
    p = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if p is not None:
        bd, gender = p.birth_date, p.gender
    if bd is None or gender is None:
        u = db.query(User).filter(User.id == user_id).first()
        if u is not None:
            bd = bd or getattr(u, "birth_date", None)
            gender = gender or getattr(u, "gender", None)

    age = None
    if bd is not None:
        t = get_china_today()
        age = t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))
    return age, _norm_gender(gender)


def generate_checkup_recommendations(
    age: Optional[int], gender: Optional[str]
) -> List[Dict[str, Any]]:
    """按年龄/性别筛出适用的人群筛查项(纯函数,无 db)。无年龄 → 空。"""
    if age is None:
        return []
    gender = _norm_gender(gender)
    out: List[Dict[str, Any]] = []
    for r in _SCREENING_RULES:
        if age < r["min_age"] or (r["max_age"] is not None and age > r["max_age"]):
            continue
        if r["sexes"] is not None and (gender is None or gender not in r["sexes"]):
            continue
        out.append(r)
    return out


def ensure_checkup_schedules(db: Session, user_id: int) -> Dict[str, Any]:
    """把适用人群筛查项**幂等**物化成 ReviewSchedule(已上线 agenda 投影直接消费)。

    幂等键 = (user_id, item_name) 且未完成:已有同名 is_active 且 status≠completed 的项 → 跳过
    (**不按 next_due_date**,否则每日重跑会因日期推移重复建)。advisory:priority=normal、带医生边界。
    无年龄(缺出生日期)→ 不产出({reason:'no_age'})。
    """
    age, gender = _user_age_sex(db, user_id)
    if age is None:
        return {"created": 0, "skipped": 0, "reason": "no_age"}

    recs = generate_checkup_recommendations(age, gender)
    due = get_china_today() + timedelta(days=_LEAD_DAYS)
    created = skipped = 0
    for r in recs:
        exists = (
            db.query(ReviewSchedule)
            .filter(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.item_name == r["item"],
                ReviewSchedule.is_active.is_(True),
                ReviewSchedule.status != "completed",
            )
            .first()
        )
        if exists:
            skipped += 1
            continue
        db.add(ReviewSchedule(
            user_id=user_id,
            item_name=r["item"],
            category=r["category"],
            department=r["department"],
            next_due_date=due,
            interval_months=r["interval_months"],
            priority="normal",
            status="pending",
            notes=f"{r['rationale']};{_DOCTOR_BOUNDARY}",
        ))
        created += 1
    if created:
        db.commit()
    return {"created": created, "skipped": skipped, "age": age, "gender": gender}
