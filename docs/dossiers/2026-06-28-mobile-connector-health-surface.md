# Dossier: Mobile 连接健康状态展示

| 字段 | 值 |
|---|---|
| slug | `mobile-connector-health-surface` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S5 实现 |
| 状态 | in_progress |
| 负责 | Codex |
| 反馈环 | mobile OTA |

## S0 · 用户需求(逐字)

> 继续执行

- 上下文解释: 后端已发布 `connection_health` 合同；本切片把该合同接入已有 Mobile `/data-connections` 页面，避免移动端继续用原始字段猜连接状态。
- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1): 用户在手机上查看数据连接时，需要知道连接是否可用、是否需要重连、缓存是否还能只读使用；当前页面只显示“可用/需处理/已撤权”和原始 policy，解释不够清楚。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/services/dataConnections.ts`: 已有 `fetchDataConnections`、`revokeDataConnection`、`connectionStatusSummary`。
  - `mobile/app/data-connections.tsx`: 已有数据连接与授权页面、撤权按钮和 scope 展示。
  - `mobile/app/settings.tsx`: 设置页已显示 `connectionStatusSummary` 并可进入 `/data-connections`。
- 缺什么:
  - Mobile 类型里没有 `connection_health`。
  - 设置页摘要未优先使用后端降级合同。
  - 连接卡片没有解释“需重连 / 缓存可只读使用 / 已撤权不可用缓存”。
- 硬约束:
  - 不新增写路径。
  - 不新增 native module。
  - 不走 TestFlight，JS/TS UI 改动走 OTA。
  - Web/Mac 当前没有外部数据连接中心入口，本切片不强行扩信息架构。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `DataConnection`, `ConnectorPolicy`
- core_loop_step: Observe -> Decide 的连接可用性解释
- target_surface / safety_level / autonomy_tier: Mobile `/data-connections` / privacy_sensitive / none
- spec_required(§8.1): 复用 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` 的 DataConnection 合同。
- smallest_end_to_end_slice: Mobile service + Mobile data connections page 消费 `connection_health`。
- stale_surface_to_remove: 页面内原始状态猜测逻辑。
- **裁决**: PASS
- 用户确认: 已由“继续执行”授权。

## S2 · PRD

- 链接: `docs/prd/reva-personal-health-os-prd.md`
- 引用的权威能力: 真实数据、授权、跨端一致状态、可解释连接治理。
- 边界(不做): 不做 Web/Mac 新入口、不做二维码原生包、不做撤权删除、不做重连 flow。
- 验收 Gate: Mobile 设置摘要和连接卡片都消费 `connection_health`。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- OTA/EAS 路由: JS/TS UI 改动，走 Mobile OTA；不走 TestFlight。

## G2 · 可行性 + 安全压测

- 评审方式: Codex self-challenge
- 硬阻断(已焊进范围): 不做自动重连、不新增授权写入、不伪造 Web/Mac 入口。
- **裁决**: PASS

## S4 · 研发任务分解

- 任务表:
  - [x] T1 RED: Mobile service 测试证明摘要需优先使用 `connection_health`，且 helper 尚不存在。
  - [x] T2 GREEN: 增加 `ConnectionHealth` 类型、fallback 和 `connectionHealthDisplay`。
  - [x] T3 UI: Mobile `/data-connections` 卡片展示状态、说明、缓存可用性和重连动作语义。
  - [ ] T4 文档回写、提交、OTA 和验证。

## S5 · 实现

- 委托: Codex
- 分支: `codex/rolling-runtime-next-slice`
- commit: 待提交

## G3 · 测试闸

- RED: `mobile/services/__tests__/dataConnections.test.ts` 先失败于摘要仍返回 `1 个可用`，以及 `connectionHealthDisplay is not a function`。
- GREEN: 同测试文件通过。
- 集成闸: 待跑。
- **裁决**: 待定

## G4 · 安全闸

- 触发?: privacy_sensitive 连接状态展示。
- 自查:
  - 只读 UI。
  - 不显示 token。
  - 不扩大授权 scope。
  - 撤权和缓存状态沿用后端合同。
- **裁决**: 待定

## S6 · 发布

- 路由: Mobile OTA
- OTA group / update id: 待定

## G5 · 发布健康闸

- 待定

## S7 · 上线验证

- 待定

## G6 · 验证闸

- 待定

## S8 · 沉淀

- 待上线验证后回写计划状态。
