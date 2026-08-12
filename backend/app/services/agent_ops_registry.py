"""Agent Ops registry — Agent-Operable Module Contract 的后端操作面单一真源。

spec: docs/specs/active/2026-07-02-agent-operable-module-contract.md §3.1
姊妹注册表: app/services/atomic_capability_registry.py —— 那张表管**前端**
AtomicCapability(卡片 schema / 可挂动作 / surface);本表是它的**后端操作面
twin**:agent 能对哪个一等对象做什么操作(create/read/list/update/delete)、
确认档位、撤销通路。两表通过 object_type 对齐(spec §3.5)。

纯数据(pgx_cpic_table 风格):**不 import agent_executor** —— 一致性由
tests/test_agent_ops_registry.py 的 CI 闸负责:用 AST 扫 agent_executor 源码
(record_type 分支 / manage 映射 / query dimension)+ 直接 import 活的确认档位
集合,与本表双向比对。executor 加/删通路而不改本表 → CI 红(spec §3.4)。

诚实盘点原则:本表登记**当前真实覆盖**,不是愿景 ——
- 没有通路的格子用 ``{"gap": True, "reason": ...}`` 显式挂账;
- 刻意不开放的用 ``{"opt_out": "<理由>"}``(医疗边界/人审要求/只读面);
- 整个对象无 agent 通路 → 顶层 ``{"gap": True, "reason": ...}`` 或
  ``{"opt_out": ...}``。

条目 schema(registry_violations() 结构校验)::

    AGENT_OPS[object_type] =
        {"opt_out": <reason>}                      # 整对象刻意不开放
      | {"gap": True, "reason": <reason>}          # 整对象空洞(有 UI 面无 agent 通路)
      | {op: entry for op in ("create","read","list","update","delete")}

    entry =
        {"tool": ..., "via": ..., <op 专属字段>}    # 真实通路
      | {"opt_out": <reason>}
      | {"gap": True, "reason": <reason>}

    create(tool=health_record)额外字段:
        record_type  — _exec_health_record 的 rtype(canonical 名,别名不入表)
        confirm      — "auto" | "typed_only" | "never_auto"(spec §3.2;
                       镜像 executor 的 _FAST_RECORD_*_CONFIRM_KINDS 活集合)
        undo         — auto/typed_only 写入必填(spec §3.3 撤销通路);
                       通路缺失时 undo=None + undo_gap=<理由> 显式挂账
    read(tool=health_query)额外字段:
        dimensions   — 该对象经 health_query 可读的 dimension 枚举
    list/update/delete(tool=health_manage)额外字段:
        record_type  — _exec_health_manage 的 list_paths/record_paths 映射键

确认档位现状(诚实说明):confirm 目前只有 create 有执行机制(快路由
_auto_confirm_fast_record_args gate);spec §3.1 示例里 delete 的 typed_only
档位尚无 executor 执行点,故本表不在 delete 上登记 confirm —— 见 spec
"落地状态(2026-07-03)" gap 清单。
"""
from __future__ import annotations

from typing import Any, Dict

OPS: tuple[str, ...] = ("create", "read", "list", "update", "delete")
CONFIRM_TIERS: frozenset[str] = frozenset({"auto", "typed_only", "never_auto"})


