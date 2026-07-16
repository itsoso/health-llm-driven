# Controlled App Update Plane Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 建立 Remote Config、OTA telemetry、发布 manifest 和 Mobile 手工回滚组成的第一版生产更新闭环。

**Architecture:** 后端保存带版本的全局 Mobile 发布策略，客户端启动/前台时读取并以 last-known-good 降级；OTA 更新状态机通过统一的 content-free client events 上报；发布脚本在 EAS 成功后保存不可变 manifest，回滚脚本只允许将已验证 artifact 重新指向生产入口。原生改动和灰度自动化不在本批实现。

**Tech Stack:** FastAPI, SQLAlchemy, managed PostgreSQL/SQLite migrations, React Native/Expo Updates, TypeScript/Jest, pytest, Bash.

---

### Task 1: 写入需求脊柱和协议文档

**Status: completed** — PRD、Plan、Dossier 已建立，G1/G2 已裁决 PASS。

**Files:**
- Create: `docs/dossiers/2026-07-16-controlled-app-update-plane.md`
- Create: `docs/prd/2026-07-16-controlled-app-update-plane.md`
- Create: `docs/plans/2026-07-16-controlled-app-update-plane.md`

**Steps:**
1. 记录用户原话、现状、范围、非目标和安全边界。
2. 把 Remote Config、OTA、原生发版和回滚映射到项目核心循环。
3. 记录本批 G1/G2 结论：基础设施需求 PASS；医疗安全核心逻辑不由远程配置控制。

### Task 2: Remote Config 数据模型和客户端策略 API

**Status: completed** — 版本化策略、管理员并发校验、客户端读取、安全默认、审计和双数据库 migration 已实现。

**Files:**
- Create: `backend/app/models/app_release_policy.py`
- Create: `backend/app/api/app_release_policy.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/api/main.py`
- Create: `backend/migrations/managed/20260716_180000_add_app_release_policies.postgresql.sql`
- Create: `backend/migrations/managed/20260716_180000_add_app_release_policies.sqlite.sql`
- Test: `backend/tests/test_app_release_policy.py`

**Contract:**
- Client `GET /api/v1/app-release-policy?platform=ios&channel=production` returns the active policy, only safe release fields.
- Admin `GET /api/v1/admin/app-release-policy` returns the current policy.
- Admin `PUT /api/v1/admin/app-release-policy` requires `expected_config_version`, increments `config_version`, validates rollout 0-100 and minimum versions, and writes an audit event.
- No active row returns a safe default: OTA enabled, no forced update, rollout 100, no kill switches, config version 0.

**Steps:**
1. Write pytest cases for safe default, validation, client read isolation, admin permission, and optimistic concurrency.
2. Run the focused test and verify RED.
3. Add the model, migrations, Pydantic contracts and router.
4. Run the focused test and verify GREEN.
5. Add model import and router registration; run schema/create-all compatibility checks.

### Task 3: Mobile Remote Config cache and update policy

**Status: completed** — SecureStore last-known-good、过期/格式/作用域校验、稳定灰度 cohort、OTA 开关/最低 native build/灰度门已接入检查入口。

**Files:**
- Create: `mobile/services/remoteConfig.ts`
- Test: `mobile/services/__tests__/remoteConfig.test.ts`
- Modify: `mobile/services/api.ts` only if the existing API wrapper requires a typed helper.

**Contract:**
- Store only the latest valid policy in SecureStore/AsyncStorage-compatible local storage.
- Reject malformed, expired, incompatible or unknown policy versions.
- Network failure returns last-known-good, otherwise embedded safe defaults.
- Policy fetch does not block chat, health records, or startup indefinitely.

**Steps:**
1. Write tests for valid policy, malformed payload, expired payload, storage fallback and timeout fallback.
2. Run the focused Jest test and verify RED.
3. Implement the smallest typed cache and fetch helper.
4. Run the focused test and verify GREEN.

### Task 4: OTA lifecycle telemetry

**Status: completed** — 启动来源、检查阶段、终态和失败率聚合已接入；字段严格 content-free。

**Files:**
- Modify: `mobile/services/clientEvents.ts`
- Modify: `backend/app/api/client_events.py`
- Modify: `backend/app/services/observability_service.py`
- Test: `mobile/services/__tests__/clientEvents.test.ts`
- Test: `backend/tests/test_client_events.py` or the existing client-event test module.

**Contract:**
- Add content-free events for check, available, download, apply, failed, launch source and rollback.
- Client sanitizes platform/channel/runtime/version/update id/error code and bounded duration.
- Events are best-effort and never block the update or user flow.
- Admin dashboard exposes counts and terminal failure rates for the selected window.

**Steps:**
1. Add failing client and backend schema tests.
2. Verify RED.
3. Extend the shared whitelist and aggregation.
4. Add telemetry calls to `useAppUpdate` and app bootstrap diagnostics.
5. Verify focused tests and existing client-event tests.

### Task 5: Release manifest and rollback command

**Status: completed** — OTA 成功写 manifest；rollback 默认 dry-run，`--confirm` 后通过 EAS `update:republish` 执行并记录状态。

**Files:**
- Create: `scripts/mobile-ota-rollback.sh`
- Modify: `scripts/mobile-ota.sh`
- Modify: `scripts/test_mobile_fast_feedback_scripts.py`
- Create: `docs/release/mobile-update-manifest.md`

**Contract:**
- Successful OTA writes a JSON manifest containing commit, runtime, branch/channel, group id, update id, platform and timestamp.
- Rollback requires an explicit update id or last-known-good manifest and `--confirm` for production.
- Default is dry-run; no destructive or ambiguous rollback.
- Script verifies the target artifact before republishing and prints the resulting EAS identifiers.

**Steps:**
1. Write shell-contract tests for clean-main guard, missing target, dry-run and confirmation gate.
2. Verify RED.
3. Implement manifest output and rollback wrapper using the existing `OTA_EAS_RUNNER` seam.
4. Run shell tests and verify GREEN.

### Task 6: Verification and release gates

**Status: in progress** — 本地 G3/G4 已通过；待完成提交、后端部署健康和 production OTA 上线证据。

**Files:**
- Modify: `docs/dossiers/2026-07-16-controlled-app-update-plane.md`
- Modify: `docs/ARCHITECTURE.md` only if the new model/service is listed there.
- Regenerate: `docs/_generated/system-map.json` if architecture counts change.

**Steps:**
1. Run focused backend pytest, Mobile Jest, TypeScript、ESLint、脚本和 migration checks.
2. Run the project doc drift checker and dossier consistency checker.
3. Run the CI-mode backend integration gate with `TZ=Asia/Shanghai` and in-memory DB where supported.
4. Perform security review for admin auth, config poisoning, stale policy and telemetry minimization.
5. Commit only files owned by this slice, push `main`, then deploy backend and run production health verification.
6. Publish Mobile OTA only after backend and tests are green; record update group/id and rollback target in the Dossier.
