# Dossier: iOS 1.3.3 App Store 正式发布

| 字段 | 值 |
|---|---|
| slug | `ios-1-3-3-app-store-release` |
| 创建日期 | 2026-08-05 |
| 当前阶段 | S5 · 聊天层级优化与 CI 整改已推主干，最新完整 CI 44/44 通过；G3 PASS，待 EAS Store Build/精确包真机/G5 |
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
- 发布前聊天视觉层级 Design: `docs/plans/2026-08-06-mobile-chat-visual-hierarchy-design.md`
- 发布前聊天视觉层级 Implementation: `docs/plans/2026-08-06-mobile-chat-visual-hierarchy.md`
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
  - [x] T4 审核账号与虚构数据验收
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
  - `4af790ecc` / `2a7577c3a`：冻结发布前聊天视觉层级设计与实施计划，范围仅限标题、第一排焦点条、助手身份和输入栏的层级/间距。
  - `38186b9fe` / `c8736d717` / `7af1d1b3f` / `0182e9c2f`：按“舒展易读”方案完成聊天界面视觉优化；保持正文 15/23、44pt 触控目标、业务行为、API、健康数据与写入流程不变。
  - `9d8416b11`：清理新增测试的 lint warning，保持 Mobile 既有 92 warnings 基线不增长。
