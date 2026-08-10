"""Deterministic tool capability policy for XiaoBa Agent Kernel."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.services.agent_kernel.goal_spec import (
    SIMPLE_ILLNESS_CREATE_RE,
    illness_entity_has_medical_semantics,
    illness_read_has_unowned_subject,
    illness_target_is_unowned_or_referential,
    simple_illness_target,
)
from app.services.agent_kernel.health_semantics import (
    HEALTH_ENTITY_CONNECTOR_RE,
    READ_VERB_RE,
    active_health_read_clause,
    authorization_grammar_digest,
    has_explicit_health_read_request,
    health_read_cancelled,
    health_semantics_contract_payload,
    is_unresolved_health_reference,
    resolve_medical_exam_query,
)
from app.services.agent_kernel.tool_registry import (
    ToolRegistryError,
    get_tool_spec,
    list_tool_specs,
)
from app.services.agent_kernel.types import (
    AgentEnvelope,
    CapabilityDecision,
    ToolExecutionRequest,
    TurnSnapshot,
)
from app.services.agent_kernel.write_safety import (
    is_explicit_aigc_media_provider_veto,
    is_explicit_write_cancellation,
)
from app.services.clinician_provenance_guard import classify_clinician_turn
from app.services.health_query_dimensions import normalize_health_query_args

READ_ONLY_TOOLS = frozenset(
    spec.name
    for spec in list_tool_specs()
    if spec.effect == "read" and spec.adapter_kind == "executor"
)
SPECIALIST_READ_ONLY_TOOLS = frozenset(
    spec.name for spec in list_tool_specs() if spec.adapter_kind == "specialist"
)
WRITE_TOOL_NAMES = frozenset(
    spec.name for spec in list_tool_specs() if spec.effect in {"write", "mixed"}
)
KNOWN_TOOL_NAMES = READ_ONLY_TOOLS | SPECIALIST_READ_ONLY_TOOLS | WRITE_TOOL_NAMES
MANAGE_WRITE_OPERATIONS = get_tool_spec("health_manage").write_actions
INTERVENTION_WRITE_ACTIONS = get_tool_spec("intervention_cycle").write_actions
INTERVENTION_READ_ACTIONS = get_tool_spec("intervention_cycle").read_actions
MANAGE_PLAN_ACTIONS = get_tool_spec("manage_plan").write_actions

# Procedure recipes are exact-triggered routines. Their scope is intentionally
# narrower than normal one-shot health_record calls: no long-lived reminders or
# goals, no account/profile mutation, and no external ingestion jobs.
RECIPE_REPLAY_ALLOWED_RECORD_TYPES = frozenset(
    {
        "water",
        "weight",
        "blood_pressure",
        "diet",
        "exercise",
        "waist",
        "sleep",
        "excretion",
        "mood",
        "symptom",
        "rhinitis",
    }
)
_RECIPE_RECORD_TYPE_ALIASES = {
    "bp": "blood_pressure",
    "blood-pressure": "blood_pressure",
    "bloodpressure": "blood_pressure",
}
_CAPABILITY_POLICY_CONTRACT_VERSION = "agent-capability-policy-v40"
_HEALTH_RECORD_TARGET_BINDING_VERSION = "authorized-target-set-v31"
_HEALTH_MANAGE_UPDATE_EVIDENCE_VERSION = "record-update-evidence-v23"
_SERVER_AUTHORIZED_HEALTH_RECORD_FIELDS_KEY = "_server_authorized_health_record_fields"
_HEALTH_RECORD_DOMAIN_TYPES = {
    "diet": "diet",
    "water": "water",
    "medication": "medication",
    "supplement": "supplement",
    "symptom": "symptom",
    "reminder": "reminder",
    "mood": "mood",
    "exercise": "exercise",
    "sleep": "sleep",
}


@dataclass(frozen=True)
class _ServerAuthorizedHealthRecordFields:
    """Opaque executor-to-policy authority that model JSON cannot construct."""

    values: tuple[tuple[str, Any], ...]


def bind_server_authorized_health_record_fields(
    args: dict[str, Any],
    **values: Any,
) -> dict[str, Any]:
    """Replace any untrusted marker and bind executor-derived record fields."""
    args.pop(_SERVER_AUTHORIZED_HEALTH_RECORD_FIELDS_KEY, None)
    authorized = tuple(
        (key, value) for key, value in values.items() if value not in (None, "", [])
    )
    if authorized:
        args[_SERVER_AUTHORIZED_HEALTH_RECORD_FIELDS_KEY] = (
            _ServerAuthorizedHealthRecordFields(authorized)
        )
    return args


def _server_authorized_health_record_fields(args: dict[str, Any]) -> dict[str, Any]:
    marker = args.get(_SERVER_AUTHORIZED_HEALTH_RECORD_FIELDS_KEY)
    if not isinstance(marker, _ServerAuthorizedHealthRecordFields):
        return {}
    return dict(marker.values)


_NUMERIC_DISPATCH_ALIAS_GROUPS = {
    "water": (("amount", ("amount", "amount_ml", "ml")),),
    "weight": (("weight", ("weight", "value", "weight_kg", "体重")),),
    "blood_pressure": (
        ("systolic", ("systolic",)),
        ("diastolic", ("diastolic",)),
    ),
    "waist": (("waist_cm", ("waist_cm", "waist", "value", "腰围")),),
}
_METRIC_RECORD_TYPE_TERMS = (
    ("blood_pressure", ("血压", "高压", "低压", "收缩压", "舒张压")),
    ("weight", ("体重", "称重", "kg", "公斤", "千克", "斤")),
    ("waist", ("腰围",)),
    ("sleep", ("睡眠", "睡觉", "入睡", "起床")),
    ("exercise", ("运动", "训练", "跑步", "步数", "走了")),
)
_EXPLICIT_RECORD_TYPE_TERMS = (
    ("water", ("喝水", "饮水", "补水", "ml水", "毫升水")),
    (
        "diet",
        (
            "早餐",
            "早饭",
            "午餐",
            "午饭",
            "中饭",
            "晚餐",
            "晚饭",
            "加餐",
            "零食",
            "夜宵",
        ),
    ),
    ("medication", ("吃药", "服药", "用药", "药物", "药片", "胶囊")),
    ("supplement", ("补剂", "维生素", "益生菌", "鱼油")),
    ("symptom", ("头痛", "头疼", "眼痒", "嗓子疼", "不适", "症状")),
    ("mood", ("心情", "情绪", "心境")),
    ("excretion", ("排便", "大便", "便秘", "腹泻")),
    ("reminder", ("提醒", "闹钟")),
    ("goal", ("目标",)),
)
_ILLNESS_TARGET_TERMS = (
    "口腔溃疡",
    "舌尖溃疡",
    "嘴唇起泡",
    "麦粒肿",
    "甲沟炎",
    "带状疱疹",
    "感冒",
    "流感",
    "湿疹",
    "烫伤",
    "水泡",
    "伤口",
    "痘痘发作",
)
_ILLNESS_ASSERTION_BOUNDARY_RE = re.compile(
    r"(?:但是|不过|然而|反而|可是|但|却|就|"
    r"可(?=前天|昨天|昨日|今日|今天|现在|目前))"
)
_QUERY_DIMENSION_TEXT_TERMS: dict[str, tuple[str, ...]] = {
    "sleep": ("睡眠", "入睡", "起床", "睡觉"),
    "diet": (
        "饮食",
        "餐",
        "吃",
        "热量",
        "营养",
        "蛋白质",
        "碳水",
        "脂肪",
        "膳食纤维",
        "早餐",
        "早饭",
        "午餐",
        "午饭",
        "晚餐",
        "晚饭",
        "加餐",
        "零食",
        "夜宵",
    ),
    "water": ("饮水", "喝水", "补水"),
    "weight": ("体重", "称重"),
    "blood_pressure": ("血压", "收缩压", "舒张压"),
    "workout": (
        "运动",
        "跑步",
        "跑步训练",
        "骑行",
        "游泳",
        "训练",
        "训练负荷",
        "跑量",
        "健身",
    ),
    "manual_exercise": ("俯卧撑", "瑜伽", "拉伸", "深蹲", "仰卧起坐"),
    "activity": ("步数", "活动", "日常活动", "活动分钟"),
    "heart_rate": ("心率", "静息心率", "平均心率"),
    "hrv": ("hrv", "心率变异性"),
    "spo2": ("血氧", "夜间血氧", "spo2"),
    "spo2_sleep_correlation": ("睡眠血氧关联", "睡眠阶段血氧", "血氧睡眠关联"),
    "body_battery": ("身体电量", "电量"),
    "stress": ("压力", "压力水平", "心理压力"),
    "supplements": ("补剂", "补剂服用"),
    "medication": ("用药", "服药", "药物"),
    "events": ("行程", "事件", "时间线"),
    "medical_exam": (
        "化验",
        "检查",
        "体检",
        "影像",
        "MRI",
        "MRI检查",
        "MRI检查报告",
        "核磁",
        "磁共振",
        "CT",
        "CT报告",
        "X光",
        "B超",
        "胃镜",
        "检查报告",
    ),
    "genetic": ("基因", "基因位点"),
    "genetic_cognitive": ("认知基因", "认知能力基因"),
    "genetic_personality": ("人格基因", "性格基因"),
    "genetic_comprehensive": ("综合基因", "基因综合解读"),
    "comprehensive": ("健康", "健康数据", "健康指标", "综合健康"),
}
_QUERY_DIMENSION_SEMANTIC_ALIASES = {"exercise": "workout"}
_QUERY_DIMENSION_ENTITY_PREFIX_PATTERN = r"(?:夜间|每日|日均|平均|静息|全天)?"
_QUERY_DIMENSION_ENTITY_SUFFIX_PATTERN = (
    r"(?:(?:的)?(?:数据|指标|数值|读数|情况|状况|状态|评分|分数|质量|时长|时间|趋势|"
    r"变化|明细|详情|汇总|统计|清单|列表|次数|频率|总量|平均值|最高值|"
    r"最低值|波动|距离|摄入|报告|倍数|比率|比例))?"
)
_READ_QUERY_VERB_PATTERN = READ_VERB_RE.pattern
_READ_QUERY_VERB_RE = READ_VERB_RE
_HISTORY_QUERY_WINDOW_PATTERN = (
    r"(?:(?:最近|近|过去)(?:\d+|[一二两三四五六七八九十]+|半)"
    r"(?:个)?(?:天|周|月|年)(?:内|以来)?|"
    r"(?:这|本)(?:一)?周|这个月|这月|本月|今年|本年|今天|今日|"
    r"昨天|昨日|前天|昨晚|昨夜|上周|上一周|上个月|去年|"
    r"最近(?!(?:的)?(?:那)?(?:一)?(?:次|回))|近来)"
)
_HISTORY_QUERY_WINDOW_RE = re.compile(_HISTORY_QUERY_WINDOW_PATTERN)
_UNSUPPORTED_CALENDAR_QUERY_WINDOW_RE = re.compile(
    r"(?:"
    r"昨天|昨日|前天|昨晚|昨夜|"
    r"(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]|"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"(?<!\d)\d{1,2}[-/]\d{1,2}(?!\d)|"
    r"(?:这个|本个|上个|下个|前个|后个)(?:星期|礼拜)|"
    r"(?:这|本|上|下|前|后)(?:个|一)?(?:周|星期|礼拜)|"
    r"周(?:[一二三四五六日天]|末)|(?:星期|礼拜)[一二三四五六日天]|"
    r"(?:这|本|上|下|前|后)(?:一个|个|一)?月|"
    r"(?:今年|本年|去年|前年|明年)|"
    r"(?:本|这|上|下)(?:个)?季度|(?:上|下)半年|"
    r"(?:(?:今年|去年|本年)?第?[一二三四1-4]季度)|"
    r"(?:元旦|春节|清明节|端午节|中秋节|国庆节|劳动节|儿童节|圣诞节)"
    r"(?:那天|当天)?"
    r")"
)
_HISTORY_QUERY_QUESTION_RE = re.compile(
    r"(?:上一次|是什么时候|在什么时候|何时|在何时|是何时|是哪天|是几号|"
    r"哪天|哪一天|几号|时间|日期|"
    r"分别有哪些|有哪些|有那些|"
    r"有什么|有几条|有几次|有多少条|多少条|是多少|平均多少|多少(?:呢)?|"
    r"(?:是)?升还是降|上升还是下降|有多高|怎么样|怎样|如何|呢|最近一次)"
)
_HISTORY_QUERY_MULTI_ENTITY_RE = HEALTH_ENTITY_CONNECTOR_RE
_HISTORY_QUERY_LEADING_VERB_RE = re.compile(rf"^(?:{_READ_QUERY_VERB_PATTERN}|把)")
_HISTORY_QUERY_TRAILING_VERB_RE = re.compile(
    r"(?:[，,、]?(?:(?:给我)?(?:找出来|查出来|列出来|调出来|找出|查看|看看)|"
    r"(?:打开|调出|调阅|展示)(?:一下)?|拉出来|发我|发给我|"
    r"(?:对比|比较)(?:一下|倍数|比例|比率)?))$"
)
_ILLNESS_MEDICAL_ACRONYMS = frozenset({"sle"})
_LATEST_OCCURRENCE_MARKER_PATTERN = (
    r"(?:(?:我)?(?:(?:上(?:一)?|最近|最后)(?:的)?(?:那)?(?:一)?(?:次|回)|"
    r"末次|最近(?=(?:的)?(?:记录|发作|发生|复发))|最近))"
)
_LATEST_OCCURRENCE_EVENT_PATTERN = r"(?:记录|发作|发生|复发|出现|加重|犯过)?"
_LATEST_OCCURRENCE_QUESTION_PATTERN = (
    r"(?:(?:是)?(?:在|于)?(?:什么时候|什么时间|何时|哪天|哪一天|几号|时间|日期)|呢)"
)
_ILLNESS_PARTIAL_RECOVERY_RE = re.compile(
    r"(?:好了点|好了一些|好了一半|好了一丢丢|好了一小点|快好了|基本好了|"
    r"一点点好了|稍微好了|有点好了|算是好了|差点好了)"
)
_ILLNESS_CLEAR_IMPROVEMENT_RE = re.compile(
    r"(?:(?:已经|确实|真的)?(?:明显|有所|逐步|慢慢)?"
    r"(?:好转|改善|缓解)(?:了)?|未用药(?:便|就)好转)"
)
_ILLNESS_CLEAR_RESOLUTION_RE = re.compile(
    r"(?:(?:已经)?(?:完全|彻底)?好了|(?:已经)?(?:完全|彻底)?(?:康复|痊愈))"
)
_ILLNESS_CLEAR_ACTIVE_RE = re.compile(r"(?:还在发作中|发作中|还没好|仍未好)")
_ILLNESS_STATE_TIME_PREFIX_RE = re.compile(
    r"^(?:在|于)?(?:之前|此前|先前|前天|昨天|昨日|今日|今天|刚刚|刚才|现在|目前)"
)
_ILLNESS_UPDATE_INSTRUCTION_SUFFIX_RE = re.compile(
    r"[，,。.!！；;]?(?:(?:请|请你|帮我|麻烦|麻烦你))?"
    r"(?:修改|更新|更正)(?:一下)?(?:这条)?记录[。.!！]?$"
)
_ILLNESS_RECORD_ID_PATTERNS = (
    re.compile(
        r"(?<![A-Za-z0-9])(?:(?:id|编号)(?:号)?|#)(?:是|为|=|#|：|:)?"
        r"(?P<record_id>\d+)(?!\d)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:疾病)?(?:记录|条目)(?:(?:编号|id)(?:号)?|号)?(?:是|为|=)?[#：:]?"
        r"(?P<record_id>\d+)(?!\d)",
        re.IGNORECASE,
    ),
    re.compile(
        r"第(?P<record_id>\d+)(?:个|号|条)(?:疾病)?(?:记录|条目)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:疾病)?(?:记录|条目)第(?P<record_id>\d+)(?:号|条)?",
        re.IGNORECASE,
    ),
)
_MEAL_TYPE_ALIASES = {
    "breakfast": "breakfast",
    "早餐": "breakfast",
    "早饭": "breakfast",
    "lunch": "lunch",
    "午餐": "lunch",
    "午饭": "lunch",
    "中饭": "lunch",
    "dinner": "dinner",
    "晚餐": "dinner",
    "晚饭": "dinner",
    "snack": "snack",
    "加餐": "snack",
    "零食": "snack",
    "夜宵": "snack",
}
_WEIGHT_TARGET_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)(?P<unit>kg|公斤|千克|斤)", re.IGNORECASE
)
_BLOOD_PRESSURE_TARGET_RE = re.compile(
    r"(?P<systolic>\d{2,3})[/／](?P<diastolic>\d{2,3})"
)
_WAIST_TARGET_RE = re.compile(
    r"腰围(?P<value>\d+(?:\.\d+)?)(?:cm|厘米)?", re.IGNORECASE
)
_WATER_TARGET_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ml|毫升|l|升)(?:的)?(?:水)?",
    re.IGNORECASE,
)
_WRITE_TARGET_ACTION_RE = re.compile(
    r"(?:记录|记一下|记下|打个卡|打卡|新增|录入|保存|写入|存下来)"
)
_NON_ILLNESS_QUERY_ENTITY_TERMS = frozenset(
    {
        "腰围",
        "蛋白质",
        "碳水",
        "碳水化合物",
        "脂肪",
        "膳食纤维",
        "训练负荷",
    }
)
_SUPPLEMENT_TARGET_TERMS = (
    "鱼油",
    "维生素d",
    "维d",
    "维生素c",
    "维c",
    "复合维生素",
    "益生菌",
    "镁",
    "钙",
    "辅酶q10",
    "红参液",
)
_MEDICATION_TARGET_TERMS = ("二甲双胍",)
_MEDICATION_DOSE_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?|[一二两三四五六七八九十])\s*"
    r"(?P<unit>片|粒|丸|袋|支|mg|g|mcg|ug|μg|毫克|克|ml|毫升)",
    re.IGNORECASE,
)
_MEDICATION_STRENGTH_RE = re.compile(
    r"(?:每(?:片|粒|丸|袋|支)|规格(?:是|为)?)\s*"
    r"(?P<value>\d+(?:\.\d+)?|[一二两三四五六七八九十])\s*"
    r"(?P<unit>mg|g|mcg|ug|μg|毫克|克|ml|毫升)",
    re.IGNORECASE,
)
_SUPPLEMENT_DOSE_RE = re.compile(
    r"(?:(?:剂量|用量|每次|服用|吃)(?:是|为)?)?"
    r"(?P<value>\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)\s*"
    r"(?P<unit>片|粒|丸|袋|支|颗|滴|喷|ml|毫升|mg|毫克|g|克)",
    re.IGNORECASE,
)
_SUPPLEMENT_TIMING_RE = re.compile(
    r"(?:早上|早晨|上午|中午|午间|晚上|晚间|睡前)(?:吃|服用)?"
)
_MEDICATION_NAME_SUFFIX_RE = re.compile(
    r"(?:霉素|必利|瑞酮|二甲双胍|沙坦|普利|洛尔|他汀|唑仑|西泮)$"
)
_CHINESE_DOSE_NUMBERS = {
    "一": "1",
    "二": "2",
    "两": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
}
_EXERCISE_TARGET_TERMS = (
    "跑步",
    "散步",
    "走路",
    "游泳",
    "骑车",
    "骑行",
    "力量训练",
    "瑜伽",
    "俯卧撑",
    "深蹲",
    "引体向上",
    "仰卧起坐",
)
_EXERCISE_DURATION_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>分钟|小时|min|h)",
    re.IGNORECASE,
)
_EXERCISE_DISTANCE_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>公里|千米|km|米|m)(?!l|in)",
    re.IGNORECASE,
)
_EXERCISE_REPS_RE = re.compile(r"(?P<value>\d+)\s*(?:个|次)(?!数)")
_EXERCISE_SETS_RE = re.compile(r"(?:做)?(?P<value>\d+)\s*组")
_REMEMBER_FACT_RE = re.compile(
    r"(?:记一下|记住|记录|保存)(?:我|我的)?"
    r"(?P<predicate>鞋码|衣服尺码|衣码|昵称|职业|血型|生日|忌口|喜好)"
    r"(?:是|为)?(?P<value>[^，,。！；;：:\s]{1,80})"
)
_EVENT_TARGET_RE = re.compile(
    r"(?:记录|新增|保存)(?:一下)?(?:生活)?事件(?:是|为)?[：:]?"
    r"(?P<title>[^，,。.!！；;]{1,80})"
)
_EVENT_ARRIVAL_FACT_RE = re.compile(
    r"^(?P<subject>.*?)到(?P<place>[\u4e00-\u9fff][^，,。.!！；;：:?？]{0,19})"
    r"(?:了|$)"
)
_MOOD_SCORE_RE = re.compile(r"(?:心情|情绪|心境).{0,6}?(?P<value>[1-5])\s*分")
_MOOD_TARGET_TERMS = (
    "calm",
    "平静",
    "开心",
    "愉快",
    "低落",
    "焦虑",
    "烦躁",
    "生气",
)
_MOOD_TARGET_ALIASES = {
    "calm": "calm",
    "平静": "calm",
    "开心": "happy",
    "愉快": "happy",
    "低落": "low",
    "焦虑": "anxious",
    "烦躁": "irritable",
    "生气": "angry",
}
_EXCRETION_TARGET_ALIASES = {
    "bowel": "bowel",
    "排便": "bowel",
    "大便": "bowel",
    "constipation": "constipation",
    "便秘": "constipation",
    "diarrhea": "diarrhea",
    "腹泻": "diarrhea",
}
_CLOCK_RE = re.compile(
    r"(?<!\d)(?P<hour>[01]?\d|2[0-3])[:：点]"
    r"(?P<minute>[0-5]\d|半|一刻|三刻)?(?:钟)?"
)
_CHINESE_CLOCK_RE = re.compile(
    r"(?P<hour>[零〇一二两三四五六七八九十]{1,3})点"
    r"(?P<minute>半|一刻|三刻|[零〇一二两三四五六七八九十]{1,3}分)?(?:钟)?"
)
_REMINDER_INTERVAL_RE = re.compile(
    r"(?:每隔|每|间隔)\s*(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>分钟|小时|分|h)(?:一次)?",
    re.IGNORECASE,
)
_SLEEP_QUALITY_RE = re.compile(r"(?:睡眠)?质量.{0,3}(?P<value>[1-5])\s*分?")
_SEVERITY_TARGET_RE = re.compile(
    r"(?:严重程度|严重度|程度|强度)?\s*(?P<value>10|[1-9])\s*"
    r"(?:分(?!钟)|级|/\s*10)"
)
_WHOLE_RECORD_DELETE_EVIDENCE_VERSION = "record-delete-evidence-v2"
_HEALTH_MANAGE_CANONICAL_RECORD_TYPES = frozenset(
    {
        "diet",
        "water",
        "weight",
        "waist",
        "blood_pressure",
        "sleep",
        "mood",
        "excretion",
        "exercise",
        "illness",
        "symptom",
        "medication",
        "medication_log",
        "supplement",
        "supplement_definition",
        "reminder",
        "goal",
        "medical_exam",
        "event",
        "rhinitis",
    }
)
_DELETE_RECORD_TYPE_TEXT_ALIASES = {
    "diet": "diet",
    "food": "diet",
    "foods": "diet",
    "meal": "diet",
    "meals": "diet",
    "nutrition": "diet",
    "饮食": "diet",
    "膳食": "diet",
    "餐食": "diet",
    "早餐": "diet",
    "午餐": "diet",
    "晚餐": "diet",
    "water": "water",
    "hydration": "water",
    "饮水": "water",
    "喝水": "water",
    "weight": "weight",
    "体重": "weight",
    "waist": "waist",
    "腰围": "waist",
    "blood_pressure": "blood_pressure",
    "blood-pressure": "blood_pressure",
    "bloodpressure": "blood_pressure",
    "bp": "blood_pressure",
    "血压": "blood_pressure",
    "sleep": "sleep",
    "睡眠": "sleep",
    "mood": "mood",
    "心情": "mood",
    "情绪": "mood",
    "excretion": "excretion",
    "bowel": "excretion",
    "排便": "excretion",
    "大便": "excretion",
    "exercise": "exercise",
    "workout": "exercise",
    "运动": "exercise",
    "锻炼": "exercise",
    "illness": "illness",
    "生病": "illness",
    "symptom": "symptom",
    "symptoms": "symptom",
    "症状": "symptom",
    "medication_log": "medication_log",
    "medication-log": "medication_log",
    "用药日志": "medication_log",
    "服药日志": "medication_log",
    "medication": "medication",
    "medications": "medication",
    "medicine": "medication",
    "meds": "medication",
    "用药": "medication",
    "药物": "medication",
    "supplement_definition": "supplement_definition",
    "supplement-definition": "supplement_definition",
    "补剂定义": "supplement_definition",
    "supplement": "supplement",
    "supplements": "supplement",
    "补剂": "supplement",
    "reminder": "reminder",
    "提醒": "reminder",
    "goal": "goal",
    "目标": "goal",
    "medical_exam": "medical_exam",
    "medical-exam": "medical_exam",
    "labs": "medical_exam",
    "lab": "medical_exam",
    "体检": "medical_exam",
    "化验": "medical_exam",
    "event": "event",
    "events": "event",
    "事件": "event",
    "rhinitis": "rhinitis",
    "鼻炎": "rhinitis",
}
_WHOLE_RECORD_DELETE_VERBS = (
    "删除",
    "删掉",
    "删去",
    "删了",
    "移除",
    "清除",
    "清掉",
    "去掉",
)
_DELETE_UNDO_MARKERS = ("撤销", "取消", "恢复", "还原", "回退")
_DELETE_MIXED_UPDATE_MARKERS = (
    "修改",
    "更改",
    "更新",
    "改成",
    "改为",
    "调整",
    "修正",
)
_DELETE_RECORD_TYPE_TEXT_ALIAS_PATTERN = "|".join(
    re.escape(alias)
    for alias in sorted(
        _DELETE_RECORD_TYPE_TEXT_ALIASES,
        key=len,
        reverse=True,
    )
)
_EXACT_RECORD_TARGET_PATTERN = (
    rf"(?:{_DELETE_RECORD_TYPE_TEXT_ALIAS_PATTERN})"
    rf"(?:记录|条目)#?\d+"
)
_DELETE_REQUEST_PREFIXES = (
    "请你帮我",
    "麻烦你帮我",
    "麻烦帮我",
    "可以帮我",
    "能否帮我",
    "能不能帮我",
    "请帮我",
    "请你",
    "请您",
    "麻烦你",
    "请帮忙",
    "麻烦帮忙",
    "请替我",
    "帮我",
    "帮忙",
    "麻烦",
    "能否",
    "能不能",
    "可以",
    "替我",
    "我要",
    "给我",
    "确认",
    "请",
)
_DELETE_REQUEST_PREFIX_PATTERN = "|".join(
    re.escape(prefix)
    for prefix in sorted(_DELETE_REQUEST_PREFIXES, key=len, reverse=True)
)
_WHOLE_RECORD_DELETE_VERB_PATTERN = "|".join(
    re.escape(verb)
    for verb in sorted(_WHOLE_RECORD_DELETE_VERBS, key=len, reverse=True)
)
_DELETE_REQUEST_SUFFIX_PATTERN = (
    r"(?:一下)?(?:吧)?"
    r"(?:[,，]?(?:谢谢(?:你)?|可以吗|好吗|行吗))?"
    r"[。.!！?？]*(?:🩺)?"
)
_WHOLE_RECORD_DELETE_VERB_FIRST_RE = re.compile(
    rf"^(?:(?:{_DELETE_REQUEST_PREFIX_PATTERN}))?"
    rf"(?:{_WHOLE_RECORD_DELETE_VERB_PATTERN})"
    rf"(?P<target>{_EXACT_RECORD_TARGET_PATTERN})"
    rf"{_DELETE_REQUEST_SUFFIX_PATTERN}$",
    re.IGNORECASE,
)
_WHOLE_RECORD_DELETE_TARGET_FIRST_RE = re.compile(
    rf"^(?:(?:{_DELETE_REQUEST_PREFIX_PATTERN}))?"
    rf"(?:把|将)(?P<target>{_EXACT_RECORD_TARGET_PATTERN})"
    rf"(?:{_WHOLE_RECORD_DELETE_VERB_PATTERN})"
    rf"{_DELETE_REQUEST_SUFFIX_PATTERN}$",
    re.IGNORECASE,
)
_EXACT_RECORD_TARGET_RE = re.compile(
    rf"^(?P<record_type_alias>{_DELETE_RECORD_TYPE_TEXT_ALIAS_PATTERN})"
    r"(?:记录|条目)#?(?P<record_id>\d+)$",
    re.IGNORECASE,
)
_EXACT_RECORD_TARGET_SEARCH_RE = re.compile(
    rf"(?P<record_type_alias>{_DELETE_RECORD_TYPE_TEXT_ALIAS_PATTERN})"
    r"(?:记录|条目)#?(?P<record_id>\d+)",
    re.IGNORECASE,
)
_UPDATE_VALUE_MARKER_RE = re.compile(
    r"(?:改成|改为|修改成|修改为|更正为|修正为|调整为|更新为|"
    r"应该是|实际是|其实是)"
)
_RECORD_ID_CONTINUATION_RE = re.compile(
    r"(?:和|与|及|、|,)(?:记录|条目)?#?(?P<record_id>\d+)"
    r"(?!\d|\s*(?:ml|毫升|l|升|kg|公斤|千克|斤))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _WholeRecordDeleteEvidence:
    """Content-free authorization evidence derived only from the user turn."""

    target_kind: str
    record_type: str | None = None
    record_id: int | None = None


def canonical_health_manage_record_id(value: Any) -> int | None:
    """Return a strict positive-integer record identity, or fail closed."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        normalized = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"\d+", stripped) is None:
            return None
        normalized = int(stripped)
    else:
        return None
    return normalized if normalized > 0 else None


