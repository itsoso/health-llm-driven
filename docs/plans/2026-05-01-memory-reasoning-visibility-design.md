# 记忆与推理可见化 — v1 设计 (2026-05-01)

**状态**: 设计已批准, 待 writing-plans 拆实现步骤
**作者**: itsoso + Claude
**上下文**: 刚 ship 观察期看板 (2e1939d), STRATEGY §七 优先级 #3/#4 前置完成

---

## 1. 范围 & 非目标

### 要做的三件事 (候选 B: 主力记忆/推理, 另外两条各一个最小动作)

1. **Journal Timeline v1** — Mobile Journal tab 从扁平列表改为 case-thread 分组 timeline. 按 theme 聚合 (高血压/鼻炎/周度摘要…), 点 thread 展开内部 SOAP 按日期降序.
2. **Reasoning Trace 抽屉 v1** — Mobile 主屏 Safety 告警卡 + Specialist finding 卡 加"为什么"按钮. 点击弹底部抽屉, 展示 `rule_name / rule_category / 触发的 Twin 分区字段 / 相关 MemoryFact (最多 3 条)`.
3. **Specialist 命中详情页 v1** — 新路由 `mobile/specialist/[name].tsx`. 展示近 30 天该 specialist 产的 ActionCard + accuracy_score + 实际 vs 预期对比. Hero 主屏加入口 chip.

### 附赠的两条线最小动作

4. Admin 看板加 "Celery beat 健康" 区块 (约 1 天).
5. 信任循环信号浮到主屏: `TrustHintChip` tooltip 展示 specialist 近 30 天 hit-rate.

### 明确不做 (YAGNI)

- KG fact 列表页 (查询频次低, 等数据说有需求)
- Reasoning trace 全量可回放 / 时间旅行 (只做"当场解释一次")
- Web 端任何新 UI (按 CLAUDE.md: iPhone/iPad 原生只走 RN)
- Sentry 接入 (和本次 scope 无关, 留后)
- 新 DB 表 / Twin schema 改动 (全是读模型)

---

## 2. 架构 & 组件

### 新增 / 修改文件 (最小面)

```
backend/
  app/api/reasoning_trace.py          ← 新: POST /reasoning/explain
                                        body: {source, ref_id, user_id}
                                        resp: {rule, twin_evidence, related_facts}
  app/api/journal.py                  ← 扩: GET /journal/timeline?days=30
                                        resp: [{thread_id, theme, entries:[...]}]
  app/api/specialists.py              ← 新: GET /specialists/{name}/scorecard?days=30
  app/services/reasoning_explainer.py ← 新: 从 audit_log + Twin + MemoryFact 拼 trace (不调 LLM)
  app/services/celery_health.py       ← 新: 读 agent_audit_log + NotificationLog 近 24h 推算

mobile/
  app/(tabs)/journal.tsx              ← 重构: 列表改 timeline 分组
  app/specialist/[name].tsx           ← 新: scorecard 详情页
  components/reasoning/
    ExplainButton.tsx                 ← 新: 挂 Safety/Specialist 卡片的入口
    ExplainSheet.tsx                  ← 新: 底部抽屉 (reanimated)
  components/home/TrustHintChip.tsx   ← 新: hit-rate tooltip
  hooks/useReasoningTrace.ts          ← 新
  hooks/useJournalTimeline.ts         ← 新
  hooks/useSpecialistScorecard.ts     ← 新

frontend/
  src/app/admin/components/
    CeleryHealthBlock.tsx             ← 新: Observability tab 追加
```

### 为什么不拆新 service 层

三个新 API 的数据源全是现成表: `agent_audit_log / action_cards / clinical_journal_entries / memory_facts / case_threads`. 不新建表, 不改 Twin schema, 不调 LLM. 纯读模型.

### Day-by-Day 依赖

