# Dossier: App Store MVP Release

| 字段 | 值 |
|---|---|
| slug | `app-store-mvp-release` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S6 部署准备 |
| 状态 | app-store-batch2-web-deployed-app-store-external-pending |
| 负责 | Codex |
| 分支 | `main` |
| 工作区 | `/Users/liqiuhua/work/personal/health-llm-driven` |

## S0 · 用户需求

> 可以 按照你规划执行

上下文: 用户认可“下周发布一个可用版本:统一 UI、支持核心用户动线、能上架到 App Store”的规划,要求直接执行。

目标用户: 35-55 岁高强度工作者, 已有 Apple Watch / HealthKit / 体检报告 / 日常记录需求。

## S1 · Discovery

- 现有系统定位: Reva 是 Personal Health OS, 不做医疗诊断/处方/治疗承诺。
- Mobile 当前主导航已经是 `今日 / 私教 / 记录 / 我`, 但 `我` tab 仍像内部功能清单, App Store 版需要更清晰的“核心健康动线 + 数据与隐私”结构。
- HealthKit 已在 `mobile/app.json` 开启 entitlement 和 `NSHealthShareUsageDescription`;根布局已挂 `useHealthKitForegroundSync()`。
- App Store 硬风险:
  - 健康类表述必须保守,避免诊断、治疗、药物剂量调整和疗效保证。
  - 支持账号创建时,App 内必须能发起账号删除。
  - HealthKit 数据用途、隐私政策、权限文案、Review Notes 和截图要一致。
- 并发状态:
  - 根 worktree 曾有其他会话未提交改动;本 feature 在独立 worktree 从 `origin/main@e8289123` 开发,避免混入并发 WIP。

## G1 · 准入裁决

- first_class_objects: `HealthTwin`, `HealthAgendaItem`, `ExecutionEvent`, `InterventionCycle`, `WriteIntent`, `ConsentGrant`, `ProvenanceRecord`
- core_loop_step: data intake -> today action -> capture/chat execution -> review -> privacy control
- target_surface / safety_level / autonomy_tier: Mobile + Backend / privacy_sensitive + medical_boundary wording / manual_confirm
- spec_required: yes,涉及 App Store 上架、隐私入口、账号删除请求、Mobile 主入口收敛。
- smallest_end_to_end_slice: Mobile “我”页收敛为上架版信息架构,补账号删除请求入口和后端 audit,并用测试锁住。
- stale_surface_to_remove: 不删除历史路由;先从主入口隐藏/降噪 Rokid/admin/debug/实验能力。
- 裁决: PASS。

## S2 · PRD

本切片引用:

