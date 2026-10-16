# Dossier: 用药提醒落地页重设计

| 字段 | 值 |
|---|---|
| slug | medication-reminder-landing |
| 创建日期 | 2026-10-16 |
| 当前阶段 | S5 |
| 状态 | building |
| 负责 | unified publishing session |
| 反馈环 | synthetic tests / simulator / backend / trusted OTA |

## S0 · 用户需求
> 重新设计用药提醒的landing页面

用户已有持续实现与部署授权；本次沿用，不重复请求批准常规可逆实现。

## S1 · Discovery
- mobile/services/notificationRoutes.ts:62 当前把用药通知落到 /medications，丢失剂次。
- mobile/services/medicationReminders.ts 本地重复通知没有日期，不能从点击推断服药日期。
- backend/app/tasks/notifications.py 远端带 scheduled_date/time/timezone。
- backend/app/api/medication.py 与 services/medication_service.py 提供本人药品详情和唯一日期/时间日志；today API 无历史剂次读取能力。
- 当前截图存在指令式条目；本需求只保护快捷操作，不删除历史数据。
- System Map selector services/notificationRoutes 未索引；源码与邻近测试调查，system-map-check 已通过。

## G1 · 准入
- **裁决**: PASS；HealthAgendaItem → 手动确认 → ExecutionEvent；medical_boundary，manual_confirm。
- 用户直接要求重新设计；范围与持续授权一致。

## S2 · PRD / S3 · 规划
- 合并 spec/plan: docs/specs/2026-10-16-medication-reminder-landing.md
- 四任务 T1–T4，同一产品流水线。无未决产品分叉。

## G2 · 可行性与安全
- 初审 BLOCK：GET 与通用 POST 之间存在药品变更竞态。回 S3，补充事务内校验的提醒专用 POST，保留通用手动日志语义。
- **裁决**: GO；复审：独立 critic 确认原始本地剂次、精确日期、事务校验与 owner 边界。确定性检查 228 dossier 通过。
- run_path: docs/_generated/harness-runs/f47e40e993ae.jsonl

## S4 / S5
- 委托 health-harness-orchestrator，同一 parent run。T1 backend agent；T2 parent service/container/routes + 独立 pure view agent，文件互斥。
- 引用权威 PRD R1/R10/R12/R15；不增加通知出口。

## G3 / G4 / G5 / G6
- pending，尚未实现、发布或线上验收。

## 发布边界
- 与已有 ed608fe290 修复一起收口；生产基线 b2948b77 仅历史观测。
- 外部 publisher b6dd746e9c404d50ad28ea0af5616ca5 已终态但归属交接尚未核实，不启动第二发布。
- 不备份、不读真实健康记录、不调用真实模型。

## 实现与增量验证
- T1 服务器精确剂次 GET/POST，事务内药品版本与活跃/时区/日期/计划校验；终态日志幂等；通用日志回写议程采用真实持久化状态。
- T2 新独立页面、账号失效守卫、只读重试与回执核对，通知原始本地时间保留；用药管理每项增加提醒重入入口。
- PostgreSQL: 25 passed，包含双连接验证药品变更被事务锁阻止；自建 55463 已正常停止。SQLite: 13 passed / 1 PostgreSQL 专用 skip；邻近回归 41 passed / 1 skip。
- Mobile 核心路径 48 passed，新增不确定结果重读测试已先失败后修复。整包首次暴露旧路由断言已修；第二轮与新红测试并发，捕获到预期缺失重读按钮；现已冻结第三轮整包验证，未将前两轮算通过。
- API 双端类型由锁定依赖环境重新生成；首次尝试现有 backend venv 被版本校验正确拒绝，未放宽校验。
- 实际 RN 组件的 RNWeb 合成预览：390×844、320×740、768×1024 已检查；320 无横向溢出，长名换行，底部按钮可滚动点击；确认后已记录态且写按钮消失。截图 /tmp/reva-medication-reminder-390.png。仅合成 UI，不代表原生推送/真机验收。
- CUA 原生界面因 Mac 锁定不可用，未主动操作真机；浏览器合成验收完成。真机通知投递、原生大字号未验证。
- 新发现远端 main 已推进 63b565518（#282 Health-to-KBase owner login）。无任务文件重叠；先本地受控整合并重验，不执行外部写入。