```
Day 1-2  reasoning_explainer + api/reasoning_trace + ExplainSheet
Day 3    集成到主屏 Safety/Specialist 卡片
Day 4-5  journal/timeline API + Mobile journal tab 重构
Day 6-7  specialist/scorecard API + 详情页 + Hero chip
Day 8    TrustHintChip 主屏 tooltip + Admin Celery Health block
Day 9    eval suite 补 reasoning trace grounding 测试
Day 10   真机冒烟 + EAS OTA preview + 观察期看板新区块验证
```

10 天 ≤ 2 周, 留 4 天 bug/buffer.

---

## 3. 数据流 & API 契约

### 3.1 Reasoning Trace API

```
POST /api/v1/reasoning/explain
Body: { "source": "safety" | "specialist",
        "ref_id": int,         // alert audit_id 或 finding_id
        "user_id": int }       // JWT 自动校验归属
```

响应:
```json
{
  "source": "safety",
  "summary": "Recovery Coach: readiness=54 (偏低)",
  "rule": {
    "name": "acute_hrv_drop",
    "category": "vitals",
    "threshold": "HRV < 30 且环比 -40%",
    "code_path": "agents/safety_guardian/rules/vitals.py:L187"
  },
  "twin_evidence": [
    {"partition": "physiological", "field": "hrv", "value": 28,
     "at": "2026-05-01T07:32:00+08:00", "source": "garmin", "freshness_hours": 1.2}
  ],
  "related_facts": [
    {"subject": "user", "predicate": "experienced", "object": "poor_sleep",
     "tier": "episodic", "confidence": 0.85, "last_seen": "2026-04-30"}
  ],
  "confidence_note": "基于 1 条 Garmin 读数 + 1 条记忆事实"
}
```

**实现**: `reasoning_explainer.py` 是 dict builder. agent_audit_log → rule → Twin 分区反查 → MemoryFact top-K (BM25 已就位). **不调 LLM**.

### 3.2 Journal Timeline API

```
GET /api/v1/journal/timeline?days=30&theme=*
```

```json
{
  "threads": [
    {
      "thread_id": 12, "theme": "鼻炎管理", "status": "active",
      "entry_count": 5, "last_updated": "...",
      "entries": [
        {"id": 102, "generated_at": "...", "created_by": "orchestrator",
         "subjective_short": "晨起鼻塞...", "has_soap": true}
      ]
    },
    {"thread_id": null, "theme": "无主题", "entries": [...]}
  ]
}
```

`subjective_short` 截 60 字, 详情点 `journal/[id]`.

### 3.3 Specialist Scorecard API

```
GET /api/v1/specialists/{name}/scorecard?days=30
```

```json
{
  "specialist": "recovery_coach",
  "window_days": 30,
  "proposed_count": 12, "graded_count": 8,
  "hit_rate": 0.625, "avg_accuracy": 71.3,
  "cards": [
    {"id": 334, "title": "今晚 22:30 前入睡",
     "metric_key": "sleep_score", "target_value": "78",
     "actual_value": "81", "accuracy_score": 90,
     "adherence_kind": "device", "adherence_confidence": 85,
     "why_short": "提前入睡 42 分钟, 睡眠评分超目标"}
  ]
}
```

`why_short` 复用已有 `grading_notes` 字段.

### 3.4 Celery Health (Admin Observability)

Observability tab 新增 block, 读现有日志间接推算, 5 个任务硬编码:

```json
{
  "tasks": [
    {"task": "open_loop_daily_briefing", "expected_per_day": 1,
     "observed_24h": 1, "last_run": "...", "status": "ok"},
    {"task": "outcome_grader", "expected_per_day": 1,
     "observed_24h": 0, "last_run": "2026-04-28", "status": "stale"},
    {"task": "doctor_weekly_report", "expected_per_week": 1,
     "observed_7d": 1, "status": "ok"}
  ]
}
```

### 3.5 错误 & 边界

| 场景 | 处理 |
|---|---|
| ref_id 找不到 alert/finding | 404 + "过期或无权限" |
| JWT user_id ≠ 资源 owner | 403 (不泄露 "存在但无权") |
| 用户没基因 / 没 Garmin | twin_evidence=[], confidence_note="数据不足" |
| MemoryFact BM25 > 500ms | 截断 related_facts=[], log warn 不阻塞 |
| Specialist 名字错 | 404 + 列出合法 names |
| Celery health 读日志空 | 每任务单独降级 status="no_data" |

