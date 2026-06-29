# Dossier: 本周发布优先级与阿衡品牌闸

| 字段 | 值 |
|---|---|
| slug | `weekly-release-priority-and-brand-gate` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | local tests / release pack gate / mobile QR later |

## S0 · 用户需求(逐字)

> 列出本周要做的事情，基于规划，逐个研究下，然后确定优先级去实现。

- 谁用 / 解决什么 / 现在怎么绕过:创始人和首批用户需要下周可用发布版;现在功能很多,但发布材料、品牌名、每日主线和上架闸门仍分散。
- 锚点用户相关性:35-55 高强度慢病早期用户需要每天打开就知道该做什么,而不是在功能列表里找入口。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `docs/PRODUCT_ROADMAP.md`:H1 排序是 Daily Artifact + 5 分钟 on-ramp + trust-custodianship。
  - `docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`:立即下一步前五项为安全、Daily Artifact、收敛、文档漂移、onboarding。
  - `docs/dossiers/2026-06-28-app-store-mvp-release.md`:App Store 发布仍 pending demo 截图、人审、ASC credentials、真机走查。
  - `docs/release/app-store/submission-pack.md`:最新主名为 `阿衡`,全称 `中和知微`,公司 `睿为健康`。
  - `mobile/app.json`:`CFBundleDisplayName` 已是 `阿衡`,但 Expo `name` 仍残留旧名。
- 缺什么:
  - 本周优先级需要固化成计划,避免继续按“功能列表”推进。
  - 发布检查缺少用户可见 App 名一致性闸。
- 硬约束 / 平台·安全边界:
  - App Store 发布不能跳过 demo account、截图人审、ASC 凭证。
  - 不重命名 Xcode target / bundle id / 工程历史符号,只修用户可见发布名。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`HealthAgendaItem`, `ExecutionEvent`, `ConsentGrant`, `ProvenanceRecord`
- core_loop_step:发布入口一致性 -> 用户进入 Today/Chat/Record/Me 核心动线。
- target_surface / safety_level / autonomy_tier:Mobile + release docs / low + privacy_sensitive wording / none。
- spec_required(§8.1):否,本切片是发布治理和用户可见命名一致性,不新增健康行为。
- smallest_end_to_end_slice:锁定 `阿衡` 为 app.json name、CFBundleDisplayName、variant displayName 和 release gate 期望值。
- stale_surface_to_remove:不删除旧技术符号;仅防用户可见发布面回退。
- 裁决:PASS。

## S2 · PRD

- 链接:沿用 `docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`。
- 引用的权威 R 号:Daily Artifact、5 分钟 on-ramp、App Store 可用版。
- 边界(不做):不提交 App Store、不生成 ASC 凭证、不重命名 Xcode target。
- 验收 Gate:release checker 和 app config tests 能阻止旧名回退。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-weekly-release-execution-plan.md`
- 分阶段 + 反馈环路由:
  1. P0 发布一致性闸(local tests)。
  2. P0 截图/审核材料闸(需人审与 demo account)。
  3. P1 Daily Artifact 主线(OTA)。
  4. P1 Chat card 主路径(OTA + backend deploy if needed)。
  5. P2 Watch/HealthKit 真机能力(QR/EAS/用户配合)。
- 长杆 / spike:ASC credentials、demo account、App Store screenshot 人审、watch 真机签名。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 硬阻断(已焊进规划):不能把旧名 `HealthPilot` 作为用户可见 App 名;不能假装提交已完成。
- 待拍板分叉:无。
- 裁决:PASS。

## S4 · 研发任务分解

- 任务表:
  - [x] T1 固化本周计划和优先级。
  - [x] T2 把用户可见 App 名统一为 `阿衡`。
  - [x] T3 增强 release checker 和 Jest 测试,防止旧名回退。
  - [x] T4 验证、回写 App Store dossier、提交。
- 并发检查:已 `git pull --ff-only` 同步 `origin/main`;本地仅有未跟踪截图证据目录,不触碰。

## S5 · 实现

- 修改 `mobile/app.json`、`mobile/app.config.ts`、`mobile/__tests__/app-config.test.ts`、`scripts/check_ios_app_store_submission.py`、`scripts/check_app_store_release_pack.py`、`backend/tests/test_ios_app_store_submission_preflight.py`。

## G3 · 测试闸

- PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath __tests__/app-config.test.ts --runInBand`
  - 1 suite passed,7 tests passed。
- PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_ios_app_store_submission_preflight.py backend/tests/test_app_store_release_pack.py -q --no-cov`
  - 4 passed。
- PASS: `python3 scripts/check_ios_app_store_submission.py`
  - 输出包含 `app_name=阿衡 bundle_id=life.executor.health asc_app_id=6763569720`。
- PASS: `python3 scripts/check_app_store_release_pack.py`
  - App Store release pack check passed。
- PASS: `cd mobile && ./node_modules/.bin/tsc --noEmit`
- PASS: `python3 -m py_compile scripts/check_ios_app_store_submission.py scripts/check_app_store_release_pack.py`
- PASS: `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
  - 16 份 dossier 全自洽。
- PASS: `backend/venv/bin/python scripts/check_doc_drift.py`

## G4 · 安全闸

- 触发?:未改用药/基因/化验/消息/safety/认证/写路径;只改发布配置和文案检查。
- 裁决:GO。

## S6 · 部署

- 路由:本批不部署;后续 mobile 仍默认二维码发版,App Store 提交需用户明确/凭证齐备。
- 提交前新增硬闸:若 Expo `name`、`CFBundleDisplayName` 或 submission pack App name 不等于 `阿衡`,release pack 和 iOS submission preflight 均失败。

## G5 · 部署健康闸

- 本地发布闸 PASS;无线上部署。

## S7 · 上线验证

- 本地验证:发布配置和检查脚本均以 `阿衡` 为用户可见主名;仍保留 `HealthPilot` 作为 Xcode target / bundle 历史技术名。

## G6 · 验证闸(人在环)

- App Store 上线仍需用户提供 demo account、截图人审和 ASC credentials。本批只关闭品牌一致性本地闸。

## S8 · 沉淀

- 文档同步:新增本周执行计划,并在 App Store MVP release dossier 记录 Batch 8。
- 状态 -> **shipped-local-gate**。