AGENT_OPS: Dict[str, Dict[str, Any]] = {
    # ── 日常打卡记录(auto 档:可逆、非医疗级、写错方向安全)────────────
    "water": {
        "create": {
            "tool": "health_record", "record_type": "water", "confirm": "auto",
            "via": "health_record(water) → POST /water/records/quick",
            "undo": "health_manage(delete water {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("water",),
                 "via": "health_query(water) → GET /water/records/me/date/{today}"},
        "list": {"tool": "health_manage", "record_type": "water",
                 "via": "GET /water/records/me"},
        "update": {"tool": "health_manage", "record_type": "water",
                   "via": "PUT /water/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "water",
                   "via": "DELETE /water/records/{id}"},
    },
    "diet": {
        "create": {
            "tool": "health_record", "record_type": "diet", "confirm": "auto",
            "via": "health_record(diet) → POST /diet/records",
            "undo": "health_manage(delete diet {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("diet",),
                 "via": "health_query(diet) → GET /diet/records/me/date/{today}"},
        "list": {"tool": "health_manage", "record_type": "diet",
                 "via": "GET /diet/records/me"},
        "update": {"tool": "health_manage", "record_type": "diet",
                   "via": "PUT /diet/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "diet",
                   "via": "DELETE /diet/records/{id}"},
    },
    "weight": {
        "create": {
            "tool": "health_record", "record_type": "weight", "confirm": "auto",
            "via": "health_record(weight) → POST /weight/records",
            "undo": "health_manage(delete weight {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("weight",),
                 "via": "health_query(weight) → GET /weight/records/me"},
        "list": {"tool": "health_manage", "record_type": "weight",
                 "via": "GET /weight/records/me"},
        "update": {"tool": "health_manage", "record_type": "weight",
                   "via": "PUT /weight/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "weight",
                   "via": "DELETE /weight/records/{id}"},
    },
    "blood_pressure": {
        "create": {
            "tool": "health_record", "record_type": "blood_pressure", "confirm": "auto",
            "via": "health_record(blood_pressure) → POST /blood-pressure/records",
            "undo": "health_manage(delete blood_pressure {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("blood_pressure",),
                 "via": "health_query(blood_pressure) → GET /blood-pressure/records/me"},
        "list": {"tool": "health_manage", "record_type": "blood_pressure",
                 "via": "GET /blood-pressure/records/me"},
        "update": {"tool": "health_manage", "record_type": "blood_pressure",
                   "via": "PUT /blood-pressure/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "blood_pressure",
                   "via": "DELETE /blood-pressure/records/{id}"},
    },
    "exercise": {
        "create": {
            "tool": "health_record", "record_type": "exercise", "confirm": "auto",
            "via": "health_record(exercise) → POST /daily-health/exercise",
            "undo": "health_manage(delete exercise {record_id})",
        },
        # exercise/workout 读 WorkoutRecord(Garmin 同步), manual_exercise 读
        # ExerciseRecord(手动录入) —— 见 _exec_health_query endpoint_map 注释。
        "read": {"tool": "health_query",
                 "dimensions": ("exercise", "workout", "manual_exercise"),
                 "via": "health_query(exercise|workout|manual_exercise)"},
        "list": {"tool": "health_manage", "record_type": "exercise",
                 "via": "GET /daily-health/exercise/me"},
        "update": {"tool": "health_manage", "record_type": "exercise",
                   "via": "PUT /daily-health/exercise/{id}"},
        "delete": {"tool": "health_manage", "record_type": "exercise",
                   "via": "DELETE /daily-health/exercise/{id}"},
    },
    "reminder": {
        "create": {
            "tool": "health_record", "record_type": "reminder", "confirm": "auto",
            "via": "health_record(reminder) → POST /reminders/me",
            "undo": "health_manage(delete reminder {record_id})",
        },
        # health_query 无 reminder dimension —— 读走 manage list(非 gap:同一数据面)。
        "read": {"tool": "health_manage", "record_type": "reminder",
                 "via": "health_manage(list reminder)"},
        "list": {"tool": "health_manage", "record_type": "reminder",
                 "via": "GET /reminders/me?status=all"},
        "update": {"tool": "health_manage", "record_type": "reminder",
                   "via": "PUT /reminders/{id}"},
        "delete": {"tool": "health_manage", "record_type": "reminder",
                   "via": "DELETE /reminders/{id}"},
    },
    "mood": {
        # 不在 AUTO 集 → 快路由 fail-closed 恒确认(=never_auto 语义)。
        # 已知洞:慢路径无 _confirm_or_describe(与 medication 修过的洞同类),
        # 见 spec 落地状态 #6。
        "create": {
            "tool": "health_record", "record_type": "mood", "confirm": "never_auto",
            "via": "health_record(mood) → POST /mood/records",
            "undo": "health_manage(delete mood {record_id})",
        },
        "read": {"tool": "health_manage", "record_type": "mood",
                 "via": "health_manage(list mood)"},
        "list": {"tool": "health_manage", "record_type": "mood",
                 "via": "GET /mood/records/me"},
        "update": {"tool": "health_manage", "record_type": "mood",
                   "via": "PUT /mood/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "mood",
                   "via": "DELETE /mood/records/{id}"},
    },

    # ── 手动身体记录:Agent 可新增,并复用 manage 做改删撤销 ──────────────
    "waist": {
        "create": {
            "tool": "health_record", "record_type": "waist", "confirm": "auto",
            "via": "health_record(waist) → POST /waist/records",
            "undo": "health_manage(delete waist {record_id})",
        },
        "read": {"tool": "health_manage", "record_type": "waist",
                 "via": "health_manage(list waist)"},
        "list": {"tool": "health_manage", "record_type": "waist",
                 "via": "GET /waist/records/me"},
        "update": {"tool": "health_manage", "record_type": "waist",
                   "via": "PUT /waist/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "waist",
                   "via": "DELETE /waist/records/{id}"},
    },
    "sleep": {
        "create": {
            "tool": "health_record", "record_type": "sleep", "confirm": "auto",
            "via": "health_record(sleep) → POST /sleep/records",
            "undo": "health_manage(delete sleep {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("sleep",),
                 "via": "health_query(sleep) → GET /garmin-analysis/me/sleep"},
        "list": {"tool": "health_manage", "record_type": "sleep",
                 "via": "GET /sleep/records/me"},
        "update": {"tool": "health_manage", "record_type": "sleep",
                   "via": "PUT /sleep/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "sleep",
                   "via": "DELETE /sleep/records/{id}"},
    },
    "excretion": {
        "create": {
            "tool": "health_record", "record_type": "excretion", "confirm": "auto",
            "via": "health_record(excretion) → POST /excretion/records",
            "undo": "health_manage(delete excretion {record_id})",
        },
        "read": {"tool": "health_manage", "record_type": "excretion",
                 "via": "health_manage(list excretion)"},
        "list": {"tool": "health_manage", "record_type": "excretion",
                 "via": "GET /excretion/records/me"},
        "update": {"tool": "health_manage", "record_type": "excretion",
                   "via": "PUT /excretion/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "excretion",
                   "via": "DELETE /excretion/records/{id}"},
    },

    # ── 症状/疾病(typed_only:打字免确认,语音/未声明通道确认前置)────────
    "symptom": {
        "create": {
            "tool": "health_record", "record_type": "symptom", "confirm": "typed_only",
            "via": "health_record(symptom) → POST /symptoms",
            "undo": "health_manage(delete symptom {record_id})",
        },
        "read": {"tool": "health_manage", "record_type": "symptom",
                 "via": "health_manage(list symptom)"},
        "list": {"tool": "health_manage", "record_type": "symptom",
                 "via": "GET /symptoms/me"},
        "update": {"tool": "health_manage", "record_type": "symptom",
                   "via": "PUT /symptoms/{id}"},
        "delete": {"tool": "health_manage", "record_type": "symptom",
                   "via": "DELETE /symptoms/{id}"},
    },
    "rhinitis": {
        # rhinitis 每日打卡 → HealthCheckin(按 checkin_date upsert,单条/日滚动),
        # 直接喂 RhinitisSpecialist(rhinitis_today)+ rhinitis_trend。旧设计每次打卡 mint
        # 一条 "鼻炎发作" illness_episode → 无界堆积 active 且喂不到 specialist,已弃用。
        # 遗留 鼻炎发作 episode 仍可经 illness 管理面收尾(不再新增)。
        "create": {
            "tool": "health_record", "record_type": "rhinitis", "confirm": "typed_only",
            "via": "health_record(rhinitis) → POST /checkin/(按 checkin_date upsert)",
            "undo": "前端打卡页 / health_checkin API 编辑当日打卡",
        },
        "read": {"tool": "health_manage", "record_type": "rhinitis",
                 "via": "health_manage(list rhinitis) → GET /checkin/me/history"},
        "list": {"tool": "health_manage", "record_type": "rhinitis",
                 "via": "GET /checkin/me/history"},
        "update": {"tool": "health_manage", "record_type": "illness",
                   "via": "遗留 episode:PUT /illness/episodes/{id}"},
        "delete": {"tool": "health_manage", "record_type": "rhinitis",
                   "via": "DELETE /checkin/{id}/rhinitis/latest"},
    },
    "illness": {
        "create": {
            "tool": "health_record", "record_type": "illness", "confirm": "never_auto",
            "via": "health_record(illness) → POST /illness/episodes",
            "undo": "health_manage(delete illness {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("illness",),
                 "via": "health_query(illness) → canonical illness read"},
        "list": {"tool": "health_manage", "record_type": "illness",
                 "via": "GET /illness/episodes/all"},
        "update": {"tool": "health_manage", "record_type": "illness",
                   "via": "PUT /illness/episodes/{id}"},
        "delete": {"tool": "health_manage", "record_type": "illness",
                   "via": "DELETE /illness/episodes/{id}"},
    },

    "life_event": {
        # 情景事件账本(2026-07-12,复用 HealthEpisode episode_type=life_event)。
        # 2026-07-13 founder 裁决升 AUTO·全通道:非医疗、L0、可逆的纯时间打点,
        # 恒确认违背时间线账本低摩擦初衷;undo 通路(list/delete)同批补齐
        # (spec §3.3:auto 写入必须有 undo)。update 不开——occurred_at 由
        # 确定性代码折算,改动走删除后重记。
        # 写入双路径:① agent 显式 health_record(event) ② 系统转后异步自动抽取
        # (services/life_event_extractor.py + tasks/life_event_extraction.py,
        #  派生写不算 agent 自由写;canonical record_type = "event")。
        "create": {
            "tool": "health_record", "record_type": "event", "confirm": "auto",
            "via": "health_record(event) → POST /episodes/life-event",
            "undo": "health_manage(delete event {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("events",),
                 "via": "health_query(events) → GET /episodes/me/life-events?days={days}"},
        "list": {"tool": "health_manage", "record_type": "event",
                 "via": "GET /episodes/me/life-events?days=30"},
        "update": {"gap": True,
                   "reason": "无 agent 改通路;occurred_at 由确定性代码折算,改动走删除后重记"},
        "delete": {"tool": "health_manage", "record_type": "event",
                   "via": "DELETE /episodes/life-event/{id}(user_id + episode_type=life_event 双过滤 fail-closed)"},
    },

    # ── 医疗级(never_auto:恒确认前置,spec §3.2)────────────────────────
    "medication": {
        "create": {
            "tool": "health_record", "record_type": "medication", "confirm": "never_auto",
            "via": "health_record(medication) 未注册自动建档 → POST /medication/medications",
            "undo": "health_manage(delete medication {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("medication",),
                 "via": "health_query(medication) → GET /medication/medications/me"},
        "list": {"tool": "health_manage", "record_type": "medication",
                 "via": "GET /medication/medications/me?active_only=false"},
        "update": {"tool": "health_manage", "record_type": "medication",
                   "via": "PUT /medication/medications/{id}"},
        "delete": {"tool": "health_manage", "record_type": "medication",
                   "via": "DELETE /medication/medications/{id}"},
    },
    "medication_log": {
        # 同一 health_record(medication) 通路:匹配/建档后写服药 log。
        "create": {
            "tool": "health_record", "record_type": "medication", "confirm": "never_auto",
            "via": "health_record(medication) → POST /medication/logs(status=taken)",
            "undo": "health_manage(delete medication_log {record_id})",
        },
        "read": {"tool": "health_manage", "record_type": "medication_log",
                 "via": "health_manage(list medication_log) → GET /medication/today/me"},
        "list": {"tool": "health_manage", "record_type": "medication_log",
                 "via": "GET /medication/today/me"},
        "update": {"tool": "health_manage", "record_type": "medication_log",
                   "via": "PUT /medication/logs/{id}"},
        "delete": {"tool": "health_manage", "record_type": "medication_log",
                   "via": "DELETE /medication/logs/{id}"},
    },

    # ── 补剂三兄弟 ─────────────────────────────────────────────────────────
    "supplement": {
        "create": {
            "tool": "health_record", "record_type": "supplement", "confirm": "auto",
            "via": "health_record(supplement) 名称匹配活跃定义 → POST /nfc/tap(action=supplement)",
            "undo": "health_manage(delete supplement {record_id})",
        },
        "read": {"tool": "health_query", "dimensions": ("supplements",),
                 "via": "health_query(supplements) → GET /supplements/me/stats"},
        "list": {"tool": "health_manage", "record_type": "supplement",
                 "via": "GET /supplements/me/records"},
        "update": {"tool": "health_manage", "record_type": "supplement",
                   "via": "PUT /supplements/records/{id}"},
        "delete": {"tool": "health_manage", "record_type": "supplement",
                   "via": "DELETE /supplements/records/{id}"},
    },
    "supplement_definition": {
        # spec §5 First Application:supplement 自动建档(镜像 medication 先例)。
        "create": {
            "tool": "health_record", "record_type": "supplement", "confirm": "auto",
            "via": "health_record(supplement) 查无活跃匹配 → 自动建档 POST /supplements/definitions",
            "undo": "health_manage(delete supplement_definition {record_id})",
        },
        "read": {"tool": "health_manage", "record_type": "supplement_definition",
                 "via": "health_manage(list supplement_definition)"},
        "list": {"tool": "health_manage", "record_type": "supplement_definition",
                 "via": "GET /supplements/me/definitions?active_only=false"},
        "update": {"tool": "health_manage", "record_type": "supplement_definition",
                   "via": "PUT /supplements/definitions/{id}"},
        "delete": {"tool": "health_manage", "record_type": "supplement_definition",
                   "via": "DELETE /supplements/definitions/{id}"},
    },
    "supplement_group": {
        # 批量打卡动作(按时段),非独立记录对象。不在 AUTO 集 → fail-closed 恒确认。
        "create": {
            "tool": "health_record", "record_type": "supplement_group", "confirm": "never_auto",
            "via": "health_record(supplement_group) → POST /nfc/tap(action=supplement_group, timing)",
        },
        "read": {"opt_out": "批量打卡动作,无独立记录;个体打卡见 supplement,定义见 supplement_definition"},
        "list": {"opt_out": "同 read:非独立记录对象"},
        "update": {"opt_out": "同 read:非独立记录对象"},
        "delete": {"opt_out": "同 read:非独立记录对象"},
    },

    # ── 触发动作/只读面 ────────────────────────────────────────────────────
    "garmin_sync": {
        # 同步触发动作,非记录对象。founder 2026-07-14 裁决 confirm=auto ——
        # 幂等读拉、无用户可见突变、可安全重复,不是不可逆写(R4 允许 agent 自动执行)。
        # 执行走专属异步分支 _trigger_garmin_sync:本地 precondition fail-loud →
        # Celery enqueue(sync_user_garmin_data)→ 乐观 ack,不再内联阻塞。
        "create": {
            "tool": "health_record", "record_type": "garmin_sync", "confirm": "auto",
            "via": "health_record(garmin_sync) → _trigger_garmin_sync → sync_user_garmin_data.delay()",
            # 幂等读拉,无写入产物可撤销;重复同步安全(upsert)。
            "undo": None,
            "undo_gap": "幂等读拉(登录+域限定 upsert+invalidate);下游推送/Episode 均去重、与定时 fan-out 同权,无新增不可逆写,无产物可撤销",
        },
        "read": {"opt_out": "同步结果经 wearable/garmin/activity 等维度读(见 health_query 对象)"},
        "list": {"opt_out": "同步触发动作,无独立记录可管理"},
        "update": {"opt_out": "同步触发动作,无独立记录可管理"},
        "delete": {"opt_out": "同步触发动作,无独立记录可管理"},
    },
    "medical_exam": {
        "create": {"opt_out": "化验/体检数值只走文件导入+LLM解析+人工核对管线,agent 不得代写数值(R4)"},
        # canonical read 层(health_read.read_medical_indicators, 与 Twin 同源)。
        "read": {"tool": "health_query", "dimensions": ("medical_exam",),
                 "via": "health_query(medical_exam) → canonical MedicalIndicator 读层"},
        "list": {"tool": "health_manage", "record_type": "medical_exam",
                 "via": "GET /medical-exams/me/reports"},
        "update": {"opt_out": "数值修正走人工核对管线,不开放 agent 改"},
        "delete": {"opt_out": "体检报告不开放 agent 删除"},
    },
    "genetic_profile": {
        "create": {"opt_out": "基因数据只能走文件导入+人审,agent 不得代写(spec §3.1 示例)"},
        "read": {"tool": "health_query",
                 "dimensions": ("genetic", "genetic_cognitive",
                                "genetic_personality", "genetic_comprehensive"),
                 "via": "health_query(genetic*) → GET /genetic/variants/me 等"},
        "list": {"tool": "health_query",
                 "via": "health_query(genetic) 即全量变异列表"},
        "update": {"opt_out": "基因档案不开放 agent 修改"},
        "delete": {"opt_out": "基因档案不开放 agent 删除(隐私 Tier 最高,删除走账号级流程)"},
    },
    "health_query": {
        # 共享只读分析面(task #43 (d)):不属于单一对象的聚合/可穿戴分析维度挂这里。
        # wearable/garmin 是 canonical 读层(health_read._WEARABLE_DIMS)的别名维度。
        # 声明式批查询 health_query_batch(Slice 1)复用同一套 dimension + 数据面
        # (services/health_query_batch.py),只读、无新对象/新维度,故不单列条目。
        "create": {"opt_out": "聚合分析视图,只读"},
        "read": {"tool": "health_query",
                 "dimensions": ("comprehensive", "heart_rate", "hrv", "activity",
                                "spo2", "spo2_sleep_correlation", "body_battery",
                                "stress", "wearable", "garmin"),
                 "via": "health_query(各分析维度) → garmin-analysis / spo2 / canonical wearable 读层"},
        "list": {"opt_out": "聚合分析视图,只读"},
        "update": {"opt_out": "聚合分析视图,只读"},
        "delete": {"opt_out": "聚合分析视图,只读"},
    },
    # ── 专属工具对象(通用三件套之外,如实登记)──────────────────────────
    "intervention_cycle": {
        "create": {
            "tool": "intervention_cycle", "confirm": "never_auto",
            "via": "intervention_cycle(action=start) — 显式 confirmed=true 恒确认",
        },
        "read": {"tool": "intervention_cycle",
                 "via": "intervention_cycle(action=status)"},
        "list": {"tool": "intervention_cycle",
                 "via": "intervention_cycle(action=list) / GET /intervention-cycles"},
        "update": {
            "tool": "intervention_cycle", "confirm": "never_auto",
            "via": "intervention_cycle(action=update) / PATCH /intervention-cycles/{id}",
        },
        "delete": {
            "tool": "intervention_cycle", "confirm": "never_auto",
            "via": "intervention_cycle(action=cancel) / POST /intervention-cycles/{id}/cancel",
        },
    },

    "goal": {
        "create": {
            "tool": "health_record", "record_type": "goal", "confirm": "typed_only",
            "via": "health_record(goal) → POST /goals",
            "undo": "health_manage(delete goal {record_id})",
        },
        "read": {"tool": "health_manage", "record_type": "goal",
                 "via": "health_manage(list goal) / GET /goals/{id}"},
        "list": {"tool": "health_manage", "record_type": "goal",
                 "via": "GET /goals/me"},
        "update": {"tool": "health_manage", "record_type": "goal",
                   "via": "PUT /goals/{id}"},
        "delete": {"tool": "health_manage", "record_type": "goal",
                   "via": "DELETE /goals/{id}"},
    },
    "remember": {
        # 无结构化类型的个人属性/事实(鞋码/衣码/喜好/习惯等)→ MemoryFact 三元组(可召回)。
        # 补齐"档案属性"缺口:此前小巴主动说"补充进档案"却无工具可写, 用户给了值也 0 工具调用。
        "create": {
            "tool": "health_record", "record_type": "remember", "confirm": "typed_only",
            "via": "health_record(remember) → POST /memory-facts(写 MemoryFact 三元组)",
            "undo": "POST /memory-facts/{id}/dismiss(用户标记'这条不对', soft-delete)",
        },
        # 记忆事实经 memory 面(GET /memory-facts/me + 记忆 UI)读写, 暂无 health_manage/
        # health_query 通路, 显式挂账为 gap(诚实盘点, 不假装有 agent CRUD 通路)。
        "read": {"gap": True, "reason": "读取走 GET /memory-facts/me + 记忆 UI, 非 health_query dimension"},
        "list": {"gap": True, "reason": "同 read:/memory-facts/me"},
        "update": {"gap": True, "reason": "记忆用 supersede/reinforce 语义, 非 health_manage update"},
        "delete": {"gap": True, "reason": "soft-delete 走 POST /memory-facts/{id}/dismiss, 非 health_manage delete"},
    },
}


