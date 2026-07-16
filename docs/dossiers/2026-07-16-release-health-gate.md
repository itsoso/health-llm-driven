# Dossier: 发布健康门

| 字段 | 值 |
|---|---|
| slug | `release-health-gate` |
| 创建日期 | 2026-07-16 |
| 当前阶段 | G5 部署健康 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | backend tests -> doc drift -> backend deploy -> production admin verification |

## S0 · 需求与准入

- 需求：让已上线的 OTA/Remote Config 具备发布后健康判断，能指导管理员暂停放量。
- 产品对象：Controlled App Update Plane 的 Admin 观察能力。
- 不改变用户健康数据链路，不改变 Mobile 更新行为。
- G1 / G2：**PASS**。理由：直接服务既定 P0 发布控制能力，边界清晰，风险低于自动回滚。

## S1 · 决策

- 先做服务端可解释的只读健康门；
- 样本不足返回 `observe`；
- `pause_rollout` 只产生建议，不自动写 Remote Config，不执行 EAS；
- 自动回滚、原生升级页、跨端统一发布留到后续独立切片。

## G1 / G2 · 准入与可行性

- 输入为白名单客户端生命周期事件；
- 只使用聚合计数，不读取消息正文或健康数据；
- 沿用现有 Admin 看板权限；
- 无外部副作用，避免误触发回滚；
- **裁决：PASS。**

## S4 / S5 · 实现与测试

- [x] 写 PRD、Plan、Dossier；
- [x] 新增发布健康纯函数和固定阈值；
- [x] 接入 `client_events_stats` 的 `app_update.release_health`；
- [x] 覆盖样本不足、健康、紧急启动、更新失败和空终态分母；
- [x] 保留既有 app update 字段，并更新 schema 测试。

证据：

- `64 passed`：`backend/tests/test_observability_client_events.py backend/tests/test_client_events.py`；
- `python3 scripts/check_doc_drift.py`：架构事实一致；
- `git diff --check`：通过。

## G3 / G4 / G5 / G6 · 交付 Gate

状态：G3/G4 通过，G5 部署健康进行中，G6 待执行。

- G4 关注：管理员鉴权、用户过滤、阈值解释和埋点字段不扩张；
- G3 证据：81 个相关后端测试通过；Ruff、Python 编译、架构漂移、Dossier 一致性和 diff check 通过；
- G4 裁决：PASS。无新权限、无用户健康正文、只读聚合，沿用现有 Admin 看板鉴权；
- G5 目标：生产部署健康检查通过；
- G6 验收：生产 Admin 观察看板中出现 `client_events.app_update.release_health`，空窗口状态为 `observe`。

## 4. 变更索引

待实现：

- `backend/app/services/observability_service.py`
- `backend/tests/test_client_events.py`
- `backend/tests/test_observability_client_events.py`

## 5. 后续

需要真实样本和人工处置数据后，再定义连续窗口、自动暂停和自动回滚，不能由本切片直接推导。
