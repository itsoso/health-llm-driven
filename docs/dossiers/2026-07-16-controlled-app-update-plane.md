# Dossier: 受控应用更新平面

| 字段 | 值 |
|---|---|
| slug | `controlled-app-update-plane` |
| 创建日期 | 2026-07-16 |
| 当前阶段 | S7 上线验证 |
| 状态 | verified |
| 负责 | Codex + 用户确认 |
| 反馈环 | backend pytest / Mobile Jest / TypeScript / deploy health / Mobile OTA |

## S0 · 用户需求(逐字)
> 按照这个：Mobile OTA 负责快速迭代，原生发版负责安全和能力边界，Remote Config 负责控制，回滚系统负责生产稳定性。还需要做什么？
>
> 开干

- 谁用 / 解决什么 / 现在怎么绕过：产品研发和运维需要可控地发布跨端健康应用更新，当前主要依赖 EAS、环境变量、端内诊断和后端 deploy 回滚。
- 锚点用户相关性：更新故障不能阻断用户查看和执行既有健康行动。

## S1 · Discovery(现状勘察)

- 已有：`mobile/services/appUpdate.ts`、`mobile/hooks/useAppUpdate.tsx`、`mobile/components/updates/AppUpdateBanner.tsx`、`scripts/mobile-ota.sh`、`mobile/services/appDiagnostics.ts`、`mobile/services/clientEvents.ts`、`backend/app/api/client_events.py`、`backend/app/services/observability_service.py`、`deploy.sh`。
- 已有但不完整：后端健康分失败自动回滚；Remote Config 只有环境级 flags；Mobile 没有远程发布策略、manifest、回滚命令和 update telemetry。
- 硬约束：原生改动不可 OTA；不丢聊天草稿和未发送图片；更新 telemetry 不含健康内容；Admin 写接口必须鉴权和审计；失败必须可见，不静默假成功。

## G1 · 准入裁决

- first_class_objects: `ExecutionEvent` + 工程基础设施。
- core_loop_step: `Agenda top action -> Mobile / Watch execution` 的版本可达性。
- target_surface / safety_level / autonomy_tier: Backend Admin + Mobile；基础设施 L2；配置写入仅 admin manual-confirm。
- spec_required: 本批基础设施 spec，医疗安全行为不远程配置。
- smallest_end_to_end_slice: 获取策略 -> 检查 OTA -> 上报终态 -> 记录 manifest -> 可 dry-run/确认回滚。
- **裁决**：PASS。

## S2 · PRD

- 链接：`docs/prd/2026-07-16-controlled-app-update-plane.md`
- 边界：不做自动灰度、不做自动崩溃回滚、不修改医疗规则。

## S3 · 规划

- 链接：`docs/plans/2026-07-16-controlled-app-update-plane.md`
- 发布路由：backend deploy -> Mobile OTA；新增原生能力仍走原生构建。

## G2 · 可行性 + 安全压测

- 硬阻断已焊进规划：Remote Config 失效使用安全默认；客户端配置不携带健康数据；Admin 并发更新必须 version check；回滚默认 dry-run。
- 待拍板分叉：无。自动灰度和崩溃循环回滚明确延期，不阻塞本批。
- **裁决**：PASS。

## S4 · 研发任务分解

- [x] T1 Remote Config 数据模型与 API
- [x] T2 Mobile policy cache
- [x] T3 OTA lifecycle telemetry
- [x] T4 manifest 与 rollback command
- [x] T5 本地测试、审计和发布前检查
- [x] T6 部署、OTA、上线验证

## S5 · 实现

- 分支：`main`（按项目约束直接在 main 开发；保留并发 WIP 不触碰）
- 代码 commit：`fdb71e893`；与远端 Claude Mobile 视觉提交合并为 `2c61b638c` 并推送。

## G3 · 测试闸