- 当前断点：T0–T6 完成；审核账号固定简报 live gate、生产早餐图片领域路由和 AIGC 外发确认链整改均已完成，最终 G4 GO。发布前聊天视觉层级优化、当日新增依赖 advisory 与两条后端安全边界回归均已整改；真实 LLM 评测通过，最新完整主干 CI 44/44 通过，G3 PASS。登录态聊天页的物理 iPhone 视觉烟测、EAS Store Build 与同一精确候选 T8 仍为阻断项。
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
  - 2026-08-06 T4 收口：release checker 现在从受控 fixture 读取固定简报标题和精确消息对，登录后按当前用户查询会话并 fail closed；聚焦测试 45/45、线上只读 live gate 和基础 release-pack checker 均 PASS，未输出账号或密码。

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
- 2026-08-06 发布阻断热修复本地证据：媒体授权对抗聚焦集 280 passed；餐食图片领域/工具裁剪/Agent food vision 路由广集 1057 passed；用药与 release gate 聚焦集 126 passed；基础 release-pack checker 及审核账号 live gate PASS。新提交的主干 CI 真实色仍待取得。
- 2026-08-06 AIGC 外发确认整改最终证据：后端确认/令牌/API/网关/能力/force 聚焦集 660 passed，分类器广集 579 passed；Mobile 卡片与通用 action 115 passed，Web 卡片 40 passed 且无 jsdom 网络噪声；release-pack 48 passed。Backend Ruff、Mobile/Web TypeScript、两端 lint（0 errors）、基础 App Store checker/preflight 和 `git diff --check` 均 PASS。generated OpenAPI types 已同步到 Mobile/Web 并由 worktree venv 临时全量重生成逐字节复核；主干 CI 真实色仍待取得。
- 2026-08-07 聊天视觉层级优化证据：相关 Mobile Jest 197/197 PASS；完整 `scripts/mobile-fast-test.sh --all` PASS，TypeScript PASS，lint 0 errors / 92 baseline warnings，设计漂移检查 PASS。iPhone 17 Pro Max / iOS 26.5 模拟器 Release 构建成功并完成安装、冷启动到登录页，无启动崩溃；本地 QA 仅通过 `SENTRY_DISABLE_AUTO_UPLOAD=true` 关闭无发布凭据的符号上传，未修改或弱化正式归档配置。模拟器无审核账号登录态，且物理 iPhone 当前不可用，因此登录态聊天页视觉烟测与同一精确 Store 候选验收仍保持 pending。
- 2026-08-07 主干 CI run `31169318136`（commit `1767cfd7b52678fcca8a8290da14a91e1cbce797`）`completed/failure`：44 jobs 中 39 success、5 failure；实质红灯为 `backend-quality` 的 `h2 4.3.0 / CVE-2026-71554`、`mobile-typecheck` 的 `js-yaml / GHSA-5p4m-2wfm-xmqj`，以及两个 agent-executor 分片各 1 条回归，汇总 job 随之失败。G3 据此保持 pending，未启动 EAS。
- 2026-08-07 CI 整改本地证据：`h2` 精确锁定 4.4.1，`js-yaml` 两条兼容 major 分别锁定 3.15.1 / 4.3.1；Python hashed lock audit、Mobile full/production audit 与空例外策略闸均为 0 known vulnerabilities。复杂来源图片创作仍保持 G4 审定的通用工具集且不强制外发，但媒体生成意图在更早阶段明确跳过餐食识别；两个原失败 CI 分片 340/340、329/329 PASS，G4 分类/能力矩阵 1184/1184 PASS，依赖契约 21/21、完整 Mobile gate PASS。新修复提交的主干 CI 真实色仍待取得。
- 2026-08-07 修复提交 CI run `31175721526`（commit `0116165bdd809c8e1262b3882f480c6fb1f32164`）44 jobs 中 42 success、2 failure：原有依赖与两个 agent-executor 红灯均已转绿；唯一实质失败为 `backend-quality` 按设计阻断 `agent_executor.py` 运行时改动缺少一次性 live-eval 确认，`backend-tests` 仅为汇总失败。未绕过该闸，未启动 EAS。
- 2026-08-07 真实 LLM 评测证据：`APP_ENV=test DATABASE_URL=sqlite:///:memory: backend/venv/bin/python scripts/harness_llm_regression_gate.py --include-live-llm --json` exit 0；`invariants` 12/12、`health_agent_core` 50/50、真实 `orchestrator` 5/5，平均分 0.94，相对 `main` 无 regression；轨迹契约 12/12、金标 9/9。实际模型为 `MiniMax-M2.5`；临时 SQLite 未建 usage telemetry 表产生非生产旁路告警，但真实模型生成、LLM judge 与 Gate 结果均成功。一次性 `HARNESS_LIVE_LLM_EVAL_CONFIRMED=1` 只允许用于承载本证据的下一轮 CI，终态后必须删除并复证不存在。
- 2026-08-07 证据提交 CI run `31179125236`（commit `561b01c2750580b3e4a57943a85211c376915cde`）`completed/success`：44/44 jobs success、0 failure。一次性 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 已在终态后删除，仓库变量按名称复证为 0 条；后续 LLM 高风险改动重新默认阻断。
- **裁决**：当前发布候选 G3 PASS，可进入 EAS Store Build；同一精确候选的物理 iPhone T8 与 G5 仍须完成，不能据此提交 App Review。

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
- 2026-08-06 热修复首次独立复评:`G4: NO-GO`，无 Critical，4 个 Important：普通/既成图片记录与否定生成仍可误授权 AIGC 草稿；审核 API 基址可使用 HTTP，默认重定向可跨 origin 转发 Bearer。整改后只有未否定的显式生成 reason 可进入 AIGC 工具集；live gate 在基础 URL 与每次请求双层强制 HTTPS、拒绝 URL 凭证/片段并禁止全部重定向。对抗测试与完整聚焦集已绿，等待同一 reviewer 复审。
- 同一 reviewer 二次复评仍 `G4: NO-GO`，无 Critical：常见口语否定和动作后置否定仍可绕过，且邻近子串会误伤“分别/别的”、跨分句新命令与取消旧任务后的重新授权。现已改为显式否定短语、分句边界和局部重新授权关联，并追加“取消重新生成”和后句无关否定边界；53 个对抗用例、830 项路由广集及 126 项用药/发布闸均 PASS，等待第三次独立复评。
- 第三次独立复评继续 `G4: NO-GO`，无 Critical：`不希望/没打算/不再/不应/不该/避免` 及 provider 确认表达仍可强制 AIGC 工具；“分别生成早餐图和午餐图”被误归饮食域。整改已把完整评审矩阵加入测试，收紧后置否定对象并补充受控图片简称；64 个聚焦用例、841 项路由广集及 126 项用药/发布闸均 PASS，等待同一 reviewer 对最终 diff 继续复核。
- 同一轮扩展对抗先以 2 Important `G4: NO-GO` 推动 command-frame 架构重构；新一轮独立复评仍 `G4: NO-GO`（4 Important、无 Critical/Minor）：冒号引用归属、provider 撤销/veto、AI/模型内容约束和 prompt 内容/跨问句最后意图仍有漏洞。现已保留冒号归属，独立追踪 provider veto，补齐口语撤销，禁止把 AI/provider/model 当安全内容约束，只检查最终输出目标后的命令尾部并隔离 prompt 内嵌动作；144 个聚焦对抗、921 项路由广集及 126 项用药/发布闸均 PASS，等待独立复评。
- 最新独立复评仍 `G4: NO-GO`（4 Important、2 类 Minor，无 Critical）：跨标点通用转述、sticky provider veto、确认后的事实限定及动作名词/事实谓词仍有同构绕过。现已逐条落入 24 个安全反例与 11 个正向反例，并用跨分句状态机收紧：转述上下文需明确当前用户转折重领；provider 确认被任何非明确新媒体命令后继失效；上传/分享/外部服务 veto 仅由后续明确 provider 确认解除；prompt 内容与控制动作隔离。220 个聚焦对抗、997 项路由广集、126 项用药/发布闸及静态/结构闸均 PASS，等待同一 reviewer 再复评。
- 后续复评仍 `G4: NO-GO`（4 Important、3 类 Minor，无 Critical）：reporting/出站/动作名词同义词仍可绕过，中文引号内的转折被错当当前用户 reclaim，确认后的元描述因 attribution 早退而未失效。现已改成引号 payload 屏蔽、未知前导默认 attribution、严格裸命令对象语法、create-to-final-output payload span 以及先失效后归因的 provider 状态机；27 个新安全反例、25 个新正向反例及 8 个开放词汇变体均落测。最新 280 focused、1057 route-wide、126 medication/release 与静态闸全部 PASS，等待再次独立复评。
- 最新安全评审给出 `CONDITIONAL GO`：阻断条件是 provider 确认必须使用闭合语法且取消词在任意位置优先；owner GET 必须返回与实际外发逐字节一致的解密 prompt、短时 owner/confirmation/provider/model/prompt-version 绑定 token 并设置 no-store；POST 无 token/篡改/跨确认/过期/版本变化均须在 provider 前 fail closed；Mobile/Web 初始禁用并显示完整纯文本 prompt；通用 Mobile action 不得绕过；复杂源图片指令保持 general toolset，但 provider veto 必须由 gateway 阻断。上述条件现已全部落入代码、生成契约和回归，等待同一 reviewer 最终裁决。
- 其后最终复评返回 `G4: NO-GO`（Critical 0 / Important 2 / Minor 2）：闭合语法删除换行导致分行确认仍被 force；gateway 漏掉“必须断网/只在手机上/不得交由服务商/禁止传到云上”；token 在过期整秒仍可用；生成类型需证明无非预期漂移。现已先补红灯复现，再拒绝闭合语法中的任意空白、扩展 local-only 出站词法、把 token 边界改为严格 `exp > now`，并用临时 OpenAPI 全量重生成与两端 tracked types 逐字节比较。聚焦 9/9、完整相关集 616/616、分类器 576/576、Ruff 与 diff-check PASS，等待下一轮 G4。
- 最终复评确认 provider 授权语法闭合且与 force 共用；空白注入 fail closed；复杂来源图片合法正例保留；capability 最终闸拒绝本地/离线、设备驻留、禁止外发/上云及固定中英混输隐私表达。review token 绑定与整秒过期边界、客户端先审阅后确认链、通用 action 防绕过和 OpenAPI 类型均通过独立重放；Critical / Important / Minor 均为 0。
- **裁决**：`G4: GO`；允许提交、推送并进入下一部署 Gate，但新提交主干 CI、T4/T5、G5/G6 仍是独立阻断条件。

