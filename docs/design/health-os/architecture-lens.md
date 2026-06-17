# Health OS — 架构透镜(OS 部件 → 仓库实现 → 状态)

> **这是透镜/索引,不是新规格。** 权威细节看:产品 = [`docs/prd/reva-personal-health-os-prd.md`](../../prd/reva-personal-health-os-prd.md);
> 手表 = [`docs/plans/2026-06-16-apple-watch-health-opportunities-roadmap.md`](../../plans/2026-06-16-apple-watch-health-opportunities-roadmap.md)(v2 已有完整 OS 定调 + 三铁律 + 护城河序列);
> 战略 = [`memory project_enter_key_leverage_thesis`] + [`docs/rfc-agent-native-health-os.md`](../../rfc-agent-native-health-os.md);
> 手表执行器 = [`docs/design-watch-action-complete.md`](../../design-watch-action-complete.md) / [`docs/design-watch-voice-symptom.md`](../../design-watch-voice-symptom.md)。
>
> 本文只做一件别处没有的事:**把「OS 部件」对到「仓库里真实的模块 + 当前状态」**,一眼看出**唯一真缺的层**。
> 2026-06-17 编;Codex 的手表能力已并入下表(标注 commit)。

## 把它当真·OS:每个部件都有健康对应物

| OS 部件 | 健康 OS 对应 | 仓库实现 | 状态 |
|---|---|---|---|
| **内核 / 状态(kernel)** | Digital Twin(14 语义分区统一真相)+ per-user 因果账本 | `app/twin/`(schema/builder/cache/formatter);多源合并 `services/device_source_priority.py`(优先级 + 单位/合理性护栏 + 静息 HR 用 AW+RingConn) | ✅ 稳 |
| **对象模型** | HealthProblem → HealthProgram(8-12 周容器)→ HealthProtocol(机制+默认)→ HealthAgendaItem(今日执行)→ ExecutionEvent(双轨完成) | `models/health_protocol.py` 等;`services/health_protocol_service.py`、`agenda_service.py` | ✅ 有(PRD §对象层) |
| **调度器(scheduler)** | 一天的**时间线脊柱**(什么时候做什么)= 唯一组织原则 | `services/today_timeline_service.py`(`/timeline/today`)· `services/action_ranker.py`(按 上游性×可执行×频次×可验证 排 top_action) | ✅ 有,首页/腕上都已以它为主线 |
| **进程(processes)** | Agent 舰队:13 specialist 读 twin、产出结构化 Finding | `app/agents/*` + `app/orchestrator/*` | ✅ 有 |
| **I/O · 输入(sensors)** | Garmin / Apple Watch / RingConn / CGM / 化验 / 基因 / 环境;被动采集哨兵 | HealthKit import(source-aware)· `services/baseline_deviation_sentinel.py`(静息 HR 个人基线 z-score 漂移→归因候选,**纯后端 0 UI**,commit fb3aedc2) | ✅ 输入稳;被动哨兵起步 |
| **I/O · 输出(syscall / actuator)** | **Write 层**:替你改日历/提醒/购物车/菜单 | 局部:本地通知(`useBehaviorLoopReminders`/吃药提醒)= 弱执行;**Agent 主动写 + 分级授权 = 缺** | ❌ **唯一真缺的层** |
| **权限(permissions)** | 分级信任:外环复测 CI 收敛才升级自治权 | 原语在 `services/intervention_significance.py`(R16 RCV+置信度);**没接到 Write 层** | 🟡 原语有,未接 |
| **安全态(MMU/陷阱)** | SafetyGuardian 59 条确定性规则 = Write 的速度上限 | `app/agents/safety_guardian/*`;腕上语音症状直通确定性裁决(fail-loud + fail-safe advisory,commit 059e9961) | ✅ 强 |
| **Shell · 多端表面** | 手表=常驻/抬腕层(执行+被动采集)· 手机=控制台 · Mac/Web=深析 | 见下「手表 = OS 主表面」 | 🟡 各端在,手表层成形中 |

**一句话**:内核(twin)+ 对象模型 + 调度器(时间线)+ 进程(agent)+ 安全态都已就位;**唯一从「工具」跨到「OS」要新建的真东西,是 Write 层 syscall + 把权限层接上去**(= Enter 键)。其余都是重排现有积木。

