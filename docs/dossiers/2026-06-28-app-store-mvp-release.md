# Dossier: App Store MVP Release

| 字段 | 值 |
|---|---|
| slug | `app-store-mvp-release` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S6 部署准备 |
| 状态 | app-store-batch7-sanitized-candidate-tooling-human-review-pending |
| 负责 | Codex |
| 分支 | `main` |
| 工作区 | `/Users/liqiuhua/work/personal/health-llm-driven` |

## S0 · 用户需求

> 可以 按照你规划执行

上下文: 用户认可“下周发布一个可用版本:统一 UI、支持核心用户动线、能上架到 App Store”的规划,要求直接执行。

目标用户: 35-55 岁高强度工作者, 已有 Apple Watch / HealthKit / 体检报告 / 日常记录需求。

## S1 · Discovery

- 现有系统定位: Reva 是 Personal Health OS, 不做医疗诊断/处方/治疗承诺。
- Mobile 当前主导航已经是 `今日 / 阿衡 / 记录 / 我`, 但 `我` tab 仍像内部功能清单, App Store 版需要更清晰的“核心健康动线 + 数据与隐私”结构。
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
2. Mobile UI 主入口统一为 `今日 / 阿衡 / 记录 / 我`。
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
- Batch 3 local gates:
  - PASS: `./scripts/sim-build.sh --device 39D954B3-A2B5-41AA-8A6E-BD9750D3CB86 --keep-temp-worktree`
    - `xcodebuild` completed `Build Succeeded`, 0 errors, 7 warnings, installed `HealthPilot.app`, and opened `life.executor.health`.
  - PASS: `./scripts/mobile-sim-screenshots.sh --device 39D954B3-A2B5-41AA-8A6E-BD9750D3CB86 --output design/screenshots/app-store/batch3-20260628`
    - Captured `00-launch.png` through `06-privacy.png`, all 1206 x 2622.
    - Screenshots are local evidence only; they include real account/health context and must not be committed or submitted before replacing with a demo account.
  - PASS: `bash -n scripts/mobile-local-qr.sh scripts/sim-build.sh scripts/mobile-sim-screenshots.sh`
  - PASS: `python3 scripts/check_app_store_release_pack.py`
  - PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath __tests__/app-config.test.ts --runInBand`
    - 1 suite passed, 5 tests passed.
  - PASS: `cd mobile && ./node_modules/.bin/tsc --noEmit`
  - PASS: `/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
  - PASS: `/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python scripts/check_doc_drift.py`
  - PASS: `git diff --check`
