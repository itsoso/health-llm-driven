# Dossier: 受控应用更新平面

| 字段 | 值 |
|---|---|
| slug | `controlled-app-update-plane` |
| 创建日期 | 2026-07-16 |
| 当前阶段 | S5 实现 / 待发布 |
| 状态 | release-candidate |
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
- [ ] T6 部署、OTA、上线验证

## S5 · 实现

- 分支：`main`（按项目约束直接在 main 开发；保留并发 WIP 不触碰）
- commit：待完成

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

## S6 / G5 / S7 / G6

- 待 commit/push 后填写 backend deploy health、production OTA group/update ID、manifest 和 rollback dry-run 证据；不以本地测试替代生产健康和 OTA 证据。
