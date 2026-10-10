# 新建会话开场修复

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G4 已通过，G5/G6 待发布与模拟器验收 |

## G1 准入

裁决：PASS。用户明确要求分析并实现新建后的默认开场修复。范围是既有 Mobile 新建语义及主动提醒来源准确性，不新增健康写操作或临床建议。显式新建用本地问候开始，普通进入保留既有提醒，匹配同一用户既有行动；需求与验收见 [方案](../specs/2026-10-10-chat-fresh-start.md)。

## G2 可行性与规划

裁决：PASS。复用现有新建入口、EmptyStateHome 与确定性 conversation_opener。无新模型、依赖、API 或数据库迁移；封闭设备快照过滤须保留真实条件行动。

2026-10-10；primary controller: health-harness-orchestrator；overlay: safety-gate。
需求及实现契约见 [方案](../specs/2026-10-10-chat-fresh-start.md)。

## 范围和基线
基于 main 5fe583bf315cffe9d5fd4050344a46785d48683e，fetch 后与 origin/main 无分叉。保留其他 session 的发布收口文档和回执，不纳入本提交。
修改 conversation_opener、EmptyStateHome、chat 页面及相邻测试。无 schema/API/依赖变更。

## 验证
- RED：后端 4 failed / 56 passed；Mobile 新建开场与无关联依据断言失败。
- 独立审查首次 BLOCK：前缀匹配误过滤条件行动。补 3 个真实行动测试先失败，再改完整纯快照匹配，在原文上判断。
- 最终后端 63 passed（56.87s，含 coverage，SQLite 单元环境），日志 /tmp/reva-opener-backend-verified.log。
- 最终 Mobile 87 passed（3.578s），日志 /tmp/reva-opener-mobile-verified.log。既有 React act 警告未消除，不影响退出码；不据此声称 UI 实机验证通过。
- tsc --noEmit 与 git diff --check 通过。
- G4：独立只读评审对 6810463e6755da5d5e5b7f4ed3edd5f303f48ca7 的六个源码/测试文件裁定 GO；G5/G6：待发布与模拟器验收。未运行本候选完整 CI，不宣称线上或 PostgreSQL 已验收。

## 与待发布任务关系
上一统一发布 owner 已释放所有权。其后端 SHA 5fe583bf 已成功部署，但 OTA 38009227924 失败，无成功 vendor 回执，不得重发该候选。本改动进入新的候选，继承尚未交付 Mobile 改动。
“给我今日计划”仍属于待修复任务，本文的开场修复不代表它完成。后续统一发布需新固定 SHA、独立 G4、完整 CI、同 SHA backend 和可信 OTA validate/publish，保留模拟器验收边界。
