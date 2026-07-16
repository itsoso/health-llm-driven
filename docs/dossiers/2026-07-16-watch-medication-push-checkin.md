# Dossier: Watch 用药提醒一键打卡

| 字段 | 值 |
|---|---|
| slug | `watch-medication-push-checkin` |
| 创建日期 | 2026-07-16 |
| 当前阶段 | G4 安全闸 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | backend deploy -> Mobile production OTA -> iPhone + Apple Watch 真机验证 |

## S0 · 用户需求

> 手表上的push提醒，如果是吃药的，点击服用，要打卡到系统里里边，这样最自然，精度最高，不需要自己再去手工打卡。

- 锚点用户用 Apple Watch 承接多药多时点执行；当前动作在 App 终止时可能未进入 JS，仍需手机二次打卡。

## S1 · Discovery

- `backend/app/tasks/notifications.py` 已发送隐私泛化的 `MEDICATION_REMINDER`，data 有药物 id 和提醒时间。
- `mobile/hooks/useNotifications.ts` 已注册动作，但原 `opensAppToForeground:false` 在 terminated-app 场景不能保证 JS listener 被调用，旧写入还丢失时间槽并静默吞错。
- `backend/app/services/medication_service.py` 已提供按用户、药物、日期、时间槽的幂等 `MedicationLog`，并回写议程；无需新增表或接口。
- `apps/watch` 已把 Watch 定义为执行面；iOS actionable notification 可镜像到 Watch，本切片不新增腕上诊断或处方行为。

## G1 / G2 · 准入与可行性

- 对象：`HealthAgendaItem`、`ExecutionEvent`；核心环：提醒 -> 明确执行 -> 依从事实 -> 复盘。
- Surface：Watch 执行，Mobile 可靠桥接，Backend 为真源。
- safety / autonomy：`medical_boundary` / `manual_confirm`；不自动推断服用，不修改处方。
- Feature Spec：`docs/specs/active/2026-07-16-watch-medication-push-checkin.md`。
- 最小切片：现有推送 payload + “服用”动作 + cold-start 补偿 + 现有幂等写接口。
- **裁决：PASS。** PRD R4/R15 明确要求“腕上一键已吃”，平台限制通过 foreground wake + cold response 补偿显式处理。

## S4 / S5 · 实现

- [x] 用药通知动作改为“服用”，允许唤醒被终止的 iOS App。
- [x] 动作统一走 typed `logMedication`，携带提醒时间槽，不再走旧的无时间写路径。
- [x] 成功后刷新今日用药、时间线、议程；失败上报且不清 cold response。
- [x] response 以 notification id + action id 去重，服务端继续做同槽幂等。
- [x] 锁屏文案与按钮统一为“服用”，保持药名/剂量只在 data payload。

## G3 · 测试闸

- Mobile focused Jest：5 suites / 86 tests PASS。
- Mobile TypeScript：PASS；target ESLint：0 errors（既有 warnings 保留）。
- Backend focused pytest：64 passed（用药推送隐私、`MedicationLog` 幂等、多剂时间槽与议程回写）。
- `git diff --check`：PASS。
- Dossier 一致性闸：55 份全部自洽。
- **裁决：绿。**

## G4 · 安全闸

- 触发：用药依从写路径、跨 Watch/Mobile notification contract。
- 必审：用户归属、同槽幂等、失败不伪成功、锁屏隐私、不得把提醒动作解释为处方或已验证吞咽。
- **裁决：待独立 safety/privacy review。**

## S6 / G5 · 部署

- 路由：backend deploy -> production OTA；无原生依赖变化。
- 部署标识与健康结果：待发布后回填。

## S7 / G6 · 上线验证

- 自动化覆盖 notification category、冷启动消费、失败保留、MedicationLog contract。
- 真机待验：iPhone + Apple Watch 收到用药提醒 -> Watch 点击“服用” -> 今日用药和数据库同时间槽出现 taken 记录。
- **裁决：待用户真机确认。**