- `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
- `docs/prd/reva-personal-health-os-prd.md`

下周 App Store MVP 只承诺:

1. HealthKit / 体检导入 / 快速记录 / Chat 动态卡片 / Today top action / Review 复盘的核心闭环可用。
2. Mobile UI 主入口统一为 `今日 / 私教 / 记录 / 我`。
3. “我”页按 App Store 用户理解重组为: 数据连接、健康档案、复盘、通知与安全、账号与隐私。
4. App 内能发起账号删除与数据删除请求。

不做:

- 新医疗诊断。
- 药物剂量调整。
- 自动硬删除所有历史健康表。
- Rokid / IoT / 补剂供应链作为 App Store v1 主卖点。
- 新独立预测 dashboard。

## S3 · 规划

计划文档: `docs/plans/2026-06-28-app-store-mvp-release-plan.md`

P0:

- T1: Dossier + 发布计划。
- T2: Mobile `我` tab 信息架构收敛,主入口适配 App Store MVP。
- T3: Backend 增加登录用户账号删除请求 endpoint,写入 `AgentAuditLog`,失败不静默。
- T4: Mobile 增加账号删除请求服务和 UI 确认流。
- T5: 隐私政策摘要更新为 App Store 版,明确 HealthKit/AI/账号删除/医疗边界。
- T6: 验证、提交、推送。

## G2 · 可行性 + 安全压测

- 平台可行性: P0 改动是 JS/TS + 后端 endpoint + 文档,不需要 iOS native entitlement 变化。
- 安全边界:
  - 账号删除请求是 `manual_confirm`,必须二次确认。
  - 不执行自动硬删除,只发起可审计请求;完整删除执行器另开安全评审。
  - 隐私政策不承诺已完成自动删除,只说明请求已进入处理队列。
  - 医疗 wording 继续保持 advisory / non-diagnostic。
- 裁决: PASS。

## S4 · 研发任务

- [x] T1 Dossier + Plan
- [x] T2 Mobile Me 信息架构收敛
- [x] T3 Backend deletion request endpoint + tests
- [x] T4 Mobile deletion request service/UI + tests
- [x] T5 Privacy policy App Store wording
- [ ] T6 Verification + commit + push

## S5 · 实现

- Mobile `我` 页按 App Store MVP 用户动线重组为:
  - 数据连接: 位置、Garmin、Apple Health、数据授权、数据来源。
  - 健康档案: 化验、体检导入、用药、补剂、基因、目标。
  - 复盘与计划: 今日议程、时间轴、日历、周报、进度、代谢、抗衰、医生回路。
  - 通知与安全: 安全告警、推送、用眼、语音、Siri、Face ID。
  - 账号与隐私: 隐私政策、家庭健康、日记、硬性指令、数据自检、删除账号与数据。
  - 高级与实验: AI 模型/画像、处方扫描、运动、Rokid、诊断等保留但降级。
- Backend 新增 `POST /api/v1/auth/me/deletion-request`:
  - 只允许登录用户调用。
  - 写入 `AgentAuditLog(agent_type=account_privacy, action=account_deletion_requested)`。
  - audit 写入失败时 rollback 并返回 500,不静默成功。
- Mobile 新增 `requestAccountDeletion()` 服务和二次确认 UI。
- 隐私政策摘要补充 HealthKit 用途、AI 最小必要上下文、账号删除请求、非诊断医疗边界。

## G3 · 测试闸

- PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest backend/tests/test_account_deletion_request.py -q --no-cov`
  - 2 passed。
- PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath app/__tests__/settings.test.tsx --runInBand`
  - 8 passed。
- PASS: `cd mobile && ./node_modules/.bin/tsc --noEmit`
- PASS: `/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m compileall -q backend/app/api/auth.py`
- PASS: `/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
- PASS: `/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python scripts/check_doc_drift.py`
- PASS: `git diff --check`
- Batch 2 local gates:
  - PASS: `python3 scripts/check_app_store_release_pack.py`
  - PASS: `bash -n scripts/sim-build.sh && bash -n scripts/mobile-sim-screenshots.sh && python3 -m py_compile scripts/check_app_store_release_pack.py`
  - PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py -q --no-cov`
  - PASS: `cd frontend && npm run test -- --run 'src/app/shared/[shareToken]/sharePrivacy.test.ts'`
  - PASS: `cd frontend && npx tsc --noEmit --pretty false`
  - PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath __tests__/app-config.test.ts --runInBand`
  - PASS: `cd mobile && ./node_modules/.bin/tsc --noEmit`
  - PASS: `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
  - PASS: `backend/venv/bin/python scripts/check_doc_drift.py`

## G4 · 安全闸

- PASS。
- 账号删除请求是 destructive + 二次确认 + 登录态接口,符合 `manual_confirm`。
- 本切片只记录可审计请求,不做跨表硬删除;完整删除 worker/admin 流程需另开安全评审。
- 删除请求 audit 写入 fail-loud,不会把失败伪装成成功。
- 隐私文案说明 HealthKit 不用于广告/出售,AI 不替代诊断/治疗/处方/剂量调整。

## S6 · 部署

- Batch 1: 已完成 App Store MVP 合规/UI 切片并合入 `main`。
- Batch 2 plan: `docs/plans/2026-06-28-app-store-mvp-release-batch2-plan.md`
- Batch 2 release pack:
  - `frontend/src/app/privacy/page.tsx`: App Store Connect 可用隐私政策 URL 源码。
  - `docs/release/app-store/submission-pack.md`: App Store metadata / submission gate。
  - `docs/release/app-store/privacy-nutrition-label.draft.json`: 隐私营养标签草案。
  - `docs/release/app-store/review-notes.zh-CN.md`: Review Notes 草案。
  - `docs/release/app-store/screenshot-runbook.md`: 截图与 QA 运行手册。
  - `scripts/check_app_store_release_pack.py`: 提交包一致性检查器。
  - `scripts/sim-build.sh`: 默认在临时 worktree 中构建 iOS simulator app,避免 Pods/锁文件污染主工作区。
  - `scripts/mobile-sim-screenshots.sh`: 模拟器截图脚本。
- pending:
  - iOS production archive / EAS build 产出并进入 App Store Connect。
  - App Store Connect 手工填入隐私营养标签、metadata、Review Notes。

## G5 · 部署健康闸

- Local release-pack gate:
  - PASS: `python3 scripts/check_app_store_release_pack.py`
- Web deployment gate:
  - PASS: `./deploy.sh -f -y` 成功完成前端部署;远端 `next build` compiled successfully,生成 `/privacy` 静态页面,并重启 `health-frontend` PM2 为 online。
  - NOTE: 部署脚本报告 kuaishou GitLab 同步失败,不影响 GitHub/main 和生产前端部署;还提示 mobile 自上次 OTA 后有未发布改动,本次只发布 Web 隐私页。
- Public privacy URL gate:
  - PASS: `curl -fsSI https://health.executor.life/privacy` 返回 `HTTP/2 200`。
  - PASS: `curl -fsS https://health.executor.life/privacy | rg -n "HealthKit|删除账号|不提供诊断|support@executor.life"` 命中 App Store 审核要求的关键文案。