## 手表 = OS 的主表面(Codex 已实现的能力)

手表不是"再来一块体征表盘",而是 OS 的**常驻执行器 + 被动采集器**(roadmap v2 §0 三铁律)。已落地:

| 能力 | commit | 行为 | 文件 |
|---|---|---|---|
| **Complication = 时间线脊柱** | 1c70c273 | 表盘一眼「下一项该做什么 + readiness 灯 + 待办数」,不开 app 就知道现在干嘛 | `WatchComplication/RevaComplication.swift` · `ComplicationState/Cache` |
| **到点项一键完成 + 依从回写 + 埋点** | 143902bf | 腕上点完成 → 完成 HealthProtocol → 写 MedicationLog/SupplementRecord(幂等 UniqueConstraint+原子 UPDATE)→ 发 `watch_action_completed` 事件喂因果账本 | `api/watch.py` POST `/watch/actions/{id}/complete` · `WatchEventClient.swift` |
| **运动/活动项可腕上完成** | 05fe97b9 | training/activity/exercise 进 `watchCompletableKinds` | `WatchSummary.swift` |
| **跳过 + due 列表** | 573a4256 | 「带理由跳过」+ due_items 喂 Smart Stack | POST `/watch/actions/{id}/skip` |
| **腕上语音记症状 → SafetyGuardian** | 059e9961 | 一句话报症状 → SymptomEntry 进时间线 → 确定性裁决(R4 不诊断、critical 真命中才升级、评估失败 fail-loud 注入就医 advisory) | POST `/watch/symptoms` |
| **静息 HR 漂移哨兵** | fb3aedc2 | 被动:偏离个人基线 → 归因候选进 agenda(措辞红线:只说偏离不说病因) | `baseline_deviation_sentinel.py` |
| **top action 杠杆排序** | e2863b37 | 按 上游性/可执行/频次/可验证 排 top_action + leverage_score/priority_tier | `action_ranker.py` |

**后端 watch API**:`GET /watch/summary`(状态灯+top_action+due_items+quick_actions+push_items,R15 推送≤3)· POST `/watch/actions/{id}/complete|skip` · POST `/watch/symptoms`。腕上不持 token,经 iPhone bridge 中继;user_id 一律取自 token(不信任客户端,IDOR 安全)。

## 代码评审结论(2026-06-17)

Codex 的手表后端**质量高、可信**:① 正确规避 `build_twin`(用极简 twin + `_fill_problem_red_lines(raise_on_error=True)` 走 request db,符合 build_twin-SessionLocal 教训);② 全程 fail-loud(`evaluation_failed` + 注入 fail-safe advisory,不靠客户端读 flag,符合 safety-swallow 教训);③ 完成回写幂等(UniqueConstraint + 原子 UPDATE);④ IDOR 守卫。**一处 cosmetic 小瑕**:`watch.py:100` `written` 标签对未知 `source_model` 默认 `"none"`——只是响应里的标签可能不准(真实回写在 `complete_item` 内,不受影响),非静默漏写;新增协议域时给个非 "none" 的兜底标签即可。

## 下一刀(按本透镜的「唯一真缺」)

1. **Write 层 syscall(最高战略,= Enter 键)**:Agent 提出写意图(先「自动加日历/复查提醒」)→ 落「写意图账本」待一键确认 → 跑稳后按权限层(R16 CI 收敛)逐类升级到自治。安全带(SafetyGuardian)是速度上限。
2. **被动采集闭环(已落地 v0)**:高置信度 `HealthEvent` 可通过 `EventSource.config.health_protocol_id` 或唯一被动协议匹配 → 写 `HealthProtocolEvent.status=auto_observed` → Watch 待办自动消失、Timeline 完成数计入;低置信度与跨用户协议不自动闭环。
3. **手表表面收尾**(Codex 在推):R18★2 nudge 屏 + Smart Stack 卡 + Double-Tap 单手确认。
4. **freshness 上腕**:watch_summary 标注数据新鲜度(同首页就绪分守卫),昨晚没同步腕上也显示「待同步」而非旧值。

> 分工建议(并发):**手表表面归 Codex,Write 层 / 后端内核归本线**,减少同文件冲突。
