# 用药单次提醒与 Agent 入口

- 用户证据：2026-10-18 18:30 锁屏同一分钟出现两条“吃药提醒”和一条“用药提醒”；要求只一次并点击进 Agent。
- 工作流：Router quick_fix + safety-gate，跨端调查启用 System Map；不调用全局禁用的 superpowers。单任务记录，独立安全评审待固定提交。
- 基线 `46304ef7a`（main 已超前 8 个未推送提交）；保护既有 benchmark、Dossier/receipt，未修改旧工作。
- [合同](../specs/2026-10-18-medication-single-reminder.md)：既有通知循环修复；本人用药，显式人工发送，不新增健康写授权。产品准入 GO。

## 根因与修复

本地每日提醒与服务端扫描同时启用；本地取消/重排异步可重叠，每药每时点又各排一次。现统一服务端每用户/日期/时点一条，旧本地排程启动/前台清理。点击带核实问题进入 Agent 草稿；无 context 自动发送和自动打卡。

扫描加入 PostgreSQL owner 连接锁，保留原 rule_id 回执去重。进一步真实 PostgreSQL 双 worker 测试复现延迟队列仍会发送两次：旧代码“先查再标 pending”不是原子认领；现使用条件更新后才能发送。

## 增量证据

- 后端合并 RED：三个药两用户实际发 3 条，预期 2 条；重复 worker guard RED。移动新路由与清理错误传播先失败后修复；最早本地排程测试还暴露 permission mock 未赋值，不把该设置失败单独当行为证据。
- PostgreSQL 延迟双 worker RED：实际 send 2 次，预期 1 次；锁获取后 commit 异常 RED：连接未 invalidate。均补实现后复测。
- 一次编辑插入 import 范围过宽导致 IndentationError，已修正为唯一顶层 import；一次 PostgreSQL 复测端口错误（55437），实际隔离 cluster 在 5432，确认目录及进程后使用其测试数据库重跑。失败日志保留，不作成功证据。
- 最终冻结集成与独立审查进行中。模拟器未解锁、旧 workflow 授权未解除；未 push、deploy、OTA 或声明手机已生效。

## 冻结验证

- 后端 CI-mode 通知/推送集成：321 passed / 2 skipped；跳过为 PostgreSQL 专属用例，随后真实 PostgreSQL 执行 81 passed，含两连接扫描锁、旧快照并发出队和 quiet/dedup 回归。
- Mobile 首轮 5 suites / 64 passed，TypeScript exit 0；定向 ESLint 仅测试 import 顺序警告，已修正并重跑测试。无模拟器或真实锁屏投递验收结论。
- PostgreSQL CI 分片纳入新用例；runner 契约 37 passed / 3 skipped（其自身可选集成环境未配置，不替代上述 PG 实测）。System Map、fatal Ruff 与 diff 检查通过。未修改模型 prompt/runtime，Agent 点击契约只改变 UI 路由。
- 证据日志 `/tmp/reva-med-single-ci-final.log`、`/tmp/reva-med-single-pg-final.log`、`/tmp/reva-med-single-mobile-verified.log`。