def canonical_health_manage_record_type(value: Any) -> str | None:
    """Accept only production-supported canonical health_manage types."""
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _HEALTH_MANAGE_CANONICAL_RECORD_TYPES else None


def _whole_record_delete_evidence(
    text: str,
) -> _WholeRecordDeleteEvidence | None:
    """Extract content-free target evidence from a closed delete grammar."""
    normalized = "".join(str(text or "").split())
    if not normalized:
        return None
    if any(marker in normalized for marker in _DELETE_UNDO_MARKERS):
        return None
    if any(marker in normalized for marker in _DELETE_MIXED_UPDATE_MARKERS):
        return None
    match = _WHOLE_RECORD_DELETE_VERB_FIRST_RE.fullmatch(normalized)
    if match is None:
        match = _WHOLE_RECORD_DELETE_TARGET_FIRST_RE.fullmatch(normalized)
    if match is None:
        return None

    exact_target = _EXACT_RECORD_TARGET_RE.fullmatch(match.group("target"))
    if exact_target is None:
        return None
    record_id = canonical_health_manage_record_id(exact_target.group("record_id"))
    if record_id is None:
        return None
    record_type = _DELETE_RECORD_TYPE_TEXT_ALIASES.get(
        exact_target.group("record_type_alias").lower()
    )
    if record_type is None:
        return None
    return _WholeRecordDeleteEvidence(
        target_kind="exact_record",
        record_type=record_type,
        record_id=record_id,
    )


def _delete_evidence_authorizes_request(
    evidence: _WholeRecordDeleteEvidence | None,
    args: dict[str, Any],
) -> bool:
    if evidence is None or evidence.target_kind != "exact_record":
        return False
    requested_type = canonical_health_manage_record_type(args.get("record_type"))
    requested_id = canonical_health_manage_record_id(args.get("record_id"))
    if requested_type is None or requested_id is None:
        return False
    return evidence.record_type == requested_type and evidence.record_id == requested_id


def _authorized_health_manage_update_args(
    snapshot: TurnSnapshot,
    args: dict[str, Any],
) -> dict[str, Any] | None:
    """Bind an update to owner-scoped identity and a user-owned exact patch.

    The model may propose an ID and patch, but neither becomes authority.  For
    the first supported correction family (water), the record identity comes
    from an explicit user-visible ID or a successful owner-scoped list result;
    the replacement amount is parsed independently from the user's correction.
    Unsupported/ambiguous update families fail closed until they have an
    equivalent deterministic evidence extractor.
    """
    from app.services.write_intent_scope import (
        has_explicit_authorizing_update_request,
    )

    if not has_explicit_authorizing_update_request(snapshot.envelope.text):
        return None
    if len(_explicit_update_target_mentions(snapshot.envelope.text)) > 1:
        return None
    requested_type = canonical_health_manage_record_type(args.get("record_type"))
    requested_id = canonical_health_manage_record_id(args.get("record_id"))
    if requested_id is None:
        return None

    if requested_type == "illness":
        return _authorized_illness_update_args(snapshot, args, requested_id)
    if requested_type != "water":
        return None

    records = _owner_scoped_manage_list_records(snapshot, requested_type)
    requested_record = next(
        (
            record
            for record in records
            if canonical_health_manage_record_id(
                record.get("id", record.get("record_id"))
            )
            == requested_id
        ),
        None,
    )
    if requested_record is None:
        return None

    parsed_values = _water_update_values(snapshot.envelope.text)
    if parsed_values is None:
        return None
    old_amount, new_amount = parsed_values
    if _numbers_match(new_amount, requested_record.get("amount")):
        # A correction back to the persisted value is a cancellation/no-op,
        # not authority to emit a redundant mutation.
        return None
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    requested_amount = next(
        (
            value
            for value in (data.get("amount"), data.get("amount_ml"))
            if value not in (None, "", [])
        ),
        None,
    )
    if requested_amount is None or not _numbers_match(new_amount, requested_amount):
        return None

    explicit_target = _explicit_update_target(snapshot.envelope.text)
    if explicit_target is not None:
        if explicit_target != (requested_type, requested_id):
            return None
        if old_amount is not None and not _numbers_match(
            old_amount,
            requested_record.get("amount"),
        ):
            return None
    else:
        candidates = [
            record
            for record in records
            if old_amount is not None
            and _numbers_match(old_amount, record.get("amount"))
        ]
        if (
            not candidates
            and old_amount is None
            and re.search(r"(?:刚才|刚刚|上一条|最近一条)", snapshot.envelope.text)
        ):
            candidates = records[:1]
        candidate_ids = {
            canonical_health_manage_record_id(
                candidate.get("id", candidate.get("record_id"))
            )
            for candidate in candidates
        }
        candidate_ids.discard(None)
        if candidate_ids != {requested_id}:
            return None

    return {
        "record_type": "water",
        "operation": "update",
        "record_id": requested_id,
        "data": {"amount": _canonical_numeric_value(new_amount)},
    }


def _authorized_illness_update_args(
    snapshot: TurnSnapshot,
    args: dict[str, Any],
    requested_id: int,
) -> dict[str, Any] | None:
    records = _owner_scoped_manage_list_records(snapshot, "illness")
    requested_record = next(
        (
            record
            for record in records
            if canonical_health_manage_record_id(
                record.get("id", record.get("record_id"))
            )
            == requested_id
        ),
        None,
    )
    if requested_record is None:
        return None
    if not _illness_update_targets_owner(
        snapshot.envelope.text,
        str(requested_record.get("name") or ""),
    ):
        return None
    visible_ids = _explicit_illness_record_ids(snapshot.envelope.text)
    if visible_ids and visible_ids != {requested_id}:
        return None

    patch = _illness_update_patch(snapshot)
    requested_data = args.get("data")
    if patch is None or not isinstance(requested_data, dict):
        return None
    if requested_data != patch:
        return None

    explicit_target = _explicit_update_target(snapshot.envelope.text)
    if explicit_target is not None:
        if explicit_target != ("illness", requested_id):
            return None
    else:
        target_names = {
            _normalize_entity_name(name)
            for name in _illness_targets(snapshot.envelope.text)
            if _normalize_entity_name(name)
        }
        candidates = [
            record
            for record in records
            if _normalize_entity_name(record.get("name")) in target_names
        ]
        candidate_ids = {
            canonical_health_manage_record_id(
                candidate.get("id", candidate.get("record_id"))
            )
            for candidate in candidates
        }
        candidate_ids.discard(None)
        if candidate_ids != {requested_id}:
            return None

    return {
        "record_type": "illness",
        "operation": "update",
        "record_id": requested_id,
        "data": patch,
    }


def _illness_update_patch(snapshot: TurnSnapshot) -> dict[str, Any] | None:
    text = "".join(str(snapshot.envelope.text or "").split())
    statement = _illness_governing_state_statement(snapshot, text)
    if statement is None:
        return None
    patch: dict[str, Any]
    if _ILLNESS_CLEAR_ACTIVE_RE.fullmatch(statement):
        patch = {"status": "active"}
    elif _ILLNESS_PARTIAL_RECOVERY_RE.fullmatch(statement):
        patch = {"status": "improving"}
    elif _ILLNESS_CLEAR_IMPROVEMENT_RE.fullmatch(statement):
        patch = {"status": "improving"}
    elif _ILLNESS_CLEAR_RESOLUTION_RE.fullmatch(statement):
        patch = {"status": "resolved"}
    else:
        # Unknown qualifiers, uncertainty, relapse and additional semantic
        # clauses never inherit authority from a recovery substring.
        return None

    if patch["status"] == "resolved":
        day_offsets = {
            "前天": -2,
            "昨天": -1,
            "昨日": -1,
            "今日": 0,
            "今天": 0,
        }
        time_markers = tuple(re.finditer(r"前天|昨天|昨日|今日|今天", text))
        day_offset = day_offsets[time_markers[-1].group(0)] if time_markers else None
        if day_offset is not None:
            patch["end_date"] = (
                snapshot.context.current_time.date() + timedelta(days=day_offset)
            ).isoformat()
    return patch


def _illness_governing_state_statement(
    snapshot: TurnSnapshot,
    text: str,
) -> str | None:
    """Return one closed, final illness-state assertion or fail closed."""
    record_names = sorted(
        (
            "".join(str(record.get("name") or "").split())
            for record in _owner_scoped_manage_list_records(snapshot, "illness")
        ),
        key=len,
        reverse=True,
    )
    target_name = next((name for name in record_names if name and name in text), "")
    if not target_name:
        return None
    statement = text.split(target_name, 1)[1]
    statement = _ILLNESS_UPDATE_INSTRUCTION_SUFFIX_RE.sub("", statement)
    statement = statement.strip("，,。.!！；;：:")
    statement = _strip_illness_record_reference(statement)
    governing_parts = _ILLNESS_ASSERTION_BOUNDARY_RE.split(statement)
    statement = governing_parts[-1] if governing_parts else statement
    statement = _ILLNESS_STATE_TIME_PREFIX_RE.sub("", statement, count=1)
    statement = statement.strip("，,。.!！；;：:")
    return statement or None


def _strip_illness_record_reference(statement: str) -> str:
    candidate = statement.lstrip("的")
    for pattern in _ILLNESS_RECORD_ID_PATTERNS:
        match = pattern.match(candidate)
        if match is not None:
            return candidate[match.end() :].lstrip("的")
    return candidate


def _water_update_values(text: str) -> tuple[float | None, float] | None:
    normalized = "".join(str(text or "").split())
    markers = tuple(_UPDATE_VALUE_MARKER_RE.finditer(normalized))
    if not markers:
        return None
    marker = markers[-1]
    new_matches = tuple(_WATER_TARGET_RE.finditer(normalized[marker.end() :]))
    if not new_matches:
        return None
    new_amount = _water_match_amount_ml(new_matches[0])
    old_matches = tuple(_WATER_TARGET_RE.finditer(normalized[: marker.start()]))
    old_amount = _water_match_amount_ml(old_matches[-1]) if old_matches else None
    from app.services.write_intent_scope import (
        corrected_water_update_value,
        has_water_update_correction,
    )

    corrected_amount = corrected_water_update_value(text)
    if has_water_update_correction(text) and corrected_amount is None:
        return None
    return old_amount, corrected_amount if corrected_amount is not None else new_amount


def _water_match_amount_ml(match: re.Match[str]) -> float:
    amount = float(match.group("value"))
    return amount * 1000 if match.group("unit").lower() in {"l", "升"} else amount


def _explicit_update_target_mentions(text: str) -> tuple[tuple[str, int], ...]:
    normalized = "".join(str(text or "").split())
    mentions: list[tuple[str, int]] = []
    primary_matches = tuple(_EXACT_RECORD_TARGET_SEARCH_RE.finditer(normalized))
    for match in primary_matches:
        record_type = _DELETE_RECORD_TYPE_TEXT_ALIASES.get(
            match.group("record_type_alias").lower()
        )
        record_id = canonical_health_manage_record_id(match.group("record_id"))
        if record_type is not None and record_id is not None:
            mentions.append((record_type, record_id))
    if primary_matches:
        first = primary_matches[0]
        boundary = next(
            (
                marker.start()
                for marker in _UPDATE_VALUE_MARKER_RE.finditer(normalized)
                if marker.start() > first.end()
            ),
            len(normalized),
        )
        record_type = _DELETE_RECORD_TYPE_TEXT_ALIASES.get(
            first.group("record_type_alias").lower()
        )
        if record_type is not None:
            for match in _RECORD_ID_CONTINUATION_RE.finditer(
                normalized[first.end() : boundary]
            ):
                record_id = canonical_health_manage_record_id(match.group("record_id"))
                if record_id is not None:
                    mentions.append((record_type, record_id))
    return tuple(dict.fromkeys(mentions))


def _explicit_update_target(text: str) -> tuple[str, int] | None:
    mentions = _explicit_update_target_mentions(text)
    if len(mentions) != 1:
        return None
    return mentions[0]


def _explicit_illness_record_ids(text: str) -> set[int]:
    """Return every user-visible generic record ID in an illness update."""
    normalized = "".join(str(text or "").split())
    record_ids: set[int] = set()
    for pattern in _ILLNESS_RECORD_ID_PATTERNS:
        for match in pattern.finditer(normalized):
            record_id = canonical_health_manage_record_id(match.group("record_id"))
            if record_id is not None:
                record_ids.add(record_id)
    return record_ids