---

## 4. 风险、测试、成功判据

### 4.1 风险清单

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | Reasoning trace 对老 audit 拼不出来 | 高 | 抽屉空信任受损 | fallback: 永远至少 1 条 twin_evidence; related_facts 空显示"基于确定性规则, 无记忆关联" |
| R2 | Journal timeline 对单用户稀疏 | 中 | 空荡观感 | 无 thread 的 SOAP 归入"周度摘要 / 其他"隐式 bucket; 空态引导去对话 |
| R3 | /reasoning/explain 冷查询 >500ms | 中 | 抽屉卡顿 | 抽屉先渲染 rule+twin_evidence, related_facts 单独 Suspense 懒加载 |
| R4 | 三方向 PR 多, merge 冲突 | 中 | review 疲劳 | Day 1-10 串行 ship, 每切片独立 commit + OTA |
| R5 | Specialist scorecard 对新用户 0 命中 | 高 | 详情"暂无数据" | proposed_count<3 时隐藏入口; 详情页写清楚需要 outcome_grader 累积 |
| R6 | Celery health 硬编码误报 | 中 | 看板噪声 | ratio<0.5 或 >2 才标红; 中间灰色 "观察中"; 文案注明推算方法 |
| R7 | OTA 后卡顿 / 白屏 | 低 | 使用受阻 | 每切片 preview → 自己真机 1 晚 → production; EAS rollback 备好 |

### 4.2 测试计划

**后端** (pytest, 单轮 ≤ 5s):

| 文件 | 要点 | 条数 |
|---|---|---|
| test_reasoning_explainer.py | 空 audit → 200+evidence=[]; 有 audit → rule 字段齐; MemoryFact 超时 mock → related_facts=[] 不抛; 跨用户 → 403 | 6 |
| test_journal_timeline_api.py | 空库 schema; 3 thread + 1 无主题 → 4 组; days=30 过滤; subjective_short 截断 60 字 | 4 |
| test_specialist_scorecard_api.py | 空 → 0/0; 混合 graded; 非法 name → 404 | 4 |
| test_celery_health.py | ok/stale/no_data 各一 | 3 |

**硬约束**: reasoning_explainer 不依赖 LLM, 测试跑真 DB fixture.

**Mobile** (无单测, 真机冒烟):
- Day 3 主屏 ExplainSheet × Safety/Specialist 各一次
- Day 5 Journal tab × 空用户 / 有 thread 各一次
- Day 7 Specialist 详情页 × 有命中 / 零命中
- Day 10 EAS preview → production 前跑一遍所有主屏 tab

**前端**: Admin Celery Health mock 3 种 status (vitest 1 条).

### 4.3 观测

部署当天起往观察期看板加 3 条新 suggestion:

```
🟢/🟡/🔴 Reasoning Trace 点击率:  N/M (目标 >20%)
🟢/🟡/🔴 Journal Timeline 进入率: N/M
🟢/🟡/🔴 Specialist 详情页进入率: N/M
```

埋点复用 `interaction_feedback` 表扩 `event_type`, 不新表.

### 4.4 成功判据 (2 周后回看)

**硬指标**:
- [ ] 7 天内产品 owner 在主屏点 ≥ 5 次"为什么"
- [ ] 7 天内 Journal tab 进入 ≥ 10 次
- [ ] Specialist 详情页出现过 "actual vs target" 印象深刻的瞬间

**软指标**:
- 至少一次"看推理链发现 AI 错了, 回头改规则/prompt"
- 至少一条 Celery Health 告警揪出真 stale 任务
- 不出现"点开按钮一片空白"超过 2 次

**止损条件**:
- Day 7 点击率 <5% → 停做 Specialist 详情页, 回头重想交互
- R6 导致看板噪声大 → 直接隐藏该 block

---

## 5. 下一步

由 writing-plans 拆为 Day 1-10 的实现步骤清单.
