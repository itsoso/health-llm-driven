# App Store Release Narrative Gate Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-29 |
| Dossier | `docs/dossiers/2026-06-29-app-store-release-narrative-gate.md` |
| 目标 | 防止 App Store 高可见文案回退到旧品牌、旧 tab 或旧定位 |
| 状态 | done-local-release-gate |

## 背景

本周已经把 Mobile 主屏、Chat、Shell、Rokid 相关高可见入口收敛到 `阿衡`。App Store submission pack 也锁定了 App 名和 final-submit 人审材料,但高可见审核文案仍需要机器闸防漂移:只检查 `CFBundleDisplayName` 不足以发现文案里写回 `Reva`、`复元`、`健康助理` 或旧的 tab 名。

## 范围

- `scripts/check_app_store_release_pack.py` 增加 release narrative 校验。
- 校验对象:
  - `docs/release/app-store/submission-pack.md`
  - `docs/release/app-store/review-notes.zh-CN.md`
  - `docs/release/app-store/screenshot-runbook.md`
- 硬闸:
  - 禁止用户可见旧词: `Reva`、`复元`、`健康助理`、`守护神`。
  - 必须包含当前底部导航叙事: `今日 / 阿衡 / 记录 / 我` 或等价中文顿号写法。
  - 必须包含当前定位词: `健康参谋`。

## 非目标

- 不删除工程/历史技术名,例如 Xcode target、URL scheme、bundle 历史名。
- 不改变截图生成、ASC credentials、demo account 或 final-submit 流程。
- 不自动上传或提交 App Store Connect。

## 验收

- TDD RED:测试期望 `validate_release_narrative` 能拒绝 stale public positioning,但 helper 不存在。
- TDD GREEN:`backend/tests/test_app_store_release_pack.py` 覆盖旧词和旧 tab 拒绝。
- 普通 `scripts/check_app_store_release_pack.py` 继续通过。

## 结果

- 已实现 narrative gate。
- `submission-pack.md` keywords 中的 `健康助理` 已收敛为 `阿衡` / `健康参谋`。
