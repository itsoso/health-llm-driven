# Dossier: 本地优先私有模式与完全本地饮食

| 字段 | 值 |
|---|---|
| slug | `local-first-private-mode` |
| 创建日期 | 2026-07-18 |
| 当前阶段 | S3 规划 |
| 状态 | defining |
| 负责 | User / Codex |
| 反馈环 | iOS real-device spike / EAS-TestFlight / airplane-mode validation |

## Correct Course

- [ ] Correction Block

## S0 · 用户需求（逐字）

> 思考这个方向，能否让这个App增加一个本地模式，下载即可用，完全跑在本地，不需要注册，私有信息全部本地，只有调用大模型部分才走服务端？做出一些规划

> 按照第三种进行规划，另外也思考能否完全本地，甚至于连模型推理也走本地，换用一个很小的模型，解决饮食记录问题？

- 谁用 / 解决什么 / 现在怎么绕过：隐私敏感的健康记录用户希望先在设备上获得完整饮食记录价值，而不是先注册并上传健康数据；当前只能登录后使用服务端真源路径。
- 锚点用户相关性：饮食是既定 Personal Health OS `Capture -> Confirm -> Review` 的高频入口，并已有人工确认和来源边界。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `mobile/hooks/useAuth.tsx`：当前 App 入口由 token 决定。
  - `mobile/app/_layout.tsx`：未认证直接渲染登录页，HealthKit 等根级能力受认证状态控制。
  - `mobile/services/api.ts`：HTTP 客户端从 SecureStore 注入 Bearer token。
  - `mobile/applib/queryClient.ts`：只提供短期查询缓存，不是长期本地真源。
  - `mobile/app/diet.tsx`, `mobile/services/diet.ts`, `mobile/hooks/useDietEstimate.ts`：已有照片/语音/文字饮食入口和服务端 API。
  - `docs/specs/active/2026-07-11-diet-capture-excellence.md`：已有草稿、校准、人工确认、幂等和来源不变量。
  - `backend/app/services/food_nutrition_lookup.py`：营养表确定性校准可作为端侧实现参考。
- 缺什么：本地身份、本地加密真源、仓储接口、端侧模型桥、隐私出站断路器、导出恢复、可授权的生产食物库。
- 硬约束：当前最低 iOS 16；Apple 系统模型只覆盖部分设备/系统；新增原生模块必须走新 iOS 包；端到端加密同步会阻止现有服务端直接计算明文 Health Twin。
- 外部平台证据：Apple Foundation Models、Vision 和 Core ML 官方文档，见设计文档引用。

## G1 · 准入裁决

- first_class_objects: `WriteIntent`, `ExecutionEvent`, `HealthTwin`, later `HealthAgendaItem`
- core_loop_step: `Capture -> Confirm -> ExecutionEvent -> local projection -> Review`
- target_surface / safety_level / autonomy_tier: Mobile+iOS native / privacy_sensitive / manual_confirm
- spec_required: yes，新用户行为、新认证边界、新本地写路径和隐私契约。
- smallest_end_to_end_slice: 无账号、无网络记录一餐，重启后仍可读取。
- stale_surface_to_remove: 对本地新用户而言，登录不再是唯一入口。
- **裁决**：PASS。
- 用户确认：2026-07-18 已确认采用第三种“本地优先 + 可选同步”，并同意完全本地饮食作为第一切片。

## S2 · PRD

- 链接：`docs/prd/2026-07-18-local-first-private-mode.md`
- Feature Spec：`docs/specs/active/2026-07-18-local-first-private-mode.md`
- 权威定位：`docs/prd/reva-personal-health-os-prd.md` 的数据自持、双轨录入与 Capture/Execution/Review 核心循环。
- 边界：不承诺照片精确称重，不第一期迁移完整 Health OS，不静默创建云账户，不打包未授权数据。
- 未决问题：无产品定义级未决问题；G2 技术阻断见下。

## S3 · 规划

- 设计：`docs/plans/2026-07-18-local-first-private-mode-design.md`
- 实施计划：`docs/plans/2026-07-18-local-first-private-mode.md`
- 顺序：G2 spike -> 本地身份 -> 加密内核 -> 饮食仓储 -> 食物库 -> 离线记录 -> 端侧模型/Vision -> 出站断路器 -> 导出恢复 -> 新 iOS 包。
- 长杆：食物数据授权、加密恢复威胁模型、Apple 模型设备覆盖、真实设备内存/延迟。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge 完成初步架构压测；正式安全评审待 Task 1。
- 已焊进规划的硬阻断：
  - 生产食物数据库的再分发授权未解决前不得扩大数据包。
  - CryptoKit/Keychain/恢复设计未过威胁模型前不得承诺可恢复加密。
  - 系统模型不可用必须降级到确定性/手工，而不是强制云端。
  - 自定义视觉模型必须经过纠正成本、内存、温升和下载体积 Gate。
- **待拍板分叉**：无；用户已接受旧设备的严格本地照片能力可能较弱。
- **裁决**：待 Task 1 证据；未进入 S4。

## S4 · 研发任务分解

- 实施任务见 `docs/plans/2026-07-18-local-first-private-mode.md`。
- 当前未授权进入实现。

## S5 · 实现

- 未开始。

## G3 · 测试闸

- 未开始。

## G4 · 安全闸

- 必须触发：认证边界、健康数据本地写入、照片、模型出站、加密恢复。
- 未开始。

## S6 · 部署

- 路由：新增原生模块，必须 EAS/TestFlight 或本地 QR 新包；不能只 OTA。
- 未开始。

## G5 · 部署健康闸

- 未开始。

## S7 · 上线验证

- Anchor：真机飞行模式首次启动、首餐确认、重启读取、模型不可用、导出恢复、网络抓包零违规出站。
- 未开始。

## G6 · 验证闸

- 需要用户真机确认。
- 未开始。

## S8 · 沉淀

- 饮食切片通过 G6 后再决定是否扩到身体测量、症状、HealthKit、Agenda 和 E2EE sync。