def _project_illness_query_to_turn(text: str) -> dict[str, Any] | None:
    """Bind an illness-history read to the entity/window stated by the user."""
    normalized = _query_scope_text(text)
    if _query_contains_unresolved_reference(normalized):
        return None
    targets = _illness_query_entities(normalized)
    if len(targets) != 1:
        return None
    if _is_unresolved_query_reference(targets[0]):
        return None
    if not _is_explicit_illness_query_entity(targets[0]):
        return None
    latest_occurrence = _latest_occurrence_query_entity(normalized)
    if not (
        re.search(r"(?:记录|病史|病历|病例|历史)", normalized)
        or _READ_QUERY_VERB_RE.search(normalized)
        or _HISTORY_QUERY_WINDOW_RE.search(normalized)
        or _HISTORY_QUERY_QUESTION_RE.search(normalized)
        or re.search(r"[?？]\s*$", normalized)
        or _is_registered_illness_acronym(targets[0])
        or latest_occurrence is not None
    ):
        return None
    projected: dict[str, Any] = {
        "dimension": "illness",
        "keyword": targets[0],
    }
    window_days = (
        None
        if latest_occurrence is not None
        else _explicit_query_window_days(normalized)
    )
    if window_days is not None:
        projected["days"] = window_days
    return projected


def _is_explicit_illness_query_entity(value: str) -> bool:
    """Classify one user-owned entity independently from model-selected domain."""
    normalized = str(value or "").strip("的，,。.!！；;：:?？ ")
    return bool(
        2 <= len(normalized) <= 80
        and normalized not in _NON_ILLNESS_QUERY_ENTITY_TERMS
        and not _query_entity_known_dimensions(normalized)
        and illness_entity_has_medical_semantics(normalized)
        and not illness_target_is_unowned_or_referential(normalized)
    )


def _is_non_read_health_observation(text: str) -> bool:
    """Keep a present-tense health assertion from authorizing a read tool."""
    normalized = _query_scope_text(text)
    if (
        _READ_QUERY_VERB_RE.search(normalized)
        or re.search(r"(?:记录|病史|病历|病例|历史)", normalized)
        or _HISTORY_QUERY_QUESTION_RE.search(normalized)
        or re.search(r"[?？]\s*$", normalized)
        or re.search(
            r"(?:相比|相对|对比|比较|除以|之比|几倍|比例|比率|ratio|[vV][sS])",
            normalized,
            re.IGNORECASE,
        )
    ):
        return False
    has_current_time = bool(
        re.search(
            r"(?:今天|今日|目前|现在|刚才|刚刚|最近|这两天|上回|上次)",
            normalized,
        )
    )
    has_state_assertion = bool(
        re.search(
            r"(?:又)?(?:发作|复发|发生|出现|犯了|犯过|犯|加重|恶化|严重|厉害|"
            r"乏力|晕厥|疼痛|不适|好转|改善|缓解|痊愈|康复)(?:了|中)?$",
            normalized,
        )
    )
    return has_current_time and has_state_assertion


def _normalize_query_text(text: str) -> str:
    """Normalize spacing while preserving line breaks as entity boundaries."""
    with_boundaries = re.sub(r"[\r\n]+", "、", str(text or ""))
    return re.sub(r"[ \t\f\v]+", "", with_boundaries)


def _health_read_cancelled_by_user(text: str) -> bool:
    """Return whether the active read speech act is explicitly cancelled."""
    return health_read_cancelled(text)


def _has_explicit_read_request(text: str) -> bool:
    """Identify an explicit read speech act anywhere in a compound request."""
    return has_explicit_health_read_request(text)


def _query_scope_text(text: str) -> str:
    """Select a later positive read clause after a cancelled action."""
    return _normalize_query_text(active_health_read_clause(text))


def _illness_query_entities(text: str) -> tuple[str, ...]:
    """Extract atomic entities from one closed health-query frame."""
    normalized = _query_scope_text(text)
    entities: list[str] = []
    candidate = _history_query_entity_expression(normalized)
    if candidate:
        for value in _HISTORY_QUERY_MULTI_ENTITY_RE.split(candidate):
            entity = value.strip("的，,。.!！；;：:?？ ")
            if 2 <= len(entity) <= 40:
                entities.append(entity)
    return tuple(dict.fromkeys(entities))


def _history_query_entity_expression(text: str) -> str | None:
    """Reduce a read request to its entity expression, independent of wording."""
    scoped = _query_scope_text(text)
    has_question_punctuation = bool(re.search(r"[?？]\s*$", scoped))
    normalized = scoped.strip("。.!！?？")
    latest_entity = _latest_occurrence_query_entity(normalized)
    if latest_entity is not None:
        return latest_entity
    has_read_verb = bool(_READ_QUERY_VERB_RE.search(normalized))
    has_comparison_frame = bool(
        re.search(
            r"(?:相比|相对|对比|比较|除以|之比|占|[/／]|"
            r"比(?!(?:率|例|较))|倍数|几倍|比例|比率|ratio|[vV][sS])",
            normalized,
            re.IGNORECASE,
        )
    )
    has_history_frame = bool(
        re.search(r"(?:记录|病史|病历|病例|历史)", normalized)
        or _HISTORY_QUERY_QUESTION_RE.search(normalized)
        or has_read_verb
        or has_comparison_frame
        or has_question_punctuation
    )
    has_read_semantics = bool(
        re.search(r"(?:病史|病历|病例|历史)", normalized)
        or _HISTORY_QUERY_WINDOW_RE.search(normalized)
        or _HISTORY_QUERY_QUESTION_RE.search(normalized)
        or has_read_verb
        or has_comparison_frame
        or has_question_punctuation
    )
    if not has_history_frame or not has_read_semantics:
        return _sparse_health_query_entity_expression(normalized)

    history_container_match = re.search(
        r"(?:记录|病史|病历|病例|历史)(?:里|中)(?:的)?"
        rf"(?:{_READ_QUERY_VERB_PATTERN})?"
        r"(?P<entity>.{2,80}?)"
        r"(?:(?:分别|有哪些|有那些|有什么|有几条|有几次|有多少条|多少条)"
        r"(?:记录|病史|病历|病例|历史)?|(?:记录|病史|病历|病例|历史)|"
        r"(?:怎么样|怎样|如何|是多少|呢))$",
        normalized,
    )
    previous_match = re.search(
        r"(?:上一次|最近一次)(?:的)?(?P<entity>.{2,80}?)"
        r"(?:是什么时候|在什么时候|什么时候|何时|在何时|是何时|是哪天|是几号)",
        normalized,
    )
    trailing_previous_match = re.search(
        r"(?P<entity>.{2,80}?)(?:上一次|最近一次)(?:的)?"
        r"(?:记录|发作)?(?:是什么时候|在什么时候|什么时候|何时|在何时|"
        r"是何时|是哪天|是几号|呢)",
        normalized,
    )
    if history_container_match is not None:
        candidate = history_container_match.group("entity")
    elif trailing_previous_match is not None:
        candidate = trailing_previous_match.group("entity")
    elif previous_match is not None:
        candidate = previous_match.group("entity")
    else:
        window_matches = tuple(_HISTORY_QUERY_WINDOW_RE.finditer(normalized))
        window_match = window_matches[0] if window_matches else None
        candidate = normalized
        if len(window_matches) > 1:
            candidate = _HISTORY_QUERY_WINDOW_RE.sub("", normalized)
        elif window_match is not None:
            before_candidate = _clean_history_query_entity(
                _strip_history_query_request_prefix(normalized[: window_match.start()])
            )
            after_window = normalized[window_match.end() :]
            history_marker = re.search(r"(?:记录|病史|病历|病例|历史)", after_window)
            after_candidate = (
                after_window[: history_marker.start()]
                if history_marker is not None
                else after_window
            )
            after_candidate = _clean_history_query_entity(
                _strip_history_query_request_prefix(after_candidate)
            )
            if before_candidate and after_candidate:
                candidate = f"{before_candidate}和{after_candidate}"
            else:
                candidate = after_candidate or before_candidate

    candidate = _strip_history_query_request_prefix(candidate)
    candidate = _clean_history_query_entity(candidate)
    return candidate if 2 <= len(candidate) <= 120 else None


def _latest_occurrence_query_entity(text: str) -> str | None:
    """Extract one named entity from composable latest-occurrence grammar."""
    normalized = _strip_history_query_request_prefix(
        text.strip("的，,。.!！；;：:?？ ")
    )
    marker_first = re.fullmatch(
        rf"{_LATEST_OCCURRENCE_MARKER_PATTERN}(?:的)?"
        rf"(?P<entity>.{{1,80}}?){_LATEST_OCCURRENCE_EVENT_PATTERN}"
        rf"{_LATEST_OCCURRENCE_QUESTION_PATTERN}",
        normalized,
    )
    entity_first = re.fullmatch(
        rf"(?P<entity>.{{1,80}}?){_LATEST_OCCURRENCE_MARKER_PATTERN}(?:的)?"
        rf"{_LATEST_OCCURRENCE_EVENT_PATTERN}{_LATEST_OCCURRENCE_QUESTION_PATTERN}",
        normalized,
    )
    flexible_entity_first = re.fullmatch(
        rf"(?P<entity>.{{1,80}}?){_LATEST_OCCURRENCE_MARKER_PATTERN}(?:的)?"
        rf"{_LATEST_OCCURRENCE_EVENT_PATTERN}{_LATEST_OCCURRENCE_QUESTION_PATTERN}?"
        rf"{_LATEST_OCCURRENCE_EVENT_PATTERN}",
        normalized,
    )
    match = marker_first or entity_first or flexible_entity_first
    if match is None:
        return None
    candidate = _strip_history_query_request_prefix(match.group("entity"))
    candidate = _clean_history_query_entity(candidate)
    if _is_unresolved_query_reference(candidate):
        return candidate
    return candidate if 2 <= len(candidate) <= 80 else None


def _strip_history_query_request_prefix(value: str) -> str:
    """Strip composable request scaffolding without enumerating whole sentences."""
    candidate = value
    prefix_component_re = re.compile(
        r"^(?:请问|请您|烦请|劳烦|有劳|劳驾|拜托|方便的话|请|您|麻烦你?|能不能|可不可以|"
        r"可以不可以|能否|可否|"
        r"(?:能|可以)(?=给我|帮我|帮忙|替我|为我|查询|查找|查看|查一下|"
        r"找出|找一下|找|回顾|回看|检索|列出|翻一下|调取|调出|看看|查|把)|"
        r"我想(?:请你|知道)?|想知道|我希望|我需要|给我|帮我|帮忙|替我|只|"
        r"为我|你|把|我自己的|自己的|本人(?:的)?|我(?:的)?)"
    )
    while candidate:
        candidate = candidate.lstrip("，,。.!！；;：:?？ ")
        reduced = prefix_component_re.sub("", candidate, count=1)
        reduced = _HISTORY_QUERY_LEADING_VERB_RE.sub("", reduced, count=1)
        if reduced == candidate:
            break
        candidate = reduced
    return candidate


