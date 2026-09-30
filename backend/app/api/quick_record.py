"""快速记录 API — 自然语言解析，一句话记录健康数据"""
import re
import logging
import unicodedata
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.daily_health import DietRecord, WaterIntake
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.api.deps import get_current_user_required
from app.api.supplements import _normalized_supplement_name
from app.schemas.blood_pressure import BloodPressureSafetyGuidance
from app.services.intake_intent_classifier import NON_INTAKE_REASONS, classify_intake_intent, non_intake_reason
from app.utils.blood_pressure_classify import blood_pressure_display

logger = logging.getLogger(__name__)

router = APIRouter()


def _invalidate_twin(user_id: int) -> None:
    """Fail-soft twin-cache invalidation after a write (rank7: also drops pregen)."""
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001 — a Redis error must never fail the write
        pass


class QuickRecordRequest(BaseModel):
    text: str


class QuickRecordResponse(BaseModel):
    type: str  # diet / water / weight / bp / supplement
    message: str
    success: bool
    record_id: Optional[int] = None
    undo_path: Optional[str] = None
    category: Optional[str] = None
    category_color: Optional[str] = None
    safety_guidance: Optional[BloodPressureSafetyGuidance] = None


def _quick_record_response(
    record_type: str,
    message: str,
    record_id: Optional[int] = None,
    undo_prefix: Optional[str] = None,
    category: Optional[str] = None,
    category_color: Optional[str] = None,
    safety_guidance: Optional[BloodPressureSafetyGuidance] = None,
) -> QuickRecordResponse:
    return QuickRecordResponse(
        type=record_type,
        message=message,
        success=True,
        record_id=record_id,
        undo_path=f"{undo_prefix}/{record_id}" if undo_prefix and record_id else None,
        category=category,
        category_color=category_color,
        safety_guidance=safety_guidance,
    )


# 餐次映射
MEAL_MAP = {
    "早餐": "breakfast",
    "早饭": "breakfast",
    "午餐": "lunch",
    "午饭": "lunch",
    "晚餐": "dinner",
    "晚饭": "dinner",
    "加餐": "snack",
    "零食": "snack",
    "夜宵": "snack",
}
MEAL_TYPE_CN = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}

# 餐次关键词正则（用于匹配）
MEAL_KEYWORDS = "|".join(MEAL_MAP.keys())

# 常见食物营养估算（每份 kcal / 蛋白质g / 碳水g / 脂肪g）
# 覆盖高频中国食物，快速返回无需调用 LLM
_FOOD_NUTRITION: dict[str, tuple[int, float, float, float]] = {
    # 主食
    "米饭": (200, 4, 44, 0.5),
    "白米饭": (200, 4, 44, 0.5),
    "炒饭": (320, 7, 50, 10),
    "面条": (280, 9, 52, 3),
    "牛肉面": (450, 22, 55, 14),
    "兰州拉面": (470, 24, 58, 14),
    "拌面": (400, 12, 58, 12),
    "馒头": (220, 7, 44, 1),
    "包子": (280, 12, 40, 8),
    "饺子": (350, 16, 48, 10),
    "粥": (120, 3, 26, 0.5),
    "皮蛋瘦肉粥": (180, 10, 28, 3),
    "油条": (380, 8, 45, 18),
    "烧饼": (320, 9, 50, 9),
    "煎饼果子": (420, 15, 52, 16),
    "三明治": (350, 15, 40, 14),
    "汉堡": (500, 22, 42, 25),
    "披萨": (450, 18, 52, 18),
    # 蛋白质
    "鸡胸肉": (165, 31, 0, 3.5),
    "鸡腿": (230, 24, 0, 14),
    "牛肉": (250, 26, 0, 15),
    "猪肉": (260, 22, 0, 18),
    "鱼": (150, 22, 0, 6),
    "虾": (100, 20, 1, 1.5),
    "鸡蛋": (80, 7, 0.5, 5.5),
    "煎蛋": (95, 7, 0.5, 7),
    "荷包蛋": (95, 7, 0.5, 7),
    "豆腐": (80, 8, 2, 4),
    # 蔬菜
    "沙拉": (80, 3, 10, 3),
    "蔬菜": (50, 2, 8, 0.5),
    "西兰花": (55, 4, 10, 0.5),
    "菠菜": (30, 3, 4, 0.4),
    # 汤
    "番茄蛋汤": (80, 5, 8, 3),
    "紫菜蛋花汤": (60, 5, 6, 2),
    "排骨汤": (200, 12, 5, 15),
    # 饮料/奶制品
    "牛奶": (150, 8, 12, 8),
    "豆浆": (80, 7, 5, 3),
    "酸奶": (130, 7, 17, 3),
    "果汁": (120, 0.5, 28, 0.2),
    "咖啡": (10, 0.3, 2, 0),
    "拿铁": (180, 8, 20, 7),
    # 零食/甜食
    "苹果": (80, 0.4, 21, 0.2),
    "香蕉": (90, 1.1, 23, 0.3),
    "坚果": (180, 5, 6, 16),
    "巧克力": (160, 2, 18, 9),
}


