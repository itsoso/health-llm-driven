"""健康上下文服务 — 为 Agent 提供丰富的用户健康摘要

设计目标：
- 800-1200 tokens 输出，~15 次 DB 查询
- 5 分钟内存缓存，命中 0ms
- 包含：实时数据 + 7 日趋势 + 目标进度 + 饮食概况 + 预警 + 待办
- 注入 Skill 路由表，让 LLM 知道有哪些能力可用
- 任何失败优雅降级，不影响对话
"""
import logging
import re
import threading
import time
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, case
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── 内存缓存 ──────────────────────────────────────────
# key = (user_id, budget) —— 不同注入档输出不同, 分开缓存, 避免各 profile 互相污染。
_context_cache: dict[tuple[int, str], tuple[float, str]] = {}
_context_cache_entry_generations: dict[tuple[int, str], int] = {}
_context_generations: dict[int, int] = {}
_context_cache_lock = threading.RLock()
_CACHE_TTL = 300  # 5 分钟

# 医生反馈属于 L3 健康数据：只召回很小的近期窗口，并在字段、单条、整段三层限长。
_CLINICIAN_FEEDBACK_RECENT_LIMIT = 3
_CLINICIAN_FEEDBACK_FIELD_MAX_CHARS = 240
_CLINICIAN_FEEDBACK_ENTRY_MAX_CHARS = 640
_CLINICIAN_FEEDBACK_SECTION_MAX_CHARS = 2048

# ── 注入档 (P2 意图分级) ────────────────────────────────
# FULL:    维持现状全量注入 (个人判读意图 / 默认)。
# MINIMAL: 纯知识题 —— 保留基础画像 (年龄/性别/慢病标签/用药/过敏/目标/基因静态标签),
#          裁掉一切具体时序数值 (今日读数、7 日趋势、恢复就绪、病症天数、饮水/饮食、
#          运动、预警、打卡、补剂服用状态、周计划、记忆), 避免污染通用知识回答。
# RECOVERY/DIET/MEDICATION/LABS: 单域个人问题的固定窄档；公共安全字段始终保留。
INJECTION_FULL = "full"
INJECTION_MINIMAL = "minimal"
INJECTION_RECOVERY = "recovery"
INJECTION_DIET = "diet"
INJECTION_MEDICATION = "medication"
INJECTION_LABS = "labs"
_INJECTION_BUDGETS = (
    INJECTION_FULL,
    INJECTION_MINIMAL,
    INJECTION_RECOVERY,
    INJECTION_DIET,
    INJECTION_MEDICATION,
    INJECTION_LABS,
)


def invalidate_health_context(user_id: int) -> None:
    """清除单个用户的所有健康上下文 profile 缓存。"""
    with _context_cache_lock:
        _context_generations[user_id] = _context_generations.get(user_id, 0) + 1
        for budget in _INJECTION_BUDGETS:
            cache_key = (user_id, budget)
            _context_cache.pop(cache_key, None)
            _context_cache_entry_generations.pop(cache_key, None)


# 纯知识题标志: 问定义 / 机制 / 分期 / 通用剂量 / 科普。命中 → MINIMAL 候选。
_KNOWLEDGE_MARKERS = re.compile(
    r"什么是|是什么|啥是|定义|概念|机制|原理|为什么会|怎么形成|分几期|分几级|"
    r"分期|分级|分类|有哪些|区别是|区别在|科普|介绍一下|讲讲|讲一下|解释|"
    r"一般|通常|正常范围|正常值|标准是|指南|循证|"
    r"what is|what are|definition|mechanism|how does|stages of|difference between",
    re.IGNORECASE,
)

# 个人判读标志: 一旦命中, 说明用户在问自己的情况 → 强制回退 FULL (fail-open 给足上下文)。
# 覆盖第一/第二人称健康诉求、求助、适配性提问。保守宽松, 宁可多判 FULL。
_PERSONAL_MARKERS = re.compile(
    r"我的|我该|我要|我想|帮我|给我|我现在|我这|我最近|我今天|我能不能|我能否|"
    r"我可以|我适合|适合我|适不适合|我需要|我是不是|我有没有|我会不会|"
    r"怎么办|怎么调|如何改善|该不该|要不要吃|能不能吃|停不停|"
    r"my |should i|can i|for me|do i need|am i",
    re.IGNORECASE,
)


def classify_injection_budget(query: Optional[str]) -> str:
    """判定该 query 的个人上下文注入档。

    保守 fail-open: 只有当 query **明确是纯知识题** (命中知识标志) 且
    **不含任何个人判读诉求** (未命中个人标志) 时才降级 MINIMAL;
    任何拿不准 → FULL (宁可多给不可漏给, 安全相关上下文绝不因误判被削)。
    """
    q = (query or "").strip()
    if not q:
        return INJECTION_FULL
    if _PERSONAL_MARKERS.search(q):
        return INJECTION_FULL
    if _KNOWLEDGE_MARKERS.search(q):
        return INJECTION_MINIMAL
    return INJECTION_FULL


