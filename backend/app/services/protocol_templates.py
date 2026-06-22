"""行为协议模板注册表 + 按用户播种(Reva Personal Health OS P1a)。

§1.5.2 决策 #1(混合):模板是**代码常量**,按用户播种成各自的 HealthProtocol DB 行。
模板只描述「时钟可定位的行为最佳实践」(晨起/睡前等离散动作),量外包给行为本身
(如「生理盐水洗鼻一次」),完成式确认 —— **不是处方**。

R4 红线(强约束,守门测试钉):advisory_note 只能是「建议/可考虑/请确认」式对冲措辞,
绝不出具体量化剂量、不诊断、不下因果裁决;红旗禁忌 caveat 必须随文带上。

source_model=None:这类行为协议的完成事件(HealthProtocolEvent)**本身即记录**,
不向任何领域表写量(无饮水/用药/补剂等业务记录),因此 can_default_complete=False。

播种入口是显式的(`POST /protocols/seed/behavior`),**不在 onboarding 全员自动播种**:
洗鼻是病情相关行为(锚点用户有鼻炎才开),全员铺开 = 通知噪音。onboarding 自动播种
留作有记录的后续(见 docs 路线图)。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.health_protocol import HealthProtocol

logger = logging.getLogger(__name__)

# 模板版本:写进 implied_quantity 以便将来识别/迁移;改模板语义时 bump。
TEMPLATE_VERSION = 1


def _sleep_winddown_note() -> str:
    """睡前放松 advisory_note。

    复用 schedule_diet_sleep 的 winddown / caffeine-cutoff 卫生逻辑(收屏 / 调暗 / 停咖啡因),
    不复制其处方算法(咖啡因截止小时数由分时排程动态算;这里只给作息卫生的定性建议)。
    """
    return (
        "建议睡前 30–60 分钟开始放松:调暗屏幕、停止咖啡因、做点轻松的事,准备就寝。"
        "具体睡眠时间以你自己的作息为准(作息卫生提示,非医疗处方)。"
    )


# 行为协议模板(代码常量)。每条 → 一行 HealthProtocol(按用户播种)。
# cadence 固定 daily(模型无 intra-day interval;洗鼻每天两次 = 两条独立模板)。
BEHAVIOR_PROTOCOL_TEMPLATES: List[Dict[str, Any]] = [
    {
        "key": "nasal_wash_morning",
        "domain": "respiratory",
        "name": "晨起洗鼻",
        "cadence": "daily",
        "time_window": "morning",
        "completion_mode": "one_tap",
        "can_default_complete": False,
        "source_model": None,
        "reminder_tier": "P1",
        "implied_quantity": {
            "template_key": "nasal_wash_morning",
            "template_version": TEMPLATE_VERSION,
            "saline": True,
        },
        "advisory_note": (
            "建议晨起用生理盐水洗鼻一次,帮助清理鼻腔。"
            "若有鼻出血、明显鼻痛、发热或近期鼻部手术/外伤,请勿自行洗鼻并咨询医生。"
        ),
        "red_flags": ["nosebleed", "nasal_pain", "fever", "post_op"],
    },
    {
        "key": "nasal_wash_evening",
        "domain": "respiratory",
        "name": "睡前洗鼻",
        "cadence": "daily",
        "time_window": "bedtime",
        "completion_mode": "one_tap",
        "can_default_complete": False,
        "source_model": None,
        "reminder_tier": "P1",
        "implied_quantity": {
            "template_key": "nasal_wash_evening",
            "template_version": TEMPLATE_VERSION,
            "saline": True,
        },
        "advisory_note": (
            "建议睡前用生理盐水洗鼻一次,帮助清理鼻腔、改善夜间通气。"
            "若有鼻出血、明显鼻痛、发热或近期鼻部手术/外伤,请勿自行洗鼻并咨询医生。"
        ),
        "red_flags": ["nosebleed", "nasal_pain", "fever", "post_op"],
    },
    {
        "key": "sleep_winddown",
        "domain": "sleep",
        "name": "睡前放松",
        "cadence": "daily",
        "time_window": "bedtime",
        "completion_mode": "one_tap",
        "can_default_complete": False,
        "source_model": None,
        "reminder_tier": "P1",
        "implied_quantity": {
            "template_key": "sleep_winddown",
            "template_version": TEMPLATE_VERSION,
        },
        "advisory_note": _sleep_winddown_note(),
        "red_flags": [],
    },
]

# key → 模板,供播种 / 校验快速查表。
TEMPLATES_BY_KEY: Dict[str, Dict[str, Any]] = {
    t["key"]: t for t in BEHAVIOR_PROTOCOL_TEMPLATES
}

# 洗鼻禁忌红旗 → 当前活跃症状/病情文本里的中英文关键词(用于提醒/投影时抑制)。
# 偏严(命中即抑制),漏判由 advisory_note 自带的 caveat 兜底(home 卡始终带禁忌提示)。
NASAL_RED_FLAG_KEYWORDS: Dict[str, List[str]] = {
    "nosebleed": ["鼻出血", "鼻血", "流鼻血", "nosebleed", "epistaxis"],
    "nasal_pain": ["鼻痛", "鼻子疼", "鼻腔疼", "nasal pain"],
    "fever": ["发热", "发烧", "fever", "体温高"],
    "post_op": ["鼻部手术", "鼻窦手术", "鼻腔手术", "术后", "鼻外伤", "post-op", "post op"],
}


def _template_for_protocol(p: HealthProtocol) -> Optional[Dict[str, Any]]:
    """从一行已播种的 HealthProtocol 反查其模板(按 implied_quantity.template_key)。"""
    iq = p.implied_quantity or {}
    key = iq.get("template_key")
    if not key:
        return None
    return TEMPLATES_BY_KEY.get(key)


def _existing_template_keys(db: Session, user_id: int) -> set[str]:
    """该用户已有(active 或 paused)的行为协议 template_key 集合。

    archived 不计入 —— 用户主动归档后重新播种应允许再建(可重新启用同一行为)。
    """
    rows = (
        db.query(HealthProtocol)
        .filter(
            HealthProtocol.user_id == user_id,
            HealthProtocol.status.in_(("active", "paused")),
        )
        .all()
    )
    keys: set[str] = set()
    for p in rows:
        iq = p.implied_quantity or {}
        k = iq.get("template_key")
        if k:
            keys.add(k)
    return keys


def seed_behavior_protocols(
    db: Session, user_id: int, keys: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """按用户幂等播种行为协议模板。

    keys=None → 播种全部模板;否则只播指定 key(未知 key → ValueError,fail loud)。
    幂等:已有(active/paused)同 template_key 的协议则跳过;两次播种 → 每模板恰一行。
    返回 {"created": [keys...], "skipped": [keys...]}。
    """
    if keys is None:
        wanted = [t["key"] for t in BEHAVIOR_PROTOCOL_TEMPLATES]
    else:
        unknown = [k for k in keys if k not in TEMPLATES_BY_KEY]
        if unknown:
            raise ValueError(f"未知行为协议模板 key: {unknown}")
        wanted = list(keys)

    existing = _existing_template_keys(db, user_id)
    created: List[str] = []
    skipped: List[str] = []

    # 延迟 import 避免与 service 形成 import 环。
    from app.services.health_protocol_service import create_protocol

    for key in wanted:
        if key in existing:
            skipped.append(key)
            continue
        tpl = TEMPLATES_BY_KEY[key]
        create_protocol(db, user_id, {
            "domain": tpl["domain"],
            "name": tpl["name"],
            "mechanism": "pre_commit",  # 预承诺式行为(非容器/设备)
            "implied_quantity": tpl["implied_quantity"],
            "cadence": tpl["cadence"],
            "time_window": tpl["time_window"],
            "completion_mode": tpl["completion_mode"],
            "can_default_complete": tpl["can_default_complete"],
            "source_model": tpl["source_model"],   # None:事件本身即记录
            "notes": tpl["advisory_note"],
        })
        created.append(key)

    logger.info(
        "[ProtocolTemplate] 播种 user=%s created=%s skipped=%s",
        user_id, created, skipped,
    )
    return {"created": created, "skipped": skipped}


def nasal_red_flag_active(db: Session, user_id: int) -> bool:
    """该用户当前是否有洗鼻禁忌红旗(鼻出血/鼻痛/发热/术后)活跃 —— **fail-CLOSED**。

    用**定向查询**读近 72h 症状 + active 病程文本(绝不调 build_twin —— build_twin 自开
    SessionLocal、跑生产库,在请求/celery 事务里看不到当前数据且可能撞缺列,见 memory)。
    任一关键词命中 → True(抑制洗鼻提醒)。

    **安全门必须 fail-CLOSED(F3)**:这是禁忌抑制门,不是普通增强。任一查询异常 →
    安全状态不可验证 → 返回 True(抑制),宁可漏推一次良性的生理盐水提醒,也绝不在
    无法确认安全的情况下主动推一个可能禁忌的 nudge。异常**记 warning,不静默吞**。
    返回 False 仅当两路查询都成功且确实无红旗。
    """
    blob_parts: List[str] = []
    try:
        from app.models.symptom_entry import SymptomEntry

        cutoff = datetime.now(UTC) - timedelta(hours=72)
        rows = (
            db.query(SymptomEntry.description)
            .filter(
                SymptomEntry.user_id == user_id,
                SymptomEntry.occurred_at >= cutoff,
            )
            .limit(30)
            .all()
        )
        blob_parts += [r[0] for r in rows if r and r[0]]
    except Exception as e:  # noqa: BLE001
        # fail-CLOSED:症状状态不可验证 → 抑制(不在不可知安全态下推禁忌 nudge)。
        logger.warning("[ProtocolTemplate] 症状查询失败 user=%s,fail-closed 抑制: %s", user_id, e)
        return True

    try:
        from app.models.illness import IllnessEpisode

        rows = (
            db.query(IllnessEpisode.name)
            .filter(
                IllnessEpisode.user_id == user_id,
                IllnessEpisode.status.in_(("active", "improving")),
            )
            .limit(10)
            .all()
        )
        blob_parts += [r[0] for r in rows if r and r[0]]
    except Exception as e:  # noqa: BLE001
        # fail-CLOSED:病程状态不可验证 → 抑制。
        logger.warning("[ProtocolTemplate] 病程查询失败 user=%s,fail-closed 抑制: %s", user_id, e)
        return True

    if not blob_parts:
        return False
    blob = " ".join(blob_parts).lower()
    for kws in NASAL_RED_FLAG_KEYWORDS.values():
        for kw in kws:
            if kw.lower() in blob:
                return True
    return False


def is_nasal_wash_template(p: HealthProtocol) -> bool:
    """该协议是否为洗鼻模板(需要红旗抑制)。"""
    tpl = _template_for_protocol(p)
    return bool(tpl and tpl["key"] in ("nasal_wash_morning", "nasal_wash_evening"))


def reminder_tier_for(implied_quantity: Optional[Dict[str, Any]]) -> Optional[str]:
    """按 implied_quantity.template_key 查模板的 reminder_tier(非模板 → None)。"""
    iq = implied_quantity or {}
    tpl = TEMPLATES_BY_KEY.get(iq.get("template_key", ""))
    return tpl["reminder_tier"] if tpl else None
