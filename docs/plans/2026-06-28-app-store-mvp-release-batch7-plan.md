# App Store MVP Release Batch 7 Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-29 |
| Dossier | `docs/dossiers/2026-06-28-app-store-mvp-release.md` |
| 目标 | 从 private QA 截图生成 review-required sanitized 候选集 |
| 状态 | done-sanitized-candidate-tooling-human-review-pending |

## 背景

Batch 4–6 已经有截图 manifest gate、ready 尺寸导出和 iOS submission preflight。剩余阻塞是最终 App Store 截图需要 demo account 或脱敏数据。真实 demo account 仍需人工提供,但我们可以先把 private QA 截图变成“必须人工复核”的 sanitized candidate,避免 release 流程卡死在脚本缺口,也避免机器脱敏被误认为已可提交。

## 范围

- 新增 `scripts/sanitize_app_store_screenshots.py`,从 `privacy_status=private` 的 QA 截图集生成 `privacy_status=sanitized` 的候选集。
- 使用固定相对区域 blur 掩码处理容易泄露身份、聊天上下文、健康摘要、报告列表的区域。
- 输出 manifest 写入 `sanitization_review_required=true`、`sanitization_masks`、`sanitized_from`、`app_store_ready=false`。
- `scripts/prepare_app_store_screenshots.py` 在遇到 `sanitization_review_required=true` 时默认拒绝,只有显式 `--confirm-sanitized-reviewed` 才能继续导出 ready set。
- `scripts/check_app_store_release_pack.py` 把 sanitize 脚本和 Batch 7 plan 纳入必备发布资产。

## 非目标

- 不声称机器脱敏后的截图已经适合提交。
- 不替代 demo account。
- 不自动上传 App Store Connect。
- 不提交本地生成的截图素材。

## 验收

- TDD RED: sanitize 测试先因脚本缺失失败。
- TDD GREEN: private QA fixture 可生成 `sanitized`、`app_store_ready=false`、`sanitization_review_required=true` 的候选集。
- prepare 默认拒绝 review-required sanitized candidate。
- prepare 加 `--confirm-sanitized-reviewed` 后才能生成 App Store-ready set。
- sanitize 拒绝非 private 源目录。

## 结果

- 已实现 `scripts/sanitize_app_store_screenshots.py`。
- 已强化 `scripts/prepare_app_store_screenshots.py` 的人工复核闸。
- 已纳入 release pack gate。
- 当前可用流程:private QA 截图 -> sanitize candidate -> 人工视觉复核 -> prepare ready -> release pack with `APP_STORE_SCREENSHOT_DIR`。

## 测试

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py backend/tests/test_app_store_screenshot_checker.py -q --no-cov`
- `python3 scripts/sanitize_app_store_screenshots.py design/screenshots/app-store/batch4-private-20260628 /tmp/reva-appstore-sanitized --overwrite`
- `python3 scripts/prepare_app_store_screenshots.py /tmp/reva-appstore-sanitized /tmp/reva-appstore-ready --overwrite` (expected FAIL)
- `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_app_store_screenshots.py scripts/prepare_app_store_screenshots.py scripts/sanitize_app_store_screenshots.py`
- `python3 scripts/check_app_store_release_pack.py`
- `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
- `backend/venv/bin/python scripts/check_doc_drift.py`
- `git diff --check`