_CONTEXT_DOMAIN_PATTERNS = {
    INJECTION_RECOVERY: re.compile(
        r"睡眠|睡得|入睡|起床|深睡|REM|HRV|心率|压力|身体电量|恢复|疲劳|"
        r"锻炼|运动|训练|跑步|步行|骑行|游泳|健身|活动量|workout|exercise|sleep|recovery",
        re.IGNORECASE,
    ),
    INJECTION_DIET: re.compile(
        r"饮食|早餐|早饭|午餐|午饭|晚餐|晚饭|加餐|零食|夜宵|吃什么|"
        r"热量|卡路里|蛋白|碳水|脂肪|膳食纤维|喝水|饮水|补水|diet|meal|calorie",
        re.IGNORECASE,
    ),
    INJECTION_MEDICATION: re.compile(
        r"用药|药物|吃药|服药|停药|换药|剂量|疗程|处方|补剂|保健品|"
        r"维生素|鱼油|益生菌|medication|medicine|supplement",
        re.IGNORECASE,
    ),
    INJECTION_LABS: re.compile(
        r"化验|体检|检查报告|检验|指标|肝功能|肾功能|血常规|血脂|血糖|"
        r"影像|胃镜|核磁|MRI|CT|X光|B超|基因|位点|检验单|lab|genetic",
        re.IGNORECASE,
    ),
}


def classify_context_profile(query: Optional[str]) -> str:
    """Choose a fixed query-scoped context lane, conservatively.

    Pure knowledge keeps the existing MINIMAL contract. One unambiguous health
    domain selects a stable scoped lane; cross-domain or unknown requests fail
    open to FULL so no required personal evidence is silently removed.
    """
    q = (query or "").strip()
    if not q:
        return INJECTION_FULL
    if classify_injection_budget(q) == INJECTION_MINIMAL:
        return INJECTION_MINIMAL
    matched = [
        profile
        for profile, pattern in _CONTEXT_DOMAIN_PATTERNS.items()
        if pattern.search(q)
    ]
    if len(matched) == 1:
        return matched[0]
    return INJECTION_FULL

# ── 系统规则 + Skill 路由表（注入到 system message） ─────
AGENT_HEALTH_SYSTEM_RULES = """你是用户的 AI 健康助理，能通过 Skills 查询数据、记录健康信息和执行分析。

## 你的能力（Skills）

| 场景 | 用哪个 Skill | 示例 |
|------|-------------|------|
| 查步数/心率/睡眠/血压/体重/饮水/打卡/运动/补剂/情绪/病症/异常预警 | health-query | "我最近睡得怎么样" |
| 记录饮水/体重/血压/打卡/饮食/病症/排泄/情绪/提醒 | health-record | "记录喝水250ml" |
| 健康评分/趋势分析/睡眠洞察/心率洞察/恢复状态/风险因素 | health-analysis | "分析我的健康趋势" |
| 运动前指导/运动后分析/恢复评估 | workout-coach | "今天适合跑步吗" |
| 饮食建议/营养分析/热量估算 | nutrition-advisor | "午餐吃什么好" |
| 补剂推荐/服用提醒/交互检查 | supplement-advisor | "推荐补剂" |
| 周计划生成/今日计划/完成追踪 | weekly-planner | "帮我制定本周计划" |
| 天气/空气质量/户外运动适宜度/早间简报 | environment-health | "今天空气质量如何" |
| 基因数据查询/基因风险分析/营养运动药物基因交叉分析 | genetic-analysis | "我的基因检测结果" |

## 行为准则

1. **主动分析**：不要只回答问题，要结合档案数据主动发现问题和机会
   - 看到恢复状态好 + 近期运动少 → 主动建议运动
   - 看到饮水不足 → 顺带提醒
   - 看到 HRV 偏低/SpO2<95% → 优先建议休息
2. **数据驱动**：给建议时引用具体数据（"你的 HRV 45ms 低于 7 日均值 52ms"），不要空泛
3. **先看档案再调 Skill**：档案里已有的数据直接用，需要更详细信息时再调 Skill
4. **慢性病 & 用药**：给运动/饮食/补剂建议时必须考虑用户的慢性病和当前用药
5. **严重问题**：HRV 持续偏低、SpO2<92%、血压异常、胸痛等 → 务必建议就医
6. **中文回复**：简洁务实，给出可执行的具体建议，不要泛泛而谈
7. **⚠️ 预警优先**：有未确认的健康预警时，必须在回复开头提醒
8. **过敏禁忌**：当用户有过敏或饮食禁忌时，所有饮食建议必须避开这些食物
9. **伤病限制**：当用户有慢性病或受伤史时，运动建议必须考虑身体限制
10. **历史偏好**：参考用户记忆中的历史偏好和医嘱，保持个性化
11. **具体数据**：在回复中主动引用具体数据（步数、心率、睡眠分数），不要泛泛而谈

以下是用户的实时健康档案：
"""


