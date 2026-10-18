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

## 固定候选 G4 NO-GO 与修正

- `7fb16a4666453703bb80880962536a18eb751b39` 独立审查 NO-GO：遗漏活动的 medication 预提醒 producer，且分组 rule_id 缺 owner 会与客户端进程级消费 key 跨账号碰撞。补查还确认无显式时点的药曾由 day_schedule 解算，直接删除预提醒会漏掉；owner-only 锁也可能吞跨分钟剂次。
- 已停药域提前提醒并在共享出口拒绝其待发送副本；补剂、自定义提醒及周期复查不按自由文本删除。缺显式时点的本人活跃药只承接 scheduled 的用户本地时点，过滤 rejected/deferred/foreign ID；显式时点沿用旧北京时间语义。
- 稳定 SHA256 锁键纳入 owner/date/time，同槽互斥但下一时点可并行；rule_id 纳入 owner。Mobile 补旧 pre_event/medicine 普通点击兼容，验证非中国时区；仍无自动发送/写剂次。
- 回归保留预提醒不发、旧 delayed 副本拒绝、跨账号 key、下一时点锁、非中国跨日解算、补剂预提醒保留等证据。一次空批次 slot_time 未赋值与补剂旧目的地断言失败已修复并整批重验。
- 修正冻结后：CI-mode 扩大至通知/推送、事件提醒、议程用药/BID/协议链路，384 passed / 2 PostgreSQL 专属 skips；实际 PostgreSQL 20 passed（含全部新并发测试和 event reminders）；Mobile 7 suites / 73 passed。TypeScript、定向 lint、Ruff 和 System Map 通过。此前 PG 81 passed 仍作为未变出队/静默兼容切片证据，最终改动以本段新鲜结果为准。

## 通用历史入口兼容复审

- `3912ef754` 第二次独立审查 NO-GO：旧 `medicine` producer 经共享出口产生 `/notification-history?detailId=123`，未覆盖到 Agent 草稿。独立回归 135 passed / 2 PostgreSQL skips，其余受审改动未发现阻断。
- 先新增真实历史入口与详情入口用例，RED 为两条仍返回 history/detail；现仅对已识别用药提醒覆盖通用目的地。仅从 `/medication-reminder` 提取旧药品/剂次参数，通用详情 ID、日期与时间不冒充剂次；其他通知与专属编辑页仍保留原入口。
- 冻结复测 Mobile 7 suites / 76 passed、TypeScript 与定向 ESLint exit 0；日志 `/tmp/reva-med-generic-route-red.log`、`/tmp/reva-med-generic-route-green.log`。本轮无后端变更，保留上轮 CI-mode/PG 证据；等待新固定候选独立安全裁决。
