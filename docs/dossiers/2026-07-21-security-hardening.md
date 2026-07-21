# Security Hardening Dossier

| 字段 | 值 |
|---|---|
| slug | `security-hardening` |
| 创建日期 | 2026-07-21 |
| 当前阶段 | S5 实现与验证 |
| 状态 | building |
| 负责 | Codex |
| 范围 | 2026-07-21 只读审计确认的安全问题 |

- 明确例外: 保持当前 JWT 两年有效期。该例外不允许 URL token、脚本可读存储、缺少撤销控制或 scope 绕过。

## G1 · Requirement Admission

- 裁决: PASS。该工作保护 L3/L4 健康与凭据数据，直接支撑 Health OS 信任边界，不新增产品 surface。

## G2 · Feasibility And Risk

- 裁决: PASS。采用分批交付，先关闭生产匿名读写；兼容 URL 保留，但必须经过当前用户或管理员授权。后续批次需通过各自安全测试才可进入部署 Gate。

## Current Evidence

- Production returned `200` without authentication for multiple per-user Garmin, recommendation, disease, and diet endpoints.
- Anonymous write routes accept client-supplied `user_id` for disease and daily-health records.
- Main CI is red and includes a direct-database-write guard failure for voice shortcuts.
- Production database backup is currently captured by the deployment Git stash instead of remaining in the backup directory.
- Full finding inventory and execution order are in `docs/plans/2026-07-21-security-hardening-execution-plan.md`.

## Gate Ledger

| Gate | State | Evidence |
|---|---|---|
| G1 Admission | GO | Security/privacy requirement |
| G2 Feasibility | GO | Compatibility-preserving staged design |
| G3 Tests | IN PROGRESS | SQLite/前端/Mobile/Mac/依赖审计已分项通过；完整回归继续收口 |
| G4 Safety review | PENDING | 需完成安全与隐私复审 |
| G5 Deploy health | NOT ENTERED | 未满足生产角色、备份恢复和完整测试前不进入部署 |
| G6 Production verification | NOT ENTERED | 尚未部署，不作上线成功声明 |

## Delivery Log

- 2026-07-21: Read-only audit completed; overall verdict NO-GO.
- 2026-07-21: User accepted the current JWT lifetime and authorized all other findings to be fixed in severity order.
- 2026-07-22: P0 匿名路由、API key scope、Agent 写入授权、跨端凭据存储、上传与解析配额、备份与基础设施配置已完成本地实现；部署仍受 G3-G5 约束。
