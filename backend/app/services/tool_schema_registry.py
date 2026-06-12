"""工具 Schema 注册中心 — 统一健康 Agent 的工具定义

供 Agent 执行器使用的结构化工具接口。覆盖所有健康数据的读/写/分析操作。
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ── 核心健康工具定义 ────────────────────────────────────

HEALTH_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "health_query",
            "description": """查询用户的健康数据. 根据用户问题选对 dimension 是关键.

dimension 选择指南 (按场景):

【综合判断 / 今天/最近怎么样】
  comprehensive — 综合多维度数据 (默认选这个, 不确定也选这个)

【睡眠 / 休息】
  sleep         — 睡眠评分, 时长, 深睡/REM 分布 (一般"昨晚睡得好吗"走这里)
  spo2          — 夜间血氧逐分钟时间序列 + 平均/最低/ODI 氧减指数 (OSAHS 筛查)
  spo2_sleep_correlation — 睡眠阶段 (deep/rem/light/awake) × 血氧关联分析

【心率 / 压力 / HRV】
  heart_rate    — 心率(静息/平均/最高)历史曲线
  hrv           — HRV 7/14/30 天趋势, 状态判断 (偏低/良好)
  body_battery  — Garmin 身体电量 (充电/消耗时段)
  stress        — 压力水平时段分布

【运动 — 这里容易选错, 仔细看】
  workout / exercise — 同义, Garmin 同步的**结构化运动** (跑步/骑行/游泳/HIIT),
                       有距离/配速/心率区间/卡路里.
                       用户问"昨天的跑步"/"上周练了几次"/"跑量"选这个.
  manual_exercise    — 用户**手动录入**的简单锻炼 (俯卧撑 20 个 / 瑜伽 30 分钟 / 拉伸).
                       只有计次/时长, 没有 GPS 数据.
                       用户问"这周做了多少俯卧撑"选这个.
  activity           — 步数 / 活动分钟数 / 久坐提醒 (非训练类的日常活动)

【体重 / 血压 / 饮食 / 饮水】
  weight           — 体重历史
  blood_pressure   — 血压历史
  diet             — 今日饮食记录
  water            — 今日饮水
  supplements      — 补剂服用依从率

【体检 / 基因 / 用药】
  medical_exam     — 化验/体检指标 (读归一化指标表, 与 Twin 同源).
                     不传 indicator → 返回用户全部化验指标清单 + 每项最新值 (问"我有哪些化验指标"走这里).
                     传 indicator (如 'HCY'/'LDL'/'HbA1c') → 返回该指标时间序列.
                     化验是低频数据, days 自动放宽到至少 365 天, 不会因 days 太小漏数据.
  genetic          — 基因位点 (必须配 indicator 参数, 如 'MTHFR', 'APOE')
  genetic_cognitive / genetic_personality / genetic_comprehensive — 整合性基因解读
  medication       — 用药清单 (非单次服药, 是长期用药列表)