def _estimate_nutrition(food_text: str) -> tuple[int, float, float, float] | None:
    """根据食物描述估算营养（kcal, 蛋白质g, 碳水g, 脂肪g）"""
    for keyword, nutrition in _FOOD_NUTRITION.items():
        if keyword in food_text:
            return nutrition
    return None


# 补剂自由文本落 taken=true 会进 Twin 在服集 / DSI;否定/漏服/别日/计划/提问(没吃/忘了/昨天/
# 准备/让我吃/吗)一律 400 不写。这是只收紧的过滤,不是完整意图识别(如「睡前吃X」「我妈吃了X」
# 仍会通过),完整修复归共享 intake 分类器。先去空白,防「不 吃」绕过。
_SUPPLEMENT_NOT_TAKEN_RE = re.compile(
    r"没|沒|未|忘|漏(?:吃|服)|拒[绝絕]|不\S{0,2}(?:吃|服|喝)|[别別](?:忘|吃|服|喝)"
    r"|昨|前天|上[周週]|准备|準備|打算|待[会會]|等[会會下]|一[会會]|稍[后後]|明天|[记記]得|提醒"
    r"|要|[该該]|让我|讓我|建[议議]|吗|嗎|么|麼|[?？]"
)


def _is_not_taken_supplement_text(text: str) -> bool:
    return bool(_SUPPLEMENT_NOT_TAKEN_RE.search(re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))))


# 快速记录只写「今天」(血压/饮水时刻取 now):点名别的日子时一律 400 不写(不猜日期、不编时刻),补记去
# 各记录页选日期。只收紧:认不出的写法仍按今天记。「晚上周黑鸭/以后天天/目前天天/3号套餐」不算别日。
_CN_NUM = r"[\d几幾两兩一二三四五六七八九十]"
_OTHER_DAY_RE = re.compile(r"昨|(?<![目提以之])前[天晚]|明[天早晚]|(?<![饭飯餐午以之今])[后後]天|(?<![早晚马馬])上(?:个?(?:周|週|星期|礼拜|禮拜)|次)"
    rf"|{_CN_NUM}+\s*[天日]\s*[以之]?前|前\s*{_CN_NUM}+\s*天"
    r"|\d{1,2}\s*月\s*\d{1,2}|(?<!\d)\d{1,2}\s*[号號](?![套餐店楼樓])|\d{4}\s*[-/年]\s*\d{1,2}(?!\d)"
    r"|(?<![a-z])(?:yesterday|tomorrow|last\s*(?:night|week))(?![a-z])|days?\s*ago", re.IGNORECASE)
_OTHER_DAY_DETAIL = "快速记录只记今天，这句话提到了别的日子（如昨天、前天、上周或具体日期），本次未记录；补记请到对应记录页选择日期。"

# 剂量/时间不是补剂名(Mac 表单发「补剂<名称> <剂量与时间>」,见 apps/mac FeatureViews.submitStructured),
# 留在名字里会对不上已有定义、自动建出重复定义。数字剂量不紧贴字母数字(辅酶Q10),中文数字剂量须空格(三七片)。
_DOSE_UNIT = (r"\s*(?:粒|片|颗|顆|丸|滴|勺|袋|包|支|毫克|微克|克|毫升|国际单位|单位|單位|mcg|mg|μg|ug|iu|ml|g"
              r"|capsules?|caps?|tablets?|tabs?|softgels?|drops?|scoops?)(?![a-z])")
_NUM_DOSE = r"(?<![a-z\d.])\d+(?:\.\d+)?(?:\s*[-~～到至]\s*\d+(?:\.\d+)?)?" + _DOSE_UNIT
_CN_DOSE = r"[一二两兩三四五六七八九十半]" + _DOSE_UNIT
_SUPPLEMENT_TIMING = (r"[早午晚]?[餐饭飯][前后後中]|随餐|隨餐|睡前|空腹|早上|早晨|上午|中午|下午|晚上"
                      r"|(?:每|一)?[天日晚周週]?[一二两兩三四\d]*次|每[天日晚周週]")
