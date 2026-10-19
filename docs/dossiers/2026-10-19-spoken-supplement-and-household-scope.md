# 口语补剂查询与家居维护陈述修复

Updated: 2026-10-19
Status: implementation verified locally; G4 GO for 400cb2443; deployment blocked
Spec: `docs/specs/active/2026-10-19-spoken-supplement-and-household-scope.md`
Workflow: quick_fix, safety overlay; no superpowers skills used.

## 故障与根因

口语服用回顾不在完整的补剂读取语法内；疑问定语中的“的”被通用归属检查解释成未知主体，单日 supplements 又不能由旧 calendar fallback 完整绑定。
普通设备维护陈述没有正向 answer scope 证明，模型若提议无权限的数据查询，查询失败会成为最终任务结果。
另以合成反例复现假设补剂问句会落入 legacy 查询路径。

## 修复

完整消费本人/省略主体的单日补剂问句，复用服务器日期解析、认证主体与实际摄入适配器；读取参数只接受明确 scope 的字段，混合/假设请求不能落入旧兜底。服用计划、未服用记录、其他日期及跨账户关联不能充当摄入证据。
完整设备换滤网陈述沿用本地固定回应、持久化与重放路径。附带链接为未读取资料，不读取健康上下文、不运行模型、不新增维护记录或提醒。附加读取/写入/症状指令仍走原流程。

## 验证

- RED: 首轮新增测试 13 failed / 26 passed，复现主体误判、未绑定日期、假设绕过和家居陈述无回应路径。
- GREEN: 初始扩展测试 48 passed；真实 gateway、single/panel、实际摄入适配器及持久化被执行，LLM provider 使用合成脚本。
- 相邻授权/longitudinal/current-input 回归：1801 passed / 12 skipped。日志 `/tmp/reva-supplement-household-regression.log`。
- PostgreSQL 独立 UTF8 测试库：48 passed；初始临时库默认 SQL_ASCII 导致中文建表 fixture 错误，改建 UTF8 后通过，无应用改动掩盖错误。日志 `/tmp/reva-supplement-household-postgres.log`。
- System Map / mobile-nav / doc-drift 与 `git diff --check` 通过；无结构生成物漂移。
- 最终新增测试：SQLite 50 passed（8.98s），PostgreSQL 50 passed（25.20s），包含禁止模型跳过查询以及计划/未服用排除；日志 `/tmp/reva-supplement-household-tests.log` 与 `/tmp/reva-supplement-household-postgres-final.log`。
- 独立只读 reviewer `safety_review` 对固定实现提交 `400cb2443` 给出 **GO**：核对完整语法、认证/日期/字段边界、真实摄入、未知任务保留、URL未读取、持久化及重放。Reviewer 未重跑测试，测试执行证据由主 agent 提供；GO 只覆盖该提交，不覆盖前置提交或发布准入。

## 发布与验收边界

只读 SSH 核实生产 HEAD `1ba724dcb62ac389a72e41eecf40fea7aaca27e3`；health-backend active，API/database/redis/celery healthy。
开工时 main ahead 2，过程中他任务继续提交；当前本任务之前还有 `23b6c1399`、`c027cd7b7`、`9d80d2d46`，远端 main 当时为 `f373e2bc1c89d3ec7d10e8a50ee6ae3bce22a3c4`。
工作区包含其他任务改动，均保留。本次不替其他候选签发独立安全审查或完整 CI 证明；按 AGENTS §7 停止外部写入，待前置任务完成主干集成和发布准入。
G4 独立审查通过；G5 精确主干 CI/CI-mode/干净候选/发布回执未满足，未推送、未部署。此次无 Mobile 文件变化，无 OTA；模拟器及真实账户交互未验证。
