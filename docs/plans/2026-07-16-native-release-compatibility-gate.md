# 原生版本兼容门实施计划

> 目标：把 `minimum_native_build` 从“静默跳过 OTA 的判断”升级为可观察、可解释、可操作的原生发版边界。

## Task 1：定义协议与脊柱

**状态：in_progress**

- 建立本 PRD、Plan、Dossier。
- 记录 `required / recommended / none` 的客户端契约和非目标。
- 明确官方商店 URL allowlist，禁止 Remote Config 变成任意跳转。

## Task 2：后端策略字段

**状态：pending**

文件：

- `backend/app/models/app_release_policy.py`
- `backend/app/api/app_release_policy.py`
- `backend/app/services/app_release_policy.py`
- `backend/migrations/managed/20260716_210000_add_native_update_url.*.sql`
- `backend/tests/test_app_release_policy.py`

步骤：

1. 增加可选 `native_update_url`，只允许官方商店 HTTPS host/path。
2. 同步 safe default、公开响应、Admin 写入、审计详情和 schema。
3. 增加迁移并验证已有策略行可读。

## Task 3：Mobile 原生门与交互

**状态：pending**

文件：

- `mobile/services/remoteConfig.ts`
- `mobile/hooks/useAppUpdate.tsx`
- `mobile/components/updates/AppUpdateBanner.tsx`
- `mobile/services/appUpdate.ts`
- `mobile/services/clientEvents.ts`

步骤：

1. 提取原生版本比较函数，未知/非法 build 对最低门 fail closed。
2. 最低版本不满足时跳过 OTA，设置 `nativeUpdateRequirement=required`。
3. 推荐版本不满足时允许 OTA，设置 `recommended`。
4. 使用 `expo-linking` 打开已校验的官方链接；无链接时不显示假按钮。
5. 发出 `native_update_required` / `native_update_recommended` 终态事件。

## Task 4：验证闸

**状态：pending**

- Mobile Jest：策略解析、hook、banner、商店链接成功/失败、强制/推荐关闭行为。
- Backend pytest：URL allowlist、Admin 审计、safe default、migration/schema。
- TypeScript、Ruff、doc drift、Dossier consistency、`git diff --check`。
- 检查原生门事件不进入 OTA 失败率分母。

## Task 5：发布

**状态：pending**

- 只提交本切片文件，保留并发 Mobile WIP 不触碰。
- 推送 `main`，部署后端并检查 production health。
- 本切片没有原生二进制变化，不发布 Mobile OTA；待 App Store URL 和原生 build 发布时再由 Admin 配策略。
