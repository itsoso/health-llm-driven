# 产品其他改进空间盘点与规划(跳出抗衰垂直)

> 状态:规划草案 · 2026-06 · 基于 main(抗衰 MVP+Phase2+Phase3飞轮 已上线)
> 视角:抗衰垂直已建成一套**可复用范式**(测量→主动→闭环→群体证据→飞轮)。本文盘点
> **这条垂直之外**的产品改进空间,分四类,给优先级与第一刀。

---

## 0. 一个判断:抗衰是「模板」,不是「孤岛」

抗衰子系统沉淀出的范式(PhenoAge 算子 + 主动监测 + N-of-1 闭环 + 群体证据 + 飞轮),
**对整个产品是可复用资产**。所以最大的改进空间不是再加垂直,而是:
① 把这套范式**泛化到全产品**;② 补齐**横切赋能**(让所有 Agent 更准/更省/可观测);
③ 抓**增长/激活/留存**(产品的根);④ 还**工程债**(复杂度)。

---

## 1. 改进空间盘点(四类)

### A. 范式泛化(把抗衰打法复制到其他能力)
- **主动化推广**:`longevity_watch` 证明了"事件驱动主动 Agent"模式,但目前只服务抗衰。
  代谢(metabolic)、恢复(recovery)、安全(safety)同样能做"异常/改善→主动提醒→提 N-of-1"。
  现状:beat 里仅约 5 个 specialist 级主动任务,主动化覆盖面窄。→ 推广 RFC 方向三到全 specialist。
- **群体证据泛化**:`longevity_cohort_service` 现在只聚合生物年龄 metric;同一套去标识聚合
  可服务所有 outcome metric(weight/bp/hba1c/hrv…)→「群体里这个干预对这类人有效吗」全产品可用。

### B. Agent-Native 横切赋能(RFC 未完方向)
- **方向九 · eval/可观测看板(P0)**:现在只有埋点(`agent_audit_log` + W6 longevity 触发),**没有看板**。
  主动推送命中率/接受率、闭环评分准确率、specialist 命中率、memory 引用率——数据都在,缺聚合视图。
  这是所有主动化/飞轮**扩规模的前提**(不可观测就不敢放量)。复用 `admin_slo`/`admin_observability`。
- **方向十 · 成本/延迟(P1)**:已有 `perf_breakdown` 埋点 + `model_registry` 多模型;
  缺"按任务分级路由"(抗衰/安全用强模型,闲聊用便宜模型)+ orchestrator 耗时 attribution 看板。
- **方向二 · 因果记忆(P1)**:`LongitudinalAnalyst` 有趋势,但"上次你血糖高是因为聚餐"这类
  事件×指标因果记忆未系统沉淀进 memory,导致主动提醒缺"为什么"。
- **方向八 · 多模型 panel(P2)**:高风险裁决(safety/危机)多模型投票,降低单模型幻觉风险。

### C. 增长 / 激活 / 留存(产品的根)
- **Onboarding → first-outcome 漏斗**:北极星是"完成 ≥1 个闭环且改善的用户",但从注册到
  第一个 outcome 的转化**没有系统埋点+优化**。这是增长的命脉(对应 `onboarding` 路由已有,缺漏斗度量)。
- **留存循环**:主动 Agent 的"打扰预算"目前是固定阈值;应按用户反馈自适应(推多了流失,推少了无感)。
- **跨端 parity**:mobile 路由数已不少(84),但 deep-analytics 深度仍落后 web;按 CLAUDE.md
  feature-parity 表,daily-driver 指标补齐 RN,低频分析留 web。

### D. 工程健康(复杂度债)
- **120 个文件 > 500 行**,其中 4 个 > 2000:`garmin_connect.py`(2858)、`agent_executor.py`(2817)、
  `system_knowledge_service.py`(2552)、`genetic_data.py`(2170)。`orchestrator.py`(1795)、`notifications.py`(2043)也偏大。
- 原则(CLAUDE.md 复杂度预算):不强制重写,但"**下次碰这个文件顺手拆**";新功能禁止往 1000+ 行堆。
- `agent_executor.py` / `orchestrator.py` 是热点,最该优先拆(改动频繁 × 体积大 = 风险)。

---

## 2. 优先级矩阵

| 改进项 | 价值 | 成本 | 纯代码? | 优先级 |
|---|---|---|---|---|
| eval/可观测看板(方向九) | 高(扩规模前提) | 中 | ✅ | **P0** |
| 主动化推广(metabolic/recovery/safety) | 高 | 中 | ✅ | P0 |
| 群体证据泛化(全 metric) | 中高 | 低 | ✅ | P1 |
| 成本/延迟分级路由(方向十) | 中(省钱) | 中 | ✅ | P1 |
| first-outcome 漏斗埋点 | 高(增长) | 低 | ✅ | P1 |
| 因果记忆(方向二) | 中 | 高 | ✅ | P2 |
| 跨端 parity 补齐 | 中 | 中 | ✅ | P2 |
| 复杂度债拆分(agent_executor/orchestrator) | 中(降风险) | 中 | ✅ | 随手做 |
| 多模型 panel(方向八) | 中 | 高 | ✅ | P2 |

---

## 3. 推荐第一刀:eval / 可观测看板(方向九)

**为什么是它**:主动化(longevity_watch 已上线、即将推广)+ 飞轮一旦放量,**不可观测 = 不敢放量、骚扰用户而不自知、烧钱不自知**。它是所有后续扩规模的"仪表盘",且:
- 纯代码、数据已在(`agent_audit_log`:safety/orchestrator/specialist/memory/longevity_watch 都已埋点)
- 复用 `admin_slo` / `admin_observability` 既有通道
- 一次建成,服务全产品(不只抗衰)

**最小切面**:admin 看板聚合——① 主动推送 命中/接受率(longevity_watch + 未来推广的)② 闭环评分 improved/worsened 分布 ③ specialist 命中率 ④ orchestrator p50/p95 耗时(perf_breakdown 已埋)。去标识、只读。

之后 P0 第二刀:把主动化范式推广到 metabolic/recovery(复用 longevity_watch 的跨快照 diff 模式)。

---

## 附:诚实声明
本文基于 2026-06 main 实际 survey(120 文件 >500 行、四个 >2000 的具体文件、beat 主动任务约 5 个、mobile 84 路由均现场统计;RFC 方向编号对应 `docs/rfc-agent-native-health-os.md`)。优先级是工程判断,非承诺;增长类(漏斗/留存)的真实提升需线上数据验证,代码只是埋点与实验框架。复杂度债"随手拆"是默认姿势,非集中重写计划。
