# Dossier: App Store 前 Agent 可靠性收口

| 字段 | 值 |
|---|---|
| slug | `pre-appstore-agent-reliability-closeout` |
| 创建日期 | 2026-07-28 |
| 当前阶段 | S7 上线验证 |
| 状态 | validating |
| 负责 | Codex + 用户 |
| 规划 | `docs/plans/2026-07-28-pre-appstore-agent-reliability-closeout.md` |
| 反馈环 | Agent golden traces + privacy-safe attachment telemetry + TestFlight 240 |

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
  verification_window: automated gates plus TestFlight 240 real-device checks
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

- 附件事件 `meta` 只包含阶段、图片数量、时长桶、载荷大小桶和固定枚举错误码；
  任意 token 形态的错误字符串不能进入存储。
- 明确拒绝 URI、base64、文件名、消息正文、Turn/记录标识。事件行仍保留
  `current_user.id` 作为租户隔离和 owner-scoped 运维关联，不能把该遥测描述为匿名；
  用户 ID 不进入事件 `meta`，运维聚合也不返回用户级明细。
- Telemetry 失败不改变发送、草稿、重试或清理语义。
- Golden trace 强制声明 `fixture_origin: synthetic`，并由 Gate 递归拒绝用户标识、
  正文、token 和 URI；只使用合成 ID、日期和工具轨迹，不调用付费模型或生产数据。
- **裁决: PASS。** 新增路径均为旁路观测或确定性离线验证，可独立回滚。

## S2 / S3 · 设计与计划

实施计划见 `docs/plans/2026-07-28-pre-appstore-agent-reliability-closeout.md`。

## S4 · 实现

- [x] 增加 `chat_attachment_terminal` Mobile/Backend 双端契约与严格字段过滤。
- [x] 在本地图片准备失败、服务端拒绝、发送异常和明确接收处发出单一终态事件。
- [x] 聚合附件接收率、失败阶段、图片数、时长桶和载荷桶，并在有效样本达到
  5 次后对低于 90% 的接收率给出分阶段运维建议。
- [x] 增加历史 Agent 事故 golden trajectories，覆盖饮水、食物、餐食上下文修正、
  不确定回执、重复 Turn 副作用、同记录重复写、只读误写、缺失身份回执和幂等重放。
- [x] 核验现有 active Turn 与 WriteReceipt UI 为统一状态来源。
- [x] 附件终态增加 owner-scoped 幂等键，快速连点与终态竞态只落一条遥测；
  Backend 以唯一索引和冲突后核对兜住并发写入。
- [x] Goal Guard 拒绝模型越权写入后改走无工具文本恢复，不再把安全拦截错误呈现为
  “模型服务不可用”，单模型和多模型链路语义一致。
- [x] Jest 环境释放 React Query inactive cache 的 GC timer 引用，全量 Mobile
  回归可以自然退出，不再依赖 `--forceExit`。
- [x] 完成在线合成评测与独立安全评审。
- [x] 完成主干提交和后端生产部署；Mobile 因包含原生模块删除与图标变化，按发布
  安全策略改走 TestFlight 原生构建，不发布不完整 OTA。
- [ ] 完成 TestFlight 240 真机 G6。

## G3 · 测试闸

- Mobile 附件事件、输入框、active Turn、聊天页面、结构化回执和顶部状态均纳入
  全量 Gate。
- Backend Agent、Runtime、client event、managed migration、历史写回与 Harness
  wiring 的累计广覆盖 Gate：`1467 passed, 3 skipped`，退出码 0；第七轮整改后
  受影响域复验 `230 passed`，CI 原始六个 Agent 分片复验
  `1342 passed, 3 skipped`，第八轮生产 fail-closed 整改后受影响域
  `233 passed`、相关 Executor/Kernel/Runtime/write 分片
  `1246 passed, 3 skipped`，退出码均为 0。第九轮嵌套验证字段整改后，
  受影响域 `234 passed`、Executor `a-h` 分片按 7 个文件受控复跑合计
  `204 passed`、Executor `i-z` 分片 `329 passed`，退出码均为 0。初次聚合执行
  的测试运行器异常挂起，已停止且未作为通过证据。第十轮嵌套失败态和日期整改后，
  受影响域扩大为 `238 passed`，Executor 两分片仍为 `204 + 329 passed`。
- Agent trajectory scorer 与历史轨迹门禁已覆盖 9 个 mandatory scenarios。
- TypeScript `npx tsc --noEmit`：PASS。
- Mobile 完整 Gate：`279` 个 suites、`2156 passed`、`1 skipped`，退出码 0；
  React Query 测试 GC timer 已不再阻塞 Jest 退出。Expo lint `0 errors`，保留
  `93` 条既有 warning。