_SUPPLEMENT_LEADING_DOSE_RE = re.compile(rf"^(?:{_NUM_DOSE}|{_CN_DOSE})\s*", re.IGNORECASE)
_SUPPLEMENT_DOSE_TAIL_RE = re.compile(
    rf"(?<=\S)(?:\s*{_NUM_DOSE}|\s+{_CN_DOSE}|\s+(?:{_SUPPLEMENT_TIMING})).*$", re.IGNORECASE | re.DOTALL)
# 表单尾巴只允许剂量/时间 token;剩别的(药名等)整句拒绝,绝不截断后静默丢弃。
_SUPPLEMENT_TAIL_TOKEN_RE = re.compile(rf"{_NUM_DOSE}|(?<!\S){_CN_DOSE}|{_SUPPLEMENT_TIMING}|[\s,，、;；/+]", re.I)


def _supplement_name(value: str) -> str:
    name = _SUPPLEMENT_LEADING_DOSE_RE.sub("", re.sub(r"^补剂\s*[:：]?\s*", "", value.strip()))
    return _SUPPLEMENT_DOSE_TAIL_RE.sub("", name).strip()


def _checked_supplement_name(text: str) -> Optional[str]:
    """干净补剂名(NFKC 只在此用,不碰血压/体重/饮水);截掉的部分含剂量/时间以外内容则 None(拒绝)。"""
    body = re.sub(r"^补剂\s*[:：]?\s*", "", unicodedata.normalize("NFKC", text))
    name = _supplement_name(body)
    if not name or name not in body:
        return None
    tail = body.replace(name, "", 1)
    return None if _SUPPLEMENT_TAIL_TOKEN_RE.sub("", tail) else name


def _parse_quick_record(text: str):
    """
    解析自然语言快速记录，返回 (type, data) 元组。
    支持：
      - 饮食：早餐牛肉面 / 午餐 鸡胸肉沙拉
      - 饮水：喝水500 / 水500ml / 喝水 500
      - 体重：体重71.5 / 体重 71.5kg
      - 血压：血压120/80 / 血压 130 85
    """
    text = text.strip()

    # --- 血压 ---
    bp_match = re.match(r"血压\s*(\d{2,3})\s*[/／]\s*(\d{2,3})", text)
    if bp_match:
        systolic = int(bp_match.group(1))
        diastolic = int(bp_match.group(2))
        return "bp", {"systolic": systolic, "diastolic": diastolic}

    bp_match2 = re.match(r"血压\s*(\d{2,3})\s+(\d{2,3})", text)
    if bp_match2:
        systolic = int(bp_match2.group(1))
        diastolic = int(bp_match2.group(2))
        return "bp", {"systolic": systolic, "diastolic": diastolic}

    # --- 体重 ---
    weight_match = re.match(r"体重\s*([\d.]+)\s*(?:kg|公斤)?", text, re.IGNORECASE)
    if weight_match:
        weight = float(weight_match.group(1))
        return "weight", {"weight": weight}

    # --- 饮水 ---
    water_match = re.match(r"(?:喝水|水|饮水)\s*(\d+)\s*(?:ml|毫升)?", text, re.IGNORECASE)
    if water_match:
        amount = int(water_match.group(1))
        return "water", {"amount": amount}

    # 分类/否定过滤都看完整原文(同改动前,用药守卫不被绕过);Mac 表单只另取干净名称。
    form = text.startswith("补剂")
    form_name = _checked_supplement_name(text) if form else None
    if form and form_name is None:
        return None, None
    intake = classify_intake_intent(text)
    if intake.reason in NON_INTAKE_REASONS:
        # 漏服/否定/计划/提问不是一次摄入;下方旧正则兜底也不得把它复活成记录。
        return None, None
    if intake.kind == "supplement" and intake.text.strip():
        name = form_name or _checked_supplement_name(intake.text)
        if not name or _is_not_taken_supplement_text(text):
            return None, None
        return "supplement", {"name": name}
    if intake.kind in {"medication", "diet_management"}:
        return None, None
    if intake.kind == "diet":
        meal_type = intake.slots.get("meal_type") or "snack"
        meal_cn = MEAL_TYPE_CN.get(meal_type, "加餐")
        food = intake.text.strip()
        if food:
            return "diet", {"meal_type": meal_type, "meal_cn": meal_cn, "food": food}
    # 分类器可能先判 health_metric(「午餐没吃，血糖5.6」);旧正则兜底前再单独看言语行为。
    if non_intake_reason(text):
        return None, None

    # legacy fallback: supplement must be checked before generic "吃了 xxx",
    # otherwise "吃了 维生素D" is incorrectly treated as diet.
    supp_match = re.match(r"(?:吃了?|服用|补剂)\s*(维生素|鱼油|钙片|叶酸|益生菌|辅酶|NAC|锌|镁|铁|B族|维C|维D|omega|Omega)(.*)$", text, re.IGNORECASE)
    if supp_match:
        raw_name = supp_match.group(1) + (supp_match.group(2) or "")
        supp_name = form_name or _checked_supplement_name(raw_name)
        if not supp_name or _is_not_taken_supplement_text(text) or non_intake_reason(raw_name.strip(), named=True):
            return None, None
        return "supplement", {"name": supp_name}

    # --- 饮食（指定餐次）---
    diet_match = re.match(rf"({MEAL_KEYWORDS})\s*(.*)", text)
    if diet_match:
        meal_cn = diet_match.group(1)
        food = diet_match.group(2).strip()
        meal_type = MEAL_MAP.get(meal_cn, "snack")
        return "diet", {"meal_type": meal_type, "meal_cn": meal_cn, "food": food or "未指定"}

    # --- 饮食（"吃了xxx"，自动推断餐次）---
    ate_match = re.match(r"(?:吃了|吃)\s+(.+)", text)
    if ate_match:
        food = ate_match.group(1).strip()
        from datetime import datetime as _dt
        hour = _dt.now().hour
        if 5 <= hour < 10:
            meal_type, meal_cn = "breakfast", "早餐"
        elif 10 <= hour < 14:
            meal_type, meal_cn = "lunch", "午餐"
        elif 14 <= hour < 17:
            meal_type, meal_cn = "snack", "加餐"
        elif 17 <= hour < 21:
            meal_type, meal_cn = "dinner", "晚餐"
        else:
            meal_type, meal_cn = "snack", "加餐"
        return "diet", {"meal_type": meal_type, "meal_cn": meal_cn, "food": food}

    return None, None


