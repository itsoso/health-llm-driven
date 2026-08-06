# Dossier: iOS 1.3.3 App Store 正式发布

| 字段 | 值 |
|---|---|
| slug | `ios-1-3-3-app-store-release` |
| 创建日期 | 2026-08-05 |
| 当前阶段 | S5 · T0–T3.5/T5/T6 complete；T4 BLOCK |
| 状态 | implementing |
| 负责 | product / mobile release / Codex |
| 反馈环 | EAS Store Build → TestFlight → App Store manual release |

## Correct Course

- [x] Correction Block（2026-08-05）：最新 `main` CI 在依赖审计处失败；在 T4 前插入 T3.5 修复 Python 锁文件漏洞并重验 Mobile advisory，禁止带红进入原生构建。

## S0 · 用户需求（逐字）

> 回到原始目标，本周要发布一个正式版本，review代码，思考还有哪些需要改进，以及如何通过appstore的审核，形成规划

- 谁用 / 解决什么 / 现在怎么绕过：小巴 iPhone 用户需要一个可公开下载、可稳定登录、能记录和解释健康数据且不越过医疗边界的正式版本；当前依赖内部 Build/OTA，送审材料和精确包证据未闭环。
- 用户选择：2026-08-05 确认 1.3.3 + 新 Build 241+；选择“审核优先、功能冻结”；依次确认三部分设计。
- 锚点用户相关性：连接 HealthKit/Garmin 的健康管理用户；不要求审核员持有穿戴设备。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `mobile/app.json`：iPhone-only、HealthKit、隐私清单、按用途权限文案。
  - `mobile/app.config.ts` / `mobile/config/releaseCapabilities.ts`：production 实验能力关闭。
  - `mobile/app/settings.tsx`：隐私政策、账号删除及状态入口。
  - `scripts/check_app_store_release_pack.py` / `scripts/check_ios_app_store_submission.py`：基础与最终送审闸门。
  - `docs/release/app-store/*`：提交包、审核说明、隐私标签、截图和真机验收模板。
- 代码风险：`mobile/components/dashboard/RhinitisCard.tsx` 对所有用户展示两种处方药和固定剂量，缺失时自动创建，写失败被静默吞掉。
- 材料缺口：提交包和审核说明仍指向 1.3.2 Build 237 且为 Draft；缺审核账号/电话、当前截图、真机证据、已发布隐私标签、年龄分级确认和 ASC 凭据。
- 构建事实：最新 Store Build 240（EAS `a62a4dc5-f542-4cfe-bc87-8eb0d84a7ff4`）完成于 2026-07-29；IPA 为 Xcode 26.2 / iOS 26.2 SDK，但不嵌入当前主干代码。
- 基线验证：Mobile 292 suites / 2,399 tests PASS；TypeScript PASS；lint 0 errors / 92 warnings；依赖无 high/critical；基础 App Store 闸门 PASS；严格 final-submit 按预期 FAIL 于外部材料。
- 生产可用性：隐私政策 HTTP 200；健康检查报告 API、PostgreSQL、Redis、Celery healthy。
- 平台/安全硬约束：2026-04-28 起上传须使用 Xcode 26 / iOS 26 SDK；健康数据、账号删除、完整演示账号、发布后的 App Privacy 和医疗器械声明必须准确；审核期间不得用 OTA 改变精确包行为。

## G1 · 准入裁决（governance §8 RequirementAdmission）

- first_class_objects: `WriteIntent`, `ExecutionEvent`, `SafetyGuardian`, `HealthTwin`
- core_loop_step: Data In → Health Twin → Daily Plan → Execution → Review/Learn
- target_surface / safety_level / autonomy_tier: Mobile + App Store + Backend / medical_boundary + privacy_sensitive / manual_confirm
- source_of_truth: Backend for health/account facts; App Store Connect for submission metadata; EAS/IPA for binary evidence
- spec_required (§8.1): yes（改变用药记录安全行为并涉及正式跨系统发布）
- smallest_end_to_end_slice: 移除产品自带处方 → 精确 Build 验收 → 材料闭环 → 提交 → 手动发布验证
- stale_surface_to_remove: 鼻炎卡硬编码药物/剂量、Build 237/1.3.2 送审文案
- **裁决**: PASS —— 恢复/加固既有健康记录与执行闭环，不增加诊断、治疗或新自治写路径。
- 用户确认: ☑ 2026-08-05