- Python 变更文件 Ruff、文档漂移、Dossier 一致性和 `git diff --check`：PASS。
- 零成本 Harness：invariants `12/12`、health core `50/50`、trajectory
  contract `12/12`、goldens `9/9`，未调用付费模型。
- `harness_llm_change_gate.py --base-ref origin/main` 正确阻断本次发布：Executor
  和 trajectory evaluator 均属高风险 LLM 变更，必须先执行 5 个纯合成
  orchestrator 用例的在线模型评测。本 Gate 涉及向阿里云百炼发送约 10 次请求、
  约 12K token；不含用户、图片、账户或数据库数据。用户已明确授权，评测使用
  TokenPlan `MiniMax-M2.5` 完成，结果 `5/5 passed`、平均分 `0.92`。
- 首次 live 执行因临时 SQLite 缺少 `llm_usage_logs` 被生产配额守卫正确 fail closed；
  补齐项目完整 ORM schema 后以相同授权范围重跑通过。未关闭或绕过预算守卫，也未
  使用真实生产健康数据。
- 页面测试保留既有 React `act(...)` 警告但无失败；不作为真机 G6 的替代证据。
- **裁决: PASS。** 本地、离线、静态和已授权的在线合成评测全部通过。

## G4 · 安全闸

- 独立 reviewer 对 `4356354e` 给出 **NO-GO**，发现只读请求仍可能执行 delete、
  同一记录重复写和多写缺失 identity receipt 可绕过、附件错误码范围过宽、fixture
  隐私仅靠约定。
- 已逐项整改：任何只读写入和错误 record type/operation 均硬失败；副作用按实际
  verified write 次数计数；每个写回执必须带记录 identity；附件错误码收敛为固定
  枚举；fixture 加入 synthetic origin 和递归隐私 Gate。
- 第二轮独立 reviewer 仍给出 **NO-GO**，进一步发现空 `attempts` 可隐藏顶层工具
  调用、通用只读 Goal 的执行前守卫未收口、饮食重估仍可能 delete，以及 fixture
  根节点和正文内嵌 URI 未被扫描。
- 第二轮整改已完成：评分器合并检查顶层与所有 attempt 工具调用；所有显式只读
  Goal 在统一执行前边界阻断副作用；饮食重估只允许目标 update，并将不安全 create
  降级为权威 lookup、直接丢弃 delete；fixture 隐私 Gate 扫描完整 YAML 树并拒绝
  字符串任意位置的 URI。新增五个回归用例均先复现失败后转绿。
- 第三轮独立 reviewer 仍给出 **NO-GO**，发现 receipt-exempt
  `health_record(garmin_sync)` 可绕过只读守卫、饮食重估可夹带跨域 symptom create，
  且 scorer 把缺少 operation 的 `health_record` 误判为非写入。
- 第三轮整改已完成：完整只读 Goal 只接受严格 read-only 工具；所有
  `health_record` 默认推断为 create 并按副作用处理；饮食重估恢复仅允许
  `record_type=diet` 的目标 create；评分器采用相同的 operation 推断。三条回归测试
  先红后绿，扩大执行器回归 `723 passed`。
- 同时修正模型路由测试的环境隔离，并把只读 advice 场景的伪工具改为
  `environment_check`，避免测试本身依赖隐蔽写入。
- 第四轮独立 reviewer 仍给出 **NO-GO**，发现饮食重估可以夹带跨域写入、
  trajectory scorer 可被不一致的顶层/attempt 工具投影绕过、root Turn ID 未参与
  重试一致性检查、附件终态缺少服务端 exactly-once 约束，以及合成 fixture 的隐私
  扫描仍可能漏掉 credential/token 变体。
- 第四轮整改已完成：饮食重估硬限制 `record_type=diet`；scorer 复用 Tool
  Registry 判断副作用并对不一致投影 fail closed；root/attempt Turn ID 统一核验；
  附件终态增加 `(user_id,event_name,event_key)` 唯一约束和并发冲突核对；fixture
  必须声明 synthetic origin，并递归拒绝用户标识、正文、URI、Bearer 与密钥变体。
- 扩展测试进一步发现 Goal Guard 全量拒绝写工具后会误入下一轮工具调用并降级为
  通用失败。现已在单模型与多模型路径保存 `rejected` 状态，随后强制无工具恢复回答，
  不执行副作用、不宣称写入，也不向用户暴露内部策略。
