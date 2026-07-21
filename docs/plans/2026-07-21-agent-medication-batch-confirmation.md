# Agent 多药合并确认与可信写入 Implementation Plan

> 严格按 TDD 执行。P0 状态止血与 P1 服务端批次分开验证；任何用药写入只有可信回执后才能显示成功。

## Task 1 · P0 确认态回归

- [x] 用截图原句构造两个 `NEEDS_CONFIRMATION` 工具结果的失败测试。
- [x] 增加“只调用只读工具后谎称已记录”的反向控制测试。
- [x] 保留无回执流式缓冲；让 pending confirmation 在工具轮确定性结束，并从 `record_intent_no_tool` 排除。

## Task 2 · 确定性多药解析

- [x] 解析已知药名、共同/逐项实际服量和强度，药品规格与本次服量分栏。
- [x] 同义品牌归一去重；疑问、否定、更正、泛称、缺剂量或重复同药 fail closed。
- [x] 精确原句必须得到两项 `伊托必利/1粒`、`替普瑞酮/1粒`。

## Task 3 · Server-owned WriteIntent

- [x] 新增 `medication_intake_batch` kind，payload 冻结 conversation/source message/version/hash/本地日时/items。
- [x] 新增同 user + source message 的 DB 条件唯一索引、nullable `WriteIntent.decision_status` 和双方言 managed migration。
- [x] 计划标题、日志和指标不含药名剂量；具体内容只在 owner-scoped payload/chat 中。
- [x] 将该 kind 加入 write autonomy 永久拒绝集合。

## Task 4 · 原子、幂等执行

- [x] 确认端只消费 intent id，不接受 items；锁定 owner 和 WriteIntent 状态。
- [x] 必要药物条目与所有 MedicationLog 在同一事务内执行，不推断处方字段。
- [x] 同槽同量返回既有逐项回执；同槽异量冲突；失败整体回滚。
- [x] `executed_ref` 指向批次，确认响应可重复重建相同 `write_receipts`。
- [x] 持久化 `decision_status=executed|dismissed|expired`；expired 使用物理 `dismissed` 关闭授权，并支持提交后崩溃重放。

## Task 5 · Agent 与跨端确认

- [x] LLM 前识别明确多药句，直接提案并返回合并确认正文/卡片。
- [x] 点击动作复用 `write_intent.confirm/dismiss`；同一会话紧接着回复“确认”/“取消”消费上一条绑定计划。
- [x] 用药 `confirmed=true` 不再被视为授权；无 pending、跨用户、跨会话、过期/撤销均拒绝。
- [x] confirm/dismiss 双向竞态按服务端胜者收敛；Mobile/Web/Mac 不用本地动作覆盖权威终态。
- [x] Agent 将完整终态写入 namespaced `medication_batch_decision`，确认成功只在逐项 `write_receipts` 完整时显示；写后 SafetyGuardian 失败如实降级。

## Task 6 · 验证与交付

- [x] 聚焦 Backend + 真实 PostgreSQL、Mobile、Web、Mac 测试及 lint/typecheck/build 验证。
- [x] 完成多轮独立评审整改；最终 G4 GO 单独记入 Dossier，不以计划勾选代替裁决。
- [x] 明确交付边界：只提交本任务文件到 main，不夹带其他工作树改动。

## Task 7 · 部署与上线（人在环）

- [ ] 获得 G5 显式发布批准后，从干净 main 按项目部署规范发布并跑健康分/prod smoke。
- [ ] 在生产单账号走精确原句、确认、双击重试和两条回执的 G6 真路径验证。
