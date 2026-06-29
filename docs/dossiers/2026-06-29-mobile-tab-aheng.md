# Dossier: Mobile Tab Rename To 阿衡

| 字段 | 值 |
|---|---|
| slug | `mobile-tab-aheng` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile jest / release-pack gate |

## S0 · 用户需求(逐字)

> 确认 走1

上下文:用户确认底部导航命名方案 1,即把 `今日 / 私教 / 记录 / 我` 改为 `今日 / 阿衡 / 记录 / 我`。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/app/(tabs)/_layout.tsx`:Expo Router bottom tabs 和自定义浮动 tab bar。
  - `scripts/check_app_store_release_pack.py`:App Store 高可见文案防漂移 gate。
  - `docs/release/app-store/*`:App Store metadata / review notes / screenshot runbook。
- 缺口:
  - `Tabs.Screen` 和 `TAB_META` 仍显示 `私教`。
  - release narrative gate 仍把 `今日 / 私教 / 记录 / 我` 当作当前正确文案。
  - system-map / mobile product map 仍使用旧 tab label。
- 硬边界:
  - 不改 route name、文件名、URL scheme 或历史技术符号。
  - 不改变 Chat 功能、动态卡片、写入安全边界或 App Store final-submit 人审材料。

## G1 · 准入裁决

- first_class_objects:`AssistantPersona`, `UserSurface`, `ProvenanceRecord`
- core_loop_step:用户从底部导航进入 Chat + 动态 UI 卡片健康参谋。
- target_surface / safety_level / autonomy_tier:Mobile tab + release docs / low(copy consistency) / none。
- spec_required(§8.1):否,不新增行为或写路径。
- smallest_end_to_end_slice:Mobile tab label + release narrative gate + docs 同步。
- stale_surface_to_remove:用户可见底部 tab 中的 `私教`。
- 裁决:PASS。

## S2 · PRD

- 链接:`docs/plans/2026-06-29-mobile-tab-aheng-design.md`
- 用户价值:底部导航直接指向 AI 人格 `阿衡`,减少“私教=健身训练”的误解。
- 不做:不重命名 `/chat`、不改 Chat 功能、不改 App 名。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-mobile-tab-aheng-implementation-plan.md`

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - 只改 `Tabs.Screen.title` 会漏掉自定义 `TAB_META`。
  - App Store release gate 必须同步,否则后续会把旧 tab 文案重新引入审核材料。
  - 技术符号不应跟随 UI label 重命名。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 RED:Mobile tab label helper 测试。
- [x] T2 RED:Release narrative gate 把 `私教` 视作旧叙事。
- [x] T3 GREEN:Mobile tab label / accessibility 实现。
- [x] T4 GREEN:Release gate 和 App Store docs 更新。
- [x] T5 文档回写和验证。

## S5 · 实现

- `mobile/app/(tabs)/_layout.tsx`:第二 tab 显示为 `阿衡`,a11y 为 `阿衡，与健康参谋对话`,并导出 tab metadata helper 防漂移。
- `scripts/check_app_store_release_pack.py`:当前底部导航推进为 `今日 / 阿衡 / 记录 / 我`,并把 `私教` 纳入旧用户可见叙事。
- `docs/release/app-store/*`、`docs/system-map/*`、`mobile/PRODUCT_MAP.md`:同步当前 tab 语义。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath 'app/(tabs)/__tests__/tabLayout.test.ts' --runInBand`
  - 初始失败:`getMainTabLabels` / `getMainTabAccessibilityLabels` 不存在。
- RED: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py::test_release_narrative_rejects_stale_public_positioning -q --no-cov`
  - 初始失败:release narrative gate 未把 `私教` 视作 stale user-visible term。
- PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath 'app/(tabs)/__tests__/tabLayout.test.ts' --runInBand`
  - 1 suite passed,2 tests passed。
- PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py -q --no-cov`
  - 4 passed。
- PASS: `python3 scripts/check_app_store_release_pack.py`
- PASS: `cd mobile && ./node_modules/.bin/tsc --noEmit`

## G4 · 安全闸

- 触发?:否。仅 UI label / release docs / release gate,不改健康建议、写路径、认证、隐私数据处理或医疗边界。
- 裁决:GO。

## S6 · 部署

- 本批不部署。属于 Mobile JS/TS/UI + docs/tooling 改动,可随后续 OTA/二维码包发布。

## G5 · 部署健康闸

- 本地 release gate 通过。无线上部署。

## S7 · 上线验证

- 待后续模拟器/真机走查:底部第二 tab 显示 `阿衡`,点击仍进入原 chat route。

## G6 · 验证闸(人在环)

- 用户已确认命名方案 1:`今日 / 阿衡 / 记录 / 我`。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续:继续 Daily Artifact 主屏视觉走查、Chat card 成功反馈和最终截图/审核材料。
