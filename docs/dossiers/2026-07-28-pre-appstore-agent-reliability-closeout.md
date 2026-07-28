# Dossier: App Store 前 Agent 可靠性收口

| 字段 | 值 |
|---|---|
| slug | `pre-appstore-agent-reliability-closeout` |
| 创建日期 | 2026-07-28 |
| 当前阶段 | S5 验证 |
| 状态 | building |
| 负责 | Codex + 用户 |
| 规划 | `docs/plans/2026-07-28-pre-appstore-agent-reliability-closeout.md` |
| 反馈环 | Agent golden traces + privacy-safe attachment telemetry + TestFlight 239 |

## S0 · 用户需求

在下周考虑提交 App Store 前，继续自动完成 Agent 对话在功能、可用性、
监控、隐私与成本方面的可靠性收口。

## G1 · 准入裁决

```yaml
RequirementAdmission:
  request: close deterministic Agent reliability and observability gaps before App Store submission
  classification: reliability, observability, and release safety
  core_loop_step: Capture -> Run -> Tool -> Receipt -> Recover
  first_class_objects: [ExecutionEvent, WriteIntent]
  target_surface: [Backend Agent Runtime, Mobile Agent]
  source_of_truth: PostgreSQL Agent Run Ledger and owner-scoped conversation messages
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: false
  autonomy_tier: preserve_existing
  verification_window: automated gates plus TestFlight 239 real-device checks
  success_metric: accepted image Turns survive interruption and historical write failures remain blocked
  added_user_burden: none
  non_goals: [medical behavior changes, framework migration, content telemetry]
  smallest_end_to_end_slice: durable draft -> accepted Turn -> verified receipt -> terminal aggregate
  stale_surface_to_remove_or_archive: none
  spec_required: reuse_existing
```

- **裁决: PASS。** 本轮强化现有 Agent Native、Mobile First 链路，不增加新的
  医疗判断、产品对象或跨端协议。

## S1 · 现状与风险

- Mobile 已具备私有文件草稿、文本安全存储、多图恢复、前后台恢复和仅在服务端
  明确接收后清草稿。
- Agent Turn 已使用稳定 `client_turn_id`、权威状态核对和可验证
  `WriteReceipt`，顶部状态和消息回执由同一 active Turn 驱动。
- 仍缺附件链路的无内容终态指标，无法区分本地准备失败与服务端未接收。
- 历史事故已覆盖到单元测试，但缺少统一的 deterministic trajectory gate 来保证
  “成功必须有回执、重放不得重复写”等不变量。

## G2 · 可行性与风险压测

- 附件事件只包含阶段、图片数量、时长桶、载荷大小桶和安全错误码。
- 明确拒绝 URI、base64、文件名、消息正文、用户/Turn/记录标识。
- Telemetry 失败不改变发送、草稿、重试或清理语义。
- Golden trace 使用合成 ID、日期和去标识工具轨迹，不调用付费模型或生产数据。
- **裁决: PASS。** 新增路径均为旁路观测或确定性离线验证，可独立回滚。

## S2 / S3 · 设计与计划

实施计划见 `docs/plans/2026-07-28-pre-appstore-agent-reliability-closeout.md`。

## S4 · 实现

- [x] 增加 `chat_attachment_terminal` Mobile/Backend 双端契约与严格字段过滤。
- [x] 在本地图片准备失败、服务端拒绝、发送异常和明确接收处发出单一终态事件。
- [x] 聚合附件接收率、失败阶段、图片数、时长桶和载荷桶，并在有效样本达到
  5 次后对低于 90% 的接收率给出分阶段运维建议。
- [x] 增加历史 Agent 事故 golden trajectories，覆盖饮水、食物、餐食上下文修正、
  不确定回执、重复 Turn 副作用和幂等重放。
- [x] 核验现有 active Turn 与 WriteReceipt UI 为统一状态来源。
- [ ] 完成独立安全评审、提交、部署和 OTA。
- [ ] 完成 TestFlight 239 真机 G6。

## G3 · 测试闸

- Mobile 附件事件和输入框：`87 passed`。
- Mobile active Turn、聊天页面、结构化回执和顶部状态：`184 passed`；
  Chat 页面端到端组件回归：`44 passed`。
- Backend client event、聚合、Agent trajectory 与 Harness wiring：
  `124 passed`。
- Agent trajectory scorer 与历史轨迹门禁聚焦回归：`19 passed`。
- TypeScript `npx tsc --noEmit`：PASS。
- 零成本 Harness：invariants `12/12`、health core `50/50`、trajectory
  contract `12/12`、goldens `6/6`，未调用付费模型。
- 页面测试保留既有 React `act(...)` 警告但无失败；不作为真机 G6 的替代证据。
- **裁决: PASS。**

## G4 · 安全闸

- 待独立 reviewer 对提交 SHA 复核附件遥测隐私、Agent 写入诚实性和回归测试范围。
- 在 reviewer 给出 GO 前不进入部署。
- **裁决: PENDING。** 当前代码级隐私检查已通过；独立发布评审仍是后续 G5 前置条件。

## S6 / G5 · 部署与健康

- 后端部署和 Mobile production OTA 尚未执行。
- **裁决: PENDING。** 本段仅声明部署尚未开始，不冒充生产健康验证。

## S7 / G6 · 上线验证

- TestFlight `1.3.2 (239)` 已上传。
- 待真机验证：多图连续拍摄、切后台恢复、弱网重试、草稿不丢、只生成一个
  accepted Turn、写操作显示唯一可验证回执、自动滚动到最新输出。
- **裁决: PENDING。** 当前保持 in progress；只有上述真实设备证据齐全后才改为 shipped。

## 回滚

- 后端：部署上一已验证主干提交。
- Mobile：使用 production OTA manifest 的前一 known-good group。
- Telemetry：删除 `chat_attachment_terminal` 发送与聚合，不影响业务发送链路。
- Golden gate：不得静默删除历史事故；如 fixture 本身错误，需在 Dossier 中说明并
  同步 scorer 测试。
