# 明确查询与饮食修正误拦截

| 字段 | 值 |
| --- | --- |
| 状态 | partial / release-blocked |
| 当前阶段 | 续作本地 G3 通过、G4 GO；完整远端 CI 未跑，发布恢复待授权 |
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
  首次 live LLM Gate BLOCK：评测进程未加载已有 TokenPlan 配置，尝试的 OpenAI 路径因
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

首轮没有实现的照片引用，续作已收敛为下述手动确认流程；不是自动覆盖。
旧照片没有签名快照时必须重新发送，不从旧模型回复中推断识别结果。
最终发布仍需完整精确主干 CI、旧发布恢复授权及部署后验证。

## 续作 — 照片识别到修正编辑器

- 代码提交：`fb20d82b981c3dc58ef588ce2e8a5e2223d5d79f`。
- 结构化识别描述经服务端签名，与本人/会话/图片消息/图片集合/时间绑定，
  最长引用 24 小时。只引用紧邻、已完成的照片回合；今天指定餐别须有唯一记录。
- 生成已有编辑器的待确认预填，不修改饮食、不产生保存回执。用户确认才调用
  已有营养重算 API；原始版本、CAS、幂等、重复点击保护不变，照片不迁移。
- `1/5` 等已有食用比例保留；另存成另一条饮食的照片停止替换，避免重复计入。
- G3：新增服务组 19 passed，覆盖率 89.61%；相关组合 646 passed、1 skipped
  （SQLite 不证明 PG 并发），独立临时 PostgreSQL 组 146 passed，已停止实例。
- Mobile 新增预填测试 RED 1 failed/43 passed，GREEN 44 passed；正式 CI 拆分
  Mobile 主组 2839 passed/1 skipped，输入框 75、聊天页 62、auth 33、GPS 7 passed。
  Web 401 passed，两端类型检查通过；Web lint 0 errors、37 既有 warnings。
- 通用 run-all-tests 混跑不是完整通过：Mobile 有状态测试混跑停滞后中断，
  已按正式 CI 的主组+四个独立组重跑通过；Backend 全库单进程在 1074 passed
  时中断，改用正式 CI 分片和有界进程，不能宣称全库通过。
- 正式 runner 的受影响分片通过：agent-executor-food 115，agent-m-p 237，
  agent-s-v 709（9 skipped），d-diet 406（3 skipped）；合计 1467 passed/12 skipped。
  这四片不等于全部后端测试，最终目标 revision 的完整远端 CI 尚未执行。
- 最终代码 live LLM 再跑通过：orchestrator 5/5、均分 0.94；离线四组全部通过。
  只从本地既有 `.env-online` 读取三个 TokenPlan 连接项，使用合成数据及内存库，
  未加载生产数据库/Redis 配置、未打印密钥、未更改披露或同意策略。
  内存评测库缺少 usage 表的既有警告保留，不作为生产配额审计通过证据。
- G4：独立只读静态复审上述固定提交，GO；不豁免发布 Gate。
- System Map/doc-drift、秘密扫描和 `git diff --check` 通过；未新增依赖、API 或 schema。
- 发布前只读核实：生产仍为 `a1e39bbfab675ac7f52227b33d4673f7bc3ccf87`，
  `/var/lock/health-app-release` 仍存在。未清锁、重启、部署或改生产健康数据；
  已向用户询问是否授权按审计流程恢复旧失败发布任务，等待答复。

后续用户已明确回答“允许”。恢复发布器与受控收尾工具及当前 app 修复已推至
主干 `a30153b86`，新恢复工具独立 G4 GO；发布仍未执行。续办与主干 CI 文档
格式修复状态见 [恢复 Dossier](2026-09-23-frontend-publisher-recovery.md)。

续作证据：`/tmp/reva-photo-correction-{combined,pg,coverage,final-live-gate}.log`、
`/tmp/reva-photo-correction-mobile-ci-{main,input,chat,auth,gps}.log`、
`/tmp/reva-photo-correction-ci-{food-policy,diet-read}.log`。