## S2 · PRD / Feature Spec

- PRD: `docs/prd/2026-08-05-ios-1-3-3-app-store-release.md`
- Feature Spec: `docs/specs/active/2026-08-05-ios-1-3-3-app-store-release.md`
- 引用的权威边界：R4 身体状态/安全边界、R15 失败透明、HealthKit/隐私/写入承重墙。
- 边界：不新增功能；不诊断、开药、调整剂量；不以 OTA 代替 Store Build；不保证 Apple 审核完成时间。
- 验收 Gate：G3 全绿、G4 GO、G5 精确包/TestFlight/服务健康、G6 公开版本真机确认。
- 未决问题：无阻塞性未决问题。

## S3 · 规划

- Design: `docs/plans/2026-08-05-ios-1-3-3-app-store-release-design.md`
- Implementation: `docs/plans/2026-08-05-ios-1-3-3-app-store-release.md`
- 分阶段：功能冻结 → 医疗风险修复 → 发布闸补强 → 材料 → G3/G4 → EAS Build → 精确包真机 → 提交 → 手动发布/G6。
- 反馈环路由：本地/Jest → EAS Store Build（原生版本变更）→ TestFlight → App Store；审核期间 production OTA 冻结。
- 长杆：Apple 审核时长、TestFlight 处理、审核账号稳定、截图/隐私/年龄分级人工确认。

## G2 · 可行性 + 安全压测

- 评审方式: Codex code/config challenge + Apple primary-source review + 用户逐节确认
- 硬阻断（已焊进规划）：
  - 不提交 Build 240；新包必须嵌入当前审定代码。
  - 移除硬编码处方/剂量和静默失败。
  - 年龄分级、App Privacy、医疗器械 `No`、审核联系人和账号必须完成。
  - 同一 Build 完成真机/截图/工具链证据。
  - 审核期间冻结 production OTA。
- 待拍板分叉：无；用户已选择审核优先方案。
- **裁决**: PASS —— 用户确认 2026-08-05。

## S4 · 研发任务分解

- 跨端 API 契约：无 schema/API 变更；用药写入继续使用现有用户确认路径。
- 任务表：
  - [x] T0 干净 origin/main 基线、并发检查、冻结声明
  - [x] T1 鼻炎卡医疗安全 TDD 修复
  - [x] T2 版本 1.3.3 与配置测试
  - [x] T3 年龄分级/OTA 冻结/IPA 工具链最终闸
  - [x] T3.5 主干依赖审计修复与 CI 复绿
  - [ ] T4 审核账号与虚构数据验收
  - [x] T5 提交材料与 App Store Connect 字段
  - [x] T6 G3 全量 + 独立 G4
  - [ ] T7 EAS Store Build / IPA / TestFlight
  - [ ] T8 精确 Build 真机与截图
  - [ ] T9 final-submit / App Review
  - [ ] T10 手动发布 / production G6
- 并发检查：2026-08-05 已检查开放 PR 与 `origin/main` 最近提交；未发现其他变更占用鼻炎用药 surface 或 1.3.3 发布配置。1.3.3 仅接收审核阻断修复，其他请求进入 1.3.4。

## S5 · 实现