## S6 · 部署

- 路由：EAS production Store Build → TestFlight → App Store manual release。
- production OTA：审核开始前冻结，G6 后解除。
- T5 法务材料部署：commit `ac1695445` 通过根 `deploy.sh --all` 发布；数据库备份、恢复演练、站外加密归档、schema probe、runtime-only KB、skills manifest、精确 revision 均通过，连续后端健康分 60/60；前端 Next.js production build/TypeScript/73 个静态页面生成 PASS。线上 `/privacy` 和 `/api/v1/health` 已独立验证。
- EAS Build ID / commit / App Store submission ID / 回滚点：待记录。

## G5 · 部署健康闸

- IPA toolchain/version/build/commit：待精确候选。
- TestFlight processing + physical iPhone + backend health：待执行。
- 本地原生预验：iOS 26.5 Release 模拟器构建、安装和启动 PASS；该产物为 development 变体且禁用本地 Sentry 符号上传，只证明当前原生工程可编译/启动，不替代 production Store Build、TestFlight、精确 commit/Build 绑定或 T8 物理真机证据。
- **裁决**：pending。

## S7 · 上线验证

- App Store 公开安装、版本核对、登录/文字 Agent、隐私/删除、鼻炎卡、服务健康：待执行。

## G6 · 验证闸（人在环）

- 真机/发布用户确认：待 Apple 批准和手动发布后请求。
- **裁决**：pending。

## S8 · 沉淀

- 新坑：年龄分级和审核期间 OTA 冻结已进入 final-submit 机器闸；精确 IPA 工具链和 app/build 对齐也已 fail-closed。
- 本地 iOS 构建若只配置 macOS 系统代理，CocoaPods/Expo 子进程仍可能因 shell 无代理变量而误报依赖不可解析；先验证代理出口并显式传递 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`。无 Sentry 发布凭据的本地模拟器 QA 可用 `SENTRY_DISABLE_AUTO_UPLOAD=true`，但正式 Store 归档不得沿用该临时设置。
- 新坑：发布规划文档提交也会触发实时依赖 advisory；必须把最新主干 CI 颜色作为预构建 Gate，锁文件安全修复不得延后到构建后。
- 文档同步：若架构计数未变化，无 system-map 生成物变更；最终以 doc-drift 为准。
- 状态：待 shipped。
