# App Store MVP Release Batch 5 Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-28 |
| Dossier | `docs/dossiers/2026-06-28-app-store-mvp-release.md` |
| 目标 | 把 demo/sanitized 截图集导出成 App Store Connect 可接受尺寸,并纳入 release gate |
| 状态 | done-final-screenshot-export-demo-source-pending |

## 背景

Batch 4 已经把截图候选集变成机器可验证的 manifest 合同,并证明真实账号截图会被 App Store-ready gate 拒绝。仍缺一段稳定的最终导出流程:当我们用 demo account 或脱敏数据完成截图后,需要把原始模拟器截图导出为 App Store Connect 接受的 6.9-inch portrait 尺寸,再统一过 release pack gate。

## 范围

- 新增 `scripts/prepare_app_store_screenshots.py`,读取已捕获截图集,拒绝 `privacy_status=private` 的源目录。
- 支持导出为 `1260x2736`、`1290x2796` 或 `1320x2868`,默认 `1290x2796`。
- 输出目录写入新的 `manifest.json`,标记 `privacy_status=demo|sanitized`、`app_store_ready=true` 和 `target_size`。
- 导出完成后调用现有截图 checker 自检,失败则返回非 0。
- `scripts/check_app_store_release_pack.py` 将 Batch 5 plan 和 prepare 脚本列为必备提交资产。
- 更新截图 runbook 与提交包,让操作者先采集 demo/sanitized 原图,再 prepare,最后用 `APP_STORE_SCREENSHOT_DIR` 过完整 gate。

## 非目标

- 不把当前 private QA 截图转成 App Store-ready。
- 不伪造 demo account 截图已经完成。
- 不自动上传 App Store Connect。
- 不改变 Mobile UI 或业务行为。

## 验收

- TDD RED: 新增 prepare 脚本测试先因脚本缺失失败。
- TDD GREEN: prepare 脚本能把 demo 源截图导出为 `1290x2796`,并通过 `check_app_store_screenshots.py --app-store-ready`。
- private 源目录 prepare 必须失败,错误包含 `source privacy_status must be demo or sanitized`。
- 非 accepted target size 必须失败。
- release pack checker 继续通过,并把 prepare 脚本和 Batch 5 plan 纳入必备文件。

## 结果

- 已实现 `scripts/prepare_app_store_screenshots.py`。
- 已补测试覆盖 demo 导出、private 拒绝、非法尺寸拒绝。
- 当前本地 private QA 截图仍按预期不能 prepare,避免真实账号截图被误提交。
- 最终 App Store 截图仍需重新用 demo account 或脱敏数据采集后执行 prepare。

## 测试

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py backend/tests/test_app_store_screenshot_checker.py -q --no-cov`
- `bash -n scripts/mobile-sim-screenshots.sh`
- `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_app_store_screenshots.py scripts/prepare_app_store_screenshots.py`
- `python3 scripts/check_app_store_release_pack.py`
- `python3 scripts/prepare_app_store_screenshots.py design/screenshots/app-store/batch4-private-20260628 /tmp/reva-appstore-private-ready` (expected FAIL)
- `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
- `backend/venv/bin/python scripts/check_doc_drift.py`
- `git diff --check`
