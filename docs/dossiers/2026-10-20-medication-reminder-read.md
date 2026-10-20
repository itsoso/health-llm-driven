# 用药通知查询被授权规则误拦截

| 字段 | 值 |
|---|---|
| 状态 | building |
| 当前阶段 | S6 验证 |

Spec: `docs/specs/active/2026-10-20-medication-reminder-read.md`
Workflow: quick_fix + safety-gate；System Map 按路径查询未索引，已运行全量 check 并阅读实际源码/测试。未使用 superpowers。

## G1 · 准入

- 裁决: PASS
- 修复通知已生成的只读草稿与授权绑定不一致；ExecutionEvent 只读，不新增写入授权。

## 实现与边界

- 整句解析固定客户端语句，日期/时间合法且时区与服务端一致，绑定认证本人。
- 现有 health_query/batch 单日参数与原文本时刻联合限定；执行前校验原快照，禁止身份或文本漂移触发通用重新绑定后读库。
- 查询匹配时段的当前有效计划及真实日志；双 owner join 拒绝损坏外键跨账户。范围外计划/日期/时刻不返回。
- 完成投影核验来源和时刻；计划和服药事实分开，保留“不证明历史通知计划”“无打卡不等于未服用”的边界。不可继承为整日继续查询。
- Mobile 仅补固定语句契约测试，打开通知仍不自动发送或记录服药；无 API/schema 变化。

## 验证

- RED：新增测试 **7 failed / 28 passed**，复现截图的查询拒绝及宽泛分析工具暴露，日志 `/tmp/reva-reminder-scope-red.log`。
- 第一轮实现 **2 failed / 182 passed**：执行入口通用 helper 会在账户/文本变化时重建快照，导致局部身份检查失效；已把提醒只读核验移到该 helper 前，保留原错误日志 `/tmp/reva-reminder-scope-green1.log`。
- 第二轮 **189 passed**，含真实 gateway → scoped adapter → completion → 保存回复。日志 `/tmp/reva-reminder-scope-green2.log`。更宽回归、PostgreSQL、独立审查待完成。

## 发布边界

用户已要求修复后部署。此前远端完整 CI 失败，按 AGENTS §7 暂停外部写入；旧维护 UNKNOWN 回执也未完成合法收尾。当前截图不视为允许绕过这些门禁的回复。未推送、未部署；没有读取真实健康记录或调用真实模型。
