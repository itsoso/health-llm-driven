# 明确查询与饮食修正误拦截

| 字段 | 值 |
| --- | --- |
| 状态 | partial / release-blocked |
| 当前阶段 | G3 本地回归通过，live LLM Gate 阻断；G4 代码安全 GO |
| Overlay | safety-gate |
| 研发 Run Ledger | `docs/_generated/harness-runs/a9130cdbd778.jsonl`（本地，不提交） |

## G1 — 准入

裁决: PASS。截图反馈的既有聊天行为回归，不扩大自动写入权限。
对象为 WriteIntent、HealthTwin 与已有记录的证据链；后端为真源，Mobile 仅展示。
修正明确请求的分类/范围绑定，以及查询失败后通用知识卡误导问题。
这是独立于足迹发布的新问题；此前受控前端发布的失败审计与锁保持不变，
截图不授予清锁、恢复发布或原生签名权限。

## 范围与根因证据

- 原话“基于识别的这一餐来修改今天午餐记录”在本地被分类为 chat/diet/none，
  前置查询被拒绝；必须复用受控 mutation lookup，不能直接开放模型选定记录。
- “分析最近一周的睡眠血氧情况，给出你的建议”的建议从句被误当额外范围，
  复合血氧对象未被完整支持；不能删除血氧词后冒充已经分析血氧。
- 知识卡来自通用 KB，模型生成结束不等于查询成功；需按业务 outcome 控制
  补充知识卡，不抑制独立 SafetyGuardian 警报或已核实写入回执。

## Gate 状态

- G2：最小方案和前置安全条件见对应 spec；引用/否定/他人/未知时间继续拒绝。
- G3：词法/知识卡 RED 3 failed、11 passed，修复后相关回归 1190 passed；
  血氧范围 RED 8 failed、16 passed，修复后相关回归 392 passed。
  独立临时 PostgreSQL 17 同组 392 passed；追加单次/批量 executor 读取证据后
  血氧专用组 34 passed。均为合成数据；证明固定窗口、本人隔离、来源排除，
  不回退 latest-night，不证明真实模型完成回答。
  SafetyGuardian 与中断回合专项 2 passed。
  离线 LLM Gate：invariants 12/12、health_agent_core 50/50、轨迹 12/12、goldens 9/9。
  live LLM Gate BLOCK：本机未配置 TokenPlan key，尝试的 OpenAI 路径因
  `ai_recipient_not_disclosed` 被安全闸拒绝（0/5）。没有绕过披露、同意或更改生产配置。
- 最终组合回归：1814 passed（含 executor completion、读取适配器与 integration.py），
  不替代完整发布集成闸。System Map、mobile navigation、doc-drift、秘密扫描通过。
- G4：独立只读审查 `68500075faf6c8ec2313cf5705ab93ca0e67905f`，裁决代码安全 GO，
  无阻断性发现；审查者另跑新两组测试 45 passed。不豁免缺失的发布验证。
- G5/G6：未发布、未操作生产用户记录。

## 可重放证据

本机日志：`/tmp/reva-read-intent-combined.log`、`/tmp/reva-read-intent-pg.log`、
`/tmp/reva-read-intent-pg-dispatch.log`、`/tmp/reva-read-intent-offline-gate.log`、
`/tmp/reva-read-intent-llm-gate.log`、`/tmp/reva-read-intent-map.log`。
临时合成 PostgreSQL 实例已正常停止，未删除数据目录；未使用生产数据库。
工作流要求的外部 karpathy-guidelines/TDD/verification skills 在本会话不可用，
已依仓库 RED/GREEN、PostgreSQL、固定提交独立评审规则执行，未调用禁用的 superpowers。

## 尚未完成

“识别”的误否定已修复，但照片结果到既有午餐记录的自动覆盖链尚未实现。
现有受控 update 前置查找不包含按日期/餐别绑定的可信照片来源，因此不能
仅放开 diet 权限；本次负例确保模型传入任意 record_id/食物仍被拒绝。
用户仍需通过已有饮食编辑页确认修改；不能宣称截图中的自动覆盖操作已修好。
发布还需 live LLM、完整 CI-mode 集成、精确主干 CI 及独立 G4，旧发布恢复另行授权。
