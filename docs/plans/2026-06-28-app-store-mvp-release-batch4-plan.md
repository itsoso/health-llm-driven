# App Store MVP Release Batch 4 Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-28 |
| Dossier | `docs/dossiers/2026-06-28-app-store-mvp-release.md` |
| 目标 | 截图脱敏/尺寸合规闸门,防止真实用户截图误进入 App Store 提交 |
| 状态 | done-private-qa-gated-demo-screenshots-pending |

## 背景

Batch 3 已经证明当前代码可 simulator build、可截图、可二维码安装。但截图来自真实账号上下文,且原始 simulator 尺寸为 1206 x 2622,不能直接作为 App Store 6.9-inch 截图提交。第四批把“截图是否可提交”从人工提醒升级为机器可验证的发布合同。

## 范围

- `scripts/mobile-sim-screenshots.sh` 生成 `manifest.json`,记录 routes、bundle、url scheme、privacy status、App Store-ready 标记。
- 新增 `scripts/check_app_store_screenshots.py`,验证 manifest、核心截图完整性、privacy status、App Store 6.9-inch 接受尺寸。
- `scripts/check_app_store_release_pack.py` 支持 `APP_STORE_SCREENSHOT_DIR`,在提供候选截图目录时把截图合规纳入 release pack 硬闸。
- 更新截图 runbook 和提交包 checklist。
- 重新捕获一套 private QA 截图,证明本地证据可验证,但不能被误判为 App Store-ready。

## 非目标

- 不提交真实账号截图。
- 不伪造 demo account 或 App Store Connect metadata 已完成。
- 不把 1206 x 2622 simulator 原图硬标为 App Store-ready。
- 不改变 Mobile 主 UI/业务行为。

## 验收

- 截图 checker 接受 demo/sanitized + accepted size 的测试 fixture。
- 截图 checker 拒绝 private ready set。
- 截图 checker 拒绝 1206 x 2622 作为 App Store-ready。
- release pack 在设置 `APP_STORE_SCREENSHOT_DIR` 时会调用截图 checker。
- 当前 private QA 截图普通检查 PASS,`--app-store-ready` FAIL。

## 结果

- `design/screenshots/app-store/batch4-private-20260628` 已生成本地 QA 证据,含 `manifest.json`。
- 普通截图检查 PASS:`privacy_status=private app_store_ready=False`。
- App Store-ready 检查按预期 FAIL:private status + 1206 x 2622 非 accepted size。
- 下一步仍需 demo account / sanitized data + accepted 6.9-inch 输出后再提交 App Store Connect。

## 测试

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py backend/tests/test_app_store_screenshot_checker.py -q --no-cov`
- `bash -n scripts/mobile-sim-screenshots.sh`
- `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_app_store_screenshots.py`
- `python3 scripts/check_app_store_release_pack.py`
- `python3 scripts/check_app_store_screenshots.py design/screenshots/app-store/batch4-private-20260628`
- `python3 scripts/check_app_store_screenshots.py design/screenshots/app-store/batch4-private-20260628 --app-store-ready` (expected FAIL)
