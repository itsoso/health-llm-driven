# Dossier: Web 数据连接与授权中心

| 字段 | 值 |
|---|---|
| slug | `web-data-connections-center` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | frontend deploy |

## S0 · 用户需求(逐字)

> 继续执行

- 上下文解释: 后端已发布 `connection_health`，Mobile 已展示连接健康；本切片把同一只读合同接入 Web，补齐 Web 用户查看外部数据源、授权 scope、同步和降级状态的入口。
- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1): Web 用户需要从管理中心查看真实数据连接状态；当前只能在设置的分散设备区查看局部信息，无法看到统一 `DataConnection` / `ConnectorPolicy` 合同。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `frontend/src/services/api/client.ts`: Web API client 已统一处理 token 和 401。
  - `frontend/src/components/Navigation.tsx`: 管理中心已有 `/data-collection`、`/settings` 等入口。
  - `frontend/src/app/settings/page.tsx`: 设置页已有设备与授权相关卡片区。
  - `frontend/src/services/api/medicalExams.test.ts`: 服务层 Vitest 模式可复用。
- 缺什么:
  - Web 没有 `dataConnections` service。
  - Web 没有 `/data-connections` 页面。
  - 导航和设置页没有统一连接中心入口。
- 硬约束:
  - 只读展示，不做重连 flow。
  - 不显示 token 或原始外部数据。
  - 不做撤权删除。
  - Mac 入口另起切片，避免一次横跨 Swift sidebar/IA。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `DataConnection`, `ConnectorPolicy`, `ConsentGrant`
- core_loop_step: Observe -> Decide 的数据可信度与授权透明化
- target_surface / safety_level / autonomy_tier: Web `/data-connections` / privacy_sensitive / none
- spec_required(§8.1): 复用 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` DataConnection 合同。
- smallest_end_to_end_slice: Web service + Web page + navigation/settings entry。
- stale_surface_to_remove: 无
- **裁决**: PASS
- 用户确认: 已由“继续执行”授权。

## S2 · PRD

- 链接: `docs/prd/reva-personal-health-os-prd.md`
- 引用的权威能力: 真实数据、授权、可追溯、跨端一致连接状态。
- 边界(不做): 不做重连、不做 token refresh、不做撤权删除、不做 Mac。
- 验收 Gate: Web 用户可从导航或设置进入连接中心并看到 `connection_health` 映射后的状态。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 部署路由: Web 前端改动，走 `./deploy.sh -f -y`。

## G2 · 可行性 + 安全压测

- 评审方式: Codex self-challenge
- 硬阻断(已焊进范围): 不显示 token、不新增写路径、不把 degraded 连接说成正常。
- **裁决**: PASS

## S4 · 研发任务分解

- 任务表:
  - [x] T1 RED: Web service 测试证明缺少 `dataConnections` service。
  - [x] T2 GREEN: 增加 Web service 类型、fallback、display 映射和 endpoint。
  - [x] T3 UI: 增加 `/data-connections` 页面、导航入口和设置页入口。
  - [x] T4 验证、提交、部署、生产 smoke 和文档回写。

## S5 · 实现

- 委托: Codex
- 分支: `codex/rolling-runtime-next-slice`
- commit: `f6ab4e3dc688e583a72f43583e3fd51c8d69926a`

## G3 · 测试闸

- RED: `frontend/src/services/api/dataConnections.test.ts` 先失败于 `Failed to resolve import "./dataConnections"`。
- GREEN: 同测试通过。
- 集成闸:
  - `npm test -- src/services/api/dataConnections.test.ts`: `3 passed`。
  - `npx tsc --noEmit`: 通过。
  - `npm run build`: 通过，`/data-connections` 进入 Next route table。
  - `scripts/check_doc_drift.py`: 通过，Web pages 派生计数更新。
  - `git diff --check`: 通过。
- **裁决**: 绿

## G4 · 安全闸

- 触发?: privacy_sensitive 连接状态展示。
- 自查:
  - 只读 UI。
  - 不显示 token。
  - 不扩大授权 scope。
  - 连接健康以 backend `connection_health` 为准。
- **裁决**: GO

## S6 · 部署

- 路由: frontend deploy
- 部署 SHA / 回滚点:
  - 前端部署 HEAD: `f6ab4e3dc688e583a72f43583e3fd51c8d69926a`
  - 回滚点: `b7116a17`

## G5 · 部署健康闸

- frontend deploy: `./deploy.sh -f -y` 成功，PM2 `health-frontend` online。
- production page smoke:
  - `GET https://health.executor.life/data-connections`: `page_status=200 page_bytes=24530 next_payload_present=True route_text_present=True`。
- production service smoke:
  - `GET https://health.executor.life/api/v1/health`: `health_status=200 status=healthy`。
  - 服务器本机 user_id=3 authenticated `GET /api/v1/data-connections/me`: `http_status=200 connections=0 health_count=0 health_statuses=[] user_actions=[]`。
- **裁决**: PASS

## S7 · 上线验证

- 真实路径验证: Web 连接中心页面已在生产路由可访问；页面使用同一 `/api/v1/data-connections/me` 只读合同，生产 anchor 用户 user_id=3 的 API 合同返回 200。
- 结果(相关非因果措辞): 本切片已补齐 Web 端查看外部数据连接健康、授权范围、同步状态和降级解释的入口；user_id=3 当前没有连接记录，因此正向连接卡片状态由本地 service/unit test 和已发布 backend rollback 合同 smoke 覆盖。

## G6 · 验证闸

- 需求在 prod 对 anchor 用户真成立?: PASS；Web 页面路由、Next payload、后端只读合同均已生产验证。
- 真机/发布用户确认: 不涉及 Mobile 真机或 TestFlight；Web 生产发布已完成。
- **裁决**: PASS(回路闭合)

## S8 · 沉淀

- 新坑沉淀: Web/Mobile 均消费同一个 `connection_health` display mapping；后续 Mac 实现应复用语义，不再各端手写 degraded/revoked 文案。
- 文档同步: `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` 和 `docs/plans/2026-06-27-health-runtime-governance-plan.md` 已回写。
- 状态 -> **shipped**: 完成