- Batch 4 local gates:
  - RED then PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py backend/tests/test_app_store_screenshot_checker.py -q --no-cov`
    - 初始 RED:缺少 `scripts/check_app_store_screenshots.py`,release pack 未调用截图 checker。
    - GREEN:5 passed。
  - PASS: `bash -n scripts/mobile-sim-screenshots.sh`
  - PASS: `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_app_store_screenshots.py`
  - PASS: `python3 scripts/check_app_store_release_pack.py`
  - PASS: `python3 scripts/check_app_store_screenshots.py design/screenshots/app-store/batch4-private-20260628`
    - `screens=7 privacy_status=private app_store_ready=False`。
  - EXPECTED FAIL: `python3 scripts/check_app_store_screenshots.py design/screenshots/app-store/batch4-private-20260628 --app-store-ready`
    - 拒绝 private status,并拒绝 1206 x 2622 作为 App Store 6.9-inch ready size。
- Batch 5 local gates:
  - RED then PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py backend/tests/test_app_store_screenshot_checker.py -q --no-cov`
    - 初始 RED:缺少 `scripts/prepare_app_store_screenshots.py`。
    - GREEN:8 passed。
  - PASS: `bash -n scripts/mobile-sim-screenshots.sh`
  - PASS: `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_app_store_screenshots.py scripts/prepare_app_store_screenshots.py`
  - PASS: `python3 scripts/check_app_store_release_pack.py`
  - EXPECTED FAIL: `python3 scripts/prepare_app_store_screenshots.py design/screenshots/app-store/batch4-private-20260628 /tmp/reva-appstore-private-ready --overwrite`
    - `source privacy_status must be demo or sanitized`。
  - PASS: `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
    - 15 份 dossier 全自洽。
  - PASS: `backend/venv/bin/python scripts/check_doc_drift.py`
- Batch 6 local gates:
  - RED then PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_ios_app_store_submission_preflight.py backend/tests/test_app_store_release_pack.py -q --no-cov`
    - 初始 RED:缺少 `scripts/check_ios_app_store_submission.py`,release pack 未调用 iOS submission preflight。
    - GREEN:4 passed。
  - PASS: `python3 scripts/check_ios_app_store_submission.py`
    - 校验 bundle id、ASC app id、EAS production profile、HealthKit/Push entitlement、usage strings、watch extension bundle id、updates URL 和 submit helper。
  - EXPECTED FAIL: `env -u ASC_KEY_ID -u APP_STORE_CONNECT_API_KEY -u ASC_ISSUER_ID -u APP_STORE_CONNECT_ISSUER_ID -u ASC_PRIVATE_KEY_PATH -u ASC_PRIVATE_KEY_BASE64 python3 scripts/check_ios_app_store_submission.py --require-asc-credentials`
    - 缺少 App Store Connect credentials 时 fail-loud。
  - PASS: `python3 scripts/check_app_store_release_pack.py`
    - release pack 自动执行 iOS submission preflight。
  - PASS: `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_ios_app_store_submission.py scripts/check_app_store_screenshots.py scripts/prepare_app_store_screenshots.py`
  - PASS: `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
  - PASS: `backend/venv/bin/python scripts/check_doc_drift.py`
- Batch 7 local gates:
  - RED then PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_screenshot_checker.py -q --no-cov`
    - 初始 RED:缺少 `scripts/sanitize_app_store_screenshots.py`,prepare 未阻断 review-required sanitized candidate。
    - GREEN:9 passed。
  - PASS: `scripts/sanitize_app_store_screenshots.py` 能从 private QA 截图生成 `privacy_status=sanitized`、`app_store_ready=false`、`sanitization_review_required=true` 的候选集。
  - PASS: `scripts/prepare_app_store_screenshots.py` 默认拒绝 review-required sanitized candidate。
  - PASS: `--confirm-sanitized-reviewed` 后才允许 prepare 生成 ready set。
  - PASS: `python3 scripts/sanitize_app_store_screenshots.py design/screenshots/app-store/batch4-private-20260628 /tmp/reva-appstore-sanitized --overwrite`
  - EXPECTED FAIL: `python3 scripts/prepare_app_store_screenshots.py /tmp/reva-appstore-sanitized /tmp/reva-appstore-ready --overwrite`
    - `sanitized screenshots require human review`。
  - PASS: `python3 scripts/prepare_app_store_screenshots.py /tmp/reva-appstore-sanitized /tmp/reva-appstore-ready --overwrite --confirm-sanitized-reviewed && python3 scripts/check_app_store_screenshots.py /tmp/reva-appstore-ready --app-store-ready`
    - 7 张截图导出为 1290 x 2796,`privacy_status=sanitized app_store_ready=True`。
  - PASS: `python3 scripts/check_app_store_release_pack.py`
  - PASS: `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_app_store_screenshots.py scripts/prepare_app_store_screenshots.py scripts/sanitize_app_store_screenshots.py scripts/check_ios_app_store_submission.py`

## G4 · 安全闸

- PASS。
- 账号删除请求是 destructive + 二次确认 + 登录态接口,符合 `manual_confirm`。
- 本切片只记录可审计请求,不做跨表硬删除;完整删除 worker/admin 流程需另开安全评审。
- 删除请求 audit 写入 fail-loud,不会把失败伪装成成功。
- 隐私文案说明 HealthKit 不用于广告/出售,AI 不替代诊断/治疗/处方/剂量调整。

## S6 · 部署

