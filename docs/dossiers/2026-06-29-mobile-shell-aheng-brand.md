# Dossier: Mobile Shell 阿衡品牌一致性

| 字段 | 值 |
|---|---|
| slug | `mobile-shell-aheng-brand` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile jest |

## S0 · 用户需求(逐字)

> 继续执行

本切片承接本周 P0 发布一致性。Chat / 首页主路径已经收敛为 `阿衡`,但登录页、锁屏态和 Siri 使用说明仍出现旧英文名 `HealthPilot`,会破坏上架前的统一品牌体验。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/app/login.tsx`:未登录入口标题。
  - `mobile/app/_layout.tsx`:Face ID 锁定时的根锁屏。
  - `mobile/app/settings.tsx`:Siri 语音记录使用说明。
- 缺口:
  - 三处高可见 shell surface 仍使用 `HealthPilot`。
  - App 显示名没有统一常量,容易继续漂移。
- 硬边界:
  - 不改 bundle id、target、URL scheme、历史服务名或 Siri Shortcuts 技术命名。
  - 不改认证、锁屏或 Siri 功能逻辑。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`AssistantPersona`, `UserSurface`, `ProvenanceRecord`
- core_loop_step:用户进入 App -> 解锁/登录/语音记录说明 -> 回到健康管理主线。
- target_surface / safety_level / autonomy_tier:Mobile shell / low(copy consistency) / read-only UI。
- spec_required(§8.1):否,不新增行为或写路径;收敛既有命名。
- smallest_end_to_end_slice:新增品牌常量,替换登录/锁屏/Siri 示例旧称并加回归测试。
- stale_surface_to_remove:`HealthPilot` 用户可见残留。
- 裁决:PASS。

## S2 · PRD

- 链接:`docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`
- 引用能力:统一产品人格与发布一致性。
- 不做:不重命名技术符号、不改 native 配置、不发版。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-mobile-shell-aheng-brand-plan.md`
- 任务:
  1. TDD:新增登录页、锁屏组件、Settings Siri 示例测试并确认 RED。
  2. 新增 `APP_DISPLAY_NAME` 常量。
  3. 抽出 `AppLockScreen` 并接回根布局。
  4. 替换登录页和 Settings 文案。
  5. 跑聚焦测试、TypeScript、dossier/doc drift。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - 改 Siri 技术标识可能破坏快捷指令;本批只改说明文案。
  - 改 root layout 可能影响锁屏;通过独立 `AppLockScreen` 测试保留解锁回调。
  - 品牌常量不应触发 native app.json 变更;本批仅 JS/TS。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 增加登录页品牌测试。
- [x] T2 增加锁屏品牌测试。
- [x] T3 增加 Settings Siri 示例测试。
- [x] T4 实现品牌常量和文案替换。
- [x] T5 回写 plan / dossier / weekly plan。

## S5 · 实现

- `mobile/constants/brand.ts`:新增 `APP_DISPLAY_NAME`。
- `mobile/app/login.tsx`:登录标题使用品牌常量。
- `mobile/components/AppLockScreen.tsx`:新增可测试锁屏组件。
- `mobile/app/_layout.tsx`:使用 `AppLockScreen`,移除内联旧锁屏。
- `mobile/app/settings.tsx`:Siri 示例使用品牌常量。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath __tests__/login.test.tsx components/__tests__/AppLockScreen.test.tsx app/__tests__/settings.test.tsx --runInBand`
  - 预期失败:登录页和 Siri 示例仍显示 `HealthPilot`;锁屏组件不存在。
- PASS:同一命令。
  - 3 suites passed,11 tests passed。

## G4 · 安全闸

- 触发?:否。仅品牌文案和锁屏组件抽取,不改变认证、锁屏、安全策略或写路径。
- 裁决:GO。

## S6 · 部署

- 本批未部署。属于 Mobile JS/TS/UI 文案变更,后续可随二维码包或 OTA 一起发布。

## G5 · 部署健康闸

- 本地测试闸通过。无线上部署。

## S7 · 上线验证

- 待后续真机/模拟器走查:登录页、Face ID 锁屏、Settings Siri 使用说明均显示 `阿衡`。

## G6 · 验证闸(人在环)

- 无新增人审阻塞。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续:继续 Rokid 专页旧称与 App Store 截图/审核材料收敛。