def _clean_history_query_entity(value: str) -> str:
    """Remove only structural query decorators surrounding one entity span."""
    candidate = _HISTORY_QUERY_TRAILING_VERB_RE.sub("", value, count=1)
    candidate = _HISTORY_QUERY_WINDOW_RE.sub("", candidate)
    candidate = re.sub(
        r"(?:的)?(?:倍数|几倍|比例|比率|ratio|之比|占比|占多少)$",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = candidate.removesuffix("是")
    candidate = re.sub(
        r"(?:的)?(?:记录|病史|病历|病例|历史).*$", "", candidate, count=1
    )
    candidate = re.sub(
        r"(?:所有|全部|分别|有哪些|有那些|有什么|有几条|有几次|有多少条|多少条|"
        r"是什么时候|在什么时候|什么时候|何时|是几号|是多少|平均多少|多少(?:呢)?|"
        r"(?:是)?升还是降|上升还是下降|有多高|怎么样|怎样|如何|呢)$",
        "",
        candidate,
    )
    candidate = re.sub(r"(?:的)?(?:情况|状况|状态)$", "", candidate)
    candidate = re.sub(r"^(?:(?:在|里|期间|的|关于)+|和|与|及|或|跟)+", "", candidate)
    candidate = re.sub(r"(?:的|相关|吗|在)+$", "", candidate)
    return candidate.strip("的，,。.!！；;：:?？ ")


def _is_registered_illness_acronym(value: str) -> bool:
    return str(value or "").strip().casefold() in _ILLNESS_MEDICAL_ACRONYMS


def _is_unresolved_query_reference(value: str) -> bool:
    return is_unresolved_health_reference(value)


def _query_contains_unresolved_reference(text: str) -> bool:
    """Detect a discourse pointer that names no durable health entity."""
    scoped = _query_scope_text(text)
    if is_unresolved_health_reference(scoped):
        return True
    latest_entity = _latest_occurrence_query_entity(scoped)
    if latest_entity is not None:
        return is_unresolved_health_reference(latest_entity)
    candidate = _history_query_entity_expression(scoped)
    if candidate is not None:
        return is_unresolved_health_reference(candidate)
    return False


def _sparse_health_query_entity_expression(text: str) -> str | None:
    """Recognize terse entity fragments without granting arbitrary model scope."""
    candidate = _strip_history_query_request_prefix(text)
    candidate = _clean_history_query_entity(candidate)
    if not candidate:
        return None
    entities = tuple(
        _clean_history_query_entity(value)
        for value in _HISTORY_QUERY_MULTI_ENTITY_RE.split(candidate)
        if _clean_history_query_entity(value)
    )
    if not entities:
        return None
    if not all(
        len(_query_entity_known_dimensions(entity)) == 1
        or _is_registered_illness_acronym(entity)
        for entity in entities
    ):
        return None
    return "和".join(entities)


def _history_query_has_multiple_scopes(text: str) -> bool:
    """Reject history requests whose separate scopes need a batch/read plan."""
    normalized = _query_scope_text(text)
    if len(tuple(_HISTORY_QUERY_WINDOW_RE.finditer(normalized))) > 1:
        return True
    markers = tuple(
        re.finditer(r"(?:历史记录|记录历史|记录|病史|病历|病例|历史)", normalized)
    )
    if len(markers) <= 1:
        return False
    # “历史记录” and “历史中……有哪些记录” are one natural query frame, not
    # two independently scoped reads. Separate repeated record/history clauses
    # remain closed so a single tool call cannot silently choose one of them.
    return (
        re.search(
            r"(?:记录|病史|病历|病例|历史)(?:里|中)(?:的)?"
            rf"(?:{_READ_QUERY_VERB_PATTERN})?"
            r".{2,80}(?:(?:有哪些|有那些|有什么|有几条|有几次|"
            r"有多少条|多少条)(?:记录|病史|病历|病例|历史)?|"
            r"(?:记录|病史|病历|病例|历史)|(?:怎么样|怎样|如何|是多少|呢))$",
            normalized,
        )
        is None
    )


def _query_entities_match_dimension(
    entities: tuple[str, ...],
    dimension: str,
) -> bool:
    terms = _QUERY_DIMENSION_TEXT_TERMS.get(dimension, ())
    if not terms:
        return False
    if dimension == "medical_exam":
        modality_terms = ("MRI", "核磁", "磁共振", "CT", "X光", "B超", "胃镜")
        if all(
            any(
                re.fullmatch(
                    rf"[\u4e00-\u9fffA-Za-z0-9]{{0,24}}{re.escape(term)}"
                    r"(?:检查|报告|检查报告|影像|结果)?",
                    entity,
                    flags=re.IGNORECASE,
                )
                for term in modality_terms
            )
            for entity in entities
        ):
            return True
    return all(
        any(
            re.fullmatch(
                rf"{_QUERY_DIMENSION_ENTITY_PREFIX_PATTERN}"
                rf"{re.escape(term)}{_QUERY_DIMENSION_ENTITY_SUFFIX_PATTERN}",
                entity,
                flags=re.IGNORECASE,
            )
            for term in terms
        )
        for entity in entities
    )


def _query_entities_known_dimension(entities: tuple[str, ...]) -> str | None:
    matches = tuple(
        dimension
        for dimension in _QUERY_DIMENSION_TEXT_TERMS
        if _query_entities_match_dimension(entities, dimension)
    )
    return matches[0] if len(matches) == 1 else None


def _query_text_known_dimension(text: str) -> str | None:
    """Resolve one unambiguous registered dimension from free observation text."""
    normalized = _query_scope_text(text)
    if re.search(r"(?:上传|导入)", normalized) and re.search(
        r"(?:报告|检查|体检|影像|化验)", normalized
    ):
        return "medical_exam"
    matches: list[tuple[int, int, str]] = []
    for dimension, terms in _QUERY_DIMENSION_TEXT_TERMS.items():
        semantic_dimension = _semantic_query_dimension(dimension)
        for term in terms:
            if len(term) < 2 and term.isascii() is False:
                continue
            for match in re.finditer(re.escape(term), normalized, flags=re.IGNORECASE):
                if _query_dimension_match_embedded_in_illness_name(
                    normalized,
                    match.start(),
                    match.end(),
                ):
                    continue
                matches.append((match.start(), match.end(), semantic_dimension))
    selected: list[tuple[int, int, str]] = []
    for match in sorted(matches, key=lambda item: item[1] - item[0], reverse=True):
        if any(
            match[0] >= existing[0] and match[1] <= existing[1] for existing in selected
        ):
            continue
        selected.append(match)
    dimensions = {dimension for _start, _end, dimension in selected}
    return next(iter(dimensions)) if len(dimensions) == 1 else None


def _project_known_dimension_query_args(
    text: str,
    entities: tuple[str, ...],
    dimension: str,
) -> dict[str, Any] | None:
    """Build exact read arguments from user text, never from model selectors."""
    semantic_dimension = _semantic_query_dimension(dimension)
    projected: dict[str, Any] = {"dimension": semantic_dimension}
    if semantic_dimension == "medical_exam" and re.search(r"(?:上传|导入)", text):
        uploaded_days = _projected_uploaded_days(text)
        if uploaded_days is None:
            return None
        projected["uploaded_days"] = uploaded_days
        return projected

    days = _explicit_query_window_days(text)
    if days is not None:
        projected["days"] = days
    elif semantic_dimension != "medical_exam":
        projected["days"] = 7

    if semantic_dimension == "medical_exam":
        if len(entities) != 1:
            return None
        keyword = re.sub(
            r"(?:检查报告|检查|报告|影像|结果)$",
            "",
            entities[0],
            flags=re.IGNORECASE,
        ).strip()
        if not keyword:
            return None
        projected["keyword"] = keyword
    return projected


def _project_medical_exam_query_to_turn(text: str) -> dict[str, Any] | None:
    """Project one exact current-user exam through the shared semantic contract."""
    resolution = resolve_medical_exam_query(text)
    if resolution.status != "exact" or not resolution.entity:
        return None
    return {"dimension": "medical_exam", "keyword": resolution.entity}


def _manage_list_turn_record_type(text: str) -> str | None:
    """Bind a user-facing manage-list call to the domain named in the turn."""
    if _project_medical_exam_query_to_turn(text) is not None:
        return "medical_exam"
    entities = _illness_query_entities(text)
    dimension = _query_entities_known_dimension(entities)
    if dimension is None:
        dimension = _query_text_known_dimension(text)
    semantic_dimension = _semantic_query_dimension(dimension or "")
    record_type_by_dimension = {
        "diet": "diet",
        "water": "water",
        "weight": "weight",
        "blood_pressure": "blood_pressure",
        "sleep": "sleep",
        "workout": "exercise",
        "manual_exercise": "exercise",
        "medication": "medication",
        "supplements": "supplement",
        "medical_exam": "medical_exam",
        "events": "event",
    }
    if semantic_dimension in record_type_by_dimension:
        return record_type_by_dimension[semantic_dimension]
    if _project_illness_query_to_turn(text) is not None:
        return "illness"
    return None


def _is_completed_health_mutation_observation(text: str) -> bool:
    """Keep completed-state narration from authorizing an internal lookup."""
    normalized = _normalize_query_text(text).strip("，,。.!！?？;； ")
    mutation = r"(?:更新|修改|删除|删掉|移除|更正|修正|调整|改成|改为)"
    return bool(
        re.search(
            rf"(?:刚|刚刚|已经|已|昨天|前天|上次|之前)"
            rf"[^，,。.!！?？;；]{{0,48}}{mutation}"
            r"(?:完|完了|完毕|好了?|的是)",
            normalized,
        )
        or re.search(
            rf"(?:被)?{mutation}[^，,。.!！?？;；]{{0,20}}"
            r"(?:完|完了|完毕|好了|结束|了)$",
            normalized,
        )
    )


def _projected_uploaded_days(text: str) -> int | None:
    """Bind rolling upload time to the integer N×24-hour runtime contract."""
    normalized = _query_scope_text(text)
    hours_match = re.search(
        r"(?:最近|近|过去)(?P<value>\d+|[一二两三四五六七八九十]+)"
        r"(?:个)?小时(?:内|以来)?",
        normalized,
    )
    if hours_match is not None:
        hours = _parse_small_chinese_number(hours_match.group("value"))
        if hours is None or hours <= 0 or hours % 24 != 0:
            return None
        return hours // 24
    days = _explicit_query_window_days(normalized)
    if days is not None:
        return days
    if re.search(r"(?:最近|近来).*(?:上传|导入)|(?:上传|导入).*最近", normalized):
        return 7
    return None


def _query_dimension_match_embedded_in_illness_name(
    text: str,
    start: int,
    end: int,
) -> bool:
    """Reject metric substrings that are lexical parts of a disease name."""
    prefix = text[max(0, start - 16) : start]
    suffix = text[end : end + 20]
    return bool(
        re.search(r"(?:患有|患的是|确诊为|诊断为|诊断是)$", prefix)
        or (
            re.search(r"[\u4e00-\u9fff]{1,12}$", prefix)
            and re.match(
                r"(?:(?:今天|今日|最近|目前|现在)(?:又|更)?)?"
                r"(?:加重|恶化|复发|发作|更严重)",
                suffix,
            )
        )
        or re.match(
            r"(?:(?:相关|诱发|依赖|关联)?性)?"
            r"(?:呼吸暂停(?:综合征)?|"
            r"[\u4e00-\u9fff]{0,12}(?:哮喘|肾炎|癫痫|闭经|综合征|障碍|"
            r"疾病|感染|溃疡|疱疹|脑梗|偏头痛|疼痛|过敏|贫血|尿失禁|"
            r"心率失常|焦虑|病|症|炎|癌|疹|痛|敏|虑|禁|失常))",
            suffix,
        )
    )


def _semantic_query_dimension(dimension: str) -> str:
    normalized = str(dimension or "").strip().lower()
    return _QUERY_DIMENSION_SEMANTIC_ALIASES.get(normalized, normalized)


def _query_entity_known_dimensions(entity: str) -> frozenset[str]:
    return frozenset(
        _semantic_query_dimension(dimension)
        for dimension in _QUERY_DIMENSION_TEXT_TERMS
        if _query_entities_match_dimension((entity,), dimension)
    )


def _batch_query_semantic_bindings(
    args: dict[str, Any],
) -> tuple[tuple[str, int, str | None], ...] | None:
    queries = args.get("queries")
    if not isinstance(queries, list) or not queries:
        return None
    bindings: list[tuple[str, int, str | None]] = []
    for query in queries:
        if not isinstance(query, dict):
            return None
        canonical = normalize_health_query_args(query)
        dimension = canonical.get("dimension")
        if not isinstance(dimension, str) or not dimension.strip():
            return None
        days = canonical.get("days")
        if isinstance(days, bool):
            return None
        try:
            normalized_days = int(days)
        except (TypeError, ValueError):
            return None
        if normalized_days <= 0:
            return None
        raw_agg = query.get("agg")
        agg = str(raw_agg).strip().lower() if raw_agg not in (None, "") else None
        bindings.append((_semantic_query_dimension(dimension), normalized_days, agg))
    return tuple(bindings)


def _query_requested_aggregate(text: str) -> str | None:
    """Resolve one explicit aggregation operation from a user-owned span."""
    requested: set[str] = set()
    patterns = {
        "trend": r"(?:趋势|升还是降|上升还是下降)",
        "avg": r"(?:平均(?:值)?|均值|日均)",
        "min": r"(?:最低(?:值)?|最小(?:值)?)",
        "max": r"(?:最高(?:值)?|最大(?:值)?)",
        "latest": r"(?:最新(?:值)?|最近一个值)",
    }
    for agg, pattern in patterns.items():
        if re.search(pattern, text):
            requested.add(agg)
    return next(iter(requested)) if len(requested) == 1 else None


def _normalize_batch_query_plan(
    args: dict[str, Any],
) -> dict[str, Any]:
    """Canonicalize a valid batch plan without granting model JSON authority."""
    try:
        from app.services.health_query_batch import known_dimensions, validate_plan

        queries, compare, error = validate_plan(
            args,
            valid_dimensions=known_dimensions(),
        )
    except Exception:  # noqa: BLE001 - validation still fails loud downstream
        return args
    if error is not None or queries is None:
        return args
    normalized: dict[str, Any] = {"queries": queries}
    if compare is not None:
        normalized["compare"] = compare
    return normalized


def _query_window_days(window_text: str) -> int | None:
    if window_text in {"今天", "今日"}:
        return 1
    if window_text in {"最近", "近来"}:
        return 7
    match = re.fullmatch(
        r"(?:最近|近|过去)(?P<value>\d+|[一二两三四五六七八九十]+|半)"
        r"(?:个)?(?P<unit>天|周|月|年)(?:内|以来)?",
        window_text,
    )
    if match is None:
        return None
    if match.group("value") == "半" and match.group("unit") == "年":
        return 183
    value = _parse_small_chinese_number(match.group("value"))
    if value is None or value <= 0:
        return None
    if match.group("unit") == "周":
        return value * 7
    if match.group("unit") == "月":
        return 183 if value == 6 else value * 30
    if match.group("unit") == "年":
        return value * 365
    return value


def _explicit_query_windows(text: str) -> tuple[tuple[int, int, int], ...]:
    normalized = _query_scope_text(text)
    windows: list[tuple[int, int, int]] = []
    for match in _HISTORY_QUERY_WINDOW_RE.finditer(normalized):
        if match.group(0) == "最近" and normalized[match.end() :].startswith(
            ("那次", "一回", "记录", "发作", "发生", "复发")
        ):
            continue
        days = _query_window_days(match.group(0))
        if days is not None:
            windows.append((match.start(), match.end(), days))
    return tuple(windows)


def _explicit_query_window_days(text: str) -> int | None:
    windows = _explicit_query_windows(text)
    return windows[0][2] if windows else None


def _batch_query_plan_bound_to_turn(
    text: str,
    entities: tuple[str, ...],
    normalized_plan: dict[str, Any],
) -> dict[str, Any] | None:
    """Authorize a complete batch plan from turn entity/window cardinality."""
    entity_dimensions: list[str] = []
    for entity in entities:
        dimensions = _query_entity_known_dimensions(entity)
        if len(dimensions) != 1:
            return None
        entity_dimensions.append(next(iter(dimensions)))

    # Distinct textual filters that collapse to one public dimension (for
    # example breakfast+dinner, MRI+CT or run+cycle) cannot be represented by
    # health_query_batch. Never broaden them into one unfiltered dimension.
    if len(set(entity_dimensions)) != len(entity_dimensions):
        return None

    proposed_bindings = _batch_query_semantic_bindings(normalized_plan)
    queries = normalized_plan.get("queries")
    if proposed_bindings is None or not isinstance(queries, list):
        return None

    windows = _explicit_query_windows(text)
    expected_dimensions = tuple(entity_dimensions)
    if len(windows) > 1 and len(entity_dimensions) == 1:
        expected_dimensions = tuple(entity_dimensions[0] for _window in windows)
    expected_query_count = len(expected_dimensions)
    if len(proposed_bindings) < expected_query_count:
        return None
    authoritative_bindings = proposed_bindings[:expected_query_count]
    proposed_dimensions = tuple(
        dimension for dimension, _days, _agg in proposed_bindings
    )[:expected_query_count]
    if proposed_dimensions != expected_dimensions:
        return None

    normalized_text = _query_scope_text(text)
    entity_segments = [normalized_text]
    if len(entity_dimensions) > 1:
        search_text = normalized_text.casefold()
        entity_spans: list[tuple[int, int]] = []
        cursor = 0
        for entity in entities:
            position = search_text.find(entity.casefold(), cursor)
            if position < 0:
                return None
            entity_spans.append((position, position + len(entity)))
            cursor = position + len(entity)

        separators: list[tuple[int, int]] = []
        for current_span, next_span in zip(entity_spans, entity_spans[1:]):
            between_start = current_span[1]
            between = normalized_text[between_start : next_span[0]]
            separator_matches = tuple(_HISTORY_QUERY_MULTI_ENTITY_RE.finditer(between))
            if not separator_matches:
                return None
            separator = separator_matches[-1]
            separators.append(
                (
                    between_start + separator.start(),
                    between_start + separator.end(),
                )
            )
        entity_segments = []
        for index in range(len(entity_dimensions)):
            segment_start = separators[index - 1][1] if index > 0 else 0
            segment_end = (
                separators[index][0]
                if index < len(separators)
                else len(normalized_text)
            )
            entity_segments.append(normalized_text[segment_start:segment_end])

    if not windows:
        expected_days = tuple(7 for _dimension in expected_dimensions)
    elif len(windows) == 1:
        expected_days = tuple(windows[0][2] for _dimension in expected_dimensions)
    elif len(entity_dimensions) == 1:
        if len({days for _start, _end, days in windows}) != len(windows):
            return None
        expected_days = tuple(days for _start, _end, days in windows)
    else:
        local_days: list[int] = []
        for segment in entity_segments:
            segment_windows = _explicit_query_windows(segment)
            if len(segment_windows) != 1:
                return None
            local_days.append(segment_windows[0][2])
        expected_days = tuple(local_days)

    if (
        len(windows) > 1
        and tuple(days for _dimension, days, _agg in authoritative_bindings)
        != expected_days
    ):
        return None

    global_agg = _query_requested_aggregate(normalized_text)
    compare = normalized_plan.get("compare")
    text_requests_comparison = bool(
        re.search(
            r"(?:相比|对比|比较|除以|之比|占|[/／]|倍数|几倍|比例|比率|ratio|[vV][sS])",
            normalized_text,
            re.IGNORECASE,
        )
    )
    default_compare_agg = "avg" if text_requests_comparison else None
    if len(entity_dimensions) == 1:
        expected_aggs = tuple(
            global_agg or default_compare_agg for _dimension in expected_dimensions
        )
    else:
        expected_aggs = tuple(
            _query_requested_aggregate(segment) or global_agg or default_compare_agg
            for segment in entity_segments
        )
    proposed_aggs = tuple(agg for _dimension, _days, agg in authoritative_bindings)
    if text_requests_comparison:
        # For an explicit user-owned comparison, ``avg`` is the deterministic
        # default.  Models commonly omit that default from each batch member;
        # project it here, but never accept a conflicting model-owned aggregate.
        if any(
            proposed not in {None, expected}
            for proposed, expected in zip(proposed_aggs, expected_aggs, strict=True)
        ):
            return None
    elif proposed_aggs != expected_aggs:
        return None

    projected_compare: dict[str, Any] | None = None
    if text_requests_comparison:
        if len(expected_dimensions) != 2:
            return None
        requested_op = (
            "ratio"
            if re.search(
                r"(?:除以|之比|占|[/／]|倍数|几倍|比例|比率|ratio)",
                normalized_text,
                re.I,
            )
            else "diff"
        )
        projected_compare = {"a": 0, "b": 1, "op": requested_op}
        if compare is not None and compare != projected_compare:
            return None
    elif compare is not None:
        return None

    projected_queries = [
        {
            "dimension": expected_dimensions[index],
            "days": expected_days[index],
            "agg": expected_aggs[index],
        }
        for index in range(expected_query_count)
    ]
    projected_plan: dict[str, Any] = {"queries": projected_queries}
    if projected_compare is not None:
        projected_plan["compare"] = projected_compare
    return projected_plan


def _illness_update_targets_owner(text: str, record_name: str) -> bool:
    normalized = "".join(str(text or "").split()).strip("。.!！?？")
    name = "".join(str(record_name or "").split())
    if not name:
        return False
    current_prefix = (
        r"(?:(?:请|请你|麻烦|麻烦你|帮我|请帮我|请你帮我|麻烦帮我|"
        r"可以帮我|能帮我|替我|给我|为我|"
        r"我想|我想请你|我要|我希望|我需要))?"
    )
    time_prefix = (
        r"(?:(?:在|于)?(?:之前|此前|先前|前天|昨天|昨日|今日|今天|刚刚|"
        r"刚才|现在|目前))?"
    )
    current_owner = r"(?:我(?:的)?)?"
    owner_and_time = rf"(?:{current_owner}{time_prefix}|{time_prefix}{current_owner})"
    return (
        re.fullmatch(
            rf"{current_prefix}{owner_and_time}{re.escape(name)}"
            r".{1,180}[，,]"
            rf"{current_prefix}(?:修改|更新|更正)(?:一下)?(?:这条)?记录",
            normalized,
        )
        is not None
    )


def _owner_scoped_manage_list_records(
    snapshot: TurnSnapshot,
    record_type: str,
) -> list[dict[str, Any]]:
    for reference in reversed(snapshot.actionable_references):
        if reference.kind != "owner_scoped_health_manage_list":
            continue
        if (
            canonical_health_manage_record_type(reference.data.get("record_type"))
            != record_type
        ):
            continue
        records = reference.data.get("records")
        if isinstance(records, (list, tuple)):
            return [dict(item) for item in records if isinstance(item, dict)]
    return []


def capability_policy_contract_payload() -> dict[str, Any]:
    """Return static, content-free metadata that governs tool authorization."""
    return {
        "contract_version": _CAPABILITY_POLICY_CONTRACT_VERSION,
        "whole_record_delete_evidence_version": (_WHOLE_RECORD_DELETE_EVIDENCE_VERSION),
        "health_manage_update_evidence_version": (
            _HEALTH_MANAGE_UPDATE_EVIDENCE_VERSION
        ),
        "read_only_tools": sorted(READ_ONLY_TOOLS),
        "specialist_read_only_tools": sorted(SPECIALIST_READ_ONLY_TOOLS),
        "write_tools": sorted(WRITE_TOOL_NAMES),
        "known_tools": sorted(KNOWN_TOOL_NAMES),
        "manage_write_operations": sorted(MANAGE_WRITE_OPERATIONS),
        "intervention_write_actions": sorted(INTERVENTION_WRITE_ACTIONS),
        "intervention_read_actions": sorted(INTERVENTION_READ_ACTIONS),
        "manage_plan_actions": sorted(MANAGE_PLAN_ACTIONS),
        "health_record_target_binding": {
            "version": _HEALTH_RECORD_TARGET_BINDING_VERSION,
            "domain_types": dict(sorted(_HEALTH_RECORD_DOMAIN_TYPES.items())),
        },
        "health_semantics": health_semantics_contract_payload(),
        "authorization_grammar_digest": authorization_grammar_digest(globals()),
        "recipe_record_types": sorted(RECIPE_REPLAY_ALLOWED_RECORD_TYPES),
        "recipe_record_type_aliases": dict(sorted(_RECIPE_RECORD_TYPE_ALIASES.items())),
    }


def capability_policy_digest() -> str:
    """Fingerprint policy metadata without prompts, arguments or user content."""
    encoded = json.dumps(
        capability_policy_contract_payload(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def decide_tool_capability(
    snapshot: TurnSnapshot,
    request: ToolExecutionRequest,
) -> CapabilityDecision:
    """Return the policy decision for one tool request.

    This function is intentionally independent from prompt text and tool schema
    exposure. It evaluates the turn intent plus normalized tool arguments.
    """
    tool_name = str(request.tool_name or "").strip()
    args = _parse_args(request.arguments)
    health_record_alias_conflict = False
    if tool_name == "health_record":
        health_record_alias_conflict = health_record_dispatch_aliases_conflict(args)
        args = normalize_health_record_dispatch_args(args)
    primary = snapshot.intent.primary
    health_record_target_authorized = False

    if not tool_name:
        return _decision("block", "missing_tool_name", tool_name, args)
    if health_record_alias_conflict:
        return _decision(
            "block",
            "health_record_target_mismatch",
            tool_name,
            args,
            receipt_required=True,
        )
    if tool_name == "health_record" and request.source != "procedure_recipe_replay":
        args = _recover_explicit_illness_create_from_generic_memory(snapshot, args)
        args = _project_exact_illness_create_from_model_fields(snapshot, args)

    mutating_request = _is_mutating_request(tool_name, args)
    if tool_name == "draft_aigc_media" and is_explicit_aigc_media_provider_veto(
        snapshot.envelope.text
    ):
        return _decision(
            "block",
            "explicit_aigc_media_provider_veto",
            tool_name,
            args,
            receipt_required=True,
        )
    if (
        mutating_request
        and not (
            tool_name == "health_manage"
            and str(args.get("operation") or "").strip().lower() == "delete"
        )
        and is_explicit_write_cancellation(snapshot.envelope.text)
    ):
        mixed_health_record_target = False
        if tool_name == "health_record":
            from app.services.write_intent_scope import (
                authorized_health_record_clauses,
            )

            mixed_health_record_target = bool(
                authorized_health_record_clauses(snapshot.envelope.text)
            )
        if not mixed_health_record_target:
            return _decision(
                "block",
                "explicit_write_cancellation",
                tool_name,
                args,
                receipt_required=True,
            )
    if tool_name == "health_record" and snapshot.intent.domain == "aigc_media":
        return _decision(
            "block",
            "aigc_media_turn_disallows_health_write",
            tool_name,
            args,
            receipt_required=True,
        )
    if (
        mutating_request
        and snapshot.goal is not None
        and snapshot.goal.requires_clarification
    ):
        return _decision(
            "block",
            "goal_requires_clarification",
            tool_name,
            args,
            receipt_required=True,
        )
    if tool_name == "health_record" and request.source != "procedure_recipe_replay":
        target_status = _health_record_target_status(snapshot, args)
        if target_status == "mismatch":
            return _decision(
                "block",
                "health_record_target_mismatch",
                tool_name,
                args,
                receipt_required=True,
            )
        if target_status == "unresolved":
            return _decision(
                "block",
                "health_record_authorization_target_unresolved",
                tool_name,
                args,
                receipt_required=True,
            )
        health_record_target_authorized = target_status == "match"
        if target_status == "unauthorized":
            return _decision(
                "block",
                (
                    "ambiguous_intent_requires_clarification"
                    if primary == "unknown"
                    else "write_tool_without_write_intent"
                ),
                tool_name,
                args,
                receipt_required=True,
            )

    # Procedure recipes are user-owned, exact-triggered, server-stored tool
    # sequences. Their AUTO/typed-only confirmation semantics are still applied
    # by the recipe executor before this policy runs. This source is internal to
    # AgentExecutor and deliberately authorizes only the recipe allowlisted tool.
    if request.source == "procedure_recipe_replay":
        if tool_name != "health_record":
            return _decision(
                "block",
                "recipe_replay_tool_not_allowed",
                tool_name,
                args,
                receipt_required=True,
            )
        if recipe_replay_record_type(args) not in RECIPE_REPLAY_ALLOWED_RECORD_TYPES:
            return _decision(
                "block",
                "recipe_replay_record_type_not_allowed",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "allow",
            "prevalidated_recipe_replay",
            tool_name,
            args,
            receipt_required=True,
        )

    if request.source == "telegram_directive":
        if tool_name != "user_directive":
            return _decision(
                "block",
                "telegram_directive_tool_not_allowed",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "allow",
            "prevalidated_telegram_directive",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name == "health_query":
        turn_text = snapshot.envelope.text
        canonical_args = normalize_health_query_args(args)
        proposed_dimension = str(canonical_args.get("dimension") or "").strip().lower()
        medical_exam_args = _project_medical_exam_query_to_turn(turn_text)
        if _health_read_cancelled_by_user(turn_text):
            return _decision(
                "block",
                "health_query_cancelled_by_user",
                tool_name,
                canonical_args,
            )
        if medical_exam_args is None and _UNSUPPORTED_CALENDAR_QUERY_WINDOW_RE.search(
            _query_scope_text(turn_text)
        ):
            return _decision(
                "block",
                "health_query_calendar_window_unsupported",
                tool_name,
                canonical_args,
            )
        if _query_contains_unresolved_reference(turn_text):
            return _decision(
                "block",
                "health_query_semantics_unresolved",
                tool_name,
                canonical_args,
            )
        if illness_read_has_unowned_subject(_query_scope_text(turn_text)):
            return _decision(
                "block",
                "health_query_subject_not_current_user",
                tool_name,
                canonical_args,
            )
        if _is_non_read_health_observation(turn_text):
            return _decision(
                "block",
                "health_query_not_requested",
                tool_name,
                canonical_args,
            )
        if medical_exam_args is not None and _has_explicit_read_request(turn_text):
            return _decision(
                "allow",
                "health_query_projected_to_turn_semantics",
                tool_name,
                medical_exam_args,
            )
        known_illness_entities = _illness_targets(turn_text)
        illness_query_entities = _illness_query_entities(turn_text)
        has_safe_illness_entity = bool(
            len(illness_query_entities) == 1
            and _is_explicit_illness_query_entity(illness_query_entities[0])
        )
        known_non_illness_dimension = _query_entities_known_dimension(
            illness_query_entities
        )
        if has_safe_illness_entity:
            known_non_illness_dimension = None
        if known_non_illness_dimension is None and (
            not illness_query_entities
            or (
                re.search(r"(?:上传|导入)", turn_text)
                and re.search(r"(?:报告|检查|体检|影像|化验)", turn_text)
            )
        ):
            known_non_illness_dimension = _query_text_known_dimension(turn_text)
        illness_query_args = (
            _project_illness_query_to_turn(turn_text)
            if known_non_illness_dimension is None
            else None
        )
        proposed_semantic_dimension = _semantic_query_dimension(proposed_dimension)
        if (
            _history_query_has_multiple_scopes(turn_text)
            or len(illness_query_entities) > 1
        ):
            return _decision(
                "block",
                "illness_query_entity_requires_clarification",
                tool_name,
                canonical_args,
            )
        if known_non_illness_dimension is not None:
            if proposed_semantic_dimension != _semantic_query_dimension(
                known_non_illness_dimension
            ) and _query_scope_text(turn_text) == _normalize_query_text(turn_text):
                return _decision(
                    "block",
                    "health_query_dimension_conflict",
                    tool_name,
                    canonical_args,
                )
            projected_args = _project_known_dimension_query_args(
                turn_text,
                illness_query_entities,
                known_non_illness_dimension,
            )
            if projected_args is None:
                return _decision(
                    "block",
                    "health_query_semantics_unresolved",
                    tool_name,
                    canonical_args,
                )
            return _decision(
                "allow",
                "health_query_projected_to_turn_semantics",
                tool_name,
                projected_args,
            )
        elif illness_query_args is not None and (
            bool(known_illness_entities)
            or has_safe_illness_entity
            or proposed_dimension == "illness"
            or _is_registered_illness_acronym(illness_query_args.get("keyword"))
        ):
            return _decision(
                "allow",
                "illness_query_projected_to_turn_semantics",
                tool_name,
                illness_query_args,
            )
        elif known_illness_entities or proposed_dimension == "illness":
            return _decision(
                "block",
                "illness_query_entity_requires_clarification",
                tool_name,
                canonical_args,
            )
        elif illness_query_entities:
            return _decision(
                "block",
                "health_query_dimension_conflict",
                tool_name,
                canonical_args,
            )
        return _decision(
            "block",
            "health_query_semantics_unresolved",
            tool_name,
            canonical_args,
        )

    if tool_name == "health_query_batch":
        turn_text = snapshot.envelope.text
        normalized_plan = _normalize_batch_query_plan(args)
        if _health_read_cancelled_by_user(turn_text):
            return _decision(
                "block",
                "health_query_cancelled_by_user",
                tool_name,
                normalized_plan,
            )
        if _project_medical_exam_query_to_turn(
            turn_text
        ) is None and _UNSUPPORTED_CALENDAR_QUERY_WINDOW_RE.search(
            _query_scope_text(turn_text)
        ):
            return _decision(
                "block",
                "health_query_calendar_window_unsupported",
                tool_name,
                normalized_plan,
            )
        if _query_contains_unresolved_reference(turn_text):
            return _decision(
                "block",
                "health_query_semantics_unresolved",
                tool_name,
                normalized_plan,
            )
        if illness_read_has_unowned_subject(_query_scope_text(turn_text)):
            return _decision(
                "block",
                "health_query_subject_not_current_user",
                tool_name,
                normalized_plan,
            )
        if _is_non_read_health_observation(turn_text):
            return _decision(
                "block",
                "health_query_not_requested",
                tool_name,
                normalized_plan,
            )
        query_entities = _illness_query_entities(turn_text)
        if not query_entities:
            return _decision(
                "block",
                "health_query_semantics_unresolved",
                tool_name,
                normalized_plan,
            )
        bound_plan = _batch_query_plan_bound_to_turn(
            turn_text,
            query_entities,
            normalized_plan,
        )
        if bound_plan is None:
            return _decision(
                "block",
                "health_query_dimension_conflict",
                tool_name,
                normalized_plan,
            )
        normalized_plan = bound_plan
        return _decision("allow", "read_only_tool", tool_name, normalized_plan)

    if tool_name in READ_ONLY_TOOLS:
        return _decision("allow", "read_only_tool", tool_name, args)

    if tool_name in SPECIALIST_READ_ONLY_TOOLS:
        return _decision("allow", "specialist_read_only_tool", tool_name, args)

    if (
        snapshot.intent.domain == "aigc_media"
        and tool_name in WRITE_TOOL_NAMES
        and tool_name != "draft_aigc_media"
    ):
        # An explicit AIGC request can create only a confirmation draft. It
        # must never be reinterpreted as consent to write health data merely
        # because the attached image looks like food.
        return _decision(
            "block",
            "aigc_media_turn_disallows_health_write",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name == "record_doctor_feedback":
        clinician_decision = classify_clinician_turn(snapshot.envelope.text)
        explicit_clinician_write = (
            primary == "write"
            and snapshot.intent.domain == "clinical_context"
            and snapshot.intent.operation == "create"
            and snapshot.intent.is_write
            and clinician_decision.authorizes_feedback_write
        )
        if explicit_clinician_write:
            return _decision(
                "allow",
                "explicit_doctor_feedback_write",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            "doctor_feedback_without_explicit_clinician_write",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name == "health_manage":
        operation = str(args.get("operation") or "").strip().lower()
        if operation == "list":
            turn_text = snapshot.envelope.text
            if _health_read_cancelled_by_user(turn_text):
                return _decision(
                    "block",
                    "health_query_cancelled_by_user",
                    tool_name,
                    args,
                )
            mutation_lookup_cancelled = is_explicit_write_cancellation(
                turn_text
            ) or bool(
                re.search(
                    r"(?:先不要|暂不)[^，,。.!！?？;；]{0,16}执行",
                    turn_text,
                )
            )
            internal_mutation_lookup = (
                not mutation_lookup_cancelled
                and not _is_completed_health_mutation_observation(turn_text)
                and (
                    primary == "mutate"
                    or (
                        not _has_explicit_read_request(turn_text)
                        and bool(
                            re.search(
                                r"(?:修改|更新|更正|删除|删掉|移除)(?:一下|下)?(?:记录)?",
                                turn_text,
                            )
                        )
                    )
                )
            )
            guarding_user_read = not internal_mutation_lookup
            if _query_contains_unresolved_reference(turn_text) and (
                guarding_user_read or _has_explicit_read_request(turn_text)
            ):
                return _decision(
                    "block",
                    "health_query_semantics_unresolved",
                    tool_name,
                    args,
                )
            if guarding_user_read and not (
                _has_explicit_read_request(turn_text)
                or primary == "read"
                or _HISTORY_QUERY_QUESTION_RE.search(_query_scope_text(turn_text))
                or re.search(r"[?？]\s*$", turn_text)
            ):
                return _decision(
                    "block",
                    "health_query_not_requested",
                    tool_name,
                    args,
                )
            if (
                guarding_user_read
                and _UNSUPPORTED_CALENDAR_QUERY_WINDOW_RE.search(
                    _query_scope_text(turn_text)
                )
                and _project_medical_exam_query_to_turn(turn_text) is None
            ):
                return _decision(
                    "block",
                    "health_query_calendar_window_unsupported",
                    tool_name,
                    args,
                )
            if guarding_user_read and illness_read_has_unowned_subject(
                _query_scope_text(turn_text)
            ):
                return _decision(
                    "block",
                    "health_query_subject_not_current_user",
                    tool_name,
                    args,
                )
            if guarding_user_read and _is_non_read_health_observation(turn_text):
                return _decision(
                    "block",
                    "health_query_not_requested",
                    tool_name,
                    args,
                )
            if guarding_user_read:
                expected_record_type = _manage_list_turn_record_type(turn_text)
                requested_record_type = canonical_health_manage_record_type(
                    args.get("record_type")
                )
                if (
                    expected_record_type is None
                    or expected_record_type != requested_record_type
                ):
                    return _decision(
                        "block",
                        "health_query_dimension_conflict",
                        tool_name,
                        args,
                    )
            return _decision(
                "allow", "health_manage_list_is_read_only", tool_name, args
            )
        if (
            operation == "delete"
            and not _delete_evidence_authorizes_request(
                _whole_record_delete_evidence(snapshot.envelope.text),
                args,
            )
            and (
                (primary == "mutate" and snapshot.intent.operation == "delete")
                or is_explicit_write_cancellation(snapshot.envelope.text)
            )
        ):
            # Undo/field-removal language may intentionally classify as chat,
            # but a model-proposed whole-record delete must still receive the
            # closed delete-grammar denial. Other intent mismatches retain
            # their more specific policy reasons below.
            return _decision(
                "block",
                "delete_requires_explicit_whole_record_intent",
                tool_name,
                args,
                receipt_required=True,
            )
        if operation in MANAGE_WRITE_OPERATIONS:
            if primary == "mutate" and snapshot.intent.operation == operation:
                if operation == "update":
                    authorized_update = _authorized_health_manage_update_args(
                        snapshot,
                        args,
                    )
                    if authorized_update is None:
                        return _decision(
                            "block",
                            "update_requires_exact_target_evidence",
                            tool_name,
                            args,
                            receipt_required=True,
                        )
                    args = authorized_update
                return _decision(
                    "allow",
                    "explicit_mutation_intent",
                    tool_name,
                    args,
                    receipt_required=True,
                )
            if (
                primary == "mutate"
                and snapshot.intent.operation in MANAGE_WRITE_OPERATIONS
            ):
                return _decision(
                    "block",
                    "manage_operation_mismatch",
                    tool_name,
                    args,
                    receipt_required=True,
                )
            return _decision(
                "block",
                (
                    "ambiguous_intent_requires_clarification"
                    if primary == "unknown"
                    else "manage_write_without_mutate_intent"
                ),
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision("block", "unknown_health_manage_operation", tool_name, args)

    if tool_name == "health_record":
        if health_record_target_authorized:
            return _decision(
                "allow",
                "explicit_create_intent",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            (
                "ambiguous_intent_requires_clarification"
                if primary == "unknown"
                else "write_tool_without_write_intent"
            ),
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name == "user_directive":
        if primary in {"write", "mutate"} and snapshot.intent.is_write:
            return _decision(
                "allow",
                "explicit_user_directive",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            "user_directive_without_write_intent",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name == "intervention_cycle":
        action = str(args.get("action") or "").strip().lower()
        if action in INTERVENTION_WRITE_ACTIONS:
            if primary in {"write", "mutate"}:
                return _decision(
                    "allow",
                    "explicit_intervention_write_intent",
                    tool_name,
                    args,
                    receipt_required=True,
                )
            return _decision(
                "block",
                (
                    "ambiguous_intent_requires_clarification"
                    if primary == "unknown"
                    else "intervention_write_without_mutation_intent"
                ),
                tool_name,
                args,
                receipt_required=True,
            )
        if action in INTERVENTION_READ_ACTIONS:
            return _decision("allow", "intervention_read_only_action", tool_name, args)
        return _decision(
            "block",
            "unknown_intervention_action",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name in {"manage_plan", "upload_genetic_txt", "upload_medical_exam_text"}:
        if tool_name == "manage_plan":
            action = str(args.get("action") or "").strip().lower()
            if action not in MANAGE_PLAN_ACTIONS:
                return _decision(
                    "block",
                    "unknown_manage_plan_action",
                    tool_name,
                    args,
                    receipt_required=True,
                )
        if primary in {"write", "mutate"} and snapshot.intent.is_write:
            return _decision(
                "allow",
                "explicit_write_intent",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            "write_tool_without_write_intent",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name == "draft_aigc_media":
        if (
            primary == "write"
            and snapshot.intent.domain == "aigc_media"
            and snapshot.intent.operation == "create"
        ):
            return _decision(
                "allow",
                "explicit_aigc_media_draft",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            "aigc_media_without_explicit_draft_intent",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name in WRITE_TOOL_NAMES:
        return _decision(
            "block", "unhandled_write_tool", tool_name, args, receipt_required=True
        )

    return _decision("block", "unknown_tool", tool_name, args, receipt_required=True)


def _is_mutating_request(tool_name: str, args: dict[str, Any]) -> bool:
    try:
        return get_tool_spec(tool_name).classify_effect(args) == "write"
    except ToolRegistryError:
        return tool_name in WRITE_TOOL_NAMES


def _decision(
    action: str,
    reason: str,
    tool_name: str,
    args: dict[str, Any],
    *,
    receipt_required: bool = False,
) -> CapabilityDecision:
    normalized_args = dict(args)
    marker = normalized_args.pop(
        _SERVER_AUTHORIZED_HEALTH_RECORD_FIELDS_KEY,
        None,
    )
    if isinstance(marker, _ServerAuthorizedHealthRecordFields):
        raw_data = normalized_args.get("data")
        data = dict(raw_data) if isinstance(raw_data, dict) else {}
        data.update(dict(marker.values))
        normalized_args["data"] = data
    return CapabilityDecision(
        action=action,
        reason=reason,
        normalized_tool_name=tool_name or None,
        normalized_args=normalized_args,
        receipt_required=receipt_required,
    )


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    try:
        return dict(raw or {})
    except (TypeError, ValueError):
        return {}


def normalize_health_record_dispatch_args(
    args: dict[str, Any],
) -> dict[str, Any]:
    """Canonicalize aliases before both policy comparison and dispatch.

    The gateway dispatches ``CapabilityDecision.normalized_args``.  This makes
    the exact payload inspected by the authorization policy the payload later
    consumed by the executor, instead of merely *recognizing* aliases that an
    adapter would ignore.
    """
    normalized = dict(args)
    raw_data = normalized.get("data")
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    record_type = recipe_replay_record_type(normalized)
    if record_type:
        normalized["record_type"] = record_type
    normalized.pop("type", None)
    normalized.pop("kind", None)
    data.pop("record_type", None)

    for canonical_key, aliases in _NUMERIC_DISPATCH_ALIAS_GROUPS.get(record_type, ()):
        _canonicalize_named_field(
            normalized,
            data,
            canonical_key=canonical_key,
            aliases=aliases,
        )

    if record_type == "illness":
        canonical_key = "start_date"
        candidates = (
            data.get("start_date"),
            data.get("record_date"),
            data.get("date"),
            normalized.get("start_date"),
            normalized.get("record_date"),
            normalized.get("date"),
        )
        name = next(
            (
                value
                for value in (
                    data.get("name"),
                    data.get("illness_name"),
                    normalized.get("name"),
                    normalized.get("illness_name"),
                )
                if value not in (None, "", [])
            ),
            None,
        )
        for container in (data, normalized):
            container.pop("name", None)
            container.pop("illness_name", None)
        if name is not None:
            data["name"] = name
        _canonicalize_top_level_fields(
            normalized,
            data,
            ("status", "notes", "severity", "end_date"),
        )
    elif record_type == "symptom":
        canonical_key = "record_date"
        candidates = (
            data.get("record_date"),
            data.get("date"),
            normalized.get("record_date"),
            normalized.get("date"),
        )
        _canonicalize_top_level_fields(
            normalized,
            data,
            ("body_part", "description", "severity", "occurred_at"),
        )
    elif record_type == "reminder":
        candidates = ()
        canonical_key = ""
    else:
        canonical_key = "record_date"
        candidates = (
            data.get("record_date"),
            data.get("date"),
            normalized.get("record_date"),
            normalized.get("date"),
        )
    canonical_date = next(
        (value for value in candidates if value not in (None, "", [])),
        None,
    )
    if canonical_key and canonical_date is not None:
        date_aliases = (
            ("start_date", "record_date", "date")
            if record_type == "illness"
            else ("record_date", "date")
        )
        for container in (data, normalized):
            for alias in date_aliases:
                container.pop(alias, None)
        data[canonical_key] = canonical_date

    if record_type == "medication":
        _canonicalize_named_field(
            normalized,
            data,
            canonical_key="medication_name",
            aliases=("medication_name", "name"),
        )
        _canonicalize_medication_aliases(normalized, data)
    elif record_type == "supplement":
        _canonicalize_named_field(
            normalized,
            data,
            canonical_key="supplement_name",
            aliases=("supplement_name", "name"),
        )
        _canonicalize_top_level_fields(
            normalized,
            data,
            ("dosage", "timing", "category", "description"),
        )

    if isinstance(raw_data, dict) or data:
        normalized["data"] = data
    return normalized


def _canonicalize_top_level_fields(
    args: dict[str, Any],
    data: dict[str, Any],
    keys: tuple[str, ...],
) -> None:
    for key in keys:
        value = data.get(key)
        if value in (None, "", []):
            value = args.get(key)
        args.pop(key, None)
        if value not in (None, "", []):
            data[key] = value


def _canonicalize_named_field(
    args: dict[str, Any],
    data: dict[str, Any],
    *,
    canonical_key: str,
    aliases: tuple[str, ...],
) -> None:
    value = next(
        (
            container.get(alias)
            for container in (data, args)
            for alias in aliases
            if container.get(alias) not in (None, "", [])
        ),
        None,
    )
    for container in (data, args):
        for alias in aliases:
            container.pop(alias, None)
    if value is not None:
        data[canonical_key] = value


_MEDICATION_ACTUAL_VALUE_RE = re.compile(
    r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半])\s*"
    r"(?:粒|片|袋|支|丸|颗|滴|喷|毫升|ml|单位|iu|u)",
    re.IGNORECASE,
)


def _medication_alias_values(
    args: dict[str, Any],
    data: dict[str, Any],
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    actual: list[Any] = []
    strengths: list[Any] = []
    for container in (data, args):
        for key in ("actual_dosage", "dose"):
            value = container.get(key)
            if value not in (None, "", []):
                actual.append(value)
        for key in ("observed_strength", "strength"):
            value = container.get(key)
            if value not in (None, "", []):
                strengths.append(value)

    for container in (data, args):
        legacy = container.get("dosage")
        if legacy in (None, "", []):
            continue
        if _MEDICATION_ACTUAL_VALUE_RE.fullmatch(str(legacy).strip()):
            actual.append(legacy)
        else:
            strengths.append(legacy)
    return tuple(actual), tuple(strengths)


def _canonicalize_medication_aliases(
    args: dict[str, Any],
    data: dict[str, Any],
) -> None:
    actual_values, strength_values = _medication_alias_values(args, data)
    normalized_actual = {
        _normalize_medication_dosage(value)
        for value in actual_values
        if _normalize_medication_dosage(value)
    }
    normalized_strengths = {
        _normalize_medication_dosage(value)
        for value in strength_values
        if _normalize_medication_dosage(value)
    }
    if len(normalized_actual) > 1 or len(normalized_strengths) > 1:
        return
    for container in (data, args):
        for key in (
            "actual_dosage",
            "dose",
            "dosage",
            "observed_strength",
            "strength",
        ):
            container.pop(key, None)
    if actual_values:
        data["actual_dosage"] = actual_values[0]
    if strength_values:
        data["observed_strength"] = strength_values[0]


def medication_dispatch_aliases_conflict(args: dict[str, Any]) -> bool:
    """Return whether model aliases express multiple consumed medication values."""
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    actual_values, strength_values = _medication_alias_values(args, data)
    normalized_actual = {
        _normalize_medication_dosage(value)
        for value in actual_values
        if _normalize_medication_dosage(value)
    }
    normalized_strengths = {
        _normalize_medication_dosage(value)
        for value in strength_values
        if _normalize_medication_dosage(value)
    }
    return len(normalized_actual) > 1 or len(normalized_strengths) > 1


def health_record_dispatch_aliases_conflict(args: dict[str, Any]) -> bool:
    """Reject contradictory aliases before collapsing them to one payload."""
    if medication_dispatch_aliases_conflict(args):
        return True
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    record_type_values = (
        args.get("record_type"),
        args.get("type"),
        args.get("kind"),
        data.get("record_type"),
    )
    if not any(value not in (None, "") for value in record_type_values):
        # Nested ``type``/``kind`` are legacy record-type aliases only when no
        # unambiguous type exists. Several adapters use ``data.type`` as an
        # ordinary selector (for example excretion type).
        record_type_values = (data.get("type"), data.get("kind"))
    record_types = tuple(
        _RECIPE_RECORD_TYPE_ALIASES.get(normalized, normalized)
        for value in record_type_values
        if value not in (None, "")
        if (normalized := str(value).strip().lower())
    )
    if len(set(record_types)) > 1:
        return True
    record_type = record_types[0] if record_types else ""
    for _canonical_key, aliases in _NUMERIC_DISPATCH_ALIAS_GROUPS.get(record_type, ()):
        values = [
            container[key]
            for container in (data, args)
            for key in aliases
            if key in container and container[key] not in (None, "", [])
        ]
        if values and any(not _numbers_match(values[0], value) for value in values[1:]):
            return True
    return False


def recipe_replay_record_type(args: dict[str, Any]) -> str:
    """Return the normalized health_record type used by recipe policy checks."""
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    for value in (
        args.get("record_type"),
        args.get("type"),
        args.get("kind"),
        data.get("record_type"),
        data.get("type"),
        data.get("kind"),
    ):
        if value is not None:
            record_type = str(value).strip().lower()
            return _RECIPE_RECORD_TYPE_ALIASES.get(record_type, record_type)
    return ""


def _health_record_target_status(
    snapshot: TurnSnapshot,
    args: dict[str, Any],
) -> str:
    """Bind one request to one member of the direct authorized target set."""
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.write_intent_scope import authorized_health_record_clauses

    requested_type = recipe_replay_record_type(args)
    if not requested_type:
        return "unresolved"
    if requested_type == "illness":
        normalized_turn = "".join(str(snapshot.envelope.text or "").split()).strip(
            "，,。.!！；;：: "
        )
        explicit_label = SIMPLE_ILLNESS_CREATE_RE.fullmatch(normalized_turn)
        if explicit_label is not None:
            exact_name = simple_illness_target(snapshot.envelope.text)
            if exact_name is None:
                return "mismatch"
            data = args.get("data") if isinstance(args.get("data"), dict) else {}
            requested_name = _effective_argument_value(
                args,
                data,
                data_keys=("name", "illness_name"),
                arg_keys=("name", "illness_name"),
            )
            return (
                "match"
                if _normalize_entity_name(requested_name)
                == _normalize_entity_name(exact_name)
                else "mismatch"
            )
    clauses = authorized_health_record_clauses(snapshot.envelope.text)
    if not clauses:
        return "unauthorized"

    direct_write_seen = False
    matching_type_seen = False
    incomplete_target_seen = False
    default_date = snapshot.context.current_time.date().isoformat()
    for clause in clauses:
        clause_envelope = AgentEnvelope(
            user_id=snapshot.envelope.user_id,
            channel=snapshot.envelope.channel,
            text=clause,
            media=snapshot.envelope.media,
            source_message_id=snapshot.envelope.source_message_id,
            client_capabilities=snapshot.envelope.client_capabilities,
            client_time_context=snapshot.envelope.client_time_context,
            client_turn_id=snapshot.envelope.client_turn_id,
        )
        if (
            len(clauses) == 1
            and "continuation:reminder_schedule" in snapshot.intent.evidence
        ):
            clause_intent = snapshot.intent
        else:
            clause_intent = build_intent_frame(clause_envelope, snapshot.context)
        if (
            not clause_intent.is_write
            or clause_intent.primary not in {"write", "mutate"}
            or clause_intent.operation != "create"
        ):
            continue
        direct_write_seen = True
        clause_goal = compile_goal_spec(
            envelope=clause_envelope,
            context=snapshot.context,
            intent=clause_intent,
        )
        expected_types = _authorized_record_types(
            clause,
            clause_intent.domain,
            str(clause_goal.target_record_type or "").strip().lower(),
        )
        server_authorized = _server_authorized_health_record_fields(args)
        if (
            requested_type == "rhinitis"
            and clause_intent.domain == "symptom"
            and isinstance(server_authorized.get("rhinitis_payload"), dict)
        ):
            expected_types = frozenset((*expected_types, "rhinitis"))
        if (
            not expected_types
            and len(clauses) == 1
            and snapshot.goal is not None
            and any(referent in clause for referent in ("这个", "这条", "它"))
        ):
            contextual_type = (
                str(snapshot.goal.target_record_type or "").strip().lower()
            )
            if contextual_type:
                expected_types = frozenset({contextual_type})
        if requested_type not in expected_types:
            continue
        matching_type_seen = True

        clause_goal_type = str(clause_goal.target_record_type or "").strip().lower()
        expected_values = (
            dict(clause_goal.target_values)
            if requested_type == clause_goal_type
            else {}
        )
        if (
            not expected_values
            and len(clauses) == 1
            and snapshot.goal is not None
            and requested_type
            == str(snapshot.goal.target_record_type or "").strip().lower()
            and any(referent in clause for referent in ("这个", "这条", "它"))
        ):
            expected_values = dict(snapshot.goal.target_values)
        if requested_type == "diet" and clause_goal.target_meal_types:
            expected_values["meal_types"] = clause_goal.target_meal_types
        elif requested_type == "diet" and clause_intent.scope.get("meal_type"):
            expected_values["meal_types"] = (clause_intent.scope["meal_type"],)
        deterministic_values = _deterministic_target_values(
            clause,
            requested_type,
        )
        event_time_source = ""
        if requested_type == "event" and not deterministic_values.get("occurred_clock"):
            event_time_status, event_time_clock, event_time_source = (
                _related_event_time_evidence(
                    clauses,
                    str(deterministic_values.get("title") or ""),
                )
            )
            if event_time_status == "unique":
                deterministic_values["occurred_clock"] = event_time_clock
            elif event_time_status == "ambiguous":
                deterministic_values["event_time_ambiguous"] = True
        if requested_type == "diet" and expected_values.get("food_items"):
            deterministic_values.pop("meal_food_targets", None)
        expected_values.update(deterministic_values)
        if requested_type == "rhinitis" and isinstance(
            server_authorized.get("rhinitis_payload"), dict
        ):
            expected_values["rhinitis_payload"] = dict(
                server_authorized["rhinitis_payload"]
            )
        if (
            requested_type == "reminder"
            and "continuation:reminder_schedule" in clause_intent.evidence
        ):
            expected_values["contextual_continuation"] = True
            server_authorized = _server_authorized_health_record_fields(args)
            if server_authorized.get("reminder_title"):
                expected_values["titles"] = (server_authorized["reminder_title"],)
            if server_authorized.get("reminder_interval_minutes") is not None:
                expected_values["interval_minutes"] = server_authorized[
                    "reminder_interval_minutes"
                ]
            if server_authorized.get("reminder_recurrence"):
                expected_values["recurrence"] = server_authorized["reminder_recurrence"]
        if (
            requested_type == "diet"
            and snapshot.envelope.media
            and any(referent in clause for referent in ("这餐", "这一餐", "这顿"))
        ):
            expected_values["attachment_authorized"] = True
        expected_values["target_date"] = clause_goal.target_date or default_date
        expected_values["default_date"] = default_date
        if requested_type in {"symptom", "event"} and expected_values.get(
            "occurred_clock"
        ):
            target_day = (
                _event_occurrence_date(
                    event_time_source or clause,
                    snapshot.context.current_time.date(),
                )
                if requested_type == "event"
                else date.fromisoformat(expected_values["target_date"])
            )
            hour, minute = (
                int(value)
                for value in str(expected_values["occurred_clock"]).split(":", 1)
            )
            expected_values["canonical_occurred_at"] = (
                snapshot.context.current_time.replace(
                    year=target_day.year,
                    month=target_day.month,
                    day=target_day.day,
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                ).isoformat()
            )
        if not _authorization_target_complete(requested_type, expected_values):
            incomplete_target_seen = True
            continue
        if not _target_values_mismatch(requested_type, expected_values, args):
            return "match"

    if matching_type_seen and incomplete_target_seen:
        return "unresolved"
    if direct_write_seen:
        return "mismatch"
    return "unauthorized"


def _recover_explicit_illness_create_from_generic_memory(
    snapshot: TurnSnapshot,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild one exact illness create when the model chose generic memory.

    The correction is intentionally narrow: the user must own one direct
    ``记录疾病`` clause, that clause must name exactly one illness, and the
    proposed memory object must name the same illness. Quoted, attributed,
    third-party and substituted targets therefore remain blocked.
    """
    if recipe_replay_record_type(args) != "remember":
        return args
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    predicate = str(
        _effective_argument_value(
            args,
            data,
            data_keys=("predicate",),
            arg_keys=("predicate",),
        )
        or ""
    ).strip()
    if predicate not in {"确诊疾病", "疾病诊断", "确诊", "疾病", "疾病史"}:
        return args
    proposed_name = _effective_argument_value(
        args,
        data,
        data_keys=("object_value", "value"),
        arg_keys=("object_value", "value"),
    )

    target_name = simple_illness_target(snapshot.envelope.text)
    if target_name is None:
        return args
    proposed_text = "".join(str(proposed_name or "").split()).casefold()
    target_text = "".join(str(target_name).split()).casefold()
    proposed_matches_target = proposed_text == target_text or bool(
        re.fullmatch(
            rf"{re.escape(target_text)}(?:\([^()（）]{{1,80}}\)|（[^()（）]{{1,80}}）)",
            proposed_text,
        )
    )
    if not proposed_matches_target:
        return args
    return {"record_type": "illness", "data": {"name": target_name}}


def _project_exact_illness_create_from_model_fields(
    snapshot: TurnSnapshot,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Keep only the illness name from one exact name-only create command.

    Qwen can populate optional illness fields with plausible-looking defaults
    even when the user supplied only a disease name.  Those values are health
    facts, so neither persisting them nor using them to reject an otherwise
    exact command is acceptable.  Projection is deliberately limited to a
    single direct ``记录疾病：<name>`` clause whose proposed name matches the
    validated user-owned name.  Richer, substituted, quoted or compound turns
    continue through the normal mismatch checks.
    """
    if recipe_replay_record_type(args) != "illness":
        return args
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    proposed_name = _effective_argument_value(
        args,
        data,
        data_keys=("name", "illness_name"),
        arg_keys=("name", "illness_name"),
    )

    target_name = simple_illness_target(snapshot.envelope.text)
    if target_name is None:
        return args
    if _normalize_entity_name(proposed_name) != _normalize_entity_name(target_name):
        return args
    if _is_registered_illness_acronym(target_name):
        target_name = target_name.upper()
    projected_data = {"name": target_name}
    proposed_status = (
        str(
            _effective_argument_value(
                args,
                data,
                data_keys=("status",),
                arg_keys=("status",),
            )
            or ""
        )
        .strip()
        .lower()
    )
    if proposed_status == "active":
        projected_data["status"] = "active"
    return {"record_type": "illness", "data": projected_data}


def _authorized_record_types(
    clause: str,
    domain: str,
    goal_record_type: str,
) -> frozenset[str]:
    from app.services.write_intent_scope import (
        direct_event_values,
        direct_remember_fact_values,
        direct_supplement_group_values,
    )

    record_types: set[str] = set()
    if goal_record_type:
        record_types.add(goal_record_type)
    if any(term in clause for term in ("提醒", "闹钟")):
        return frozenset({"reminder"})
    if _REMEMBER_FACT_RE.search(clause) or direct_remember_fact_values(clause):
        record_types.add("remember")
    if (
        _EVENT_TARGET_RE.search(clause)
        or direct_event_values(clause)
        or any(
            term in clause
            for term in ("准备开始睡觉", "准备入睡", "开始睡眠", "开始入睡", "上床睡觉")
        )
    ):
        record_types.add("event")
    if direct_supplement_group_values(clause):
        record_types.add("supplement_group")
    if "鼻炎" in clause:
        record_types.add("rhinitis")
    for record_type, terms in _EXPLICIT_RECORD_TYPE_TERMS:
        if any(term in clause for term in terms):
            record_types.add(record_type)
    if "药" in clause and not any(
        term in clause for term in ("补剂", "维生素", "益生菌", "鱼油")
    ):
        record_types.add("medication")
    if any(term in clause for term in _MEDICATION_TARGET_TERMS):
        record_types.add("medication")
    if _looks_like_medication_clause(clause):
        record_types.add("medication")
    illness_targets = _illness_targets(clause)
    if illness_targets and not (
        record_types & {"medication", "supplement"}
        and all(f"{target}药" in clause for target in illness_targets)
    ):
        record_types.add("illness")
    for record_type, terms in _METRIC_RECORD_TYPE_TERMS:
        if any(term in clause for term in terms):
            record_types.add(record_type)
    if any(term in clause for term in _EXERCISE_TARGET_TERMS):
        record_types.add("exercise")
    if domain in _HEALTH_RECORD_DOMAIN_TYPES:
        record_types.add(_HEALTH_RECORD_DOMAIN_TYPES[domain])
    return frozenset(record_types)


def _deterministic_target_values(
    clause: str,
    record_type: str,
) -> dict[str, Any]:
    from app.services.write_intent_scope import (
        direct_event_values,
        direct_remember_fact_values,
        direct_supplement_group_values,
    )

    values: dict[str, Any] = {}
    if record_type == "water" and (matches := tuple(_WATER_TARGET_RE.finditer(clause))):
        match = matches[-1]
        amount = float(match.group("value"))
        if match.group("unit").lower() in {"l", "升"}:
            amount *= 1000
        values["amount_ml"] = amount
    elif record_type == "weight" and (
        matches := tuple(_WEIGHT_TARGET_RE.finditer(clause))
    ):
        match = matches[-1]
        weight = float(match.group("value"))
        if match.group("unit") == "斤":
            weight /= 2
        values["weight"] = weight
    elif record_type == "blood_pressure" and (
        matches := tuple(_BLOOD_PRESSURE_TARGET_RE.finditer(clause))
    ):
        match = matches[-1]
        values["systolic"] = int(match.group("systolic"))
        values["diastolic"] = int(match.group("diastolic"))
    elif record_type == "waist" and (
        matches := tuple(_WAIST_TARGET_RE.finditer(clause))
    ):
        match = matches[-1]
        values["waist_cm"] = float(match.group("value"))
    elif record_type == "illness":
        targets = _illness_targets(clause)
        if targets:
            values["names"] = targets
        if notes := _target_text_after_marker(clause, "备注"):
            values["notes"] = notes
        if any(term in clause for term in ("已痊愈", "痊愈", "已经好了", "已好了")):
            values["status"] = "resolved"
        elif any(term in clause for term in ("好转", "改善中")):
            values["status"] = "improving"
        elif any(term in clause for term in ("发作中", "还没好", "仍未好")):
            values["status"] = "active"
    elif record_type == "diet":
        meal_food_targets = _diet_meal_food_targets(clause)
        if meal_food_targets:
            values["meal_food_targets"] = meal_food_targets
            values["meal_types"] = tuple(meal_food_targets)
    elif record_type == "medication":
        medication_details = _medication_item_details(clause)
        if medication_details:
            values["names"] = tuple(medication_details)
            dosages = {
                name: details["dosage"]
                for name, details in medication_details.items()
                if details.get("dosage")
            }
            if dosages:
                values["dosages"] = dosages
            strengths = {
                name: details["observed_strength"]
                for name, details in medication_details.items()
                if details.get("observed_strength")
            }
            if strengths:
                values["observed_strengths"] = strengths
    elif record_type == "supplement":
        names = _named_item_targets(clause, record_type)
        if names:
            values["names"] = names
        dosage_match = _SUPPLEMENT_DOSE_RE.search(clause)
        if dosage_match is not None:
            values["dosage"] = _canonical_medication_dosage(dosage_match)
        timing = next(
            (
                canonical
                for terms, canonical in (
                    (("晚上", "晚间", "睡前"), "evening"),
                    (("早上", "早晨", "上午"), "morning"),
                    (("中午", "午间"), "noon"),
                )
                if any(term in clause for term in terms)
            ),
            "",
        )
        if timing:
            values["timing"] = timing
    elif record_type == "symptom" and (
        occurred_clock := _normalize_clock_value(clause)
    ):
        values["occurred_clock"] = occurred_clock
    elif record_type == "exercise":
        exercise_types = tuple(
            term for term in _EXERCISE_TARGET_TERMS if term in clause
        )
        if exercise_types:
            values["exercise_types"] = tuple(dict.fromkeys(exercise_types))
        duration_matches = tuple(_EXERCISE_DURATION_RE.finditer(clause))
        if duration_matches:
            duration = float(duration_matches[-1].group("value"))
            if duration_matches[-1].group("unit").lower() in {"小时", "h"}:
                duration *= 60
            values["duration_minutes"] = duration
        if distance_match := _EXERCISE_DISTANCE_RE.search(clause):
            distance = float(distance_match.group("value"))
            if distance_match.group("unit").lower() in {"米", "m"}:
                distance /= 1000
            values["distance"] = distance
        if reps_match := _EXERCISE_REPS_RE.search(clause):
            values["reps"] = int(reps_match.group("value"))
        if sets_match := _EXERCISE_SETS_RE.search(clause):
            values["sets"] = int(sets_match.group("value"))
    elif record_type == "mood" and (match := _MOOD_SCORE_RE.search(clause)):
        values["mood_score"] = int(match.group("value"))
    elif record_type == "mood":
        mood_values = tuple(term for term in _MOOD_TARGET_TERMS if term in clause)
        if mood_values:
            values["mood_values"] = tuple(dict.fromkeys(mood_values))
    elif record_type == "excretion":
        kinds: list[str] = []
        if any(term in clause for term in ("排便", "大便")):
            kinds.append("bowel")
        if "便秘" in clause:
            kinds.append("constipation")
        if "腹泻" in clause:
            kinds.append("diarrhea")
        if kinds:
            values["excretion_types"] = tuple(dict.fromkeys(kinds))
    elif record_type == "sleep":
        clocks = tuple(_CLOCK_RE.finditer(clause))
        if clocks:
            normalized_clocks = tuple(
                _normalize_clock_value(match.group(0)) for match in clocks
            )
            values["bedtime"] = normalized_clocks[0]
            if len(normalized_clocks) > 1:
                values["wake_time"] = normalized_clocks[-1]
        if match := _SLEEP_QUALITY_RE.search(clause):
            values["sleep_quality"] = int(match.group("value"))
        if any(term in clause for term in ("准备开始睡觉", "开始睡觉", "要睡觉")):
            values["sleep_start"] = True
    elif record_type == "goal":
        title = _target_text_after_marker(clause, "目标")
        if title:
            values["titles"] = (title,)
        goal_type = next(
            (
                canonical
                for terms, canonical in (
                    (("饮水", "喝水"), "water"),
                    (("体重", "腰围"), "weight"),
                    (("运动", "锻炼", "训练", "跑步", "步行", "快走"), "exercise"),
                    (("睡眠", "睡觉", "入睡"), "sleep"),
                    (("饮食", "早餐", "午餐", "晚餐"), "diet"),
                    (("补剂", "维生素", "鱼油"), "supplement"),
                    (("户外", "晒太阳"), "outdoor"),
                )
                if any(term in clause for term in terms)
            ),
            "",
        )
        if goal_type:
            values["goal_type"] = goal_type
        goal_period = next(
            (
                canonical
                for terms, canonical in (
                    (("每天", "每日"), "daily"),
                    (("每周", "每星期"), "weekly"),
                    (("每月",), "monthly"),
                    (("每年",), "yearly"),
                )
                if any(term in clause for term in terms)
            ),
            "",
        )
        if goal_period:
            values["goal_period"] = goal_period
        target_match = re.search(
            r"(?:降到|减到|达到|目标值)(?P<value>\d+(?:\.\d+)?)"
            r"(?P<unit>kg|公斤|千克|斤|cm|厘米|%|次|分钟)?",
            clause,
            re.IGNORECASE,
        )
        if target_match is not None:
            values["target_value"] = float(target_match.group("value"))
            if target_match.group("unit"):
                values["target_unit"] = target_match.group("unit").lower()
    elif record_type == "reminder":
        title = _reminder_target_title(clause)
        if title:
            values["titles"] = (title,)
        clocks = tuple(_CLOCK_RE.finditer(clause))
        if clocks:
            values["times"] = tuple(
                _normalize_clock_value(match.group(0)) for match in clocks
            )
        if interval_match := _REMINDER_INTERVAL_RE.search(clause):
            interval = float(interval_match.group("value"))
            if interval_match.group("unit").lower() in {"小时", "h"}:
                interval *= 60
            values["interval_minutes"] = _canonical_numeric_value(interval)
        if any(term in clause for term in ("每天", "每日")):
            values["recurrence"] = "daily"
    elif record_type == "supplement_group":
        if direct_values := direct_supplement_group_values(clause):
            return direct_values
        timing = next(
            (
                canonical
                for terms, canonical in (
                    (("睡前", "临睡"), "bedtime"),
                    (("晚上", "晚间"), "evening"),
                    (("中午", "午间"), "noon"),
                    (("早上", "早晨", "上午"), "morning"),
                )
                if any(term in clause for term in terms)
            ),
            "",
        )
        if timing:
            values["timing"] = timing
    elif record_type == "remember":
        if direct_values := direct_remember_fact_values(clause):
            return direct_values
        if remember_match := _REMEMBER_FACT_RE.search(clause):
            values["predicate"] = remember_match.group("predicate")
            values["object_value"] = remember_match.group("value").strip(".!！")
    elif record_type == "event":
        if direct_values := direct_event_values(clause):
            values.update(direct_values)
        if event_match := _EVENT_TARGET_RE.search(clause):
            values["title"] = event_match.group("title").strip()
        elif any(
            term in clause
            for term in ("准备开始睡觉", "准备入睡", "开始睡眠", "开始入睡", "上床睡觉")
        ):
            values["title"] = "准备开始睡觉"
        event_clock_count = _clock_match_count(clause)
        if event_clock_count == 1 and (
            occurred_clock := _normalize_clock_value(clause)
        ):
            values["occurred_clock"] = occurred_clock
        elif event_clock_count > 1:
            values["event_time_ambiguous"] = True
        elif "刚才" in clause or "刚刚" in clause:
            values["occurred_at"] = "刚才"
    if record_type in {"illness", "symptom"} and (
        severity_match := _SEVERITY_TARGET_RE.search(clause)
    ):
        values["severity"] = int(severity_match.group("value"))
    return values


def _related_event_time_evidence(
    clauses: tuple[str, ...],
    expected_title: str,
) -> tuple[str, str, str]:
    """Bind one arrival clock to the matching event title across clauses."""
    normalized_title = _normalize_entity_name(expected_title)
    if not normalized_title:
        return "none", "", ""
    candidates: list[tuple[str, str]] = []
    for clause in clauses:
        arrival = _EVENT_ARRIVAL_FACT_RE.fullmatch(clause)
        if arrival is None:
            continue
        place = arrival.group("place").strip().removesuffix("了")
        if _normalize_entity_name(f"到达{place}") != normalized_title:
            continue
        clock_count = _clock_match_count(clause)
        if clock_count > 1:
            return "ambiguous", "", clause
        clock = _unique_clock_value(clause)
        if clock:
            candidates.append((clock, clause))
    unique = tuple(dict.fromkeys(candidates))
    if len(unique) == 1:
        return "unique", unique[0][0], unique[0][1]
    if len(unique) > 1:
        return "ambiguous", "", ""
    return "none", "", ""


def _target_text_after_marker(clause: str, marker: str) -> str:
    marker_position = clause.rfind(marker)
    if marker_position < 0:
        return ""
    value = clause[marker_position + len(marker) :]
    return value.strip("是为：:，,。.!！；;的 ")


def _target_text_before_marker(clause: str, marker: str) -> str:
    marker_position = clause.rfind(marker)
    if marker_position < 0:
        return ""
    value = clause[:marker_position]
    value = re.sub(
        r"^(?:请|帮我|替我|为我|给我|设置|创建|新增|记录|每天|每日)+",
        "",
        value,
    )
    value = _CLOCK_RE.sub("", value)
    value = re.sub(
        r"^(?:从)?(?:今天|今日|明天|明日|后天)(?:开始|起)?",
        "",
        value,
    )
    value = re.sub(r"^(?:从)?(?:到|至)?(?:每天|每日)?", "", value)
    return value.strip("是为：:，,。.!！；;的 ")


def _reminder_target_title(clause: str) -> str:
    title = _target_text_before_marker(clause, "提醒")
    if title:
        return title
    title = _target_text_after_marker(clause, "提醒")
    title = re.sub(r"^(?:一下)?(?:我|自己)", "", title)
    return title.strip("是为：:，,。.!！；;的 ")


def _diet_meal_food_targets(clause: str) -> dict[str, str]:
    matches: list[tuple[int, int, str]] = []
    for alias, meal_type in _MEAL_TYPE_ALIASES.items():
        if not re.search(r"[\u4e00-\u9fff]", alias):
            continue
        start = clause.find(alias)
        if start >= 0:
            matches.append((start, start + len(alias), meal_type))
    matches.sort()
    targets: dict[str, str] = {}
    for index, (_start, end, meal_type) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(clause)
        food = clause[end:next_start]
        food = food.lstrip("，,：: ")
        food = re.sub(r"^(?:我)?(?:吃了|吃的是|吃|有|是)?", "", food)
        food = re.sub(
            r"(?:然后|再)?(?:请|帮我|替我|为我)?"
            r"(?:记录|记下|保存|录入|写入|打卡)(?:一下)?$",
            "",
            food,
        )
        food = food.strip("和与的了，,。.!！；;：: ")
        if food and food not in {"饮食", "一餐", "饭", "食物"}:
            targets[meal_type] = food[:1000]
    return targets


def _named_item_targets(clause: str, record_type: str) -> tuple[str, ...]:
    if record_type == "medication":
        return tuple(_medication_item_targets(clause))
    action_matches = tuple(_WRITE_TARGET_ACTION_RE.finditer(clause))
    candidate = clause[action_matches[-1].end() :] if action_matches else clause
    candidate = re.sub(
        r"^(?:(?:一下|一条|一个|我的|我|今天|今日|已经|刚才|刚刚|"
        r"吃了|服了|服用(?:了)?|用了))+",
        "",
        candidate,
    )
    candidate = re.split(r"(?:，|,|然后|并且|再)", candidate, maxsplit=1)[0]
    if record_type == "supplement":
        candidate = _SUPPLEMENT_DOSE_RE.sub("", candidate)
        candidate = _SUPPLEMENT_TIMING_RE.sub("", candidate)
        candidate = re.sub(r"(?:吃|服用)$", "", candidate)
    candidate = candidate.strip("的了，,。.!！；;：: ")
    if candidate:
        return (candidate,)
    if record_type == "supplement":
        known = tuple(term for term in _SUPPLEMENT_TARGET_TERMS if term in clause)
        return tuple(dict.fromkeys(known))
    return ()


def _looks_like_medication_clause(clause: str) -> bool:
    from app.services.drug_lexicon import contains_medication_reference

    if contains_medication_reference(clause):
        return True
    return any(
        _MEDICATION_NAME_SUFFIX_RE.search(name)
        for name in _medication_item_targets(clause)
    )


def _medication_item_targets(clause: str) -> dict[str, str]:
    return {
        name: details.get("dosage", "")
        for name, details in _medication_item_details(clause).items()
    }


def _medication_item_details(clause: str) -> dict[str, dict[str, str]]:
    action_matches = tuple(_WRITE_TARGET_ACTION_RE.finditer(clause))
    candidate = clause[action_matches[-1].end() :] if action_matches else clause
    for _ in range(12):
        stripped = re.sub(
            r"^(?:一下|一条|一个|我的|我|今天|今日|已经|刚才|刚刚|"
            r"吃了|吃的|服了|服用(?:了|的)?|用了|的)",
            "",
            candidate,
        )
        if stripped == candidate:
            break
        candidate = stripped
    candidate = re.split(r"(?:然后|并且|再)", candidate, maxsplit=1)[0]
    targets: dict[str, dict[str, str]] = {}
    for raw_item in re.split(r"[、]|(?:和|与|及)", candidate):
        item = raw_item.strip("的了，,。.!！；;：: ")
        if not item:
            continue
        strength_matches = tuple(_MEDICATION_STRENGTH_RE.finditer(item))
        explicit_strength = (
            _canonical_medication_dosage(strength_matches[-1])
            if strength_matches
            else ""
        )
        item_without_strength = _MEDICATION_STRENGTH_RE.sub("", item)
        dose_matches = tuple(_MEDICATION_DOSE_RE.finditer(item_without_strength))
        count_matches = tuple(
            match
            for match in dose_matches
            if match.group("unit").lower() in {"片", "粒", "丸", "袋", "支"}
        )
        mass_matches = tuple(
            match for match in dose_matches if match not in count_matches
        )
        dosage_match = (
            count_matches[0]
            if count_matches
            else (dose_matches[0] if dose_matches else None)
        )
        dosage = _canonical_medication_dosage(dosage_match) if dosage_match else ""
        observed_strength = explicit_strength or (
            _canonical_medication_dosage(mass_matches[0])
            if count_matches and mass_matches
            else ""
        )
        name = _MEDICATION_DOSE_RE.sub("", item_without_strength)
        name = re.sub(r"^(?:我)?(?:吃了|吃的|服了|服用(?:了|的)?|用了)", "", name)
        name = name.strip("的了，,。.!！；;：: ")
        if name and name not in {"药", "药物", "这次药", "那次药"}:
            targets[name] = {
                "dosage": dosage,
                "observed_strength": observed_strength,
            }
    return targets


def _canonical_medication_dosage(match: re.Match[str]) -> str:
    value = match.group("value")
    value = _CHINESE_DOSE_NUMBERS.get(value, value)
    unit = match.group("unit").lower()
    unit_aliases = {
        "毫克": "mg",
        "克": "g",
        "毫升": "ml",
        "μg": "mcg",
        "ug": "mcg",
    }
    return f"{value}{unit_aliases.get(unit, unit)}"


def _illness_targets(clause: str) -> tuple[str, ...]:
    explicit_create_name = simple_illness_target(clause)
    normalized_clause = "".join(str(clause or "").split()).strip("，,。.!！；;：: ")
    if SIMPLE_ILLNESS_CREATE_RE.fullmatch(normalized_clause) is not None:
        return (explicit_create_name,) if explicit_create_name is not None else ()

    known = tuple(
        term
        for term in _ILLNESS_TARGET_TERMS
        if term in clause and f"{term}药" not in clause
    )
    if known:
        return tuple(dict.fromkeys(known))

    action_matches = tuple(_WRITE_TARGET_ACTION_RE.finditer(clause))
    if not action_matches:
        return ()

    candidate = ""
    if action_matches:
        action = action_matches[-1]
        candidate = clause[action.end() :]
        candidate = re.sub(
            r"^(?:一下|一条|一个|我的|我|今天|今日|昨天|昨日|以前的|既往|疾病)",
            "",
            candidate,
        )
        candidate = re.split(
            r"(?:发作|开始|起病)?(?:日期|时间)(?:是|为)|然后|再分析|再告诉",
            candidate,
            maxsplit=1,
        )[0]
        candidate = candidate.removesuffix("下来")
    if not candidate and action_matches:
        before = clause[: action_matches[-1].start()]
        match = re.search(r"(?:把|将)(?P<target>.+)$", before)
        if match is not None:
            candidate = match.group("target")
    candidate = candidate.strip("的了，,。.!！；;：: ")
    if not candidate or candidate in {"疾病", "不适", "症状", "健康数据", "数据"}:
        return ()
    parts = tuple(
        part.strip() for part in re.split(r"[、/]|(?:和|与)", candidate) if part.strip()
    )
    if explicit_create_name is not None and len(parts) == 1:
        return (explicit_create_name,)
    validated = tuple(simple_illness_target(f"记录疾病：{part}") for part in parts)
    if not validated or any(value is None for value in validated):
        return ()
    return tuple(dict.fromkeys(value for value in validated if value is not None))


def _authorization_target_complete(
    record_type: str,
    expected: dict[str, Any],
) -> bool:
    required = {
        "water": ("amount_ml",),
        "weight": ("weight",),
        "blood_pressure": ("systolic", "diastolic"),
        "waist": ("waist_cm",),
        "illness": ("names",),
        "diet": ("meal_types", "food_items"),
        "symptom": ("body_part", "description"),
        "medication": ("names",),
        "supplement": ("names",),
        "exercise": ("exercise_types",),
        "mood": ("mood_score",),
        "excretion": ("excretion_types",),
        "goal": ("titles", "goal_type", "goal_period"),
        "supplement_group": ("timing",),
        "remember": ("predicate", "object_value"),
        "event": ("title",),
        "rhinitis": ("rhinitis_payload",),
    }
    if record_type == "diet" and expected.get("meal_food_targets"):
        return True
    if record_type == "diet" and expected.get("attachment_authorized"):
        return True
    if record_type == "sleep" and (
        expected.get("sleep_start")
        or (
            expected.get("bedtime")
            and expected.get("wake_time")
            and expected.get("sleep_quality") is not None
        )
    ):
        return True
    if record_type == "reminder":
        # A continuation still needs a server-recovered target from prior
        # context; the model cannot supply a new title in a time-only reply.
        has_title = bool(expected.get("titles"))
        times = tuple(expected.get("times") or ())
        return (
            has_title
            and bool(times)
            and (len(times) < 2 or expected.get("interval_minutes") is not None)
        )
    if record_type == "event" and expected.get("event_time_ambiguous"):
        return False
    fields = required.get(record_type)
    if fields is None:
        return False
    return all(expected.get(field) not in (None, "", (), []) for field in fields)


def _target_values_mismatch(
    record_type: str,
    expected: dict[str, Any],
    args: dict[str, Any],
) -> bool:
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    if record_type == "diet":
        requested_meal = _MEAL_TYPE_ALIASES.get(
            str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("meal_type",),
                    arg_keys=("meal_type",),
                )
                or ""
            )
            .strip()
            .lower(),
            "",
        )
        if expected.get("meal_types"):
            allowed_meals = {
                _MEAL_TYPE_ALIASES.get(
                    str(value).strip().lower(), str(value).strip().lower()
                )
                for value in expected["meal_types"]
            }
            if not requested_meal or requested_meal not in allowed_meals:
                return True
        elif expected.get("attachment_authorized") and not requested_meal:
            return True
        requested_food = _effective_argument_value(
            args,
            data,
            data_keys=("food_items",),
            arg_keys=("food_items",),
        )
        if expected.get("attachment_authorized"):
            if not str(requested_food or "").strip():
                return True
        else:
            meal_food_targets = expected.get("meal_food_targets") or {}
            expected_food = meal_food_targets.get(
                requested_meal,
                expected.get("food_items"),
            )
            if not _food_targets_match(expected_food, requested_food):
                return True

    numeric_keys = {
        "water": (
            ("amount", "amount_ml"),
            ("amount", "amount_ml"),
            expected.get("amount_ml"),
        ),
        "weight": (
            ("weight", "value", "weight_kg"),
            ("weight", "value", "weight_kg", "体重"),
            expected.get("weight"),
        ),
        "blood_pressure": (
            ("systolic",),
            ("systolic",),
            expected.get("systolic"),
        ),
        "waist": (
            ("waist_cm", "waist", "value", "腰围"),
            ("waist_cm", "waist", "value", "腰围"),
            expected.get("waist_cm"),
        ),
    }
    if record_type in numeric_keys:
        data_keys, arg_keys, expected_number = numeric_keys[record_type]
        requested_number = _effective_argument_value(
            args,
            data,
            data_keys=data_keys,
            arg_keys=arg_keys,
        )
        if expected_number is not None and (
            requested_number is None
            or not _numbers_match(expected_number, requested_number)
        ):
            return True
    if record_type == "blood_pressure" and expected.get("diastolic") is not None:
        requested_diastolic = _effective_argument_value(
            args,
            data,
            data_keys=("diastolic",),
            arg_keys=("diastolic",),
        )
        if requested_diastolic is None or not _numbers_match(
            expected["diastolic"],
            requested_diastolic,
        ):
            return True
    if record_type == "illness" and expected.get("names"):
        requested_name = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("name", "illness_name"),
                arg_keys=("name", "illness_name"),
            )
            or ""
        ).strip()
        allowed_names = {_normalize_entity_name(value) for value in expected["names"]}
        if (
            not requested_name
            or _normalize_entity_name(requested_name) not in allowed_names
        ):
            return True
        requested_status = (
            str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("status",),
                    arg_keys=("status",),
                )
                or ""
            )
            .strip()
            .lower()
        )
        expected_status = str(expected.get("status") or "").strip().lower()
        if expected_status:
            if requested_status != expected_status:
                return True
        elif requested_status and requested_status != "active":
            return True
        requested_end_date = _effective_argument_value(
            args,
            data,
            data_keys=("end_date",),
            arg_keys=("end_date",),
        )
        if requested_end_date not in (None, "", []):
            return True
        requested_notes = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("notes",),
                arg_keys=("notes",),
            )
            or ""
        ).strip()
        expected_notes = str(expected.get("notes") or "").strip()
        if expected_notes:
            if _normalize_entity_name(requested_notes) != _normalize_entity_name(
                expected_notes
            ):
                return True
        elif requested_notes:
            return True
    if record_type == "symptom":
        requested_body_part = (
            str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("body_part",),
                    arg_keys=("body_part",),
                )
                or ""
            )
            .strip()
            .lower()
        )
        requested_description = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("description",),
                arg_keys=("description",),
            )
            or ""
        ).strip()
        if requested_body_part != str(expected.get("body_part") or "").strip().lower():
            return True
        if not requested_description:
            return True
        expected_description = _normalize_entity_name(expected.get("description"))
        normalized_description = _normalize_entity_name(requested_description)
        if normalized_description not in expected_description and (
            expected_description not in normalized_description
        ):
            return True
        canonical_occurred_at = str(expected.get("canonical_occurred_at") or "").strip()
        if canonical_occurred_at:
            requested_occurred_at = _effective_argument_value(
                args,
                data,
                data_keys=("occurred_at",),
                arg_keys=("occurred_at",),
            )
            if _normalize_clock_value(requested_occurred_at) != str(
                expected.get("occurred_clock") or ""
            ):
                return True
            data.pop("record_date", None)
            data["occurred_at"] = canonical_occurred_at
        else:
            data.pop("occurred_at", None)
            data["record_date"] = str(expected.get("target_date") or "")
        args.pop("occurred_at", None)
        args.pop("record_date", None)
        args.pop("date", None)
    if record_type in {"illness", "symptom"}:
        requested_severity = _effective_argument_value(
            args,
            data,
            data_keys=("severity",),
            arg_keys=("severity",),
        )
        if expected.get("severity") is not None:
            if requested_severity is None or not _numbers_match(
                expected["severity"],
                requested_severity,
            ):
                return True
        elif requested_severity not in (None, "", []):
            # Severity has no safe semantic default.  The model frequently
            # fills the optional schema field with a plausible midpoint even
            # when the user never supplied one.  Project that untrusted field
            # out of the dispatch payload instead of either persisting an
            # invented health fact or rejecting an otherwise exact write.
            data.pop("severity", None)
            args.pop("severity", None)
    if record_type in {"medication", "supplement"}:
        if record_type == "medication":
            name_keys = ("medication_name", "name")
        else:
            name_keys = ("supplement_name", "name")
        requested_name = str(
            _effective_argument_value(
                args,
                data,
                data_keys=name_keys,
                arg_keys=name_keys,
            )
            or ""
        )
        allowed_names = {
            _normalize_entity_name(value) for value in expected.get("names", ())
        }
        normalized_requested_name = _normalize_entity_name(requested_name)
        if normalized_requested_name not in allowed_names:
            return True
        if record_type == "medication":
            expected_dosages = {
                _normalize_entity_name(name): _normalize_medication_dosage(dosage)
                for name, dosage in (expected.get("dosages") or {}).items()
            }
            dosage_values = _medication_actual_dosage_values(args, data)
            normalized_dosage_values = {
                _normalize_medication_dosage(value)
                for value in dosage_values
                if _normalize_medication_dosage(value)
            }
            if len(normalized_dosage_values) > 1:
                return True
            requested_dosage = dosage_values[0] if dosage_values else None
            normalized_requested_dosage = _normalize_medication_dosage(requested_dosage)
            expected_dosage = expected_dosages.get(normalized_requested_name, "")
            if expected_dosage:
                if normalized_requested_dosage != expected_dosage:
                    return True
            elif normalized_requested_dosage:
                return True
            expected_strengths = {
                _normalize_entity_name(name): _normalize_medication_dosage(strength)
                for name, strength in (expected.get("observed_strengths") or {}).items()
            }
            strength_values = _medication_observed_strength_values(args, data)
            normalized_strength_values = {
                _normalize_medication_dosage(value)
                for value in strength_values
                if _normalize_medication_dosage(value)
            }
            if len(normalized_strength_values) > 1:
                return True
            requested_strength = strength_values[0] if strength_values else None
            normalized_requested_strength = _normalize_medication_dosage(
                requested_strength
            )
            expected_strength = expected_strengths.get(
                normalized_requested_name,
                "",
            )
            if expected_strength:
                if normalized_requested_strength != expected_strength:
                    return True
            elif normalized_requested_strength:
                return True
        else:
            for field in ("dosage", "timing", "category", "description"):
                requested_value = _effective_argument_value(
                    args,
                    data,
                    data_keys=(field,),
                    arg_keys=(field,),
                )
                expected_value = expected.get(field)
                if expected_value not in (None, "", []):
                    if field == "dosage":
                        matches = _normalize_medication_dosage(
                            requested_value
                        ) == _normalize_medication_dosage(expected_value)
                    else:
                        matches = _normalize_entity_name(
                            requested_value
                        ) == _normalize_entity_name(expected_value)
                    if not matches:
                        return True
                    data[field] = expected_value
                    args.pop(field, None)
                else:
                    data.pop(field, None)
                    args.pop(field, None)
    if record_type == "exercise":
        requested_exercise = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("exercise_type", "type", "name"),
                arg_keys=("exercise_type", "type", "name"),
            )
            or ""
        )
        allowed_exercises = {
            _normalize_entity_name(value)
            for value in expected.get("exercise_types", ())
        }
        if _normalize_entity_name(requested_exercise) not in allowed_exercises:
            return True
        if expected.get("duration_minutes") is not None:
            requested_duration = _effective_argument_value(
                args,
                data,
                data_keys=("duration", "duration_minutes", "minutes", "分钟"),
                arg_keys=("duration", "duration_minutes", "minutes", "分钟"),
            )
            if requested_duration is None or not _numbers_match(
                expected["duration_minutes"],
                requested_duration,
            ):
                return True
        for field in ("distance", "reps", "sets"):
            if expected.get(field) is None:
                continue
            requested_value = _effective_argument_value(
                args,
                data,
                data_keys=(field,),
                arg_keys=(field,),
            )
            if requested_value is None or not _numbers_match(
                expected[field],
                requested_value,
            ):
                return True
    if record_type == "mood":
        if expected.get("mood_score") is not None:
            requested_score = _effective_argument_value(
                args,
                data,
                data_keys=("mood_score", "score"),
                arg_keys=("mood_score", "score"),
            )
            if requested_score is None or not _numbers_match(
                expected["mood_score"],
                requested_score,
            ):
                return True
        elif expected.get("mood_values"):
            requested_mood = (
                str(
                    _effective_argument_value(
                        args,
                        data,
                        data_keys=("mood", "status", "mood_label"),
                        arg_keys=("mood", "status", "mood_label"),
                    )
                    or ""
                )
                .strip()
                .lower()
            )
            allowed_moods = {
                _MOOD_TARGET_ALIASES.get(str(value).strip().lower(), "")
                for value in expected["mood_values"]
            }
            if _MOOD_TARGET_ALIASES.get(requested_mood, "") not in allowed_moods:
                return True
    if record_type == "excretion":
        requested_type = (
            str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("type", "excretion_type"),
                    arg_keys=("type", "excretion_type"),
                )
                or ""
            )
            .strip()
            .lower()
        )
        allowed_types = {
            _EXCRETION_TARGET_ALIASES.get(str(value).strip().lower(), "")
            for value in expected.get("excretion_types", ())
        }
        if _EXCRETION_TARGET_ALIASES.get(requested_type, "") not in allowed_types:
            return True
    if record_type == "sleep":
        if expected.get("bedtime"):
            requested_bedtime = _effective_argument_value(
                args,
                data,
                data_keys=("bedtime",),
                arg_keys=("bedtime",),
            )
            if _normalize_clock_value(requested_bedtime) != expected["bedtime"]:
                return True
        if expected.get("wake_time"):
            requested_wake_time = _effective_argument_value(
                args,
                data,
                data_keys=("wake_time",),
                arg_keys=("wake_time",),
            )
            if _normalize_clock_value(requested_wake_time) != expected["wake_time"]:
                return True
        if expected.get("sleep_quality") is not None:
            requested_quality = _effective_argument_value(
                args,
                data,
                data_keys=("sleep_quality", "quality"),
                arg_keys=("sleep_quality", "quality"),
            )
            if requested_quality is None or not _numbers_match(
                expected["sleep_quality"],
                requested_quality,
            ):
                return True
    if record_type == "goal":
        requested_title = _effective_argument_value(
            args,
            data,
            data_keys=("title",),
            arg_keys=("title",),
        )
        allowed_titles = {
            _normalize_entity_name(value) for value in expected.get("titles", ())
        }
        if _normalize_entity_name(requested_title) not in allowed_titles:
            return True
        for field in ("goal_type", "goal_period"):
            requested_value = (
                str(
                    _effective_argument_value(
                        args,
                        data,
                        data_keys=(field,),
                        arg_keys=(field,),
                    )
                    or ""
                )
                .strip()
                .lower()
            )
            if requested_value != str(expected.get(field) or "").strip().lower():
                return True
        if expected.get("target_value") is not None:
            requested_target = _effective_argument_value(
                args,
                data,
                data_keys=("target_value",),
                arg_keys=("target_value",),
            )
            if requested_target is None or not _numbers_match(
                expected["target_value"],
                requested_target,
            ):
                return True
        if expected.get("target_unit"):
            requested_unit = _effective_argument_value(
                args,
                data,
                data_keys=("target_unit",),
                arg_keys=("target_unit",),
            )
            if _normalize_unit(requested_unit) != _normalize_unit(
                expected["target_unit"]
            ):
                return True
    if record_type == "reminder":
        if expected.get("titles"):
            requested_title = _effective_argument_value(
                args,
                data,
                data_keys=("title",),
                arg_keys=("title",),
            )
            allowed_titles = {
                _normalize_reminder_title(value) for value in expected["titles"]
            }
            if _normalize_reminder_title(requested_title) not in allowed_titles:
                return True
        requested_times = tuple(
            clock
            for clock in (
                _normalize_clock_value(
                    _effective_argument_value(
                        args,
                        data,
                        data_keys=(key,),
                        arg_keys=(key,),
                    )
                )
                for key in ("time", "remind_at", "start_time", "end_time")
            )
            if clock
        )
        if set(requested_times) != set(expected.get("times", ())):
            return True
        if expected.get("recurrence"):
            requested_recurrence = (
                str(
                    _effective_argument_value(
                        args,
                        data,
                        data_keys=("recurrence",),
                        arg_keys=("recurrence",),
                    )
                    or ""
                )
                .strip()
                .lower()
            )
            if requested_recurrence != expected["recurrence"]:
                return True
        if expected.get("interval_minutes") is not None:
            requested_interval = _effective_argument_value(
                args,
                data,
                data_keys=("interval_minutes",),
                arg_keys=("interval_minutes",),
            )
            if requested_interval is None or not _numbers_match(
                expected["interval_minutes"],
                requested_interval,
            ):
                return True
    if record_type == "supplement_group":
        requested_timing = (
            str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("timing",),
                    arg_keys=("timing",),
                )
                or ""
            )
            .strip()
            .lower()
        )
        if requested_timing != expected.get("timing"):
            return True
    if record_type == "remember":
        for field in ("predicate", "object_value"):
            requested_value = _effective_argument_value(
                args,
                data,
                data_keys=(field,),
                arg_keys=(field,),
            )
            if _normalize_entity_name(requested_value) != _normalize_entity_name(
                expected.get(field)
            ):
                return True
    if record_type == "event":
        requested_title = _effective_argument_value(
            args,
            data,
            data_keys=("title", "name", "event"),
            arg_keys=("title", "name", "event"),
        )
        if _normalize_entity_name(requested_title) != _normalize_entity_name(
            expected.get("title")
        ):
            return True
        canonical_occurred_at = str(expected.get("canonical_occurred_at") or "").strip()
        if canonical_occurred_at:
            requested_time = _effective_argument_value(
                args,
                data,
                data_keys=("occurred_at",),
                arg_keys=("occurred_at",),
            )
            if requested_time not in (None, "", []) and (
                _normalize_clock_value(requested_time)
                != str(expected.get("occurred_clock") or "")
            ):
                return True
        elif expected.get("occurred_at"):
            requested_time = _effective_argument_value(
                args,
                data,
                data_keys=("occurred_at",),
                arg_keys=("occurred_at",),
            )
            if requested_time not in (None, "", []) and (
                _normalize_entity_name(requested_time)
                != _normalize_entity_name(expected["occurred_at"])
            ):
                return True
    if record_type == "rhinitis":
        authorized_payload = expected.get("rhinitis_payload")
        if not isinstance(authorized_payload, dict) or data != authorized_payload:
            return True

    skip_default_recurring_date = (
        record_type == "reminder"
        and bool(expected.get("recurrence"))
        and str(expected.get("target_date") or "")
        == str(expected.get("default_date") or "")
    )
    if not skip_default_recurring_date:
        requested_date = _effective_record_date(record_type, args, data)
        effective_date = requested_date or str(expected.get("default_date") or "")
        if str(expected.get("target_date") or "") != effective_date:
            return True
    _project_authorized_dispatch_payload(record_type, expected, args, data)
    return False