- Batch 1: 已完成 App Store MVP 合规/UI 切片并合入 `main`。
- Batch 2 plan: `docs/plans/2026-06-28-app-store-mvp-release-batch2-plan.md`
- Batch 3 plan: `docs/plans/2026-06-28-app-store-mvp-release-batch3-plan.md`
- Batch 4 plan: `docs/plans/2026-06-28-app-store-mvp-release-batch4-plan.md`
- Batch 5 plan: `docs/plans/2026-06-28-app-store-mvp-release-batch5-plan.md`
- Batch 6 plan: `docs/plans/2026-06-28-app-store-mvp-release-batch6-plan.md`
- Batch 7 plan: `docs/plans/2026-06-28-app-store-mvp-release-batch7-plan.md`
- Batch 2 release pack:
  - `frontend/src/app/privacy/page.tsx`: App Store Connect 可用隐私政策 URL 源码。
  - `docs/release/app-store/submission-pack.md`: App Store metadata / submission gate。
  - `docs/release/app-store/privacy-nutrition-label.draft.json`: 隐私营养标签草案。
  - `docs/release/app-store/review-notes.zh-CN.md`: Review Notes 草案。
  - `docs/release/app-store/screenshot-runbook.md`: 截图与 QA 运行手册。
  - `scripts/check_app_store_release_pack.py`: 提交包一致性检查器。
  - `scripts/sim-build.sh`: 默认在临时 worktree 中构建 iOS simulator app,避免 Pods/锁文件污染主工作区。
  - `scripts/mobile-sim-screenshots.sh`: 模拟器截图脚本。
  - `scripts/check_app_store_screenshots.py`: 截图 manifest/privacy/尺寸合规检查器。
  - `scripts/prepare_app_store_screenshots.py`: 将 demo/sanitized 原始截图导出为 App Store Connect 接受尺寸,并写入 ready manifest。
  - `scripts/check_ios_app_store_submission.py`: iOS production build / App Store Connect submit 配置预检,默认不联网;真正上传前用 `--require-asc-credentials` 检查本机 ASC 凭证。
  - `scripts/sanitize_app_store_screenshots.py`: 将 private QA 截图生成 review-required sanitized candidate;不等于可提交截图。
- pending:
  - iOS production archive / EAS build 产出并进入 App Store Connect。
  - App Store Connect 手工填入隐私营养标签、metadata、Review Notes。
  - App Store 截图需要用 demo account / 脱敏数据重新采集,经 `prepare_app_store_screenshots.py` 导出并过闸后再提交。

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
  - PASS: `./scripts/mobile-sim-screenshots.sh --device 39D954B3-A2B5-41AA-8A6E-BD9750D3CB86 --output design/screenshots/app-store/batch3-20260628` 在当时代码 simulator app 上遍历 `今日 / 私教 / 记录 / 我 / 体检导入 / 隐私政策` 并输出 1206 x 2622 截图;当前可见 tab 已在后续批次收敛为 `今日 / 阿衡 / 记录 / 我`。
  - 注意: 本次截图包含真实账号和健康上下文,只作为本地 QA 证据,未提交进仓库,不可直接用于 App Store Connect。
- Local screenshot compliance gate:
  - PASS: `./scripts/mobile-sim-screenshots.sh --device 39D954B3-A2B5-41AA-8A6E-BD9750D3CB86 --output design/screenshots/app-store/batch4-private-20260628 --privacy-status private` 生成带 `manifest.json` 的 QA 截图集。
  - PASS: 普通检查接受 private QA set,用于本地回归证据。
  - EXPECTED FAIL: `--app-store-ready` 拒绝该 set,原因是 `privacy_status=private` 且截图尺寸为 1206 x 2622,不属于 App Store Connect 6.9-inch accepted portrait sizes。
  - Release pack 增强:设置 `APP_STORE_SCREENSHOT_DIR` 时,`scripts/check_app_store_release_pack.py` 会调用截图 checker;未提供该变量时仍只检查 App Store 文案/配置包。
- Local final screenshot export gate:
  - PASS: `scripts/prepare_app_store_screenshots.py` 能将 demo/sanitized raw set 导出为 App Store Connect accepted portrait size,并写入 `app_store_ready=true` manifest。
  - EXPECTED FAIL: 当前 private QA set 不能 prepare,防止真实账号截图被误提交。
  - pending: 仍需用 demo account 或脱敏数据重新采集 raw set 后生成最终 ready set。