def _resolve_supplement_definition(db: Session, user_id: int, name: str) -> Optional[SupplementDefinition]:
    """镜像 /records/intake-batch:只看 active 定义(Twin 只统计它们);唯一精确同名才落卡,重复或仅相似(可能是
    复方)一律 409 列出、不猜;None = 需新建。Python 侧比较,不把用户文本拼进 LIKE(% / _ 是通配符)。"""
    normalized = _normalized_supplement_name(name)
    if not normalized:
        raise HTTPException(status_code=400, detail="补剂名称无效，本次未记录。")
    definitions = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == user_id,
        SupplementDefinition.is_active.is_(True),
    ).order_by(SupplementDefinition.id).all()
    keys = [(d, _normalized_supplement_name(d.name)) for d in definitions]
    exact = [d for d, key in keys if key == normalized]
    candidates = exact or [d for d, key in keys if key and (normalized in key or key in normalized)]
    if len(candidates) > 1 or (candidates and not exact):
        listed = "、".join(f"「{d.name}」" for d in candidates[:3]) + ("等" if len(candidates) > 3 else "")
        raise HTTPException(status_code=409, detail=(
            f"「{name}」在补剂列表里有重复定义：{listed}，本次未记录；请先在补剂页停用多余的一项。" if exact
            else f"「{name}」与已有补剂相似：{listed}，本次未记录；请写明完整名称。"))
    return candidates[0] if candidates else None


