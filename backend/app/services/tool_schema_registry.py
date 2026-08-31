"""工具 Schema 注册中心 — 统一健康 Agent 的工具定义

供 Agent 执行器使用的结构化工具接口。覆盖所有健康数据的读/写/分析操作。
"""

import logging
from typing import List, Dict, Any, Optional

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
  sleep         — 睡眠评分, 时长, 深睡/REM 分布 (一般"近7天睡得好吗"走这里)
  spo2          — 夜间血氧逐分钟时间序列 + 平均/最低/ODI 氧减指数 (OSAHS 筛查)
  spo2_sleep_correlation — 睡眠阶段 (deep/rem/light/awake) × 血氧关联分析

【心率 / 压力 / HRV / 日常活动 — 同源可穿戴 daily】
  这一组 (heart_rate / hrv / body_battery / stress / activity) 读同一份归一化
  可穿戴 daily 数据 (GarminData, 多设备按优先级合并, 与 Twin 同源), 返回最近
  N 天逐日紧凑摘要 (含数据源标注), 不截断.
  heart_rate    — 心率(静息/平均)历史
  hrv           — HRV 趋势
  body_battery  — 身体电量
  stress        — 压力水平

【运动 — 这里容易选错, 仔细看】
  workout / exercise — 同义, Garmin 同步的**结构化运动** (跑步/骑行/游泳/HIIT),
                       有距离/配速/心率区间/卡路里.
                       用户问"近7天的跑步"/"最近30天跑量"选这个.
  manual_exercise    — 用户**手动录入**的简单锻炼 (俯卧撑 20 个 / 瑜伽 30 分钟 / 拉伸).
                       只有计次/时长, 没有 GPS 数据.
                       用户问"近7天做了多少俯卧撑"选这个.
  activity           — 步数 / 活动分钟数 / 日常活动 (读可穿戴 daily, 与上面同源)

【体重 / 血压 / 饮食 / 饮水】
  weight           — 体重历史
  blood_pressure   — 血压历史
  diet             — 今日饮食记录
  water            — 今日饮水
  supplements      — 补剂服用依从率

【体检 / 基因 / 用药】
  medical_exam     — 化验/体检/影像报告 (MRI/核磁/CT/X光/B超/胃镜等也在这里; 读归一化指标表 + 最近检查报告摘要, 与 Twin 同源).
                     不传 indicator → 返回用户全部化验指标清单 + 每项最新值 (问"我有哪些化验指标"走这里).
                     传 indicator (如 'HCY'/'LDL'/'HbA1c') → 返回该指标时间序列.
                     传 keyword (如 '膝关节MRI'/'核磁'/'影像') → 查询相关体检/影像条目.
                     问"最近24小时上传的记录/最近导入的报告" → 用 dimension='medical_exam' + uploaded_days,
                     返回按上传/导入时间排序的体检/影像报告清单.
                     化验是低频数据, days 自动放宽到至少 365 天, 不会因 days 太小漏数据.
  genetic          — 基因位点 (必须配 indicator 参数, 如 'MTHFR', 'APOE')
  genetic_cognitive / genetic_personality / genetic_comprehensive — 整合性基因解读
  medication       — 用药清单 (非单次服药, 是长期用药列表)

【病症发作历史】
  illness          — 有起病与痊愈周期的病症发作记录 (如口腔溃疡、感冒).
                     问"我上一次口腔溃疡是什么时候" → dimension='illness', keyword='口腔溃疡'.
                     问"最近半年口腔溃疡有哪些记录" → dimension='illness', keyword='口腔溃疡', days=183.
                     这是只读查询；新增/修改病症仍分别用 health_record / health_manage.

【生活事件时间线 / 行程 / 各节点几点】
  events           — 用户日常生活事件的**真实时间戳**时间线 (出发/到达/购买/收货/症状起点/
                     日常), 落 HealthEpisode 情景账本, 带诚实发生时间与精度 (精确/约/日期级).
                     用户问"总结我下午从家到现在各节点几点"/"今天几点出的门"/"我的行程"/
                     "刚才那些事分别几点" 走这里 —— 别去聊天记录里估算时间.
                     数据来自 agent 记录 + 系统转后自动抽取, occurred_at 为后端确定性折算.
                     worked example: 用户问"整理今天下午的时间线" → health_query(dimension='events', days=1)