- Local iOS submission preflight gate:
  - PASS: `scripts/check_ios_app_store_submission.py` 默认模式已纳入 release pack gate。
  - EXPECTED FAIL: `--require-asc-credentials` 在缺少 ASC key / issuer / private key 时失败;真正上传前必须由 release machine 跑通过。
- Local sanitized screenshot candidate gate:
  - PASS: private QA set 可生成 sanitized candidate,但 manifest 保持 `app_store_ready=false` 和 `sanitization_review_required=true`。
  - EXPECTED FAIL: 未加 `--confirm-sanitized-reviewed` 时,prepare 拒绝 sanitized candidate。
  - pending: 需要人工逐张视觉复核 sanitized PNG;若仍暴露私密数据,改用 dedicated demo account 重新采集。
- Local current-code simulator build gate:
  - PASS: `./scripts/sim-build.sh --device 39D954B3-A2B5-41AA-8A6E-BD9750D3CB86 --keep-temp-worktree` 从干净临时 worktree 构建、安装并打开当前代码。
  - 结论: Batch 2 的 Rokid compile failure 是主工作区 stale Pods/Podfile.lock 污染;干净 worktree + `ROKID_IOS_SDK_ENABLED=0` 可以稳定走通 simulator build。
- Local QR install gate:
  - PASS: 修复 `scripts/mobile-local-qr.sh` 的 `AUTH_ARGS[@]: unbound variable` 问题;在无 App Store Connect API key 文件时仍可运行 archive/export。
  - PASS: `SENTRY_DISABLE_AUTO_UPLOAD=true SENTRY_ALLOW_FAILURE=true xcodebuild ... archive` 成功生成 `HealthPilot.xcarchive`。
  - PASS with fallback: ad-hoc export 因本机缺少 `life.executor.health`、watch app、watch extension 的 ad-hoc profiles 失败;development export 成功生成 IPA。
  - PASS: `./scripts/mobile-local-qr.sh --ipa .../HealthPilot.ipa --build-id batch3-20260628-af8f7721` 生成并上传二维码安装包。
  - Public install page: `https://health.executor.life/mobile-install/ios/batch3-20260628-af8f7721/install.html`
  - Public artifacts gate: script 与独立 `curl -fsSI` 均已验证 `install.html`、`manifest.plist`、IPA 公开可访问。
  - 注意: 当前二维码包是 development-signed build,适合已纳入开发签名/配置的设备扫码安装;不等同于 App Store/TestFlight build。
- Local brand consistency gate(Batch 8):
  - PASS: `mobile/app.json` Expo `name` 与 iOS `CFBundleDisplayName` 均为 `阿衡`。
  - PASS: `mobile/app.config.ts` 生产/预览/开发显示名为 `阿衡` / `阿衡 Preview` / `阿衡 Dev`。
  - PASS: `scripts/check_ios_app_store_submission.py` 和 `scripts/check_app_store_release_pack.py` 已把用户可见 App 名锁定为 `阿衡`,防止发布材料回退到旧名。
  - PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath __tests__/app-config.test.ts --runInBand` -> 7 passed。
  - PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_ios_app_store_submission_preflight.py backend/tests/test_app_store_release_pack.py -q --no-cov` -> 4 passed。
- Local final-submit gate(Batch 9):
  - PASS: `scripts/check_app_store_release_pack.py` 新增 `--final-submit` 与 `--screenshot-dir`,把最终 App Store 提交前的人审材料升级为硬闸。
  - EXPECTED FAIL: 在缺少 `APP_STORE_SCREENSHOT_DIR` / `--screenshot-dir`、Review Notes 仍有 demo credentials 占位符、且本机无 ASC credentials 时,`python3 scripts/check_app_store_release_pack.py --final-submit` 返回 1 并列出全部阻塞。
  - 普通 `python3 scripts/check_app_store_release_pack.py` 仍可用于无人工凭证的日常回归。
