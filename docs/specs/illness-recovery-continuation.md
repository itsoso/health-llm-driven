# Feature Spec: 病症痊愈确认续接

> Status: implemented locally; publication blocked
> Updated: 2026-10-26
> Related code: `backend/app/services/illness_recovery_confirmation.py`
> Dossier: `docs/dossiers/2026-10-26-illness-recovery-continuation.md`

## 1. Decision / Problem

修复用户在病症候选确认后回复“都好了”被当成无授权查询的问题。把这句回复绑定到上一轮有限候选，补齐日期并展示最终确认，然后一次保存。上一轮模型回复不能直接成为写权限；也不能把省略日期理解为今天。

## 2. Requirement Admission

```yaml
RequirementAdmission:
  request: 修复病症恢复确认被拒绝
  classification: existing_flow_repair
  first_user_fit: 已记录病症并报告恢复的本人
  core_loop_step: 用户自述结果确认与持久化
  first_class_objects: [HealthProblem, WriteIntent, HealthTwin]
  target_surface: existing_chat
  source_of_truth: authenticated_owner_IllnessEpisode_and_WriteIntent
  safety_level: health_write_manual_confirmation
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 当前用户回复及重新核验的本人记录
  claim_hedging: 用户自述痊愈不是医学诊断
  verification_window: 选择后30分钟内
  success_metric: 指定记录原子更新且每条有已核验回执
  added_user_burden: 补充缺失日期和最终确认
  burden_justification: 原请求有两项待确认且不能猜测日期
  non_goals: [自动诊断, 停药建议, 任意历史指代, 批量关闭全部病症]
  smallest_end_to_end_slice: 都好了_日期_预览_确认_持久化回执
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 3. Product Object / Surface Contract

- HealthProblem：复用现有 IllnessEpisode，仅修改目标行的状态和结束日期。
- WriteIntent：新增内部 kind `illness_recovery`，只能 manual_confirm；执行状态和逐条回执同事务落库。
- HealthTwin：提交后使已有缓存失效。
- Backend：所有权、候选匹配、签名、来源、时区、过期、记录版本、运行控制和事务裁决。
- Mobile/Web：复用现有聊天流与通用 WriteIntent 确认端点；不新增客户端自动写行为。现有客户端 kind 为 string、payload 为开放字典；回执满足既有 ConfirmWriteIntentResult。

## 4. User Flow / AI Boundary

最近一轮已完成的病症候选确认 → 用户“都好了” → 当前账号内按名称和起病日期唯一匹配有限候选 → 展示名单并询问日期 → 用户“今天”“昨天”或 ISO 日期 → 展示精确名单和日期 → 用户确认 → 锁定意图与行、检查版本 → 原子更新并保存回执。

旧模型文本只提供候选线索。其 ID、医学判断、日期和写入成功描述均不构成权限。本流程确定性执行，不调用模型。非完整肯定句、混合意图、引用、第三方、缺失上下文、重名歧义、过期、版本或时区改变不得执行。无法核对时明确说明未修改并要求重新提供目标，不假装成功。

## 5. Data / Safety Contract

没有 schema、迁移或公开端点变化。复用 WriteIntent JSON payload 储存服务端 HMAC 签名的 owner/conversation/source、候选版本、时区和日期；meta 保存有界续接状态。不得包含病症备注全文。健康名称只出现在当前所有者受保护对话与意图中；错误日志不记录健康载荷。

执行时锁定 WriteIntent、运行控制状态和精确病症行；不能绕过运行暂停。日期必须不晚于当前本地日期且不早于任何候选起病日期。回执和所有更新一起提交；任一异常回滚。已执行重试只核验并返回同一回执；记录后来变化不得宣称旧回执仍匹配当前结果。取消与确认用已有 compare-and-set 裁决，确认已赢时返回已核验结果。

## 6. Acceptance / Verification

- “都好了”仅选择先前候选，不扩张到其他本人记录或其他账号，不立即写入。
- 日期补齐后仍需最终确认；缺失、无效、未来或早于起病的日期不生成可执行计划。
- 两条记录要么同时更新并有两条回执，要么都不更新。
- 真实 AgentExecutor 流保存续接 meta、最终回执与 waiting_for_user/完成状态。
- PostgreSQL 验证并发确认；跨账号 API 返回404，失效计划返回脱敏409；运行暂停和事务失败不写入。
- 既有单病症恢复、饮水、其他 WriteIntent、照片补剂及睡眠查询回归通过。

验证命令与结果见 Dossier；测试只使用合成数据。未执行真实模型或线上用户记录修改，不能将本地验证称作线上验收。

## 7. Rollout

随后端候选 revision 发布，不需要独立 OTA。遵循既有部署锁、回执、CI-mode、精确 SHA 绿色 CI 与安全评审。当前主干分叉，禁止外部写入；本地实现不等于已上线。不创建备份或恢复副本，不执行恢复演练；异常时停止写入和发布、保留证据后修复。