- `backend`: `64 passed`（app release policy + client events）；managed migration/deploy source `21 passed`。
- `mobile`: `5 suites / 44 tests passed`；`tsc --noEmit`、相关 ESLint 通过。
- scripts: OTA/rollback contract `13 passed`；Bash syntax 通过。
- `check_doc_drift.py`、`check_dossier_consistency.py`、`git diff --check` 通过。
- 全量 CI shards 由 push 后 CI 继续验证；本地未以 `run-all-tests.sh` 代替 CI。
- **裁决**：PASS（本地 focused G3）。

## G4 · 安全闸

- 触发：认证、Admin 配置写入、客户端更新控制。
- 已完成代码级检查：Admin 依赖、乐观并发、过期/作用域校验、按分隔符拆分的 kill switch 医疗词拒绝、telemetry 字段白名单和固定错误码；强制 OTA 仅隐藏“稍后”不自动重载。
- 策略发布写入 `AgentAuditLog`，不写健康正文；API 响应和请求已生成前端类型。
- **裁决**：PASS（本地代码级 G4；生产凭证仍需 G5/G6）。

## G5 · 部署健康

- `./deploy.sh -b -y` 完成；生产 managed migration `20260716_180000_add_app_release_policies` 已应用。
- 生产后端健康分：`60/60 PASS`。
- 线上 skills manifest：本地 `22` = 线上 `22`。
- 线上 `/api/v1/health`：`healthy`，API/database/redis/celery 均正常。
- **裁决**：PASS。

## S7 / G6 · 上线验证

- production OTA 已发布，runtime `1.3.1`。
- EAS group：`c0868df9-a54b-4cfa-a39d-4f681e4f0ed2`。
- iOS update：`019f6a9a-35cf-7b71-a493-0bff788a4136`。
- `eas update:view <group> --json` 返回上述 update、channel `production`、commit `2c61b638c`，证据有效。
- 上一组已验证回滚目标：group `1e3308a8-bd79-4064-b53f-8f6a084957f3`，iOS update `019f6a55-89cd-75c8-9eb2-d3d48c48db98`；已写入本地 ignored manifest。
- `./scripts/mobile-ota-rollback.sh production` dry-run 成功，未调用 EAS；本次没有执行破坏性回滚。
- **裁决**：PASS。后续若生产异常，必须人工确认后再执行 `--confirm`。

## S8 · 后续未纳入本批

- 自动 crash-loop 回滚、自动灰度推进和跨端（Mac/Web）统一发布策略仍进入后续阶段。
- 原生版本兼容门已由独立 dossier [`2026-07-16-native-release-compatibility-gate.md`](2026-07-16-native-release-compatibility-gate.md) 完成：策略能阻断不兼容 OTA，并在客户端显示原生升级提示。

### 2026-08-21 · EAS CLI 版本漂移收口

- 根因：`scripts/mobile-ota.sh` 的默认发布路径调用未指定版本的 `npx eas-cli`，操作者机器上的缓存或 npm 最新版本可改变正式 OTA 行为。
- 修正：默认路径固定调用 `eas-cli@22.0.0`；测试注入的 `OTA_EAS_RUNNER`、源码守卫、发布锁、同字节重试和回滚证据契约均保持不变。
- TDD：新增契约先因缺少精确版本而 RED，最小修改后 GREEN；完整 `scripts/test_mobile_fast_feedback_scripts.py` 为 `24 passed`，`/bin/bash -n scripts/mobile-ota.sh` 与真实 `eas-cli/22.0.0` 版本探针通过。
- CI：`main` 精确提交 `8c86c5e19` 的 GitHub Actions run `32476664262` 全部通过，包括 `release-invariants`、Mobile、Mac、PostgreSQL 与后端测试矩阵。
- 边界：本次完成工具版本硬化及 exact-commit G3/G4 代码闸，未发布 OTA；下一次获权正式 OTA 的 EAS group/update receipt 和真机应用结果仍分别裁决 G5–G6。