- Local persona copy gate(Batch 10):
  - PASS: Mobile 首页 Daily Artifact、试用入口、onboarding、hub、体检导入动态卡片和通用权限/分享/隐私文案已统一使用 `阿衡`。
  - PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/chat/cards/__tests__/MedicalExamImportResultCard.test.tsx components/home/__tests__/DailyArtifactCard.test.tsx components/home/__tests__/RevaTryEntryCard.test.tsx app/__tests__/reva-onboarding.test.tsx --runInBand` -> 11 passed。
  - PASS: 目标旧称扫描无命中,覆盖 `询问 Reva` / `试试新版复元` / `进入复元` / `让 Reva` / `健康助理` 等通用用户可见旧称。
  - NOTE: Rokid 专页旧称因外设 SDK 语义和测试面较大,保留为后续独立切片。
- Local release narrative gate(Batch 11):
  - PASS: `scripts/check_app_store_release_pack.py` 新增高可见审核叙事校验,覆盖 submission pack、review notes 和 screenshot runbook。
  - PASS: `backend/tests/test_app_store_release_pack.py` 拒绝 `Reva`、`复元`、`健康助理`、`守护神` 等旧用户可见叙事,并要求当时底部导航 `今日 / 私教 / 记录 / 我` 与定位词 `健康参谋`。
  - PASS: 后续 Mobile tab rename 批次把 release narrative gate 的当前底部导航推进为 `今日 / 阿衡 / 记录 / 我`,并把 `私教` 纳入 stale user-visible term。
  - PASS: `submission-pack.md` keywords 从 `健康助理` 收敛为 `阿衡` / `健康参谋`。
- pending:
  - App Store Connect build processing status。
  - App Store Connect production/distribution profile build。
  - 用 demo account 产出最终 App Store screenshot raw set,或对 private QA set 运行 sanitize 后人工视觉复核。
  - 用 `scripts/prepare_app_store_screenshots.py <raw-or-reviewed-sanitized> <ready> --size 1290x2796 --confirm-sanitized-reviewed` 导出最终 ready set,再用 `APP_STORE_SCREENSHOT_DIR=<ready> python3 scripts/check_app_store_release_pack.py` 过闸。
  - 最终提交前必须跑 `python3 scripts/check_app_store_release_pack.py --final-submit --screenshot-dir <ready>`。
  - 真正触发 EAS production build / submit 前,用 `python3 scripts/check_ios_app_store_submission.py --require-asc-credentials` 在发布机器上过闸。

## S7 · 上线验证

- pending: 需要真机或模拟器逐页验证 `我 -> 账号与隐私 -> 删除账号与数据`、HealthKit 权限文案、隐私政策入口。

## G6 · 验证闸

- pending: App Store submission still requires human-provided demo account credentials and final App Store Connect manual entry.

## S8 · 沉淀

- 下一批优先级:
  - 用 `scripts/check_app_store_release_pack.py` 作为提交前硬闸。
  - 用 `scripts/mobile-sim-screenshots.sh` 或真机截图补齐 App Store raw screenshot set。
  - 用 `docs/release/app-store/*` 作为 App Store Connect 填写真源。
  - 用 `scripts/check_ios_app_store_submission.py --require-asc-credentials` 作为 EAS production build / submit 前置闸。
  - 用 `scripts/sanitize_app_store_screenshots.py` + 人工视觉复核 + `scripts/prepare_app_store_screenshots.py` + `scripts/check_app_store_screenshots.py --app-store-ready` 防止 private/尺寸不合规截图进入提交包。
  - 用 `scripts/check_app_store_release_pack.py` 持续阻断 App Store 高可见文案回退到旧品牌、旧 tab 或旧定位。
  - 真机走查核心动线: 今日 -> Chat 动态卡片 -> 快速记录 -> 体检导入 -> 复盘 -> 隐私/删除请求。
  - 发布配置中用户可见命名必须保持 `阿衡`;`HealthPilot` 仅保留为工程/历史技术名,不得重新进入 App Store 用户可见字段。
  - 后续用独立切片处理 Rokid 专页中的旧称和测试断言,避免影响本周 App Store 主路径。
  - 若需要“完整账号删除”,新增删除工单/worker/admin 审批与跨表匿名化测试。