def get_agent_ops(object_type: str) -> Dict[str, Any] | None:
    return AGENT_OPS.get(str(object_type or "").strip())


def registry_violations() -> list[str]:
    """结构校验:返回违反条目 schema 的问题清单(CI 闸第一道)。"""
    violations: list[str] = []
    for obj, ops in AGENT_OPS.items():
        if not isinstance(ops, dict):
            violations.append(f"{obj}: expected dict")
            continue
        if "opt_out" in ops or ops.get("gap") is True:
            reason = ops.get("opt_out") or ops.get("reason")
            if not (isinstance(reason, str) and reason.strip()):
                violations.append(f"{obj}: 整对象 opt_out/gap 必须给非空理由")
            continue
        missing = [op for op in OPS if op not in ops]
        if missing:
            violations.append(f"{obj}: 缺操作格 {missing}(五格每格要么有通路、要么 opt_out/gap,spec §3.4)")
        for op in OPS:
            entry = ops.get(op)
            if entry is not None:
                violations.extend(_entry_violations(obj, op, entry))
    return violations


def _entry_violations(obj: str, op: str, entry: Any) -> list[str]:
    v: list[str] = []
    path = f"{obj}.{op}"
    if not isinstance(entry, dict):
        return [f"{path}: expected dict"]
    if "opt_out" in entry:
        if not (isinstance(entry["opt_out"], str) and entry["opt_out"].strip()):
            v.append(f"{path}: opt_out 理由必须非空")
        return v
    if entry.get("gap") is True:
        if not (isinstance(entry.get("reason"), str) and entry["reason"].strip()):
            v.append(f"{path}: gap 必须带非空 reason")
        return v
    tool = entry.get("tool")
    if not (isinstance(tool, str) and tool.strip()):
        v.append(f"{path}: 通路条目必须有 tool")
    if not (isinstance(entry.get("via"), str) and entry["via"].strip()):
        v.append(f"{path}: 通路条目必须有 via")
    if op == "create":
        confirm = entry.get("confirm")
        if confirm not in CONFIRM_TIERS:
            v.append(f"{path}: confirm 必须 ∈ {sorted(CONFIRM_TIERS)}(got {confirm!r})")
        if tool == "health_record" and not entry.get("record_type"):
            v.append(f"{path}: health_record create 必须给 record_type")
        if confirm in ("auto", "typed_only"):
            undo = entry.get("undo")
            undo_gap = entry.get("undo_gap")
            if not (
                (isinstance(undo, str) and undo.strip())
                or (isinstance(undo_gap, str) and undo_gap.strip())
            ):
                v.append(f"{path}: auto/typed_only 写入必须有 undo 通路或显式 undo_gap 理由(spec §3.3)")
    if op == "read" and tool == "health_query":
        dims = entry.get("dimensions")
        if not (
            isinstance(dims, tuple)
            and dims
            and all(isinstance(d, str) and d.strip() for d in dims)
        ):
            v.append(f"{path}: health_query read 必须给非空 dimensions tuple")
    if op in ("list", "update", "delete") and tool == "health_manage":
        if not entry.get("record_type"):
            v.append(f"{path}: health_manage {op} 必须给 record_type(manage 映射键)")
    return v
