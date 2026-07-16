# Dossier: Watch 用药提醒一键打卡

| 字段 | 值 |
|---|---|
| slug | `watch-medication-push-checkin` |
| 创建日期 | 2026-07-16 |
| 当前阶段 | G4 安全复审 |
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
- [x] 动作统一走 typed `logMedication`，携带提醒发生日期、时间槽和时区，不再走旧的无时间写路径。
- [x] 成功后刷新今日用药、时间线、议程；失败提示、保留 cold response，并在联网恢复/回前台时重试。
- [x] response 以 occurrence `rule_id` + action id 去重，避免 iOS 复用重复通知 id 吞掉次日动作；服务端继续做同槽幂等。
- [x] 锁屏文案与按钮统一为“服用”，保持药名/剂量只在 data payload。
- [x] 后端在写日志前按认证用户校验药物归属；旧日期打卡只落依从事实，不误完成今天议程。
- [x] 每日重复的本地通知取消直写 category；只有带完整 occurrence identity 的远程推送提供腕上“服用”。
- [x] 待处理动作先进入端上持久队列；连续点击多个离线提醒时按 occurrence 逐条补写，不依赖 iOS 只保留一条的 last response。
- [x] 同一时点原为“跳过/延后”时，“服用”会把该唯一记录纠正为 `taken`；客户端同时校验回执状态、药物、日期和时间，禁止冲突回执伪成功。

## G3 · 测试闸

- Mobile focused Jest：5 suites / 90 tests PASS（连续多图、媒体草稿、通知动作、持久重试队列、本地提醒）。
- Mobile TypeScript：PASS。
- Backend focused pytest：138 passed（用药推送隐私、用户隔离、明确发生日、状态纠正、`MedicationLog` 幂等、多剂时间槽、议程回写、并发和图片记餐确认闸门）。
- Mobile 目标 ESLint：0 errors（测试文件保留 10 个既有 import-order warnings）。
- `git diff --check`：PASS。
- Dossier 一致性闸：54 份全部自洽。
- **裁决：绿。**

## G4 · 安全闸

- 触发：用药依从写路径、跨 Watch/Mobile notification contract。
- 必审：用户归属、同槽幂等、失败不伪成功、锁屏隐私、不得把提醒动作解释为处方或已验证吞咽。
- 首轮独立 review：**NO-GO**。阻断项为：(1) 缺日期/时区时错误回退手机当前时间；(2) 写入失败缺少用户可见状态和自动重试；(3) 以可能复用的 iOS request id 去重会吞次日动作。
- 修正证据：远程 payload 补齐 `scheduled_date/time/timezone/rule_id` 并严格匹配；失败保留 response、显示通用失败通知和 toast、联网/前台自动重试；去重键改为 `rule_id + action`；本地重复提醒取消直写；后端补用户归属校验。
- 第二轮独立 review：**NO-GO**。阻断项为：(1) 同槽已有 `skipped/delayed` 时“服用”可能返回旧状态却提示成功；(2) iOS last response 无法保存连续多个离线动作；(3) 多图记餐仅靠提示词要求草稿，模型仍可能在首轮直接写库。
- 第二轮修正证据：服务端将同槽 `skipped/delayed -> taken` 原位纠正且保持单行；客户端严格核对写回结果；端上新增非敏感 occurrence 持久队列并串行排空，且不设静默截断上限；Agent executor 对 mobile 图片记餐首轮实施确定性 draft-only 闸门，即使模型自行传 `confirmed=true` 也禁止写入。
- **裁决：等待独立复审，复审前禁止发布。**

## S6 / G5 · 部署

- 路由：backend deploy -> production OTA；无原生依赖变化。
- 部署标识与健康结果：待发布后回填。

## S7 / G6 · 上线验证

- 自动化覆盖 notification category、冷启动消费、失败保留、MedicationLog contract。
- 真机待验：iPhone + Apple Watch 收到用药提醒 -> Watch 点击“服用” -> 今日用药和数据库同时间槽出现 taken 记录；离线连续点两个不同时点后联网，两条均补写且不重复。
- **裁决：待用户真机确认。**