def _get_time_period() -> tuple[str, str]:
    """返回当前时间和时段标签"""
    from datetime import datetime, timezone, timedelta as td
    beijing = timezone(td(hours=8))
    now = datetime.now(beijing)
    hour = now.hour
    if 5 <= hour < 8:
        period = "清晨"
    elif 8 <= hour < 12:
        period = "上午"
    elif 12 <= hour < 14:
        period = "中午"
    elif 14 <= hour < 18:
        period = "下午"
    elif 18 <= hour < 21:
        period = "晚上"
    else:
        period = "深夜"
    return now.strftime("%H:%M"), period


def _append_context_section(base: str, section: str) -> str:
    """Append one prompt section without introducing empty separators."""
    if not base:
        return section
    if not section:
        return base
    return f"{base}\n{section}"


def _with_clinician_feedback_overlay(
    db: Session,
    user_id: int,
    budget: str,
    base_context: str,
) -> str:
    """Append bounded clinician feedback to personal/scoped contexts."""
    if budget == INJECTION_MINIMAL:
        return base_context
    return _append_context_section(
        base_context,
        _clinician_feedback_context_section(db, user_id),
    )


def build_lite_health_context(
    db: Session,
    user_id: int,
    intent: Optional[str] = None,
    *,
    domain_scoped: bool = False,
) -> Optional[str]:
    """构建健康上下文（~800-1200 tokens）。

    intent=None (默认): 全量注入, 行为逐字节等同旧实现 (零回归)。
    intent 为纯知识意图字符串 (见 classify_injection_budget): 降级 MINIMAL,
    只留基础画像, 裁掉具体时序数值。判据保守 fail-open —— 拿不准一律 FULL。
    domain_scoped=True: 单域问题使用固定窄 profile；未知或跨域仍回退 FULL。
    """
    if domain_scoped:
        budget = classify_context_profile(intent)
    else:
        budget = classify_injection_budget(intent) if intent is not None else INJECTION_FULL
    cache_key = (user_id, budget)
    base_context = None
    with _context_cache_lock:
        build_generation = _context_generations.get(user_id, 0)
        cached = _context_cache.get(cache_key)
        cached_generation = _context_cache_entry_generations.get(cache_key)
        if (
            cached
            and cached_generation == build_generation
            and (time.time() - cached[0]) < _CACHE_TTL
        ):
            base_context = cached[1]
        elif cached is not None:
            _context_cache.pop(cache_key, None)
            _context_cache_entry_generations.pop(cache_key, None)

    if base_context is None:
        try:
            base_context = _build_context(db, user_id, budget=budget)
            with _context_cache_lock:
                if _context_generations.get(user_id, 0) == build_generation:
                    _context_cache[cache_key] = (time.time(), base_context)
                    _context_cache_entry_generations[cache_key] = build_generation
        except Exception as e:
            logger.error(f"构建健康上下文失败(user={user_id}): {e}", exc_info=True)
            return None

    return _with_clinician_feedback_overlay(db, user_id, budget, base_context)