- 执行方式：用户选择全局隔离 worktree；未使用含用户未提交文件的主工作区构建、测试或暂存。
- Worktree：`/Users/liqiuhua/.config/superpowers/worktrees/health-llm-driven/ios-1-3-3-app-store-release`
- 分支 / base：`codex/ios-1-3-3-app-store-release` / `dddff6ee1f3e6487fc22b8742aba030f2e587b5b`（当时最新 `origin/main`）。
- 已完成：
  - `4d6ba5b25`：移除鼻炎卡内置处方药、固定剂量、自动建药/记录及静默失败；保留洗鼻/喷嚏观察和通用用药管理入口。
  - `7ffd2e048`：production 版本升为 1.3.3，保持 `appVersion` runtime 和窄能力面。
  - `43c73a621`：final-submit 新增年龄分级、production OTA 冻结、精确 app/build、`DTXcode` / `DTPlatformVersion` 证据闸。
  - `588110a22`：新增鼻炎安全测试保持 lint-neutral。
  - `a8bf8f0b6`：升级 `aiohttp 3.14.3`、`cryptography 50.0.0`、`postcss 8.5.23` 和分 major 的 `brace-expansion` 安全版本，重生成 Linux x86_64 Python exact lock 与 Mobile lock，清空 npm audit 例外。
  - `e0c2a1e08`：同步 Python 与 Mobile 依赖安全契约测试，并显式锁定 `aiohttp 3.14.3` 契约。
  - `23e095ff1`：关闭依赖审计子闸并记录独立兼容性/安全评审证据。
  - `55f2ca457`：把 ASC 草稿升级为 1.3.3 后，同步审核材料、T4/T5 部分验收和人工阻塞项。
  - `ac1695445`：补齐云端语音转写和 linked Product Interaction 隐私披露，更新 Web/Mobile 政策并加固 release-pack 漂移闸。
- 当前断点：T0–T3.5/T5/T6 完成；T4 因演示会话确定性验收失败而 BLOCK。EAS Store Build 不得开始。
- T4 物理 iPhone（历史 1.3.2 Build 240，仅作预验）执行 7 项自动子集：5 passed / 2 failed。双冷启动首次失败于第二次恢复登录超过 30 秒，隔离重跑 1/1 PASS，判定为一次性恢复超时；会话用例稳定失败，因为设备保留旧 conversation 且生产 19 个会话里不存在最新固定演示会话。服务端 live gate 先前只验证今日计划/每日工件非空，错误放过了这个缺口。语音、相机、分享、写入/纠正/删除仍须在 T8 对同一 1.3.3 候选人工验收。
- T5 ASC 已保存年龄分级问卷（结果 16+，无分级覆盖）、`Regulated Medical Devices: No` 和审核通过后手动发布。App Privacy 已按 checked-in JSON 发布 12 个数据类型，产品页预览可见；公开隐私政策已部署并验证 2026-08-05、云端语音音频和 linked 客户端事件文案。未添加构建、未提交审核。
- T5 App Privacy 复核发现旧的“未收集数据”与生产事实不符，立即停止发布。根因是隐私 taxonomy 漂移闸只覆盖饮食照片，未绑定 `/chat/transcribe` 的云端音频出口和持久化的认证客户端事件。已按 TDD 增加跨代码/声明/政策防漂移闸并发布更正答案。
- 2026-08-05 T4/T5 进行中证据（`2026-08-05T11:25:22Z`）：
  - 审核账号凭证仅存在受控发布环境，未复制进 worktree 或 Git；production live gate 验证账号密码登录、`/auth/me` 身份、今日计划和每日工件均 PASS。
  - 虚构数据 seeder 契约 4/4 PASS；生产 seeder 与评审版本 SHA-256 一致，但真机证据证明“无需重置正式审核账号”的旧判断错误：固定演示会话未进入 production 最新列表，必须重跑 seeder 并把这项事实焊进 live gate；无需轮换密码。
  - 单独创建随机合成 QA 账号并发起删除申请；创建、查询、7 天处理窗口、重复提交幂等、pending 状态继续登录及正式审核账号隔离均 PASS。账号/密码、用户 ID、删除请求 ID 未输出或提交，删除申请留给既有受控运维清单处理。
  - 物理 iPhone 后续恢复 available 并完成上述 7 项自动子集；不得用 API 或历史 Build 替代 T8 精确候选验收。
  - App Store Connect 1.3.3 状态仍为 `PREPARE_FOR_SUBMISSION`；en-US 元数据、审核联系人/账号/备注和手动发布设置已复核保存，未绑定 Build、未创建 review submission。
  - 1.3.3 是首个 Store 版本，Apple 在当前状态拒绝 `whatsNew`，故首次提交保持该字段为空；年龄分级、App Privacy 和医疗器械人工项已完成并写入发布机开关。

