# Dossier: iOS 1.3.3 App Store 正式发布

| 字段 | 值 |
|---|---|
| slug | `ios-1-3-3-app-store-release` |
| 创建日期 | 2026-08-05 |
| 当前阶段 | G2 PASS · definition complete |
| 状态 | defining |
| 负责 | product / mobile release / Codex |
| 反馈环 | EAS Store Build → TestFlight → App Store manual release |

## Correct Course

- [ ] Correction Block（当前无）

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
  - [ ] T0 干净 origin/main 基线、并发检查、冻结声明
  - [ ] T1 鼻炎卡医疗安全 TDD 修复
  - [ ] T2 版本 1.3.3 与配置测试
  - [ ] T3 年龄分级/OTA 冻结/IPA 工具链最终闸
  - [ ] T4 审核账号与虚构数据验收
  - [ ] T5 提交材料与 App Store Connect 字段
  - [ ] T6 G3 全量 + 独立 G4
  - [ ] T7 EAS Store Build / IPA / TestFlight
  - [ ] T8 精确 Build 真机与截图
  - [ ] T9 final-submit / App Review
  - [ ] T10 手动发布 / production G6
- 并发检查：待 S4 开工时在最新 `origin/main` 干净 worktree 执行。

## S5 · 实现

- 委托：待开始。
- 分支 / commit：待记录。当前共享 workspace 落后 `origin/main` 且含用户未提交文件，不得用于构建或部署。

## G3 · 测试闸

- 预实现基线：Mobile 292/292 suites、2,399/2,399 tests PASS；TypeScript PASS；lint 0 errors；依赖 high/critical=0。
- 最终集成闸、main CI、改动后全量：待执行。
- **裁决**：pending；基线通过不等于发布 Gate 通过。

## G4 · 安全闸

- 触发：用药、健康写入、隐私、认证审核路径。
- 评审：待独立 safety/privacy review。
- **裁决**：pending；BLOCK 必须回 S5。

## S6 · 部署

- 路由：EAS production Store Build → TestFlight → App Store manual release。
- production OTA：审核开始前冻结，G6 后解除。
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

- 新坑：年龄分级和审核期间 OTA 冻结应成为 final-submit 机器闸；待实现验证后回流。
- 文档同步：若架构计数未变化，无 system-map 生成物变更；最终以 doc-drift 为准。
- 状态：待 shipped。