def _project_authorized_dispatch_payload(
    record_type: str,
    expected: dict[str, Any],
    args: dict[str, Any],
    data: dict[str, Any],
) -> None:
    """Emit the one payload shape inspected and consumed for this target."""
    server_authorized = _server_authorized_health_record_fields(args)
    numeric_fields = {
        "water": (("amount", "amount_ml"),),
        "weight": (("weight", "weight"),),
        "blood_pressure": (
            ("systolic", "systolic"),
            ("diastolic", "diastolic"),
        ),
        "waist": (("waist_cm", "waist_cm"),),
    }
    if record_type in numeric_fields:
        requested_date = _effective_record_date(record_type, args, data)
        projected = {
            output_key: _canonical_numeric_value(expected[expected_key])
            for output_key, expected_key in numeric_fields[record_type]
        }
        if requested_date:
            projected["record_date"] = str(expected.get("target_date") or "")
        args.clear()
        args.update({"record_type": record_type, "data": projected})
        return

    if record_type == "supplement":
        names = tuple(expected.get("names") or ())
        projected: dict[str, Any] = {}
        if names:
            projected["supplement_name"] = names[0]
        for field in ("dosage", "timing", "category", "description"):
            if expected.get(field) not in (None, "", []):
                projected[field] = expected[field]
        args.clear()
        args.update({"record_type": record_type, "data": projected})
        return

    projected: dict[str, Any] = {}
    target_date = str(expected.get("target_date") or "")
    if record_type == "diet":
        requested_meal = _effective_argument_value(
            args, data, data_keys=("meal_type",), arg_keys=("meal_type",)
        )
        requested_food = _effective_argument_value(
            args, data, data_keys=("food_items",), arg_keys=("food_items",)
        )
        projected = {"meal_type": requested_meal, "food_items": requested_food}
        if server_authorized.get("source") in {
            "agent_text",
            "agent_attachment",
            "contextual_diet_replay",
            "procedure_recipe",
        }:
            projected["source"] = server_authorized["source"]
        for field in ("calories", "protein", "carbs", "fat", "fiber"):
            if server_authorized.get(field) not in (None, "", []):
                projected[field] = server_authorized[field]
        if _effective_record_date(record_type, args, data):
            projected["record_date"] = target_date
    elif record_type == "illness":
        names = tuple(expected.get("names") or ())
        if names:
            projected["name"] = names[0]
        if _effective_record_date(record_type, args, data):
            projected["start_date"] = target_date
        if expected.get("status"):
            projected["status"] = str(expected["status"])
        elif (
            str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("status",),
                    arg_keys=("status",),
                )
                or ""
            )
            .strip()
            .lower()
            == "active"
        ):
            projected["status"] = "active"
        for field in ("severity", "notes"):
            if expected.get(field) not in (None, "", []):
                projected[field] = expected[field]
    elif record_type == "symptom":
        requested_description = _effective_argument_value(
            args,
            data,
            data_keys=("description",),
            arg_keys=("description",),
        )
        projected = {
            "body_part": expected.get("body_part"),
            "description": requested_description,
        }
        if expected.get("canonical_occurred_at"):
            projected["occurred_at"] = expected["canonical_occurred_at"]
        elif target_date:
            projected["record_date"] = target_date
        if expected.get("severity") is not None:
            projected["severity"] = expected["severity"]
    elif record_type == "medication":
        names = tuple(expected.get("names") or ())
        if names:
            name = names[0]
            projected["medication_name"] = name
            dosage = (expected.get("dosages") or {}).get(name)
            strength = (expected.get("observed_strengths") or {}).get(name)
            if dosage:
                projected["actual_dosage"] = dosage
            if strength:
                projected["observed_strength"] = strength
    elif record_type == "exercise":
        exercises = tuple(expected.get("exercise_types") or ())
        if exercises:
            projected["exercise_type"] = exercises[0]
        if expected.get("duration_minutes") is not None:
            projected["duration"] = _canonical_numeric_value(
                expected["duration_minutes"]
            )
        for field in ("distance", "reps", "sets"):
            if expected.get(field) is not None:
                projected[field] = _canonical_numeric_value(expected[field])
        if _effective_record_date(record_type, args, data):
            projected["record_date"] = target_date
    elif record_type == "mood":
        projected["mood_score"] = int(expected["mood_score"])
        if _effective_record_date(record_type, args, data):
            projected["record_date"] = target_date
    elif record_type == "excretion":
        kinds = tuple(expected.get("excretion_types") or ())
        if kinds:
            projected["type"] = _EXCRETION_TARGET_ALIASES.get(kinds[0], kinds[0])
        if _effective_record_date(record_type, args, data):
            projected["record_date"] = target_date
    elif record_type == "sleep":
        if expected.get("sleep_start"):
            projected["title"] = "准备开始睡觉"
        else:
            for field in ("bedtime", "wake_time", "sleep_quality"):
                if expected.get(field) not in (None, "", []):
                    projected[field] = expected[field]
            if _effective_record_date(record_type, args, data):
                projected["record_date"] = target_date
    elif record_type == "goal":
        titles = tuple(expected.get("titles") or ())
        if titles:
            projected["title"] = titles[0]
        for field in ("goal_type", "goal_period", "target_value", "target_unit"):
            if expected.get(field) not in (None, "", []):
                projected[field] = expected[field]
        if target_date:
            projected["start_date"] = target_date
    elif record_type == "reminder":
        titles = tuple(expected.get("titles") or ())
        if titles:
            projected["title"] = titles[0]
        times = tuple(expected.get("times") or ())
        if len(times) == 1:
            projected["time"] = times[0]
        elif len(times) >= 2:
            projected["start_time"] = times[0]
            projected["end_time"] = times[-1]
            projected["interval_minutes"] = expected.get("interval_minutes")
        if expected.get("recurrence"):
            projected["recurrence"] = expected["recurrence"]
    elif record_type == "supplement_group":
        projected["timing"] = expected.get("timing")
    elif record_type == "remember":
        projected = {
            "subject": "用户",
            "predicate": expected.get("predicate"),
            "object_value": expected.get("object_value"),
        }
    elif record_type == "event":
        projected["title"] = expected.get("title")
        if expected.get("canonical_occurred_at"):
            projected["occurred_at"] = expected["canonical_occurred_at"]
        elif expected.get("occurred_at"):
            projected["occurred_at"] = expected["occurred_at"]
    elif record_type == "rhinitis":
        projected = dict(expected.get("rhinitis_payload") or {})

    projected = {
        key: value for key, value in projected.items() if value not in (None, "", [])
    }
    args.clear()
    args.update({"record_type": record_type, "data": projected})