def _build_context(db: Session, user_id: int, budget: str = INJECTION_FULL) -> str:
    """按固定 profile 构建上下文；FULL 保持历史行为，MINIMAL 只留基础画像。"""
    minimal = budget == INJECTION_MINIMAL
    include_general = budget == INJECTION_FULL
    include_recovery = budget in {
        INJECTION_FULL,
        INJECTION_RECOVERY,
        INJECTION_DIET,
    }
    include_diet = budget in {INJECTION_FULL, INJECTION_DIET}
    include_workouts = budget in {INJECTION_FULL, INJECTION_RECOVERY}
    include_supplements = budget in {INJECTION_FULL, INJECTION_MEDICATION}
    include_genes = budget in {
        INJECTION_FULL,
        INJECTION_MINIMAL,
        INJECTION_MEDICATION,
        INJECTION_LABS,
    }
    from app.models.user import User
    from app.models.user_profile import UserProfile
    from app.models.daily_health import GarminData, WaterIntake, WorkoutRecord, DietRecord
    from app.models.weight import WeightRecord
    from app.models.illness import IllnessEpisode

    parts = []
    time_str, period = _get_time_period()
    today = date.today()

    # ── 1. 用户基本信息 ──────────────────────────────────
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ""

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    name = user.name or user.username or "用户"
    parts.append("[用户健康档案]")

    city = ""
    if profile:
        from app.services.location_resolver import resolve_effective_location
        city = resolve_effective_location(profile)["city"] or ""
    location_str = f" | 位置: {city}" if city else ""
    # 缓存稳定性(rank13 prefill):HH:MM 的分钟每回合都变,落在 tool schema 之前的 system 前缀里
    # → 每分钟把下游 ~27k 字符静态头(base 规则 + 21.7k tool schema)整段 cache-miss(实测隐式命中
    # 仅 29%)。降精度到「小时 + 时段」:5min TTL 窗内恒稳定(仅跨整点偶变),模型仍知大致时刻;
    # 精确时间戳由工具侧 datetime.now() 负责(记录落库时间不受影响)。
    hour_str = time_str.split(":")[0] if ":" in time_str else time_str
    parts.append(f"时间: {hour_str}点 ({period}){location_str}")

    age_str = ""
    max_hr = 0
    if profile and profile.age:
        age = profile.age
        age_str = f", {age}岁"
        max_hr = 220 - age

    gender_map = {"male": "男", "female": "女"}
    gender = gender_map.get(profile.gender, "") if profile else ""
    if gender:
        gender = f", {gender}"

    max_hr_str = f", 最大心率{max_hr}bpm" if max_hr else ""
    parts.append(f"用户: {name}{gender}{age_str}{max_hr_str}")

    # 身体数据
    if profile:
        body_parts = []
        if profile.height_cm:
            body_parts.append(f"{profile.height_cm:.0f}cm")

        weight_val = None
        latest_weight = db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id
        ).order_by(WeightRecord.record_date.desc()).first()
        if latest_weight:
            weight_val = latest_weight.weight
        elif profile.current_weight_kg:
            weight_val = profile.current_weight_kg

        if weight_val:
            target = profile.target_weight_kg
            w_str = f"{weight_val:.1f}kg"
            if target:
                diff = weight_val - target
                w_str += f"(目标{target:.0f}kg, {'需减' if diff > 0 else '需增'}{abs(diff):.1f}kg)"
            body_parts.append(w_str)

        if weight_val and profile.height_cm:
            h_m = profile.height_cm / 100
            bmi = weight_val / (h_m * h_m)
            body_parts.append(f"BMI {bmi:.1f}")

        if body_parts:
            parts.append(f"身体: {', '.join(body_parts)}")

        # 慢性病 + 用药
        conditions = profile.chronic_conditions or []
        meds = profile.current_medications or []
        med_names = [m["name"] if isinstance(m, dict) else str(m) for m in meds]

        health_info = []
        if conditions:
            health_info.append(f"慢性病: {', '.join(conditions)}")
        if med_names:
            health_info.append(f"用药: {', '.join(med_names)}")
        if health_info:
            parts.append(" | ".join(health_info))

    # ── 1b. 健康目标 ──────────────────────────────────────
    if profile:
        goal_parts = []
        if profile.target_steps:
            goal_parts.append(f"步数{profile.target_steps}")
        if profile.target_sleep_hours:
            goal_parts.append(f"睡眠{profile.target_sleep_hours}h")
        if profile.target_water_ml:
            goal_parts.append(f"饮水{profile.target_water_ml}ml")
        if profile.target_exercise_minutes:
            goal_parts.append(f"运动{profile.target_exercise_minutes}min")
        if goal_parts:
            parts.append(f"健康目标: 每日{' | '.join(goal_parts)}")

    # ── 1c. 过敏与饮食偏好 ───────────────────────────────
    if profile:
        diet_info = []
        allergies = profile.allergies or []
        if allergies:
            diet_info.append(f"过敏/禁忌: {', '.join(allergies)}")
        pref_map = {"vegetarian": "素食", "vegan": "纯素", "low_carb": "低碳水",
                     "keto": "生酮", "normal": ""}
        pref = pref_map.get(profile.diet_preference or "", profile.diet_preference or "")
        if pref:
            diet_info.append(f"饮食偏好: {pref}")
        if diet_info:
            parts.append(" | ".join(diet_info))

    # ── 1d. 用户记忆 ────────────────────────────────────
    if include_general:
        try:
            from app.services.conversation_memory_service import get_relevant_memories
            memories_str = get_relevant_memories(db, user_id, limit=5)
            if memories_str:
                parts.append(memories_str)
        except Exception:
            pass

    # ── MINIMAL 短路: 纯知识题只需基础画像 (含上方年龄/性别/身体/慢病/用药/过敏/目标) +
    # 下方基因静态标签; 具体时序数值 (今日读数/趋势/恢复/病症天数/饮水/饮食/运动/预警/
    # 打卡/补剂状态/周计划) 全部跳过 —— 避免污染通用知识回答, 也去掉「没问却翻病历」观感。
    if minimal:
        parts.append(_gene_context_section(db, user_id))
        return "\n".join(p for p in parts if p)

    # ── 2. 今日 Garmin 数据 ──────────────────────────────
    latest_garmin = None
    if include_recovery:
        latest_garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id
        ).order_by(GarminData.record_date.desc()).first()

    if latest_garmin:
        g = latest_garmin
        garmin_items = []
        if g.steps is not None:
            garmin_items.append(f"步数{g.steps}")
        if g.resting_heart_rate is not None:
            garmin_items.append(f"静息心率{g.resting_heart_rate}")
        if g.sleep_score is not None:
            sleep_h = f"({g.total_sleep_duration / 60:.1f}h)" if g.total_sleep_duration else ""
            garmin_items.append(f"睡眠{g.sleep_score}分{sleep_h}")
        if g.stress_level is not None:
            garmin_items.append(f"压力{g.stress_level}")
        if g.body_battery_most_charged is not None:
            garmin_items.append(f"电量{g.body_battery_most_charged}")
        if g.hrv is not None:
            status = f"({g.hrv_status})" if g.hrv_status else ""
            garmin_items.append(f"HRV{g.hrv:.0f}ms{status}")
        if g.spo2_avg is not None:
            garmin_items.append(f"SpO2:{g.spo2_avg:.0f}%")

        if garmin_items:
            date_label = "今日" if g.record_date == today else f"{g.record_date}"
            parts.append(f"{date_label}: {', '.join(garmin_items)}")

    # ── 3. 7 日趋势 + 变化方向 ─────────────────────────
    week_ago = today - timedelta(days=7)
    garmin_7d = []
    if include_recovery:
        garmin_7d = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= week_ago,
        ).order_by(GarminData.record_date).all()

    if len(garmin_7d) >= 3:
        steps_list = [g.steps for g in garmin_7d if g.steps is not None]
        sleep_list = [g.total_sleep_duration for g in garmin_7d if g.total_sleep_duration is not None]
        rhr_list = [g.resting_heart_rate for g in garmin_7d if g.resting_heart_rate is not None]
        stress_list = [g.stress_level for g in garmin_7d if g.stress_level is not None]
        hrv_list = [g.hrv for g in garmin_7d if g.hrv is not None]
        deep_list = [g.deep_sleep_duration for g in garmin_7d if g.deep_sleep_duration is not None]

        trend_parts = []
        if steps_list:
            avg = sum(steps_list) // len(steps_list)
            trend_parts.append(f"步数{avg}")
        if sleep_list:
            avg_h = sum(sleep_list) / len(sleep_list) / 60
            trend_parts.append(f"睡眠{avg_h:.1f}h")
        if deep_list:
            avg_deep = sum(deep_list) // len(deep_list)
            trend_parts.append(f"深睡{avg_deep}min")
        if rhr_list:
            trend_parts.append(f"静息心率{sum(rhr_list) // len(rhr_list)}")
        if stress_list:
            trend_parts.append(f"压力{sum(stress_list) // len(stress_list)}")
        if hrv_list:
            avg_hrv = sum(hrv_list) / len(hrv_list)
            trend_parts.append(f"HRV{avg_hrv:.0f}ms")

        if trend_parts:
            parts.append(f"7日均值: {', '.join(trend_parts)}")

        # 趋势方向：对比前 3 天 vs 后 3 天
        if len(garmin_7d) >= 6:
            first_half = garmin_7d[:3]
            second_half = garmin_7d[-3:]
            changes = []

            def _trend(items_early, items_late, field, label, reverse=False):
                vals_e = [getattr(g, field) for g in items_early if getattr(g, field) is not None]
                vals_l = [getattr(g, field) for g in items_late if getattr(g, field) is not None]
                if vals_e and vals_l:
                    avg_e = sum(vals_e) / len(vals_e)
                    avg_l = sum(vals_l) / len(vals_l)
                    if avg_e > 0:
                        pct = (avg_l - avg_e) / avg_e * 100
                        if abs(pct) > 10:
                            direction = "↑" if pct > 0 else "↓"
                            good = (pct > 0) != reverse
                            icon = "✅" if good else "⚠️"
                            changes.append(f"{icon}{label}{direction}{abs(pct):.0f}%")

            _trend(first_half, second_half, "steps", "步数")
            _trend(first_half, second_half, "total_sleep_duration", "睡眠")
            _trend(first_half, second_half, "deep_sleep_duration", "深睡")
            _trend(first_half, second_half, "resting_heart_rate", "静息心率", reverse=True)
            _trend(first_half, second_half, "stress_level", "压力", reverse=True)

            if changes:
                parts.append(f"趋势: {', '.join(changes)}")

    # ── 3b. 可穿戴 7 日紧凑摘要 ───────────────────────────
    if include_recovery:
        try:
            from app.services.health_context_summary import (
                build_wearable_context_summary,
                format_wearable_context_summary_for_prompt,
            )

            wearable_summary = build_wearable_context_summary(db, user_id, days=7)
            if wearable_summary:
                parts.append(format_wearable_context_summary_for_prompt(wearable_summary))
        except Exception as e:
            logger.warning(f"构建可穿戴 7 日摘要失败(user={user_id}): {e}")

    # ── 4. 恢复就绪度 ─────────────────────────────────
    if latest_garmin:
        g = latest_garmin
        recovery_parts = []
        score = 0
        has_data = False

        if g.hrv and hasattr(g, 'hrv_7day_avg') and g.hrv_7day_avg and g.hrv_7day_avg > 0:
            ratio = g.hrv / g.hrv_7day_avg
            score += ratio * 40
            recovery_parts.append(f"HRV{'正常' if 0.85 <= ratio <= 1.15 else '偏低' if ratio < 0.85 else '偏高'}")
            has_data = True

        if g.body_battery_most_charged:
            battery = g.body_battery_most_charged
            score += battery * 0.3
            recovery_parts.append(f"电量{'充足' if battery >= 60 else '中等' if battery >= 30 else '不足'}")
            has_data = True

        if g.stress_level:
            stress = g.stress_level
            score += (100 - stress) * 0.3
            recovery_parts.append(f"压力{'低' if stress < 40 else '中等' if stress < 60 else '高'}")
            has_data = True

        if has_data:
            grade = "优秀" if score >= 80 else "良好" if score >= 60 else "一般" if score >= 40 else "较差"
            suggestion = "适合高强度训练" if score >= 70 else "建议中等强度运动" if score >= 50 else "建议轻度活动或休息"
            parts.append(f"恢复就绪: {score:.0f}分({grade}) — {', '.join(recovery_parts)} → {suggestion}")

    # ── 5. 活跃病症 ─────────────────────────────────────
    illnesses = db.query(IllnessEpisode).filter(
        IllnessEpisode.user_id == user_id,
        IllnessEpisode.status != "resolved",
    ).all()

    if illnesses:
        illness_strs = []
        for ill in illnesses:
            days = (today - ill.start_date).days if ill.start_date else 0
            severity_text = (
                f"{ill.severity}/10"
                if ill.severity is not None
                else "严重度未记录"
            )
            illness_strs.append(f"{ill.name}(第{days}天, {severity_text})")
        parts.append(f"当前病症: {', '.join(illness_strs)}")
        parts.append("急性状态约束: 生病/感冒/发热期间不要求完成运动训练目标, 优先恢复、补水、睡眠和症状观察。")

    # ── 6. 今日饮水 ─────────────────────────────────────
    if include_diet:
        try:
            water_today = db.query(WaterIntake).filter(
                WaterIntake.user_id == user_id,
                WaterIntake.record_date == today
            ).all()
            total_ml = sum(w.amount_ml or w.amount or 0 for w in water_today)
            if total_ml > 0:
                parts.append(f"今日饮水: {total_ml}ml / 2000ml ({total_ml * 100 // 2000}%)")
            else:
                parts.append("今日饮水: 尚未记录")
        except Exception:
            pass

    # ── 7. 今日饮食概况 ──────────────────────────────────
    diet_today = []
    if include_diet:
        try:
            diet_today = db.query(DietRecord).filter(
                DietRecord.user_id == user_id,
                DietRecord.record_date == today
            ).all()
            if diet_today:
                total_cal = sum(d.calories or 0 for d in diet_today)
                total_protein = sum(d.protein or 0 for d in diet_today)
                meals = len(diet_today)
                parts.append(f"今日饮食: {meals}餐, {total_cal:.0f}kcal, 蛋白质{total_protein:.0f}g")
            else:
                parts.append("今日饮食: 尚未记录")
        except Exception:
            pass

    # ── 7b. 能量平衡 ──────────────────────────────────────
    if include_diet:
        try:
            cal_in = sum(d.calories or 0 for d in diet_today) if diet_today else 0
            cal_out = latest_garmin.calories_burned if latest_garmin and latest_garmin.calories_burned else 0
            if cal_in > 0 or cal_out > 0:
                balance = cal_in - cal_out
                parts.append(f"能量平衡: 摄入{cal_in:.0f}kcal / 消耗{cal_out}kcal = {'+' if balance >= 0 else ''}{balance:.0f}kcal")
        except Exception:
            pass

    # ── 8. 最近运动 ─────────────────────────────────────
    if include_workouts:
        try:
            recent_workouts = db.query(WorkoutRecord).filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= today - timedelta(days=7)
            ).order_by(WorkoutRecord.workout_date.desc()).limit(3).all()

            if recent_workouts:
                w_strs = []
                for w in recent_workouts:
                    days_ago = (today - w.workout_date).days
                    when = "今天" if days_ago == 0 else f"{days_ago}天前"
                    w_info = f"{w.workout_type or '运动'}({when})"
                    if w.duration_seconds:
                        w_info += f" {w.duration_seconds // 60}min"
                    if w.distance_meters and w.distance_meters > 0:
                        w_info += f" {w.distance_meters / 1000:.1f}km"
                    w_strs.append(w_info)
                parts.append(f"近期运动: {' | '.join(w_strs)}")
            else:
                parts.append("近7天无运动记录")
        except Exception:
            pass

    # ── 8b. 运动水平（30天） ────────────────────────────
    if include_workouts:
        try:
            workout_30d_count = db.query(func.count(WorkoutRecord.id)).filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= today - timedelta(days=30)
            ).scalar() or 0
            if workout_30d_count <= 4:
                level = "新手"
            elif workout_30d_count <= 12:
                level = "中等"
            else:
                level = "活跃"
            parts.append(f"运动水平: {level} (最近30天{workout_30d_count}次运动)")
        except Exception:
            pass

    # ── 9. 健康预警（未读） ──────────────────────────────
    try:
        from app.models.anomaly_alert import AnomalyAlert
        recent_alerts = db.query(AnomalyAlert).filter(
            AnomalyAlert.user_id == user_id,
            AnomalyAlert.detection_date >= today - timedelta(days=3),
            AnomalyAlert.acknowledged.is_(False)
        ).order_by(AnomalyAlert.detection_date.desc()).limit(3).all()

        if recent_alerts:
            alert_strs = []
            for a in recent_alerts:
                severity_icon = "🔴" if a.severity == "critical" else "🟡"
                alert_strs.append(f"{severity_icon}{a.message or a.alert_type}")
            parts.append(f"⚠️ 健康预警: {'; '.join(alert_strs)}")
    except Exception:
        pass

    # ── 10. 打卡进度 ────────────────────────────────────
    if include_general:
        try:
            from app.models.checkin import CheckinRecord, CheckinTemplate
            checkins_today = db.query(CheckinRecord, CheckinTemplate).join(
                CheckinTemplate, CheckinRecord.template_id == CheckinTemplate.id
            ).filter(
                CheckinRecord.user_id == user_id,
                CheckinRecord.checkin_date == today
            ).all()

            total_templates = db.query(CheckinTemplate).filter(
                CheckinTemplate.user_id == user_id,
                CheckinTemplate.is_active.is_(True)
            ).count()

            if total_templates > 0:
                completed = len(checkins_today)
                names = [t.name for _, t in checkins_today]
                if completed > 0:
                    parts.append(f"今日打卡: {completed}/{total_templates} ({', '.join(names[:3])})")
                else:
                    parts.append(f"今日打卡: 0/{total_templates}，尚未开始")
        except Exception:
            pass

    # ── 11. 补剂清单 + 今日服用 ───────────────────────────
    if include_supplements:
        try:
            from app.models.supplement import SupplementDefinition, SupplementRecord
            active_supps = db.query(SupplementDefinition).filter(
                SupplementDefinition.user_id == user_id,
                SupplementDefinition.is_active.is_(True)
            ).order_by(SupplementDefinition.sort_order).all()

            if active_supps:
                taken_ids = {r.supplement_id for r in db.query(SupplementRecord).filter(
                    SupplementRecord.user_id == user_id,
                    SupplementRecord.record_date == today,
                    SupplementRecord.taken.is_(True)
                ).all()}
                taken = len(taken_ids)
                total = len(active_supps)

                # 补剂详情列表
                supp_details = []
                for s in active_supps:
                    detail = s.name
                    if s.dosage:
                        detail += f" {s.dosage}"
                    timing_map = {"morning": "早", "noon": "午", "evening": "晚", "bedtime": "睡前"}
                    if s.timing:
                        detail += f"({timing_map.get(s.timing, s.timing)})"
                    status = "✅" if s.id in taken_ids else "⬜"
                    supp_details.append(f"{status}{detail}")
                parts.append(f"补剂({taken}/{total}): {', '.join(supp_details)}")
        except Exception:
            pass

    # ── 11b. 当前用药 ──────────────────────────────────────
    try:
        from app.models.medication import Medication, MedicationLog
        active_meds = db.query(Medication).filter(
            Medication.user_id == user_id,
            Medication.is_active.is_(True)
        ).all()

        if active_meds:
            # 今日服药记录
            today_logs = db.query(MedicationLog).filter(
                MedicationLog.user_id == user_id,
                MedicationLog.taken_date == today,
                MedicationLog.status == "taken"
            ).all()
            taken_med_ids = {log.medication_id for log in today_logs}

            med_details = []
            for m in active_meds:
                detail = m.name
                if m.dosage:
                    detail += f" {m.dosage}"
                if m.frequency:
                    detail += f" {m.frequency}"
                if m.purpose:
                    detail += f"(用途:{m.purpose})"
                status = "✅" if m.id in taken_med_ids else "⬜"
                med_details.append(f"{status}{detail}")
            parts.append(f"当前用药: {', '.join(med_details)}")
    except Exception:
        pass

    # ── 12. 健康目标 ────────────────────────────────────
    if include_general:
        try:
            from app.models.smart_plan import WeeklyPlan
            current_plan = db.query(WeeklyPlan).filter(
                WeeklyPlan.user_id == user_id,
                WeeklyPlan.week_start <= today,
                WeeklyPlan.week_end >= today,
            ).first()
            if current_plan and current_plan.completion_pct is not None:
                parts.append(f"本周计划完成度: {current_plan.completion_pct:.0f}%")
        except Exception:
            pass

    # ── 13. 基因特征（区分风险/优势/用药安全）────────────────
    gene_section = _gene_context_section(db, user_id) if include_genes else ""
    if gene_section:
        parts.append(gene_section)

    return "\n".join(parts)