days 参数只表示**包含今天的最近 N 个自然日**窗口: 今天/今日 → days=1，最近/近7天 → days=7.
“昨晚睡眠”是唯一跨午夜特例，调用 sleep + days=2，返回覆盖跨午夜记录的窗口，合成时取最新一夜。
它不能表示昨天、前天、本周、上周、本月、去年等其他独立日历区间；遇到这些说法不要调用，
应说明当前查询能力尚不能精确表达该区间，或请用户改成可表达的“最近 N 天”。
illness 问"上一次"且没有给时间窗时省略 days, 后端查询全部病症历史.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "dimension": {
                        "type": "string",
                        "enum": [
                            "comprehensive",
                            "sleep",
                            "heart_rate",
                            "hrv",
                            "activity",
                            "spo2",
                            "spo2_sleep_correlation",
                            "weight",
                            "blood_pressure",
                            "supplements",
                            "water",
                            "diet",
                            "exercise",
                            "workout",
                            "manual_exercise",
                            "body_battery",
                            "stress",
                            "medical_exam",
                            "genetic",
                            "genetic_cognitive",
                            "genetic_personality",
                            "genetic_comprehensive",
                            "medication",
                            "illness",
                            "events",
                        ],
                        "description": "数据维度. 见 function description 里的选择指南",
                    },
                    "days": {
                        "type": "integer",
                        "description": "包含今天的最近 N 个自然日；昨晚睡眠用 sleep+days=2；不能表达其他昨天/上周/去年等独立日历区间。"
                        "illness 支持最长 36500 天；问上一次且未给时间窗时省略，查询全部历史",
                    },
                    "indicator": {
                        "type": "string",
                        "description": "具体指标名 (仅 medical_exam / genetic). 例: HCY, LDL, HbA1c, MTHFR, APOE",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "名称关键词 (medical_exam / illness). 例: 膝关节MRI, 胃镜, 口腔溃疡, 感冒",
                    },
                    "uploaded_days": {
                        "type": "integer",
                        "description": "按上传/导入时间查询最近 N×24 小时内的体检/影像报告；不能表达昨天等独立日历区间",
                    },
                },
                "required": ["dimension"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health_query_batch",
            "description": """一次声明式批查询: 用户一句话问**多个指标 / 要对比 / 要平均·最值·趋势**时,
用本工具一次产出全部子查询, 后端确定性取数 + 聚合, **1 轮完成** —— 不要连发多次 health_query。

何时用本工具 (而非 health_query):
- 用户同时问 ≥2 个指标 ("近7天的睡眠、HRV、步数怎么样")
- 要对比两个可表达的滚动窗口 ("近7天和近14天的 HRV")；当前 plan 的 days
  只能表示最近 N 天，不能表示上周、去年等任意日期区间
- 要某指标的平均 / 最大 / 最小 / 趋势 ("最近一个月步数平均多少", "HRV 是升还是降")
单个指标的简单当前值查询仍用 health_query。

plan 结构:
- queries: 1-6 条子查询, 每条 = {dimension, days, agg?}
    - dimension: 与 health_query 同一套维度枚举 (sleep/hrv/activity/heart_rate/
      blood_pressure/weight/diet/medication/medical_exam/...)；暂不支持 illness，
      病症名称和“上一次”语义必须用单条 health_query 保留 keyword/全历史窗口。
    - days: 最近几天 (默认 7)。注意: 是"最近 N 天窗口", 不是任意日期区间。
    - agg (可选): latest | avg | min | max | trend。trend = 首尾差 (最新 - 最早)。
      **数值聚合仅对可穿戴日指标有效**: activity(步数) / heart_rate / hrv /
      sleep(睡眠评分) / body_battery / stress / spo2。其他维度 agg 会被忽略, 返回原始数据。
- compare (可选): 对比两条子查询的标量。{a:<下标>, b:<下标>, op:'diff'|'ratio'}。diff=a-b, ratio=a/b。

完整示例 (近7天 vs 近14天平均 HRV 之差 + 近7天睡眠评分趋势 + 近7天步数均值):
{
  "queries": [
    {"dimension": "hrv", "days": 7, "agg": "avg"},
    {"dimension": "hrv", "days": 14, "agg": "avg"},
    {"dimension": "sleep", "days": 7, "agg": "trend"},
    {"dimension": "activity", "days": 7, "agg": "avg"}
  ],
  "compare": {"a": 0, "b": 1, "op": "diff"}
}
→ 每条回 {dimension, days, agg, value, unit, n}; compare 回 {op:'diff', value:<近7天均值 - 近14天均值>}。

只读, 无写入, 无需确认。未知 dimension / 未知 agg / 超过 6 条 → 返回带合法值清单的报错 (下一轮改正)。""",
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "description": "1-6 条只读子查询。每条 {dimension, days, agg?}。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dimension": {
                                    "type": "string",
                                    "description": "数据维度 (同 health_query 枚举), 如 sleep/hrv/activity/heart_rate/blood_pressure/weight/diet/medication/medical_exam",
                                },
                                "days": {
                                    "type": "integer",
                                    "description": "最近几天窗口, 默认 7",
                                },
                                "agg": {
                                    "type": "string",
                                    "enum": ["latest", "avg", "min", "max", "trend"],
                                    "description": "聚合方式; 省略=返回原始数据。仅可穿戴日指标可数值聚合。trend=首尾差(最新-最早)",
                                },
                            },
                            "required": ["dimension"],
                        },
                    },
                    "compare": {
                        "type": "object",
                        "description": "可选: 对比两条子查询的标量值。diff=a-b, ratio=a/b。",
                        "properties": {
                            "a": {
                                "type": "integer",
                                "description": "第一条子查询下标 (从 0 开始)",
                            },
                            "b": {"type": "integer", "description": "第二条子查询下标"},
                            "op": {"type": "string", "enum": ["diff", "ratio"]},
                        },
                    },
                },
                "required": ["queries"],
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
- 药名/药物剂型/mg 剂量(如 替普瑞酮、奥美拉唑20mg、胶囊、肠溶片)不是 diet, 应改用 medication；补剂/保健品改用 supplement
- "删除这一餐/撤销这顿/我刚才不小心删除了" 是管理已有饮食记录, 不要作为 diet.food_items 写入; 改用 health_manage
- record_date 如果用户没明说具体日期, 默认填今天 (不要填未来日期)
- 中文日期/时间要转成 ISO 格式；但 medication 当前只支持“本次/刚刚服用”的即时事实，用户明确提历史日期或时刻时先澄清，不要伪造或透传 taken_time
- 创建/调整长期健康目标用 goal；查询/修改/删除已有目标用 health_manage(record_type=goal)
- 用户明确说"别记录/不用记/记在心里就行"时, **不要**调用本工具, 也不要回"已记录"; 只用一句话自然回应(如"好的, 我记住了, 不写进记录")

