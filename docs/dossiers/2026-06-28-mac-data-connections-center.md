# Dossier: Mac 数据连接与授权中心

| 字段 | 值 |
|---|---|
| slug | `mac-data-connections-center` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | mac-build-deploy |

## S0 · 用户需求(逐字)

> 继续

- 上下文解释: 后端、Mobile、Web 已消费 `connection_health` 合同；上一切片明确下一步最高优先级是补 Mac 端 DataConnection / ConnectorPolicy 连接中心。
- 谁用 / 解决什么 / 现在怎么绕过: Mac 用户需要从桌面端查看外部数据源连接、授权 scope、同步健康、缓存可用性和降级解释；此前只能看按设备分组的观测数据，无法看到授权和连接治理状态。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `apps/mac/Sources/HealthAgentMacCore/APIClient.swift`: Mac API client 已处理 Bearer token 和 401。
  - `apps/mac/Sources/HealthAgentMacCore/DeviceSourcesClient.swift`: 设备数据来源 client 和 display mapping 模式可复用。
  - `apps/mac/Sources/HealthAgentMac/Features/DataSources/DataSourcesView.swift`: Mac 数据页布局和刷新模式可复用。
  - `apps/mac/Sources/HealthAgentMacCore/SidebarDestination.swift`: sidebar destination 是 Mac 入口真源。
  - `.claude/skills/mac-build-deploy/SKILL.md`: Mac 验证和本地安装发布流程。
- 缺什么:
  - Mac 没有 `DataConnectionsClient`。
  - Mac 没有连接中心页面。
  - Sidebar / Command Palette 没有连接治理入口。
- 硬约束:
  - 只读展示，不做 token refresh、撤权删除或重连 flow。
  - 不显示 token 或原始外部数据。
  - 连接健康以 backend `connection_health` 为准，旧后端响应使用 fallback。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `DataConnection`, `ConnectorPolicy`, `ConsentGrant`
- core_loop_step: Observe -> Decide 的数据可信度、授权透明化和运行时解释
- target_surface / safety_level / autonomy_tier: Mac sidebar `Data Connections` / privacy_sensitive / none
- spec_required(§8.1): 复用 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` DataConnection 合同。
- smallest_end_to_end_slice: Mac client + Mac page + sidebar/command palette entry。
- stale_surface_to_remove: 无
- **裁决**: PASS

## S2 · PRD

- 链接: `docs/prd/reva-personal-health-os-prd.md`
- 引用的权威能力: 真实数据、授权、可追溯、跨端一致连接状态。
- 边界(不做): 不做重连、不做 token refresh、不做撤权删除、不接新 provider。
- 验收 Gate: Mac 用户可从 sidebar 或 command palette 进入连接中心并看到 `connection_health` 映射后的状态。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 部署路由: Mac SwiftPM 改动，走 `swift test` + `swift build` + `apps/mac/scripts/package-app.sh --install --open` 本地安装重启。

## G2 · 可行性 + 安全压测

- 评审方式: Codex self-challenge
- 硬阻断(已焊进范围): 不显示 token、不新增写路径、不把 degraded 连接说成正常、不把 Data Sources 和 Data Connections 混成一个概念。
- **裁决**: PASS

## S4 · 研发任务分解

- 任务表:
  - [x] T1 RED: Mac Core 测试证明缺少 `DataConnectionsClient` / `DataConnection` 合同。
  - [x] T2 GREEN: 增加 Mac Core 模型、fallback、display mapping 和 endpoint。
  - [x] T3 UI: 增加 Mac `DataConnectionsView`、sidebar、command palette 和 service 注入。
  - [x] T4 验证、提交、安装重启、文档回写。

## S5 · 实现

- 委托: Codex
- 分支: `codex/rolling-runtime-next-slice`
- commit: `55964db040a0952063df1824488a93cc6687c155`

## G3 · 测试闸

- RED: `DataConnectionsClientTests` 先失败于缺少 `DataConnectionsResponse`、`DataConnectionHealth`、`DataConnectionsClient`。
- GREEN: `swift test --package-path apps/mac --filter 'DataConnectionsClientTests|MacP0FeatureTests/testSidebarIncludesDataConnectionsAsGovernedDataSurface|MacP0FeatureTests/testCommandPaletteBuildsCoreDesktopCommands'` 通过，6 tests / 0 failures。
- 集成闸:
  - `swift test --package-path apps/mac --filter HealthAgentMacCoreTests` 通过，259 tests / 1 skipped / 0 failures。
  - `swift build --package-path apps/mac` 通过。
  - `backend/venv/bin/python scripts/check_doc_drift.py` 通过。
  - `git diff --check` 通过。

## G4 · 安全闸

- 触发?: privacy_sensitive 连接状态展示。
- 自查:
  - 只读 UI。
  - 不显示 token。
  - 不扩大授权 scope。
  - 连接健康以 backend `connection_health` 为准。
- **裁决**: GO

## S6 · 部署

- 路由: Mac local package/install/open
- 部署 SHA / 回滚点:
  - 部署代码 commit: `55964db040a0952063df1824488a93cc6687c155`
  - 回滚点: `bc9e1c9fffdf888fdd92a41eccef785707cf97cc`
  - 本地安装命令: `apps/mac/scripts/package-app.sh --install --open`

## G5 · 部署健康闸

- `apps/mac/scripts/package-app.sh --install --open` 退出码 0。
- 产物: `apps/mac/dist/HealthAgentMac.app`。
- 已安装: `/Applications/健康 Agent.app`。
- 安装后重启: 结束旧进程后，第一次 `open` 遇到 LaunchServices `-600`；随后 `open -n '/Applications/健康 Agent.app'` 成功，新进程 `/Applications/健康 Agent.app/Contents/MacOS/HealthAgentMac` 正在运行。
- **裁决**: PASS

## S7 · 上线验证

- 本地 Mac app 已重启到新包；用户可通过 sidebar / command palette 进入“数据连接与授权”查看连接状态、授权 scope、最近同步、缓存可用性和 degraded explanation。
- user_id=3 当前生产 API 连接记录为 0 时，页面展示空状态，不伪造连接或健康结论。

## G6 · 验证闸

- Mac 本地发布验证 PASS。
- 真机/用户手动业务验收仍可继续补充截屏或点击审计；本切片不依赖 TestFlight。

## S8 · 沉淀

- 已回写:
  - `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`
  - `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 后续未完成:
  - token refresh、rate limit、provider retry policy。
  - 撤权后删除和审计 UI。
  - 更多 provider metadata 和 Review provenance 展示。