## G3 · 测试闸

- 预实现基线：Mobile 292/292 suites、2,399/2,399 tests PASS；TypeScript PASS；lint 0 errors / 92 warnings；Mobile 依赖 high/critical=0。
- 2026-08-05 首批集成：
  - Mobile 293/293 suites、2,403 passed / 1 skipped（2,404 total）；TypeScript PASS。
  - Mobile lint 0 errors / 92 warnings，与基线一致；changed files 未新增 warning。
  - Mobile production audit PASS，无 high/critical advisory。
  - `backend/tests/test_app_store_release_pack.py`：36/36 PASS。
  - App Store release pack、iOS submission preflight、doc drift 均 PASS。
- 主干 CI 失败证据：run `30984698027`（base `dddff6ee1`）及修复前最新 run `30993466431`（commit `926f40639`）均 FAIL；后者其余测试/构建 jobs 通过，失败集中在审计：
  - Python：`aiohttp 3.14.2` / `PYSEC-2026-3545`（修复 3.14.3），`cryptography 49.0.0` / `PYSEC-2026-3552`（修复 50.0.0）。
  - Mobile 当次远端审计报告 `brace-expansion` / `minimatch` 的 `GHSA-rgw5-rvv9-x895`；当前本地同一 Gate 已 PASS，仍须以新远端 CI 复验，不能仅凭本地推断 advisory 已撤回或解析变化。
- 2026-08-05 T3.5 复验：
  - 官方 npm registry 完整与 production-only audit 均为 0 vulnerabilities；audit policy gate PASS，exceptions 为空。
  - Python 3.12 exact hashed lock 安装与 `pip-audit --require-hashes` PASS；Garmin / Fernet / HKDF / 加密确认相关回归 75 passed / 2 skipped。
  - 依赖契约测试 21/21 PASS；Mobile 293/293 suites、2,403 passed / 1 skipped；App Store release pack 36/36 PASS，checker 与 iOS submission preflight PASS。
  - 独立代码评审 `Ready to merge: Yes`，无 Critical / Important / Minor；独立依赖安全评审 `GO`，旧 Fernet 密文解密、HKDF 字节一致性和篡改 `InvalidToken` fail-closed 均 PASS。
  - 主干 CI run `30998114422`（commit `e0c2a1e084829abc0340b329b1a81e82e9812eaa`）`completed/success`，44/44 jobs 成功。
- 2026-08-05 T6 全量闸（`2026-08-05T11:50:54Z`）：
  - Mobile Jest 293/293 suites、2,403 passed / 1 skipped（2,404 total）；TypeScript PASS；lint 0 errors / 92 baseline warnings；npm full / production audit 与 policy gate 均 PASS、0 vulnerabilities。
  - App Store release-pack 测试 41/41 PASS；基础 checker、iOS submission preflight、doc drift 和 `git diff --check` PASS。
  - 主干 CI run `31003555856`（commit `642740f3729bd81ba599d94eefced38d2a1241be`）`completed/success`，44/44 jobs 成功，0 failed；包含 G4 隐私/精确构建整改及 41 项 release-pack 测试。
- 2026-08-05 T5 隐私漂移整改：先新增云端语音和客户端事件漏报回归测试并确认红灯，再更新声明、Web/Mobile 隐私政策和机器闸；针对性 4/4、release-pack 43/43、基础 checker 与 `git diff --check` PASS。主干 CI run `31067249388`（commit `ac1695445666658863d8ef5935820b0a2329cf18`）`completed/success`，44/44 jobs 成功，0 failed。
- **裁决**：完整 G3 PASS；T6 complete。仍须等 T4/T5 通过后才能进入 EAS Store Build。

## G4 · 安全闸