def _canonical_numeric_value(value: Any) -> int | float | Any:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    return int(numeric) if numeric.is_integer() else numeric


def _medication_actual_dosage_values(
    args: dict[str, Any],
    data: dict[str, Any],
) -> tuple[Any, ...]:
    values, _strengths = _medication_alias_values(args, data)
    return values


def _medication_observed_strength_values(
    args: dict[str, Any],
    data: dict[str, Any],
) -> tuple[Any, ...]:
    _actual, values = _medication_alias_values(args, data)
    return values


def _effective_argument_value(
    args: dict[str, Any],
    data: dict[str, Any],
    *,
    data_keys: tuple[str, ...],
    arg_keys: tuple[str, ...],
) -> Any:
    for container, keys in ((data, data_keys), (args, arg_keys)):
        for key in keys:
            if key in container and container[key] is not None:
                return container[key]
    return None


def _effective_record_date(
    record_type: str,
    args: dict[str, Any],
    data: dict[str, Any],
) -> str:
    if record_type == "illness":
        value = _effective_argument_value(
            args,
            data,
            data_keys=("start_date",),
            arg_keys=(),
        )
    elif record_type == "symptom":
        value = _effective_argument_value(
            args,
            data,
            data_keys=("occurred_at", "record_date"),
            arg_keys=(),
        )
    elif record_type == "reminder":
        value = _effective_argument_value(
            args,
            data,
            data_keys=("remind_at",),
            arg_keys=(),
        )
    else:
        value = _effective_argument_value(
            args,
            data,
            data_keys=("record_date",),
            arg_keys=(),
        )
    return str(value or "").strip()[:10]