完整参数示例见 data 字段描述.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "enum": [
                            "water",
                            "weight",
                            "blood_pressure",
                            "exercise",
                            "diet",
                            "supplement",
                            "supplement_group",
                            "rhinitis",
                            "waist",
                            "sleep",
                            "excretion",
                            "mood",
                            "medication",
                            "illness",
                            "symptom",
                            "garmin_sync",
                            "reminder",
                            "goal",
                            "event",
                            "remember",
                        ],
                        "description": """记录类型:
- water: 饮水 ("喝了杯水" / "喝了咖啡")
- diet: 饮食 ("早餐吃了…" / "吃了牛排")
- supplement: 单个补剂打卡 ("吃了鱼油")
- supplement_group: 按时段批量打卡 ("早上的药都吃了")
- weight: 体重
- blood_pressure: 血压
- waist: 腰围厘米数
- sleep: 手动补录睡眠 (必须有入睡/醒来时间和质量)
- excretion: 排便/排尿记录
- exercise: 用户手动录的简单锻炼 (俯卧撑/瑜伽等). 注意: Garmin 跑步手表自动同步, 不要让用户走这个
- rhinitis: 鼻炎每日打卡 (喷嚏次数/鼻塞/流涕). **单条/日**滚动 —— 同一天多次报自动累加进当天那一条, 不会堆多条。查询/撤销最近一次鼻炎事件可用 health_manage；后端只允许当前用户撤销指定打卡日的最后一条事件，不支持 update
- mood: 情绪
- medication: 服药一次
- illness: 有**起止周期、会痊愈**的病症 (记状态, 之后能标记"好了")。不只全身性生病 (感冒/流感/发烧), 也包括**局部会愈合的病灶**: 口腔溃疡/舌尖溃疡/嘴唇起泡/湿疹/麦粒肿/甲沟炎/烫伤/水泡/伤口/带状疱疹/痘痘发作 等。判据: 用户会关心它"什么时候好"、之后会说"好了/痊愈/好转"→ 走 illness。用户说"我感冒了/生病了/发烧了/长了个溃疡/起了个疱"都优先记 illness
- symptom: **一次性/当下**的身体感觉记录, 不追踪痊愈 (今天眼睛痒/打了个喷嚏/嗓子有点干/膝盖突然痛一下)。**不需要慢病档案**; 感冒相关的即时症状用 body_part=respiratory/general。**拿不准 illness 还是 symptom**: 问"用户之后会不会说'它好了'?会 → illness, 不会 → symptom"
- **急性危险症状永远走 symptom, 绝不记 illness**: 胸痛/胸闷伴放射痛或冷汗、突发呼吸困难、剧烈腹痛、卒中样(面瘫/言语不清/单侧肢体无力)、大出血 —— 这类要触发急救红线, 不是"会慢慢好"的病灶, 别因"会不会好"的判据误归 illness
- garmin_sync: 触发 Garmin 数据立即同步
- reminder: 设置提醒
- goal: 设置健康目标 ("从今天开始每天快走30分钟" / "90天把腰围降到82cm")
- remember: 无结构化类型的**个人属性/事实**(鞋码/衣服尺码/喜好/习惯/生日/昵称/血型/职业等)。用户说"记一下我鞋码42.5""记住我不吃香菜"、或你主动问了档案属性用户答了 → 走 remember 存进档案(可日后召回)。判据:**不是**饮食/体重/血压/睡眠/运动/症状/用药这些结构化健康数据,而是"关于我的一条稳定事实"。属性名+值齐了就直接记,别当成"太笼统"去追问;**绝不承诺存不了的东西**——要记的就走 remember。
- event: 生活事件/行程节点 (出发/落地/到店/药品送达/发现症状的时刻)。**带发生时间**,时间线总结靠它;occurred_at 直接放用户原话("下午"/"刚才"/"21:07"/ISO),后端确定性折算,绝不自己编时刻。
  裸陈述的行程/状态句直接记 event,别犹豫、别回问、别误当查询: "到杭州了"→{"title":"到达杭州"}、"飞机准备起飞"→{"title":"航班起飞"}、"在去公司路上"→{"title":"前往公司途中"}、"明天12:30飞机CA1714飞杭州"→{"title":"航班 CA1714 飞杭州","occurred_at":"明天12:30"}""",
                    },
                    "data": {
                        "type": "object",
                        "description": """记录的具体数据. 每种 type 的 schema:

water: {"amount": 250}  // 毫升, **必填整数 1-5000**. 用户没提具体毫升数就先问'喝了多少 ml?', 不要自己默认
diet:  {"meal_type": "breakfast|lunch|dinner|snack",  // 用英文枚举
        "food_items": "牛奶 200ml + 面包 1 片",      // 必填, 不能只给 calories
        // 注意: 药名/剂型/mg 剂量不是食物; 用 medication 或 supplement, 不要写 diet
        "calories": 450,                              // 必填/强烈建议, 用户没提就 LLM 根据份量估
        "protein": 25, "carbs": 55, "fat": 12, "fiber": 6,  // 强烈建议一并估算, 单位 g
        "record_date": "2026-05-05"}                  // 可选, 默认今天
supplement:       {"supplement_name": "鱼油"}          // 按名字匹配用户已定义的补剂
supplement_group: {"timing": "morning|noon|evening|bedtime"}
weight:           {"weight": 72.2, "record_date": "2026-05-05"}  // weight 必须在 data 里, 不能放顶层!
blood_pressure:   {"systolic": 120, "diastolic": 80, "record_date": "..."}
waist:            {"waist_cm": 88.5, "record_date": "2026-05-05"} // 腰围厘米数
sleep:            {"record_date": "2026-05-05", "bedtime": "2026-05-04T23:00:00+08:00",
                   "wake_time": "2026-05-05T07:00:00+08:00", "sleep_quality": 4}
event:            {"title": "落地北京", "occurred_at": "21:07"}  // 或 "下午"/"刚才";空=此刻
excretion:        {"type": "bowel|urine", "record_date": "2026-05-05",
                   "record_time": "08:30:00", "stool_type": 4, "notes": "正常"}
exercise:         {"exercise_type": "俯卧撑", "reps": 10, "sets": 1}
                  或 {"exercise_type": "running", "duration": 30, "distance": 5.0}
rhinitis:         {"sneezing": 5, "congestion": 1, "runny_nose": 0}  // sneezing=这次新打的喷嚏次数(增量, 端点自动累加当天); congestion/runny_nose 0-3 级. 每日一条
mood:             {"mood_score": 4, "journal": "心情不错"}    // mood_score 1-5 (1=很差 5=很好), journal=可选心情日记
medication:       {"medication_name": "布洛芬", "actual_dosage": "1片", "observed_strength": "200mg"}
                  // actual_dosage=本次实际服量，必填；observed_strength=包装/单粒规格，可选。规格绝不能替代服量，也不能从处方默认剂量推断
illness:          {"name": "感冒", "severity": 5, "start_date": "2026-05-05", "status": "active"}
symptom:          {"body_part": "eye|respiratory|skin|digestive|musculoskeletal|head|general|other",
                   "description": "咳嗽、嗓子疼、鼻塞", "severity": 3,   // severity 1-10, 可选
                   "triggers": ["pollen", "dust"],            // 可选
                   "occurred_at": "2026-05-08T09:00:00+08:00"} // 可选, 默认现在
garmin_sync:      {}
remember:         {"predicate": "鞋码", "object_value": "42.5"}  // 属性名+值; 可选 object_unit / subject(默认"用户"). 例:{"predicate":"忌口","object_value":"不吃香菜"}
reminder:         {"title": "臀中肌训练", "message": "蚌式开合、侧卧抬腿、臀桥",
                   "remind_at": "2026-06-30T10:30:00+08:00",
                   "recurrence": "daily", "priority": "normal"}
                  或 {"title": "定时饮水提醒", "message": "少量多次饮水",
                      "start_time": "09:00", "end_time": "20:00",
                      "interval_minutes": 90, "recurrence": "daily"}
goal:             {"title": "每日快走30分钟", "goal_type": "exercise|diet|sleep|water|supplement|outdoor|weight|other",
                   "goal_period": "daily|weekly|monthly|yearly", "target_value": 30,
                   "target_unit": "分钟", "start_date": "2026-07-05",
                   "implementation_steps": "1. 晚饭后快走\\n2. 心率保持轻中等强度"}""",
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

**病症痊愈/好转**("口腔溃疡好了"、"舌尖溃疡昨天好的"、"感冒好多了"、"修改记录"):
先 health_manage(record_type='illness', operation='list') 按名字找到对应 episode 的 id,
再 update —— 已痊愈 data={"status":"resolved"}(说"昨天/前天好的"就带 data={"status":"resolved","end_date":"昨天"},
后端会把相对词折算成日期); 好转未愈 data={"status":"improving","severity":<新严重度>}。
多个病症(口腔溃疡+舌尖溃疡)**分别** update 各自的 id。若 list 查不到对应病症(之前记成了
symptom 或没记过), 就直接 health_record(record_type='illness') 补一条 data={"name":"口腔溃疡",
"status":"resolved","start_date":"<起病日估计>"}(end_date 后端在 resolved 时自动补)。**别只用文字
说"已帮你修改"而不真的调用工具** —— 没有工具写入回执 = 没记上。

支持 record_type:
- diet, water, weight, waist, blood_pressure, sleep, mood, excretion, supplement: 支持 list/update/delete
- illness, medication, supplement_definition: 支持 list/update/delete
- exercise, symptom, medication_log, reminder, goal: 支持 list/update/delete
- medical_exam: 仅支持 list, 返回体检/影像/病理/胃镜等报告级摘要清单;指标时间线请用 health_query(dimension=medical_exam)
- event: 生活事件(出发/落地/送达等), 支持 list/delete;不支持 update, 时间记错请删除后重新记录
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "enum": [
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
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "list 返回条数上限, 默认 20, 最大 100。",
                    },
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                        "description": "diet list/update 可选餐次。用户说早餐/早饭=breakfast, 午餐/午饭=lunch, 晚餐/晚饭=dinner, 加餐/夜宵=snack。",
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
supplement: {"taken":false,"notes":"误记,撤回"}
exercise: {"reps":20,"sets":2}
symptom: {"severity":2,"notes":"洗鼻后缓解"}
medication_log: {"status":"skipped","skip_reason":"医生要求暂停"}
reminder: {"title":"明早复查血压","priority":"high"}
goal: {"title":"每日快走 30 分钟","status":"paused","notes":"膝盖恢复期暂停"}
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
  health_query:    拉**数据** (近7天睡了几小时, HRV 多少). 事实查询.
  health_analysis: 拉**解读** (HRV 下降和训练负荷有没有关系, 恢复得怎么样). 需要综合推理.

选择指南:
  用户问"近7天怎么样 / 最近怎么样"       → health_query comprehensive
  用户问"为什么 / 和 X 有关系吗 / 要不要调整" → health_analysis

当涉及跨领域 (睡眠 × 运动 × 饮食) 或要给建议时, 优先 analysis.
简单指标查询永远用 query.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {
                        "type": "string",
                        "enum": [
                            "comprehensive",
                            "sleep_insight",
                            "heart_rate_insight",
                            "recovery_status",
                            "risk_factors",
                            "trend",
                            "supplement_effectiveness",
                            "orchestrator",
                        ],
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
            "description": (
                "查询指定城市或用户当前位置的实时天气、未来天气预报、空气质量、"
                "户外运动适宜度。用户问明天/未来天气时必须使用 forecast；"
                "用户明确城市时必须原样传入 city，不要改用用户默认位置。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "check_type": {
                        "type": "string",
                        "enum": [
                            "weather",
                            "forecast",
                            "air_quality",
                            "outdoor_suitability",
                        ],
                        "description": "查询类型；明天或未来几天天气使用 forecast。",
                    },
                    "city": {
                        "type": "string",
                        "description": "用户明确指定的城市，如北京、上海；未指定时省略。",
                    },
                    "days": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 7,
                        "default": 3,
                        "description": "预报天数，仅 forecast 使用；查询明天时传 2 或 3 均可。",
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
            "description": """用户口述/粘贴体检化验结果或 MRI/CT/病理等报告文本时调用 (非 PDF 非图片, 纯文本).

触发场景:
- "我刚去抽血, LDL 3.8, ALT 42, 空腹血糖 5.6"
- 用户从微信/短信粘贴的化验结果文本
- 用户粘贴 MRI、CT、超声、内镜或病理报告的检查所见/结论
- 拍照 OCR 都不方便, 用户直接念出来

行为:
- 数值化验: 调 medical_text_parser 抽取指标 → 写 MedicalExamItem + MedicalIndicator.
- 叙述型报告: 按原文写入 MedicalExam.overall_assessment, 不要求虚构数值指标.
- 两者都会触发 Twin 失效.

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
                        "description": "检查日期 ISO YYYY-MM-DD 或今天/昨天等相对日期. 用户没说就填今天.",
                    },
                    "report_type": {
                        "type": "string",
                        "enum": [
                            "biochemistry",
                            "imaging",
                            "mri",
                            "ct",
                            "ultrasound",
                            "endoscopy",
                            "pathology",
                            "medical_report",
                        ],
                        "description": "报告类型. MRI/CT/病理等叙述型报告必须填写对应类型.",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_doctor_feedback",
            "description": """仅当用户明确要求记录或保存医生反馈时调用。

裸转述医生诊断/意见、询问建议、混合多个动作，或依据医生意见修改其他记录时不得调用；这些情况应先正常回应或请用户把记录命令单独重述。""",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "医生反馈的简短摘要（可选）。",
                    },
                    "assessment": {
                        "type": "string",
                        "description": "用户明确要求保存的医生评估或诊断内容（可选）。",
                    },
                    "plan": {
                        "type": "string",
                        "description": "医生提出的后续计划或建议（可选）。",
                    },
                    "visit_date": {
                        "type": "string",
                        "description": "就诊日期，ISO YYYY-MM-DD（可选）。",
                    },
                },
                "additionalProperties": False,
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

**要查多个指标时,务必用 names 一次列全**(如 names=['LDL','ALT','TSH','HDL']),不要一个个分多次调用 —— 一次调用即返回全部(结果按指标名分组在 by_name 里),省一轮 LLM 往返。单个指标用 name 也可。
name/names 是中文/英文都行 (LDL / 低密度脂蛋白). since 是 YYYY-MM-DD, 不传就给最近 1 年.
返回每条: record_date / value / unit / is_abnormal / reference_low / reference_high.
注意: 血压不是化验表指标。用户问"血压/BP/收缩压/舒张压"时优先用 health_query(dimension='blood_pressure');
如果误调用本工具, 后端会桥接到 blood_pressure_records 并返回标准化 BP/SBP/DBP 结构.

如果用户问的是"我体检结果怎么样"那种宽泛问题, 用 health_query(dimension='medical_exam') 拿最新整体快照, 不要走这个.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "**优先用这个查多个指标**: 要看的多个指标名列表(中英文均可), 如 ['LDL','ALT','TSH','HDL']. 一次调用返回全部, 结果按指标名分组在 by_name. 最多 20 个.",
                    },
                    "name": {
                        "type": "string",
                        "description": "单个指标名, 中英文均可 (LDL / 低密度脂蛋白胆固醇). 查多个请改用 names. 都不传则返回最近全部异常项.",
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
            "name": "intervention_cycle",
            "description": """N-of-1 干预结局闭环 — 用用户自己的数据验证某个干预是否真的有效。

这是产品北极星: 不是泛泛给建议, 而是"开一个周期 → 锁基线 → 过段时间复查 → 用你自己的化验数据告诉你有没有效"。

action 选择:
- status: 报告当前进行中的干预周期进展。对每个结局指标给 baseline → latest → delta/delta_pct + 状态
          (met 达标 / improving 改善中 / worsening 变差 / flat 持平 / pending 待复查)。
          **没有进行中的周期时如实说"目前没有进行中的干预周期", 不要编造。**
          用户问"我的干预周期怎么样 / 这阵子调理有没有效 / 降 LDL 进展" 走这个。
- list: 列出干预周期历史,含 active/completed/abandoned,用于用户问"之前做过哪些周期/历史干预"。
- start: 为用户开启一个新的代谢干预周期 (锁基线 Twin 快照 + 基线化验 + 目标指标)。
          **写操作 → 必须先确认**: 第一次调用 (不带 confirmed) 会返回需要向用户复述确认的提示,
          用户明确同意后**重新调用并带 confirmed=true** 才真正建周期。
          目标指标由当前异常的代谢/血脂/血糖/肝指标自动推导 (如 LDL/尿酸/HbA1c 偏高)。
          用户说"开个周期验证下 / 我想系统调理代谢三个月 / 帮我跟踪降 LDL 的效果" 走这个。
- update: 调整进行中周期的计划天数、目标指标或停止条件。**写操作 → 必须先确认**。
- cancel: 取消进行中周期,状态改为 abandoned,保留历史记录。**写操作 → 必须先确认**。

注意:
- 这是健康自我管理工具, 不是医疗诊断或处方。提议/解读时措辞要"非诊断、建议结合医生"。
- 一个用户同一时间只有一个进行中的周期; 已有进行中的周期时 start 会直接返回它, 不重复开。""",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "list", "start", "update", "cancel"],
                        "description": "status 报当前周期进展; list 列历史; start/update/cancel 是写操作, 需确认",
                    },
                    "cycle_id": {
                        "type": "integer",
                        "description": "仅 update/cancel 可选: 指定周期 ID。不传则默认当前 active 周期。",
                    },
                    "days": {
                        "type": "integer",
                        "default": 90,
                        "description": "start/update: 周期天数, 默认 90 天; update 会重算 planned_end_date。",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["all", "active", "completed", "abandoned"],
                        "default": "all",
                        "description": "仅 list: 历史周期状态过滤。",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "仅 list: 最多返回多少个周期。",
                    },
                    "target_specs": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "start/update 可选目标指标数组 [{code,target,direction}]。慎用,用户确认后再改。",
                    },
                    "stop_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "update 可选停止/升级条件列表。",
                    },
                    "reason": {
                        "type": "string",
                        "description": "cancel 可选取消原因,仅用于本次回复说明。",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "start/update/cancel: 用户已明确同意后置 true。首次提议不要带, 让确认流程走一遍。",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "description": "检索本系统医学知识库(得到医学wiki RAG)获取解读化验/体检异常、健康建议的依据。**解读异常指标或给建议前先检索,不要只凭记忆。** 返回相关知识片段,仅供参考、不替代医生,**不得据此开处方或给具体剂量(R4)**。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": '检索关键词,如"脂肪肝管理""红细胞增多 鉴别"',
                    },
                    "knowledge_source": {
                        "type": "string",
                        "description": (
                            "用户明确指定的知识库或知识源名称；必须原样传入，"
                            "不得改写成通用系统知识库。用户未指定时省略。"
                        ),
                    },
                    "n_results": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 8,
                        "description": "返回片段数量, 1-8, 默认 5",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "realtime_search",
            "description": "实时联网检索最新医学指南/外部时效信息(阿里云 IQS)。仅在需要最新指南/时效事实时使用;返回外部检索摘要,仅供参考、不替代医生、不得据此开处方或给剂量(R4)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "精炼的检索词,**只放主题关键词,不要放用户的隐私细节/完整病史**。",
                    },
                },
                "required": ["query"],
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
    {
        "type": "function",
        "function": {
            "name": "draft_aigc_media",
            "description": """为用户明确要求的健康行动图片或 3-15 秒短视频创建一个待确认草稿（例如饮食建议封面、晨间拉伸短视频）。该工具不会调用百炼，也不会发送提示词或图片；它只会展示一张确认卡片。仅当用户亲自在确认卡片上点击后，后端才会向百炼发送该草稿绑定的提示词和当前图片，并可能消耗 TokenPlan Credits 或产生费用。

硬规则：
- 仅在用户明确要求创作图片或短视频时调用，不能用于介绍 AIGC 功能或泛化聊天。
- image_to_image/image_to_video 只使用当前这条用户消息附带的第一张图片；没有附件时请用户重新上传。
- 只制作健康管理、行动沟通相关内容，不生成医疗诊断、治疗承诺或含隐私健康数据的公开素材。""",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "text_to_image",
                            "image_to_image",
                            "text_to_video",
                            "image_to_video",
                        ],
                        "description": "生成类型。当前消息含图片时可选 image_to_image/image_to_video。",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "简洁的健康行动视觉描述，不包含用户个人身份或详细医疗隐私。",
                    },
                    "purpose": {
                        "type": "string",
                        "enum": [
                            "meal_visual",
                            "movement_routine",
                            "hydration_reminder",
                            "sleep_routine",
                            "wellness_story",
                        ],
                        "description": "健康行动沟通用途，用于服务端安全边界。",
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "minimum": 3,
                        "maximum": 15,
                        "default": 5,
                        "description": "仅视频，3-15 秒。",
                    },
                    "ratio": {
                        "type": "string",
                        "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                        "default": "9:16",
                    },
                },
                "required": ["kind", "prompt", "purpose"],
            },
        },
    },
]


# fast(简单记录/查询)回合的固定工具白名单(2026-07-11 token 优化 #2)。
# 实测全量 schema 18,064 chars,big-3 仅 ~6,700 —— fast 回合(最高频)砍 ~62% 工具
# prefill。**固定**子集(不随消息内容变)以保持前缀字节稳定、不拆 provider 前缀缓存;
# fast 模型若吐出子集外工具名 → agent 侧升级回全集重跑该轮(fail-open)。
FAST_TURN_TOOL_NAMES: tuple = ("health_record", "health_query", "health_manage")

# fast 只读回合的工具白名单。语义分类为查询/列表时不暴露 health_record, 避免
# “饮食的记录,列个表格”这类名词性“记录”被模型误写成提醒/健康记录。
FAST_READ_TURN_TOOL_NAMES: tuple = ("health_query", "health_manage")

# R5 分析轮只读工具子集(fast 子集的对称补全)。纯分析/知识轮不含写/上传/管理动作,
# 只发只读工具 → 省下 health_record(~2k)/health_manage(~1k)/upload_*/manage_plan 的 schema。
# 模型若在分析轮请求被扣下的写工具 → 走同一 withheld-upgrade 护栏升级回全集(见 agent_executor)。
# 固定子集(不随消息变)以保前缀字节稳定,不拆 provider 前缀缓存。
ANALYSIS_TURN_TOOL_NAMES: tuple = (
    "health_query",
    "health_query_batch",
    "health_analysis",
    "query_lab_indicators",
    "query_genetic_profile",
    "knowledge_search",
    "realtime_search",
    "environment_check",
    "supplement_guide",
)

# Query-scoped fixed lanes. These are intentionally coarse and stable: the
# provider sees one reusable schema prefix per domain instead of a unique tool
# list per utterance. All lanes are read-only; mutation/attachments fail open to
# the full registry in AgentExecutor.
RECOVERY_TURN_TOOL_NAMES: tuple = (
    "health_query",
    "health_query_batch",
    "health_analysis",
    "knowledge_search",
    "environment_check",
)
DIET_TURN_TOOL_NAMES: tuple = (
    "health_query",
    "health_query_batch",
    "health_analysis",
    "knowledge_search",
)
MEDICATION_TURN_TOOL_NAMES: tuple = (
    "health_query",
    "health_analysis",
    "query_genetic_profile",
    "knowledge_search",
    "supplement_guide",
)
LABS_TURN_TOOL_NAMES: tuple = (
    "health_query",
    "health_analysis",
    "query_lab_indicators",
    "query_genetic_profile",
    "knowledge_search",
    "realtime_search",
)
KNOWLEDGE_TURN_TOOL_NAMES: tuple = (
    "knowledge_search",
    "realtime_search",
)


def get_health_tools(subset: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """获取健康工具定义。

    subset: 工具名白名单(如 FAST_TURN_TOOL_NAMES)。None = 全量。
    subset 模式下不追加 specialist 工具(fast 简单回合与深分析互斥)。

    RFC 方向一 Phase A: 当 settings.agent_specialist_tools 开启时, 追加
    specialist 分析工具(analyze_recovery 等), 让 Agent 自主调用。默认关闭,
    行为与现状一致。
    """
    if subset is not None:
        wanted = set(subset)
        return [t for t in HEALTH_TOOLS if t["function"]["name"] in wanted]
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