- 第五轮独立 reviewer 仍给出 **NO-GO**，发现轨迹日期和回执身份未绑定、畸形
  attempts/缺失 ID 可 fail open、`verified=false` 仍可能通过、mandatory scenario
  可被无关失败抵扣、附件事件原始幂等键会持久化，以及互相矛盾的附件终态组合仍可
  被接受。
- 第五轮整改已完成：root/attempt `client_turn_id`、查询日期、写入日期和 receipt
  identity 全部严格一致；畸形 attempts、缺失 operation/ID 和显式未验证回执统一
  fail closed；mandatory scenarios 改为逐项精确判定且不能被配置放宽；附件事件键
  使用运行时 HMAC 摘要后持久化，并只接受语义一致的 terminal tuple。fixture 隐私
  扫描同步覆盖 refresh token、credential 和内嵌 token 变体。
- Mobile 测试环境移除了全局 TanStack Query timeout manager 覆写，改为测试局部
  `gcTime=0`；完整 Jest Gate 已自然退出，不再掩盖业务定时器泄漏。
- 第六轮独立 reviewer 仍给出 **NO-GO**，发现 `status=verified` 但缺少
  `verified=true` 仍能通过；写入、回执和读回结果没有全部严格绑定目标资源与日期；
  Mobile 附件终态事件仍是内存级 fire-and-forget，进程或网络中断后不能保证重放；
  同时指出 Dossier 不能在上述不变量尚未成立时提前宣称 exactly-once。
- 第六轮整改已完成：scorer 只接受显式 `verified=true`，并对写入参数、回执
  `resource_type/date` 和读回结果日期执行统一 fail-closed 绑定；Mobile 新增
  owner-scoped 持久化附件终态 outbox，发送前先落盘，服务端确认后才移除，并在
  cloud auth 激活和 App 回前台时顺序重放。客户端提供 durable at-least-once，
  服务端按 `event_key` 唯一约束去重，组合后实现 effectively-once processing；
  不再把传输本身描述为理论上的 exactly-once。
- 第六轮整改的四个 scorer 反例和三条 outbox 断网/重放/去重测试先红后绿；
  trajectory contract `12/12`、goldens `9/9`、相关后端 `160/160`、Mobile
  全量 `2151 passed`，且 Jest 自然退出。
- 第七轮独立 reviewer 仍给出 **NO-GO**，发现 Mobile 在服务端返回
  `202 {ok:false}` 时会误删 outbox；服务端已接受图片 Turn 后，本地终态遥测落盘失败
  会被错误呈现为“发送失败”并诱导重复提交；生产饮水/饮食回执 schema 与 scorer
  期望不一致；冲突 alias 可能绕过日期、资源和餐次绑定。
- 第七轮整改已完成：Mobile 只在 `response.data.ok === true` 时移除 outbox；
  accepted Turn 后的终态遥测失败降级为隐私安全诊断，不回滚已接受发送且继续清理草稿；
  Tool Registry 建立 canonical receipt resource map，Executor 与 scorer 共用生产资源
  名；餐食上下文读回补齐实际日期，初始权威 lookup 的目标日期、结果日期、资源 identity
  与餐次 alias 冲突全部 fail closed。相关测试均先红后绿。
- 第七轮整改后完整证据：受影响后端 `230 passed`，CI Agent 六分片
  `1342 passed, 3 skipped`；Mobile `279` suites、`2155 passed, 1 skipped`；
  TypeScript、lint、Ruff、密钥扫描、文档漂移、Dossier 一致性、App Store 静态
  preflight 和零成本 Harness 全部通过。
- 第八轮独立 reviewer 仍给出 **NO-GO**，发现生产回执 builder 会把显式
  `verified=false` 归一成成功；冲突的资源 ID 和 `record_type/type` alias 在生产
  路径 fail open；Mobile `onSend` 返回 `undefined` 时仍清除私有图片草稿；损坏的
  outbox JSON 会永久阻塞终态事件重放。
- 第八轮整改已完成：写结果显式声明 `verified` 时只接受布尔 `true`；回执身份扫描
  顶层和嵌套所有候选 ID/资源类型并要求唯一一致；Tool Registry 对冲突或缺失的记录
  类型 alias 返回不可验证；ChatInputBar 契约收紧为显式布尔接受，只有
  `accepted === true` 才清理草稿；无法解析或非数组 outbox 会清除损坏容器并从空队列
  恢复，且不记录原始健康相关内容。
- 第八轮回归均先红后绿；Mobile 全量 `2156 passed, 1 skipped`，受影响后端
  `233 passed`，相关 Executor/Kernel/Runtime/write 分片
  `1246 passed, 3 skipped`，TypeScript、lint、Ruff、diff check 和零成本 Harness
  全部通过。