def _normalize_entity_name(value: Any) -> str:
    return re.sub(r"[\s,，、。.!！;；:：]+", "", str(value or "")).casefold()


def _normalize_medication_dosage(value: Any) -> str:
    text = str(value or "").strip()
    match = _MEDICATION_DOSE_RE.fullmatch(text)
    if match is None:
        return _normalize_entity_name(text)
    return _canonical_medication_dosage(match)


def _parse_small_chinese_number(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if "十" in text:
        left, right = text.split("十", 1)
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    if all(char in digits for char in text):
        return int("".join(str(digits[char]) for char in text))
    return None


def _clock_components(value: Any) -> tuple[int, int] | None:
    text = str(value or "")
    match = _CLOCK_RE.search(text)
    if match is not None:
        hour = int(match.group("hour"))
        minute_text = str(match.group("minute") or "")
        if minute_text == "半":
            minute = 30
        elif minute_text == "一刻":
            minute = 15
        elif minute_text == "三刻":
            minute = 45
        else:
            minute = int(minute_text or 0)
        match_start = match.start()
    else:
        chinese_match = _CHINESE_CLOCK_RE.search(text)
        if chinese_match is None:
            return None
        parsed_hour = _parse_small_chinese_number(chinese_match.group("hour"))
        minute_text = str(chinese_match.group("minute") or "")
        if parsed_hour is None:
            return None
        if minute_text == "半":
            minute = 30
        elif minute_text == "一刻":
            minute = 15
        elif minute_text == "三刻":
            minute = 45
        elif minute_text:
            parsed_minute = _parse_small_chinese_number(minute_text.removesuffix("分"))
            if parsed_minute is None:
                return None
            minute = parsed_minute
        else:
            minute = 0
        hour = parsed_hour
        match_start = chinese_match.start()
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    daypart_prefix = text[max(0, match_start - 8) : match_start]
    night_markers = (
        "晚上",
        "晚间",
        "夜里",
        "夜间",
        "夜晚",
        "半夜",
        "午夜",
        "深夜",
        "夜半",
        "昨晚",
        "今晚",
        "昨夜",
        "今夜",
        "凌晨",
    )
    afternoon_markers = ("下午", "傍晚")
    if any(marker in daypart_prefix for marker in night_markers) and hour == 12:
        hour = 0
    elif 1 <= hour <= 5 and "中午" in daypart_prefix:
        hour += 12
    elif hour < 12 and any(marker in daypart_prefix for marker in afternoon_markers):
        hour += 12
    elif 5 <= hour < 12 and any(marker in daypart_prefix for marker in night_markers):
        hour += 12
    return hour, minute


def _normalize_clock_value(value: Any) -> str:
    components = _clock_components(value)
    if components is None:
        return ""
    hour, minute = components
    return f"{hour:02d}:{minute:02d}"


def _unique_clock_value(value: Any) -> str:
    """Return a clock only when the text contains one unambiguous clock."""
    text = str(value or "")
    matches = tuple(_CLOCK_RE.finditer(text)) + tuple(_CHINESE_CLOCK_RE.finditer(text))
    if len(matches) != 1:
        return ""
    return _normalize_clock_value(text)


def _clock_match_count(value: Any) -> int:
    text = str(value or "")
    return len(tuple(_CLOCK_RE.finditer(text))) + len(
        tuple(_CHINESE_CLOCK_RE.finditer(text))
    )


def _event_occurrence_date(text: str, current_date: date) -> date:
    if "前天" in text:
        return current_date - timedelta(days=2)
    if any(marker in text for marker in ("昨天", "昨日", "昨晚", "昨夜")):
        return current_date - timedelta(days=1)
    return current_date


def _normalize_unit(value: Any) -> str:
    aliases = {
        "厘米": "cm",
        "公斤": "kg",
        "千克": "kg",
    }
    normalized = str(value or "").strip().lower()
    return aliases.get(normalized, normalized)


def _normalize_reminder_title(value: Any) -> str:
    normalized = _normalize_entity_name(value)
    return re.sub(r"(?:提醒|闹钟)$", "", normalized)


def _food_targets_match(expected: Any, requested: Any) -> bool:
    def split_text(value: Any) -> list[str]:
        raw_parts: list[str] = []
        for punct_part in re.split(r"[,，、;；/|+＋]", str(value or "")):
            # Protect lexical compounds, but only protect ``和牛`` when it is
            # itself an item (segment-initial or followed by quantity/end).
            # Thus ``米饭和牛肉`` uses 和 as a conjunction, while
            # ``米饭和和牛200g`` keeps the second 和 inside the Wagyu lexeme.
            wagyu = "\uf8ffWAGYU\uf8ff"
            wafuu = "\uf8ffWAFUU\uf8ff"
            protected = punct_part.replace("和风", wafuu)
            if protected.startswith("和牛"):
                protected = wagyu + protected[2:]
            protected = re.sub(
                r"和牛(?=(?:\d|[一二两三四五六七八九十百半]|$))",
                wagyu,
                protected,
            )
            raw_parts.extend(
                part.replace(wagyu, "和牛").replace(wafuu, "和风")
                for part in re.split(r"(?<=.)[和与及](?=.)", protected)
            )
        return raw_parts

    def parts(value: Any) -> tuple[str, ...]:
        if isinstance(value, (list, tuple)):
            raw_parts = []
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("food_name")
                    quantity = item.get("quantity")
                    unit = item.get("unit")
                    if name and quantity is not None and unit:
                        raw_parts.append(f"{name}{quantity}{unit}")
                    elif name:
                        raw_parts.append(str(name))
                    continue
                raw_parts.extend(split_text(item))
        else:
            raw_parts = split_text(value)
        return tuple(
            sorted(
                _canonical_food_part(part)
                for part in raw_parts
                if _canonical_food_part(part)
            )
        )

    return bool(parts(expected)) and parts(expected) == parts(requested)


def _canonical_food_part(value: Any) -> str:
    part = _normalize_entity_name(value)
    if not part:
        return ""
    quantity = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百半]+)"
    unit = r"(?:毫升|ml|克|g|碗|杯|份|个|只|枚|颗|片|块|根|条)"
    leading = re.fullmatch(
        rf"(?P<number>{quantity})(?P<unit>{unit})(?P<food>.+)",
        part,
        re.IGNORECASE,
    )
    trailing = re.fullmatch(
        rf"(?P<food>.+?)(?P<number>{quantity})(?P<unit>{unit})",
        part,
        re.IGNORECASE,
    )
    match = leading or trailing
    if match is None:
        return part
    unit_aliases = {"只": "个", "枚": "个", "颗": "个"}
    normalized_number = _CHINESE_DOSE_NUMBERS.get(
        match.group("number"),
        match.group("number"),
    )
    return (
        f"{match.group('food')}#{normalized_number}"
        f"{unit_aliases.get(match.group('unit'), match.group('unit'))}"
    ).casefold()


def _numbers_match(expected: Any, requested: Any) -> bool:
    try:
        return abs(float(expected) - float(requested)) < 1e-6
    except (TypeError, ValueError):
        return str(expected).strip() == str(requested).strip()
