# 口语补剂查询与家居维护陈述的任务边界

Status: implementing
Owner: Reva backend
Updated: 2026-10-19
Related PRD: `docs/prd/reva-personal-health-os-prd.md`

## 决策与问题

修复补剂服用回顾口语被误判为非本人、以及家居设备维护陈述继承查询失败回复的问题。
后端完整消费当前输入后确定任务；不能靠删除拒绝文案掩盖失败。

## 需求准入

- classification: bugfix；target_surface: Mobile Chat；source_of_truth: Backend。
- first_user_fit/core_loop_step: 低负担地回顾实际补剂执行事件，避免对话要求无关查询日期。
- first_class_objects: ExecutionEvent（读取既有服用事件）、HealthProtocol（维护陈述仅聊天回应）。
- safety_level: privacy_sensitive；prescription_or_causal_verdict: none；autonomy_tier: none。
- evidence_provenance: 当前完整输入、认证主体、本地业务日期、真实服用记录；链接未读取。
- claim_hedging: 不声称服用记录完整、不由配置推测实际摄入、不声称改善健康。
- verification_window: 本次修复回归及独立安全审查；success_metric: 正向进入正确路径，反向零越权分发。
- added_user_burden: 无；smallest_end_to_end_slice: 输入 → scope → gateway → 真实查询/本地回应 → 持久化与重放。
- spec_required: yes；stale_surface_to_remove_or_archive: 无。

## 流程与数据合同

已完整识别的本人/省略主语、今天/昨天/前天的补剂服用疑问，只查询认证账户该日实际补剂摄入。
沿用 health_query/health_query_batch、实际补剂读取适配器、聊天 SSE 与持久化合同，无 schema/API/mobile 类型变更。
整句家居设备换滤网陈述允许附带一个未读取的 HTTPS 分享地址，返回固定回应；不启动模型、健康上下文或工具。
其他请求、附加症状、读取链接、记录和提醒意图继续原流程，不能被此回应吞掉。

## 安全与非目标

不扩大第三方数据、任意日期、模型参数、建议或写入权限。模糊子时段、筛选、混合指令、引用、假设不授予本次新增的日查询 scope。
补剂定义/计划不证明服用；跨用户关联记录不能泄露名称；空结果不等于未服用。
滤网维护不保存为健康执行事件、不创建提醒、不读取链接，也不保证空气质量或健康收益。
无诊断、补剂剂量/频次调整、浏览器能力、通知或原生改动。

## 验收与发布

测试覆盖主体、日期、模型参数篡改、enforce/shadow gateway、数据库隔离、single/panel 流、对话持久化和幂等重放。
数据库验收使用独立 PostgreSQL 测试库；运行相邻授权与对话回归、System Map、diff-check。
上线保留独立 G4 GO、精确当前主干 CI、CI-mode 集成闸、干净候选、发布回执与健康检查。
不备份、不建回退副本；回归时用受审向前修复。仅后端变化无需制造 Mobile OTA。
执行状态与验证结果见 `docs/dossiers/2026-10-19-spoken-supplement-and-household-scope.md`。

## Changelog

- 2026-10-19：按截图故障建立最小修复合同，保留现有认证、数据及持久化边界。
