"""Structured prompt metadata for health-query tool descriptions.

The registry is public, static provider guidance.  It contains no authority or
user data.  Full and task-scoped descriptions are rendered from the same
entries so editorial formatting changes cannot silently disable projection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class QueryGuideEntry:
    dimensions: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class QueryGuideSection:
    title: str
    entries: tuple[QueryGuideEntry, ...]
    preface: str = ""


_INTRO = "查询用户的健康数据. 根据用户问题选对 dimension 是关键.\n\ndimension 选择指南 (按场景):"

QUERY_GUIDE_SECTIONS = (
    QueryGuideSection("综合判断 / 今天/最近怎么样", (
        QueryGuideEntry(("comprehensive",), "comprehensive — 仅用于用户明确请求的综合多维度查询；不能确定查询目标时先澄清，\n                不得扩大为综合读取，也不能替代用户指定的数据维度。"),
    )),
    QueryGuideSection("睡眠 / 休息", (
        QueryGuideEntry(("sleep",), "sleep         — 睡眠评分, 时长, 深睡/REM 分布 (一般\"近7天睡得好吗\"走这里)"),
        QueryGuideEntry(("spo2",), "spo2          — 夜间血氧逐分钟时间序列 + 平均/最低/ODI 氧减指数 (OSAHS 筛查)\n                用户问“最近一周的睡眠血氧”时查询 sleep + spo2，days=7；服务端冻结日期，\n                返回该窗口逐日观测、来源和覆盖情况，不是最近一晚。遵守返回的限制：\n                未验证睡眠期/连续监测时，不推算 ODI，不把无数据当正常，不确诊。"),
        QueryGuideEntry(("spo2_sleep_correlation",), "spo2_sleep_correlation — 睡眠阶段 (deep/rem/light/awake) × 血氧关联分析"),
    )),
    QueryGuideSection(
        "心率 / 压力 / HRV / 日常活动 — 同源可穿戴 daily",
        (
            QueryGuideEntry(("heart_rate",), "heart_rate    — 心率(静息/平均)历史"),
            QueryGuideEntry(("hrv",), "hrv           — HRV 趋势"),
            QueryGuideEntry(("body_battery",), "body_battery  — 身体电量"),
            QueryGuideEntry(("stress",), "stress        — 压力水平"),
        ),
        "  这一组 (heart_rate / hrv / body_battery / stress / activity) 读同一份归一化\n  可穿戴 daily 数据 (GarminData, 多设备按优先级合并, 与 Twin 同源), 返回最近\n  N 天逐日紧凑摘要 (含数据源标注), 不截断.",
    ),
    QueryGuideSection("运动 — 这里容易选错, 仔细看", (
        QueryGuideEntry(("workout", "exercise"), "workout / exercise — 同义, Garmin 同步的**结构化运动** (跑步/骑行/游泳/HIIT),\n                     有距离/配速/心率区间/卡路里.\n                     用户问\"近7天的跑步\"/\"最近30天跑量\"选这个."),
        QueryGuideEntry(("manual_exercise",), "manual_exercise    — 用户**手动录入**的简单锻炼 (俯卧撑 20 个 / 瑜伽 30 分钟 / 拉伸).\n                     只有计次/时长, 没有 GPS 数据.\n                     用户问\"近7天做了多少俯卧撑\"选这个."),
        QueryGuideEntry(("activity",), "activity           — 步数 / 活动分钟数 / 日常活动 (读可穿戴 daily, 与上面同源)"),
    )),
    QueryGuideSection("体重 / 血压 / 饮食 / 饮水", (
        QueryGuideEntry(("weight",), "weight           — 体重历史"),
        QueryGuideEntry(("waist",), "waist            — 腰围历史；体重腰围复盘入口中与 weight 一起查询，服务端绑定近30天。\n                   同次复盘的 diet/workout 只查今天；未来记录建议不授权新增记录。"),
        QueryGuideEntry(("blood_pressure",), "blood_pressure   — 血压历史"),
        QueryGuideEntry(("diet",), "diet             — 今日饮食记录"),
        QueryGuideEntry(("water",), "water            — 今日饮水"),
        QueryGuideEntry(("supplements",), "supplements      — 补剂服用依从率"),
    )),
    QueryGuideSection("体检 / 基因 / 用药", (
        QueryGuideEntry(("medical_exam",), "medical_exam     — 化验/体检/影像报告 (MRI/核磁/CT/X光/B超/胃镜等也在这里; 读归一化指标表 + 最近检查报告摘要, 与 Twin 同源).\n                   不传 indicator → 返回用户全部化验指标清单 + 每项最新值 (问\"我有哪些化验指标\"走这里).\n                   传 indicator (如 'HCY'/'LDL'/'HbA1c') → 返回该指标时间序列.\n                   传 keyword (如 '膝关节MRI'/'核磁'/'影像') → 查询相关体检/影像条目.\n                   问\"最近24小时上传的记录/最近导入的报告\" → 用 dimension='medical_exam' + uploaded_days,\n                   返回按上传/导入时间排序的体检/影像报告清单.\n                   化验是低频数据, days 自动放宽到至少 365 天, 不会因 days 太小漏数据."),
        QueryGuideEntry(("genetic",), "genetic          — 基因位点 (必须配 indicator 参数, 如 'MTHFR', 'APOE')"),
        QueryGuideEntry(("genetic_cognitive", "genetic_personality", "genetic_comprehensive"), "genetic_cognitive / genetic_personality / genetic_comprehensive — 整合性基因解读"),
        QueryGuideEntry(("medication",), "medication       — 用药清单 (非单次服药, 是长期用药列表)"),
    )),
    QueryGuideSection("病症发作历史", (
        QueryGuideEntry(("illness",), "illness          — 有起病与痊愈周期的病症发作记录 (如口腔溃疡、感冒).\n                   问\"我上一次口腔溃疡是什么时候\" → dimension='illness', keyword='口腔溃疡'.\n                   问\"最近半年口腔溃疡有哪些记录\" → dimension='illness', keyword='口腔溃疡', days=183.\n                   这是只读查询；新增/修改病症仍分别用 health_record / health_manage."),
    )),
    QueryGuideSection("生活事件时间线 / 行程 / 各节点几点", (
        QueryGuideEntry(("events",), "events           — 用户日常生活事件的**真实时间戳**时间线 (出发/到达/购买/收货/症状起点/\n                   日常), 落 HealthEpisode 情景账本, 带诚实发生时间与精度 (精确/约/日期级).\n                   用户问\"总结我下午从家到现在各节点几点\"/\"今天几点出的门\"/\"我的行程\"/\n                   \"刚才那些事分别几点\" 走这里 —— 别去聊天记录里估算时间.\n                   数据来自 agent 记录 + 系统转后自动抽取, occurred_at 为后端确定性折算.\n                   worked example: 用户问\"整理今天下午的时间线\" → health_query(dimension='events', days=1)"),
    )),
)

QUERY_DATE_RULES = (
    "days 参数只表示**包含今天的最近 N 个自然日**窗口: 今天/今日 → days=1，最近/近7天 → days=7.\n"
    "diet/sleep 的今天、昨天、前天、昨晚、明确日期与有界日期范围由服务端从当前请求绑定。\n"
    "昨晚睡眠按醒来归属日读取；若目标夜晚缺失，不能使用旧记录替代。其他维度或含糊日历区间仍不支持，不能自行扩大为最近 N 天。\n"
    "illness 问\"上一次\"且没有给时间窗时省略 days, 后端查询全部病症历史."
)

PROJECTABLE_QUERY_DIMENSIONS = frozenset(
    dimension
    for section in QUERY_GUIDE_SECTIONS
    for entry in section.entries
    for dimension in entry.dimensions
)


def render_health_query_description(dimensions: Iterable[str] | None = None) -> str | None:
    """Render the full guide or a whole-entry task projection.

    Unknown dimensions fail closed so callers can retain the canonical full
    description.  Section prefaces remain attached to every selected entry in
    that section because they contain shared provenance and source semantics.
    """
    selected = None if dimensions is None else frozenset(dimensions)
    if selected is not None and (not selected or not selected <= PROJECTABLE_QUERY_DIMENSIONS):
        return None
    found: set[str] = set()
    blocks: list[str] = []
    for section in QUERY_GUIDE_SECTIONS:
        entries = []
        for entry in section.entries:
            if selected is None or selected.intersection(entry.dimensions):
                entries.append("  " + entry.text.replace("\n", "\n  "))
                if selected is not None:
                    found.update(selected.intersection(entry.dimensions))
        if entries:
            content = f"【{section.title}】\n"
            if section.preface:
                content += section.preface + "\n"
            content += "\n".join(entries)
            blocks.append(content)
    if selected is not None and found != selected:
        return None
    return _INTRO + "\n\n" + "\n\n".join(blocks) + "\n\n" + QUERY_DATE_RULES + "\n"
