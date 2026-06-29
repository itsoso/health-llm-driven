# App Store MVP Release Batch 3 Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-28 |
| Dossier | `docs/dossiers/2026-06-28-app-store-mvp-release.md` |
| 目标 | 当前代码模拟器安装、App Store 截图路径验证、二维码发版脚本硬化 |
| 状态 | done-local-qr-published-app-store-connect-pending |

## 背景

Batch 2 已完成 Web 隐私页部署和 App Store 提交包文档。第三批聚焦把 Mobile 上架验证从“文档就绪”推进到“当前代码可构建、可截图、可走默认二维码发布路径”。

## 范围

- 用 `scripts/sim-build.sh` 从 `origin/main` 干净临时 worktree 构建并安装当前 Mobile 代码到 iOS simulator。
- 用 `scripts/mobile-sim-screenshots.sh` 遍历核心 App Store 页面并产出截图证据。
- 修复 `scripts/mobile-local-qr.sh` 在无 App Store Connect API key 文件时触发 `set -u` 空数组崩溃的问题。
- 继续尝试本地 iOS archive/export/QR install bundle；若签名或资源导致失败，记录为 G5 blocker，不伪装为发布成功。
- 回写 Dossier 的 G5/G6 状态。

## 非目标

- 不提交包含真实用户姓名、邮箱、健康数据的截图到仓库。
- 不走 TestFlight，除非用户手工指定。
- 不把并发会话在本地 `main` 上的提交一起推送。
- 不扩大 Rokid/IoT/App Store v1 的产品承诺。

## 验收

- 当前代码 simulator build PASS，或记录可复现 blocker。
- 截图脚本能点击并覆盖 `今日 / 阿衡 / 记录 / 我 / 体检导入 / 隐私政策`。
- QR 脚本 `bash -n` PASS，且无 `AUTH_ARGS[@]: unbound variable`。
- Dossier 记录第三批的测试、部署、隐私截图处理和剩余阻塞。

## 结果

- 当前代码 simulator build PASS。
- 当前代码截图路径 PASS，输出 `design/screenshots/app-store/batch3-20260628`；截图包含真实用户上下文，保留为本地 QA 证据，不提交、不用于 App Store。
- iOS archive PASS。
- ad-hoc export 因本机缺少 ad-hoc provisioning profiles 失败；development export PASS。
- 默认二维码路径 PASS，公开安装页: `https://health.executor.life/mobile-install/ios/batch3-20260628-af8f7721/install.html`。
- App Store Connect production/distribution build、metadata 手工录入、demo account 截图仍待执行。

## 测试

- `bash -n scripts/mobile-local-qr.sh scripts/sim-build.sh scripts/mobile-sim-screenshots.sh`
- `python3 scripts/check_app_store_release_pack.py`
- `cd mobile && ./node_modules/.bin/jest --runTestsByPath __tests__/app-config.test.ts --runInBand`
- `cd mobile && ./node_modules/.bin/tsc --noEmit`
- `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
- `backend/venv/bin/python scripts/check_doc_drift.py`
- `git diff --check`