@router.post("/quick-record", response_model=QuickRecordResponse)
def quick_record(
    req: QuickRecordRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """自然语言快速记录健康数据"""
    user_id = current_user.id
    if _OTHER_DAY_RE.search(unicodedata.normalize("NFKC", req.text)):
        raise HTTPException(status_code=400, detail=_OTHER_DAY_DETAIL)
    record_type, data = _parse_quick_record(req.text)

    if record_type is None:
        raise HTTPException(
            status_code=400,
            detail="无法识别。支持：午餐牛肉面 / 吃了鸡胸肉 / 喝水500 / 体重71.5 / 血压120/80 / 吃了维生素D",
        )

    today = date.today()

    try:
        if record_type == "diet":
            nutrition = _estimate_nutrition(data["food"])
            record = DietRecord(
                user_id=current_user.id,
                record_date=today,
                meal_type=data["meal_type"],
                food_items=data["food"],
                food_name=data["food"],
                calories=nutrition[0] if nutrition else None,
                protein=nutrition[1] if nutrition else None,
                carbs=nutrition[2] if nutrition else None,
                fat=nutrition[3] if nutrition else None,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            _invalidate_twin(current_user.id)
            nutrition_msg = f"，约 {nutrition[0]} kcal" if nutrition else ""
            return _quick_record_response(
                record_type="diet",
                message=f"已记录{data['meal_cn']}：{data['food']}{nutrition_msg}",
                record_id=record.id,
                undo_prefix="diet/records",
            )

        elif record_type == "water":
            record = WaterIntake(
                user_id=current_user.id,
                record_date=today,
                amount_ml=data["amount"],
                intake_time=datetime.now(),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            _invalidate_twin(current_user.id)
            return _quick_record_response(
                record_type="water",
                message=f"已记录饮水 {data['amount']}ml",
                record_id=record.id,
                undo_prefix="water/records",
            )

        elif record_type == "weight":
            record = WeightRecord(
                user_id=current_user.id,
                record_date=today,
                weight=data["weight"],
                source="quick_record",
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            _invalidate_twin(current_user.id)
            return _quick_record_response(
                record_type="weight",
                message=f"已记录体重 {data['weight']}kg",
                record_id=record.id,
                undo_prefix="weight/records",
            )

        elif record_type == "bp":
            record = BloodPressureRecord(
                user_id=current_user.id,
                record_date=today,
                systolic=data["systolic"],
                diastolic=data["diastolic"],
                measured_at=datetime.now(),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            _invalidate_twin(current_user.id)
            display = blood_pressure_display(record.systolic, record.diastolic)
            safety_guidance = display["safety_guidance"]
            return _quick_record_response(
                record_type="bp",
                message=f"已记录血压 {data['systolic']}/{data['diastolic']} mmHg",
                record_id=record.id,
                undo_prefix="blood-pressure/records",
                category=display["category"],
                category_color=display["category_color"],
                safety_guidance=(
                    BloodPressureSafetyGuidance.model_validate(safety_guidance)
                    if safety_guidance is not None
                    else None
                ),
            )

        elif record_type == "supplement":
            # 查找或创建补剂定义，然后打卡
            supp = _resolve_supplement_definition(db, current_user.id, data["name"])
            created = supp is None
            if created:
                # 自动创建补剂定义
                supp = SupplementDefinition(
                    user_id=current_user.id,
                    name=data["name"],
                    timing="morning",
                    category="其他",
                )
                db.add(supp)
                db.flush()
            # 打卡
            existing = db.query(SupplementRecord).filter(
                SupplementRecord.user_id == current_user.id,
                SupplementRecord.supplement_id == supp.id,
                SupplementRecord.record_date == today,
            ).first()
            if not existing:
                record = SupplementRecord(
                    user_id=current_user.id,
                    supplement_id=supp.id,
                    record_date=today,
                    taken=True,
                )
                db.add(record)
            elif existing.taken:
                record = existing  # 幂等:今天已打过卡
            else:
                # 当天已被取消勾选:自由文本不能把它翻回已服(误解析会虚高依从),也不假报已打卡。
                raise HTTPException(
                    status_code=409,
                    detail=f"今天的「{supp.name}」已被标记为未服,本次未改动;如确已服用,请在补剂页勾选。",
                )
            message = f"已新建补剂「{supp.name}」并打卡" if created else f"已打卡补剂：{supp.name}"  # 点名实际落到的定义
            db.commit()
            db.refresh(record)
            _invalidate_twin(current_user.id)
            return _quick_record_response(
                record_type="supplement",
                message=message,
                record_id=record.id,
            )

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        # 异常原文可能带 SQL/参数/健康值:不回显给客户端;ERROR 只记类型,堆栈只进 DEBUG(AGENTS.md §5)。
        logger.error("[quick_record] write failed record_type=%s user=%s error=%s",
                     record_type, user_id, type(exc).__name__)
        logger.debug("[quick_record] write failure detail", exc_info=True)
        raise HTTPException(status_code=500, detail="记录失败，请稍后重试。") from None
