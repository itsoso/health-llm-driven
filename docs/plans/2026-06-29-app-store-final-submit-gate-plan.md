# App Store Final Submit Gate Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-29 |
| Dossier | `docs/dossiers/2026-06-29-app-store-final-submit-gate.md` |
| 目标 | 把最终 App Store 提交前的人审阻塞项变成 fail-loud 机器闸 |
| 状态 | done-local-final-gate-human-materials-pending |

## 背景

Batch 2-8 已准备普通 release pack、截图检查、sanitized candidate、iOS submission preflight 和阿衡品牌一致性闸。普通 release pack 必须能在没有人工凭证的机器上通过,用于日常回归;但真正提交 App Store 前不能只跑普通闸,否则会遗漏 demo account、ASC credentials 和 ready 截图。

## 范围

- `scripts/check_app_store_release_pack.py` 增加 `--final-submit`。
- final-submit 模式要求:
  - App Store Connect API credentials 可用。
  - Review Notes 中 demo account / password 不再是占位符。
  - 传入 `--screenshot-dir` 或 `APP_STORE_SCREENSHOT_DIR`,且截图集通过 `--app-store-ready`。
- 普通模式保持可在无人工凭证时通过,但继续要求 Review Notes 保留显式占位符。
- 文档补充最终提交命令。

## 非目标

- 不生成 demo account。
- 不获取或写入 ASC credentials。
- 不自动上传 App Store Connect。
- 不把 sanitized candidate 自动视作人审通过。

## 验收

- TDD RED: `--final-submit` 起初被脚本忽略并错误通过。
- TDD GREEN: 缺截图、缺 demo account、缺 ASC credentials 时 `--final-submit` 返回失败并列出全部阻塞。
- 普通 `python3 scripts/check_app_store_release_pack.py` 继续通过。
- `backend/tests/test_app_store_release_pack.py` 覆盖最终提交失败闸。

## 结果

- 已实现 `--final-submit` 和 `--screenshot-dir`。
- 已把 final-submit 命令写入 App Store submission pack。
- 2026-06-30 已生成当前 UI 的 App Store-ready sanitized 截图集:`design/screenshots/app-store/batch5-ready-20260630`。
- 当前 final-submit 预期失败,因为仍缺用户提供的 demo credentials 和 ASC credentials；截图闸已通过。