days 参数: 默认 7. 问"昨天" → days=1; 问"最近 / 这周" → days=7; 问"这月" → days=30.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "dimension": {
                        "type": "string",
                        "enum": ["comprehensive", "sleep", "heart_rate", "hrv", "activity",
                                 "spo2", "spo2_sleep_correlation", "weight", "blood_pressure",
                                 "supplements", "water",
                                 "diet", "exercise", "workout", "manual_exercise",
                                 "body_battery", "stress",
                                 "medical_exam", "genetic",
                                 "genetic_cognitive", "genetic_personality", "genetic_comprehensive",
                                 "medication"],
                        "description": "数据维度. 见 function description 里的选择指南",
                    },
                    "days": {
                        "type": "integer",
                        "default": 7,
                        "description": "查询最近几天. 昨天=1, 最近/本周=7, 本月=30",
                    },
                    "indicator": {
                        "type": "string",
                        "description": "具体指标名 (仅 medical_exam / genetic). 例: HCY, LDL, HbA1c, MTHFR, APOE",
                    },
                },
                "required": ["dimension"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health_record",
            "description": """记录用户的健康数据. 记录后会真正写入数据库, 所以必须确保必填字段齐全.

常见错误 (不要犯):
- weight 必须用 data.weight, 不要放在顶层 args.weight
- diet 必须有 food_items, 不能只传 calories
- record_date 如果用户没明说具体日期, 默认填今天 (不要填未来日期)
- 中文日期/时间要转成 ISO 格式 (例: "昨天早上 8 点" → record_date='YYYY-MM-DD', taken_time='08:00')

完整参数示例见 data 字段描述.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "enum": ["water", "weight", "blood_pressure", "exercise",
                                 "diet", "supplement", "supplement_group", "rhinitis",
                                 "mood", "medication", "illness", "symptom",
                                 "garmin_sync", "reminder"],
                        "description": """记录类型:
- water: 饮水 ("喝了杯水" / "喝了咖啡")
- diet: 饮食 ("早餐吃了…" / "吃了牛排")
- supplement: 单个补剂打卡 ("吃了鱼油")
- supplement_group: 按时段批量打卡 ("早上的药都吃了")
- weight: 体重
- blood_pressure: 血压
- exercise: 用户手动录的简单锻炼 (俯卧撑/瑜伽等). 注意: Garmin 跑步手表自动同步, 不要让用户走这个
- rhinitis: 鼻炎症状 (喷嚏/鼻塞/流涕)
- mood: 情绪
- medication: 服药一次
- illness: 生病 / 急性症状周期 (感冒/流感/发烧). 用户明确说"我感冒了/生病了/发烧了"优先记录 illness
- symptom: 身体症状记录 (咳嗽/嗓子疼/鼻塞/流涕/眼痒/膝盖痛/皮肤起疹 等). **不需要慢病档案**, 任何偶发症状都走这个；感冒相关症状用 body_part=respiratory/general
- garmin_sync: 触发 Garmin 数据立即同步
- reminder: 设置提醒""",
                    },
                    "data": {
                        "type": "object",
                        "description": """记录的具体数据. 每种 type 的 schema:

water: {"amount": 250}  // 毫升, **必填整数 1-5000**. 用户没提具体毫升数就先问'喝了多少 ml?', 不要自己默认
diet:  {"meal_type": "breakfast|lunch|dinner|snack",  // 用英文枚举
        "food_items": "牛奶 200ml + 面包 1 片",      // 必填, 不能只给 calories
        "calories": 450,                              // 必填/强烈建议, 用户没提就 LLM 根据份量估
        "protein": 25, "carbs": 55, "fat": 12, "fiber": 6,  // 强烈建议一并估算, 单位 g
        "record_date": "2026-05-05"}                  // 可选, 默认今天
supplement:       {"supplement_name": "鱼油"}          // 按名字匹配用户已定义的补剂
supplement_group: {"timing": "morning|noon|evening|bedtime"}
weight:           {"weight": 72.2, "record_date": "2026-05-05"}  // weight 必须在 data 里, 不能放顶层!
blood_pressure:   {"systolic": 120, "diastolic": 80, "record_date": "..."}
exercise:         {"exercise_type": "俯卧撑", "reps": 10, "sets": 1}
                  或 {"exercise_type": "running", "duration": 30, "distance": 5.0}
rhinitis:         {"sneezing": 2, "congestion": 1, "runny_nose": 0}  // 0-3 级
mood:             {"score": 7, "notes": "心情不错"}    // score 1-10
medication:       {"medication_name": "布洛芬", "taken_time": "08:00"}
illness:          {"name": "感冒", "severity": 5, "start_date": "2026-05-05", "status": "active"}
symptom:          {"body_part": "eye|respiratory|skin|digestive|musculoskeletal|head|general|other",
                   "description": "咳嗽、嗓子疼、鼻塞", "severity": 3,   // severity 1-10, 可选
                   "triggers": ["pollen", "dust"],            // 可选
                   "occurred_at": "2026-05-08T09:00:00+08:00"} // 可选, 默认现在
garmin_sync:      {}
reminder:         {"title": "吃药", "remind_at": "2026-05-06T08:00:00+08:00"}""",
                    },
                },
                "required": ["record_type", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health_manage",
            "description": """管理已存在的健康记录: 查询列表、修改、删除。

和 health_record 的分工:
- 新增记录: health_record
- 查询事实/列表: health_query 或 health_manage(operation='list')
- 修改/删除已有记录: health_manage

当用户说"删掉 ID 605"、"删除重复午餐"、"把午餐热量改成 378"时必须调用本工具,
不能回答"没有删除功能"。如果用户只说"删除一条"但有多条候选, 先用 list 查出 ID 并让用户确认。

支持 record_type:
- diet, water, weight, waist, blood_pressure, sleep, mood, excretion: 支持 list/update/delete
- illness, medication, supplement_definition: 支持 list/update/delete
- exercise, symptom, medication_log, reminder: 支持 list/update/delete
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "enum": [
                            "diet", "water", "weight", "waist", "blood_pressure",
                            "sleep", "mood", "excretion", "exercise", "illness",
                            "symptom", "medication", "medication_log",
                            "supplement_definition", "reminder",
                        ],
                        "description": "要管理的数据类型",
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["list", "update", "delete"],
                        "description": "操作: list 查询候选记录; update 修改; delete 删除",
                    },
                    "record_id": {
                        "type": "integer",
                        "description": "update/delete 必填。必须来自 list/health_query/API 返回的真实 ID, 不要编造。",
                    },
                    "date": {
                        "type": "string",
                        "description": "list 可选日期 YYYY-MM-DD。饮食支持按日期汇总; 其他类型走最近列表。",
                    },
                    "data": {
                        "type": "object",
                        "description": """update 的字段补丁。例如:
diet: {"food_items":"鳕鱼 50g + 鲍鱼 2个","calories":378,"meal_type":"lunch"}
water: {"amount":300}
weight: {"weight":71.2}
blood_pressure: {"systolic":120,"diastolic":78}
illness: {"status":"resolved","severity":2}
medication: {"name":"二甲双胍","dosage":"500mg"}
supplement_definition: {"name":"维生素D","dosage":"2000IU"}
exercise: {"reps":20,"sets":2}
symptom: {"severity":2,"notes":"洗鼻后缓解"}
medication_log: {"status":"skipped","skip_reason":"医生要求暂停"}
reminder: {"title":"明早复查血压","priority":"high"}
""",
                    },
                },
                "required": ["record_type", "operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health_analysis",
            "description": """深度健康分析 — 与 health_query 的区别:
  health_query:    拉**数据** (昨晚睡了几小时, HRV 多少). 事实查询.
  health_analysis: 拉**解读** (HRV 下降和训练负荷有没有关系, 恢复得怎么样). 需要综合推理.

选择指南:
  用户问"昨晚怎么样 / 最近怎么样"        → health_query comprehensive
  用户问"为什么 / 和 X 有关系吗 / 要不要调整" → health_analysis

当涉及跨领域 (睡眠 × 运动 × 饮食) 或要给建议时, 优先 analysis.
简单指标查询永远用 query.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {
                        "type": "string",
                        "enum": ["comprehensive", "sleep_insight", "heart_rate_insight",
                                 "recovery_status", "risk_factors", "trend",
                                 "supplement_effectiveness", "orchestrator"],
                        "description": """分析类型:
- comprehensive: 综合健康分析 (多维度联合 insight, 不确定选这个)
- sleep_insight: 睡眠深度洞察 (阶段分布 + 质量评估)
- heart_rate_insight: 心率/HRV 洞察 (波动规律 + 恢复信号)
- recovery_status: 恢复力评估 (训练负荷 × HRV × 睡眠联合判断, 跑后问"今天能不能继续练"选这个)
- risk_factors: 风险因素分析 (心血管/代谢风险提示)
- trend: 趋势变化分析 (某个指标 N 天走势)
- supplement_effectiveness: 补剂效果评估
- orchestrator: 多专家协作深度分析 (最复杂, 跨领域, 需要用户问题放 question 参数)""",
                    },
                    "days": {
                        "type": "integer",
                        "default": 7,
                        "description": "分析时间范围. 短期=7, 趋势=14-30",
                    },
                    "question": {
                        "type": "string",
                        "description": "用户的原始问题 (仅 orchestrator 时使用). 原话传入, 不要改写.",
                    },
                },
                "required": ["analysis_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "environment_check",
            "description": "查询当前天气、空气质量、户外运动适宜度等环境数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "check_type": {
                        "type": "string",
                        "enum": ["weather", "air_quality", "outdoor_suitability"],
                        "description": "查询类型",
                    },
                },
                "required": ["check_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "supplement_guide",
            "description": "获取今日补剂服用指南，包括服用顺序、动态调整建议等。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_genetic_txt",
            "description": """用户语音/对话粘贴 23andMe / 微基因 / 全基因组 TXT 原始数据时调用.

触发场景:
- "我把基因报告 raw data 发给你"
- "这是我的 23andMe 文件" + 长文本
- 用户粘贴了大段含 rsid 的 tab 分隔行 (如 'rs1801133\\t1\\t...\\tAG')

行为: 解析 SNP 位点, 自动写入 GeneticProfile + GeneticVariant 表, 写完触发 Twin 失效.
之后用户问"我有什么基因风险"就能查到. 不要让用户重复粘贴.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "txt_content": {
                        "type": "string",
                        "description": "23andMe / WeGene 格式的 TXT 原始内容. tab 分隔, # 开头是注释, 第 1 列 rsid, 第 4 列 genotype.",
                    },
                    "test_provider": {
                        "type": "string",
                        "description": "检测机构, 如 '23andMe' / 'WeGene' / '微基因'. 用户没说就填 'unknown'.",
                        "default": "unknown",
                    },
                    "test_date": {
                        "type": "string",
                        "description": "检测日期 ISO 格式 YYYY-MM-DD. 用户没说就填今天.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "可选备注",
                    },
                },
                "required": ["txt_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_genetic_profile",
            "description": """列出用户的基因档案 (profiles) — 多份就返回多条, 含每份的 variant_count + 解析状态.

何时调用:
- "我有几份基因报告"
- "我之前传过基因数据吗"
- "上次的基因报告解析完了吗"

返回每份: id / test_provider / test_date / variant_count / status (processing/done/failed).
如果用户问基因 *指标* (MTHFR / APOE 等), 用 health_query(dimension='genetic', indicator=...) 而不是这个.""",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_medical_exam_text",
            "description": """用户口述/粘贴体检化验结果文本时调用 (非 PDF 非图片, 纯文本).

触发场景:
- "我刚去抽血, LDL 3.8, ALT 42, 空腹血糖 5.6"
- 用户从微信/短信粘贴的化验结果文本
- 拍照 OCR 都不方便, 用户直接念出来

行为: 调 medical_text_parser 抽取指标 → 写 MedicalExamItem + MedicalIndicator → 触发 Twin 失效.
之后 query_lab_indicators 能查到.

不要为单一指标 (单条血压 130/85) 走这个, 那个用 health_record(record_type='blood_pressure'). 这个适合 *多指标体检结果*.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "用户口述的体检 / 化验文本. 例: 'LDL 3.8 mmol/L, ALT 42 U/L, 空腹血糖 5.6'",
                    },
                    "exam_date": {
                        "type": "string",
                        "description": "检查日期 ISO YYYY-MM-DD. 用户没说就填今天.",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_lab_indicators",
            "description": """查询用户的化验/体检指标历史 (MedicalIndicator 表).

触发场景:
- "我上次 LDL 多少"
- "我的 ALT 历史" / "甲状腺过去几年的趋势"
- 用户想看某个指标的随时间变化

参数 name 是中文/英文都行 (LDL / 低密度脂蛋白). since 是 YYYY-MM-DD, 不传就给最近 1 年.
返回每条: record_date / value / unit / is_abnormal / reference_low / reference_high.
注意: 血压不是化验表指标。用户问"血压/BP/收缩压/舒张压"时优先用 health_query(dimension='blood_pressure');
如果误调用本工具, 后端会桥接到 blood_pressure_records 并返回标准化 BP/SBP/DBP 结构.

如果用户问的是"我体检结果怎么样"那种宽泛问题, 用 health_query(dimension='medical_exam') 拿最新整体快照, 不要走这个.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "指标名, 中英文均可 (LDL / 低密度脂蛋白胆固醇 / ALT / 谷丙转氨酶). 不传则返回最近全部异常项.",
                    },
                    "since": {
                        "type": "string",
                        "description": "起始日期 ISO YYYY-MM-DD. 不传默认最近 365 天.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "最多返回多少条",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_plan",
            "description": "管理健康计划：生成周计划、完成计划项、保存内容到首页卡片。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["generate_weekly", "complete_item", "save_to_card"],
                        "description": """操作类型：
- generate_weekly: 生成本周/下周健康计划
- complete_item: 标记计划项完成
- save_to_card: 保存内容到首页行动卡片""",
                    },
                    "data": {
                        "type": "object",
                        "description": """操作数据：
- generate_weekly: {"target_week": "current|next", "user_focus": ["睡眠", "运动"]}
- complete_item: {"plan_id": 1, "item_id": 2}
- save_to_card: {"title": "标题", "content": "markdown内容", "card_type": "plan|insight|recommendation"}""",
                    },
                },
                "required": ["action", "data"],
            },
        },
    },
]


def get_health_tools() -> List[Dict[str, Any]]:
    """获取所有健康工具定义。

    RFC 方向一 Phase A: 当 settings.agent_specialist_tools 开启时, 追加
    specialist 分析工具(analyze_recovery 等), 让 Agent 自主调用。默认关闭,
    行为与现状一致。
    """
    try:
        from app.config import settings
        if getattr(settings, "agent_specialist_tools", False):
            from app.services.specialist_tools import specialist_tool_schemas
            return HEALTH_TOOLS + specialist_tool_schemas()
    except Exception:  # noqa: BLE001 — 配置/导入异常不应影响主链路
        pass
    return HEALTH_TOOLS


def get_tool_names() -> List[str]:
    """获取所有工具名称"""
    return [t["function"]["name"] for t in HEALTH_TOOLS]
