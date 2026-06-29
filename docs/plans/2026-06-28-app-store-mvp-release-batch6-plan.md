# App Store MVP Release Batch 6 Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-29 |
| Dossier | `docs/dossiers/2026-06-28-app-store-mvp-release.md` |
| 目标 | 机器化 iOS production build / App Store Connect submit 配置预检 |
| 状态 | done-ios-submission-preflight-demo-source-pending |

## 背景

Batch 5 已经解决“截图候选集怎么变成 App Store-ready”的问题。仍然有一个高风险缺口:production iOS 包、watch extension、HealthKit entitlement、EAS submit、App Store Connect app id 和本机 ASC 凭证分散在多个脚本和配置里。如果这些配置在真正触发 EAS build / App Store Connect submit 时才发现不一致,反馈周期会很长。

## 范围

- 新增 `scripts/check_ios_app_store_submission.py`,只读校验 iOS App Store build/submit 配置,默认不联网、不上传。
- 校验 `mobile/app.json`、`mobile/eas.json`、`docs/release/app-store/privacy-nutrition-label.draft.json` 的 bundle id、ASC app id、EAS production profile、HealthKit/Push entitlement、usage strings、watch extension bundle id、updates URL 和 submit group。
- 支持 `--require-asc-credentials`,在真正准备上传前检查 `ASC_KEY_ID` / `APP_STORE_CONNECT_API_KEY`、`ASC_ISSUER_ID` / `APP_STORE_CONNECT_ISSUER_ID` 和 `.p8` 私钥。
- `scripts/check_app_store_release_pack.py` 自动调用该 preflight,并把 Batch 6 plan 与 preflight 脚本纳入必备发布资产。
- 更新 App Store submission pack,把 preflight 作为 production build / submit 前置命令。

## 非目标

- 不触发 EAS remote build。
- 不上传 App Store Connect。
- 不替代 App Store Connect 手工填写 metadata / privacy nutrition。
- 不解决 demo account / sanitized screenshots 的人工素材缺口。

## 验收

- TDD RED: 新增 preflight 测试先因脚本缺失失败。
- TDD GREEN: repo 当前 production iOS 配置通过 preflight。
- `--require-asc-credentials` 在清空 ASC 环境变量时必须失败,并明确提示缺少 App Store Connect credentials。
- release pack checker 必须自动执行 iOS submission preflight。

## 结果

- 已实现 `scripts/check_ios_app_store_submission.py`。
- 已纳入 `scripts/check_app_store_release_pack.py`。
- 当前 repo 配置通过不联网的 production iOS submission preflight。
- 真正上传前仍需 owner 提供/确认 App Store Connect API key、issuer id 和 `.p8` 私钥,再执行 `python3 scripts/check_ios_app_store_submission.py --require-asc-credentials`。

## 测试

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_ios_app_store_submission_preflight.py backend/tests/test_app_store_release_pack.py -q --no-cov`
- `python3 scripts/check_ios_app_store_submission.py`
- `env -u ASC_KEY_ID -u APP_STORE_CONNECT_API_KEY -u ASC_ISSUER_ID -u APP_STORE_CONNECT_ISSUER_ID -u ASC_PRIVATE_KEY_PATH -u ASC_PRIVATE_KEY_BASE64 python3 scripts/check_ios_app_store_submission.py --require-asc-credentials` (expected FAIL)
- `python3 scripts/check_app_store_release_pack.py`
- `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_ios_app_store_submission.py`
- `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
- `backend/venv/bin/python scripts/check_doc_drift.py`
- `git diff --check`