def _truncate_clinician_text(value: str, max_chars: int) -> str:
    """Normalize a prompt field to one line and enforce a character bound."""
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1] + "…"


def _truncate_clinician_block(value: str, max_chars: int) -> str:
    """Enforce a section bound while preserving entry line boundaries."""
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


def _format_clinician_feedback_entry(entry) -> str:
    """Render one user-reported clinician entry without elevating attribution."""
    fields = []
    for attribute, label in (
        ("subjective", "摘要"),
        ("assessment", "评估"),
        ("plan", "计划"),
    ):
        raw_value = getattr(entry, attribute, None)
        if raw_value is None:
            continue
        value = _truncate_clinician_text(
            str(raw_value),
            _CLINICIAN_FEEDBACK_FIELD_MAX_CHARS,
        )
        if value:
            fields.append(f"{label}: {value}")
    if not fields:
        return ""

    generated_at = getattr(entry, "generated_at", None)
    date_label = generated_at.date().isoformat() if generated_at else "日期未知"
    rendered = (
        f"- 用户转述的医生意见 ({date_label}): "
        + " | ".join(fields)
    )
    return _truncate_clinician_text(
        rendered,
        _CLINICIAN_FEEDBACK_ENTRY_MAX_CHARS,
    )


def _clinician_feedback_context_section(db: Session, user_id: int) -> str:
    """Load bounded clinician-attributed context for FULL injection only."""
    try:
        from app.models.clinical_journal import ClinicalJournalEntry

        entries = (
            db.query(ClinicalJournalEntry)
            .filter(
                ClinicalJournalEntry.user_id == user_id,
                ClinicalJournalEntry.created_by == "doctor",
            )
            .order_by(
                ClinicalJournalEntry.generated_at.desc(),
                ClinicalJournalEntry.id.desc(),
            )
            .limit(_CLINICIAN_FEEDBACK_RECENT_LIMIT)
            .all()
        )
        rendered_entries = [
            rendered
            for entry in entries
            if (rendered := _format_clinician_feedback_entry(entry))
        ]
        if not rendered_entries:
            return ""
        section = "[近期临床背景（仅为用户转述）]\n" + "\n".join(rendered_entries)
        return _truncate_clinician_block(
            section,
            _CLINICIAN_FEEDBACK_SECTION_MAX_CHARS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "operation=load_clinician_feedback error_type=%s",
            type(exc).__name__,
        )
        return ""


