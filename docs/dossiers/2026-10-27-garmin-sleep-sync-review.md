# 昨晚睡眠与佳明更新组合请求

| 字段 | 值 |
|---|---|
| 状态 | shipped |
| 当前阶段 | G6 后端回执核验；手机登录态重试未观察 |

## G1 准入

裁决：PASS。修复明确要求查看昨晚睡眠并更新佳明数据的组合请求被要求补充日期和类别的问题。复用现有同步入口、本人查询、完成状态和事实展示，不新增设备接入、日期猜测或健康记录写入。

## 诊断和实现

- 原实现未识别“睡眠查询＋更新佳明”的完整指令；合成回归在原代码中复现 `has_owned_sync_instruction=False`。这不是缺少用户所述日期或类别。
- 使用完整双子句匹配，支持前后语序、空格或标点分隔及明确的更新/同步/刷新动词；状态提问、引用、其他人、取消、未来计划和附加操作不获得同步权限。
- 服务端依次提议一次空参数同步和账号本地醒来日期的睡眠读取；仍经过 Pi、能力闸和认证用户隔离。模型不能扩大日期、用户或写入参数。
- 已有睡眠日汇总与本轮任务回执分别核验，排队不等于完成；同步失败仍可展示该日期实际已保存的记录。无结果不推断没有睡眠，不读取其他日期作替代。
- 使用现有有界事实投影与数字格式，明确多设备日汇总的来源限制。无 schema、API、Mobile 变更，不回放真实用户请求或手动同步用户账户。

## 验证

- 原实现失败证据：`/tmp/reva-sleep-sync-red.log`；初步定向测试 35 passed，含真实 Pi/派发和模拟队列状态。
- 最终回归、审查与生产证据见下方。

## G4 首轮审查整改

首轮 NO-GO：日期绑定类方法未纳入授权行为摘要，改变日期范围不会改变 policy digest。补充两个 scope 的 `query_args` 方法摘要与 mutation 测试；先复现两例失败后修复。复审已 GO，最终发布结果如下。


## G4–G6 最终结果

- 固定候选 `372dd6995bd8866ee91e35a35c1938343901a7e4` 独立 Safety GO；reviewer 216 项测试与额外取消/引用/第三方探针通过，包含方法变更必须改变完整授权摘要的验证。
- 最终定向 64 passed；相关回归 300 passed / 13 skipped；隔离 PostgreSQL 146 passed，测试退出与数据库停止均为 0。精确候选的 CI PostgreSQL job 也已通过。
- 真实模型闸通过：orchestrator 5/5，平均评分 0.94；invariants 12/12、health_agent_core 50/50、trajectory contracts/goldens 均通过。评测只使用合成输入和内存数据库，不代表真实账号截图路径已回放。
- CI `40431390771` 全绿；CI-mode 发布集成检查 4710 passed / 47 skipped / 127 subtests passed。System Map、Dossier 一致性、秘密扫描通过。
- validate `40433347087` success，backend `40433528469` success。2026-10-27 09:42（Asia/Shanghai）独立回读生产 SHA 精确匹配、SUCCEEDED 回执、COMMITTED/finalized/code-only-no-backup、三个 active 服务、发布租约释放、公网 health 200 与匿名 sleep API 401。完整脱敏证据见 `docs/reviews/2026-10-27-garmin-sleep-sync-release-receipt.json`。
- 已按受审脚本完成一次短期只读 GitHub 凭据续期与当前发布授权轮换；没有重放未知发布，没有创建备份或读取旧备份正文。
- 本次只有后端修改，OTA 不适用。没有触发真实账号同步、读取真实健康记录或补写记录。手机登录态原句重试尚未观察，不声称已完成用户设备数据同步。