- Local simulator screenshot route gate:
  - PASS: `./scripts/mobile-sim-screenshots.sh` 可在已安装 simulator app 上遍历 `今日 / 私教 / 记录 / 我 / 体检导入 / 隐私政策` 并输出 1206 x 2622 截图。
  - 注意: 本次生成的截图来自 simulator 上旧安装包,仅证明截图自动化路径可运行;未提交截图文件。
- Local current-code simulator build gate:
  - BLOCK: `cd mobile && ROKID_IOS_SDK_ENABLED=0 ROKID_IOS_SIMULATOR=1 SENTRY_DISABLE_AUTO_UPLOAD=true npx expo run:ios --device "iPhone 17 Pro"` 失败,`xcodebuild` exit 65。失败点在 `mobile/modules/rokid-bridge/ios/RokidBridgeModule.swift` 编译期仍看到 stale `RGCxrClient/RGCoreKit` Pods,触发 `cannot find type RGCxrClientAudioEvent`、`cannot find CxrClient`、`RGCxrClientBLE.shared` 等 82 个 Swift 错误。
  - 缓解: 新增 `scripts/sim-build.sh`,默认在临时 worktree 中清理 generated Pods/Podfile.lock 后用 `ROKID_IOS_SDK_ENABLED=0 ROKID_IOS_SIMULATOR=1` 构建,避免主工作区和 stale Rokid Pods 影响 App Store 截图安装。
- pending:
  - App Store Connect build processing status。
  - 用 `scripts/sim-build.sh` 重新安装当前代码后产出最终截图。

## S7 · 上线验证

- pending: 需要真机或模拟器逐页验证 `我 -> 账号与隐私 -> 删除账号与数据`、HealthKit 权限文案、隐私政策入口。

## G6 · 验证闸

- pending: App Store submission still requires human-provided demo account credentials and final App Store Connect manual entry.

## S8 · 沉淀

- 下一批优先级:
  - 用 `scripts/check_app_store_release_pack.py` 作为提交前硬闸。
  - 用 `scripts/mobile-sim-screenshots.sh` 或真机截图补齐 App Store screenshot set。
  - 用 `docs/release/app-store/*` 作为 App Store Connect 填写真源。
  - 真机走查核心动线: 今日 -> Chat 动态卡片 -> 快速记录 -> 体检导入 -> 复盘 -> 隐私/删除请求。
  - 若需要“完整账号删除”,新增删除工单/worker/admin 审批与跨表匿名化测试。