def _gene_context_section(db: Session, user_id: int) -> str:
    """基因静态标签段 (用药安全/风险/待确认/优势)。

    这是静态风险描述, 与今日读数无关, 且用药安全基因是安全相关字段 —— 因此
    MINIMAL 与 FULL 两档都注入。任何异常 fail-soft 返回空串, 绝不打死主链路。
    返回 "" 表示无可展示基因。
    """
    try:
        from app.models.genetic_data import GeneticVariant
        from app.services.genetic_report import _resolve_active_profile
        from app.services.genetic_risk import clinical_status, effective_risk_level

        active_profile = _resolve_active_profile(db, user_id)
        genetic_variants = []
        if active_profile is not None:
            genetic_variants = db.query(GeneticVariant).filter(
                GeneticVariant.user_id == user_id,
                GeneticVariant.profile_id == active_profile.id,
            ).order_by(
                # 用药安全基因最优先，然后风险基因，最后优势/中性
                case(
                    (GeneticVariant.category == "drug_sensitivity", 0),
                    (GeneticVariant.variant_nature == "risk", 1),
                    (GeneticVariant.variant_nature == "neutral", 2),
                    (GeneticVariant.variant_nature == "protective", 3),
                    else_=4,
                ),
                GeneticVariant.id.asc(),
            ).limit(12).all()

        seen_gene_keys = set()
        unique_variants = []
        for v in genetic_variants:
            key = (
                (getattr(v, "rsid", None) or "").lower()
                or f"{v.gene_name}:{getattr(v, 'variant_name', None)}:{getattr(v, 'category', None)}"
            )
            if key in seen_gene_keys:
                continue
            seen_gene_keys.add(key)
            unique_variants.append(v)

        if unique_variants:
            drug_genes = []
            risk_genes = []
            protective_genes = []
            confirmation_genes = []
            for v in unique_variants:
                nature = getattr(v, "variant_nature", "neutral") or "neutral"
                effective_risk = effective_risk_level(
                    getattr(v, "risk_level", None),
                    getattr(v, "category", None),
                    getattr(v, "evidence_level", None),
                    getattr(v, "health_implications", None),
                )
                status = clinical_status(
                    getattr(v, "category", None),
                    getattr(v, "evidence_level", None),
                    getattr(v, "health_implications", None),
                )
                label = f"{v.gene_name} {v.genotype}({v.result_label})"
                if v.category == "drug_sensitivity":
                    drug_genes.append(label)
                elif status == "requires_confirmation":
                    confirmation_genes.append(label)
                elif nature == "risk":
                    risk_genes.append(label)
                elif nature == "protective":
                    protective_genes.append(f"{v.gene_name} {v.genotype}[优势]({v.result_label})")
                elif effective_risk in {"high", "medium"}:
                    risk_genes.append(label)  # neutral 归入普通展示

            gene_parts = []
            if drug_genes:
                gene_parts.append(f"⚠️用药安全: {' | '.join(drug_genes)}")
            if risk_genes:
                gene_parts.append(f"风险基因: {' | '.join(risk_genes)}")
            if confirmation_genes:
                gene_parts.append(f"待确认筛查: {' | '.join(confirmation_genes)}")
            if protective_genes:
                gene_parts.append(f"优势基因: {' | '.join(protective_genes)}")
            if gene_parts:
                return "基因特征:\n" + "\n".join(gene_parts)
    except Exception:
        pass
    return ""