- 第九轮独立 reviewer 仍给出 **NO-GO**：生产回执 builder 只检查顶层
  `verified`，因此嵌套 `result.verified=false` 仍可能被归一为可验证成功回执。
- 第九轮整改已完成：回执 builder 在顶层和受支持的 `resource`、`record`、`data`、
  `result` 容器统一扫描显式验证字段；任一层声明的 `verified` 不是布尔 `true` 时
  整体 fail closed，不生成回执，也不把工具调用标记为完成。新增反例先稳定复现失败，
  修复后 `test_write_receipt_identity.py` 为 `24 passed`，扩大受影响域为
  `234 passed`，Executor `a-h` 按文件受控复跑合计 `204 passed`、`i-z` 为
  `329 passed`；零成本 Harness 再次通过
  invariants `12/12`、health core `50/50`、trajectory contract `12/12` 和
  goldens `9/9`。
- 第十轮独立 reviewer 仍给出 **NO-GO**：虽然嵌套 `verified=false` 已被阻断，
  但嵌套 `status=failed`、`ok=false`、非空 `error` 仍可能被外层成功状态覆盖；
  同时持久化日期只扫描顶层和 `data`，`result.record_date` 与请求日期冲突时仍可
  生成错误日期的 verified receipt。
- 第十轮整改已完成：新增统一的 producer envelope 来源函数，顶层和
  `resource`、`record`、`data`、`result` 现在共用完全相同的 verified、success/ok、
  error、status、失败 message 与 date/record_date 校验。任一层显式失败或任意日期
  不一致均整体 fail closed。四类 reviewer 反例先得到 `4 failed, 24 passed`，
  修复后回执身份测试 `28 passed`；扩大受影响域 `238 passed`，Executor 两分片
  `204 + 329 passed`，零成本 Harness 四项继续全绿。
- 独立 reviewer 对提交 `79550dd1` 完成第十一轮全量复审：嵌套失败态、验证状态、
  日期绑定、生产/scorer parity、Mobile 草稿清理和持久化终态 outbox 均通过对抗
  检查，未发现剩余 P0/P1 发布阻断项，明确给出 **GO**。
- **裁决: PASS。** 十轮 NO-GO 均已回到实现与测试阶段整改，第十一轮评审通过；
  仍须服从独立的 G3 在线合成评测、G5 部署健康和 G6 真机验证闸。

## S6 / G5 · 部署与健康

- 后端从独立干净 `main` 克隆部署提交 `bd7567c92860`，远端部署 SHA 核验一致。
- 部署前完成 41 MB PostgreSQL 备份、force-RLS 数据完整性检查、234 张表恢复
  演练，以及异地加密归档 hash/HMAC 校验。
- 生产托管迁移 `20260728_230000_client_event_idempotency` 已应用，服务重启后
  健康检查得分 `58/60`，Skills 本地与线上均为 `22/22`。
- Mobile OTA 安全检查发现自上个 runtime anchor 起包含本地 Health Kernel 原生
  Swift/CoreML 模块删除、App 图标/启动图和原生依赖配置变化；OTA 无法移除旧原生
  模型或更新图标，因此未发布可能造成 JS/原生不一致的 production OTA。
- 使用同一已验证提交构建 iOS `1.3.2 (240)`；EAS build
  `a62a4dc5-f542-4cfe-bc87-8eb0d84a7ff4` 成功，submission
  `dc84c785-e1b1-4db1-8a90-c3981b38429d` 已由 Apple App Store Connect 接收。
- **裁决: PASS。** 后端生产健康和 Mobile 原生交付均完成；Apple 二进制处理与真机
  行为验证继续由 G6 裁决。

## S7 / G6 · 上线验证

- TestFlight `1.3.2 (240)` 已上传并由 App Store Connect 接收，等待 Apple 完成
  二进制处理后安装。
- 待真机验证：多图连续拍摄、切后台恢复、弱网重试、草稿不丢、只生成一个
  accepted Turn、写操作显示唯一可验证回执、自动滚动到最新输出、登录持久化、
  新图标生效且安装包不再包含已删除的本地模型。
- **裁决: PENDING。** 当前保持 in progress；只有上述真实设备证据齐全后才改为 shipped。

## 回滚

- 后端：部署上一已验证主干提交。
- Mobile：使用 production OTA manifest 的前一 known-good group。
- Telemetry：删除 `chat_attachment_terminal` 发送与聚合，不影响业务发送链路。
- Golden gate：不得静默删除历史事故；如 fixture 本身错误，需在 Dossier 中说明并
  同步 scorer 测试。
