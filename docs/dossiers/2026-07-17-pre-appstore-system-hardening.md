# Dossier: App Store 前全局系统加固

| 字段 | 值 |
|---|---|
| slug | `pre-appstore-system-hardening` |
| 创建日期 | 2026-07-17 |
| 当前阶段 | S4 研发 |
| 状态 | building |
| 负责 | Codex |
| 发布策略 | 本轮只做系统加固；App Store 提交推迟到下周 |

## S0 · 需求

用户要求在下周 App Store 审核前，审计并解决功能、可用性、监控、安全、隐私和成本控制盲区，并自动执行规划。

## S1 · 现状与风险

- `basic_health` 创建和按用户读取缺少统一鉴权边界。
- 生产配置允许 DEBUG 和隐式 LLM recovery；TokenPlan 月预算只有展示配置，没有调用前阻断。
- open-loop 曾直接调用 APNs，绕过统一静默、通知预算和渠道日志，且可能把健康明细放入锁屏。
- `/health` 是存活探针，不能代表可发布；缺少 secret-free release readiness。
- 账号删除存在申请流程，但缺少机器可验证的用户范围清除报告。
- 归档文档和运维脚本曾包含明文数据库/测试登录凭据，属于发布前必须清除的密钥卫生问题。
- 语音、相机多图、网络/前后台恢复、推送点击和 App Store Connect 字段仍需要下周真实设备/人工 Gate。

## G1 · 准入

- first_class_objects: `SafetyGuardian`, `HealthAgendaItem`, `ExecutionEvent`, `WriteIntent`
- target_surface: backend + Mobile Agent
- safety_level: L3 health data
- smallest_slice: 鉴权健康数据、统一通知、预算闸门、发布 readiness、删除验证
- **裁决**: PASS

## G2 · 可行性与安全压测

- 评审范围: 认证、健康写入、锁屏隐私、主动推送、LLM 预算和账号删除。
- **裁决**: PASS，均可在现有服务边界内收口；生产删除和真机证据保留人工 Gate。

## S3 · 规划

- 规划: [`docs/plans/2026-07-17-pre-appstore-system-hardening.md`](../plans/2026-07-17-pre-appstore-system-hardening.md)
- P0: 鉴权 → 配置/预算 → 通知管线。
- P1: 删除验证 → readiness/监控 → 测试与真实发布证据。

## S4 · 研发任务

- [x] T1 健康数据鉴权与跨用户测试。
- [x] T2 生产配置、LLM 恢复和 TokenPlan 预算 fail-closed。
- [x] T3 open-loop 统一 PushService 与锁屏隐私文案。
- [x] T4 readiness、删除验证和 admin 诊断入口。
- [x] T5 前后台/网络/图片/Agent 幂等回归与测试闸。
- [x] T6 文档生成、main 提交推送和发布前阻断核对。
- T6 代码提交已推送到 `main`：`a9a59d1a0`。

## G3 · 测试

- 变更范围回归: `78 passed`。
- 额外配置回归: `7 passed`。
- 全量仓库测试曾运行到 `3514 passed, 2 skipped`；该轮启动早于本次测试修订，包含 1 个已更新断言和 2 个当时环境缺失 `icalendar` 的旧失败，随后因单个无超时测试卡住而人工中止。
- `check_doc_drift.py`: PASS；`check_dossier_consistency.py`: PASS；App Store release pack: PASS；修改文件 compileall: PASS。
- **裁决**: PASS（变更范围）；全量仓库需在下周 RC 环境以带超时命令重跑，不能把中止结果写成全量通过。

## G4 · 安全

- 评审: 认证、写回执、通知隐私、删除范围、成本闸门、仓库密钥卫生。
- 已移除当前工作树中的历史数据库密码/测试登录密码；备份和迁移脚本改为强制读取 `DATABASE_URL`/`POSTGRES_URL`，不再内置凭据。
- 生产环境必须轮换曾出现在历史提交中的凭据；Git 历史清理需另行审批，不在本轮自动重写。
- **裁决**: PASS（代码侧）；生产凭据轮换为发布前人工前置条件。

## S6/G5 · 部署

- 后端部署: 等生产 Sentry、TokenPlan 月额度和部署健康证据齐备后再执行。
- 当前资格: 未执行；本地 readiness 会在生产配置缺失时阻断。
- **裁决**: pending

## G6 · 人在环

- 真实 iPhone、相机多图、语音、推送静默/点击、网络切换、分享、删除入口和 App Store Connect 字段：下周最终 RC 执行。
- 当前资格: 未执行；不以模拟器替代。
- **裁决**: pending

## S8 · 沉淀

- 状态: completed
- 备注: system-map 和 dossier 一致性检查已通过；不把本轮代码侧通过误写成 App Store 已就绪，所有人工 Gate 保留 pending。