- 触发：用药、健康写入、隐私、认证审核路径。
- T3.5 依赖安全评审：`GO`，无阻断项；未修改用户数据、认证逻辑、医疗建议边界或 App Store 产品行为。
- 2026-08-05 完整 release diff 独立评审首轮：`NO-GO`，无 Critical，2 个 Important BLOCK：
  1. App Privacy 草稿错误声明未发布的 `strict_local` / `local_first` 与端上餐食推理，而 production 会把用户选择的图片上传到认证服务。
  2. final-submit 仅校验 EAS build ID / source SHA 格式，未把真机证据绑定到候选 EAS metadata。
- S5 整改：删除错误的 device-only 声明；把 `User Content -> Photos or Videos`、图片上传/草稿/记录用途写入隐私草案，并增加跨 release notes、Mobile `/diet/recognize` 数据流的防漂移测试。final-submit 新增 `APP_STORE_EAS_BUILD_ID` / `APP_STORE_GIT_COMMIT_HASH`（或等价 CLI 参数），要求与真机证据精确匹配，源码 SHA 必须为完整 40 位。
- G4 第一次复评仍 `NO-GO`：发现旧 device-only 声明的拒绝依赖 Review Notes 英文原句，改写文案可绕过。第二轮整改将旧 `strict_local` / `local_first` / 餐食照片 / 端上推理 markers 直接绑定 production `/diet/recognize` 上传事实；Review Notes 缺无本地模型边界或代码无法识别图片上传流时均 fail-closed。7 个针对性测试及 release-pack 41/41 PASS。
- 首轮其余评审项均 GO：鼻炎卡无内置处方/剂量/自动写入，production 无 Watch/Rokid/Siri/background，secret pattern scan 无命中，npm/pip audit 为 0，人工项保持 fail-closed pending。
- G4 第三轮独立复评：`GO`，Critical / Important / Minor 均无；实际重放 Review Notes 文案漂移与无法识别图片上传流两种绕过，均 fail-closed。release-pack 41/41、基础 checker、iOS preflight、Ruff、`git diff --check` PASS；错误 EAS UUID / 完整 source SHA 均被拒绝。
- T5 ASC 人工复核补充发现两条未声明的数据出口：录音经认证 API 发送到云端 ASR，客户端交互事件按 `user_id` 持久化。整改后声明新增 `Audio Data`（linked / App Functionality）和 `Product Interaction`（linked / App Functionality + Analytics），诊断数据仅保留 unlinked Crash/Performance；全部类型均为 not tracking。对应防漂移测试直接绑定 production 代码路径，避免再次回退为“未收集数据”。
- **裁决**：完整 G4 PASS；仍须等待整改提交的新主干 CI 复绿，并完成 T4/T5，方可构建。

## S6 · 部署

- 路由：EAS production Store Build → TestFlight → App Store manual release。
- production OTA：审核开始前冻结，G6 后解除。
- T5 法务材料部署：commit `ac1695445` 通过根 `deploy.sh --all` 发布；数据库备份、恢复演练、站外加密归档、schema probe、runtime-only KB、skills manifest、精确 revision 均通过，连续后端健康分 60/60；前端 Next.js production build/TypeScript/73 个静态页面生成 PASS。线上 `/privacy` 和 `/api/v1/health` 已独立验证。
- EAS Build ID / commit / App Store submission ID / 回滚点：待记录。

## G5 · 部署健康闸

- IPA toolchain/version/build/commit：待精确候选。
- TestFlight processing + physical iPhone + backend health：待执行。
- **裁决**：pending。

## S7 · 上线验证

- App Store 公开安装、版本核对、登录/文字 Agent、隐私/删除、鼻炎卡、服务健康：待执行。

## G6 · 验证闸（人在环）

- 真机/发布用户确认：待 Apple 批准和手动发布后请求。
- **裁决**：pending。

## S8 · 沉淀

- 新坑：年龄分级和审核期间 OTA 冻结已进入 final-submit 机器闸；精确 IPA 工具链和 app/build 对齐也已 fail-closed。
- 新坑：发布规划文档提交也会触发实时依赖 advisory；必须把最新主干 CI 颜色作为预构建 Gate，锁文件安全修复不得延后到构建后。
- 文档同步：若架构计数未变化，无 system-map 生成物变更；最终以 doc-drift 为准。
- 状态：待 shipped。
