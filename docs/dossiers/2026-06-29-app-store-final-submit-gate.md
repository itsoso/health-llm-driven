# Dossier: App Store Final Submit Gate

| 字段 | 值 |
|---|---|
| slug | `app-store-final-submit-gate` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate-final-submit-preflight-passed |
| 负责 | Codex |
| 反馈环 | local tests / final-submit gate |

## S0 · 用户需求(逐字)

> 按照计划直接开干

- 谁用 / 解决什么 / 现在怎么绕过:发布负责人需要知道普通 release pack 与最终 App Store submission gate 的差异;现在普通 release pack 能通过,但最终提交所需的人审材料仍可能被漏跑。
- 锚点用户相关性:首批用户下周可用版需要可提交的 App Store 包,但不能把缺 demo account、缺截图、缺凭证的状态误报成 ready。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `scripts/check_app_store_release_pack.py`:普通发布材料一致性检查。
  - `scripts/check_ios_app_store_submission.py --require-asc-credentials`:ASC credentials 检查。
  - `scripts/check_app_store_screenshots.py --app-store-ready`:最终截图检查。
  - `docs/release/app-store/review-notes.zh-CN.md`:仍保留 demo account/password 占位符。
- 缺什么:
  - 一个“一键最终提交前闸”同时要求 screenshot、demo credentials 和 ASC credentials。
- 硬约束 / 平台·安全边界:
  - 普通回归检查不能要求人工密钥。
  - final-submit 必须 fail-loud,不能因为人审材料缺失仍返回 0。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`ConsentGrant`, `ProvenanceRecord`
- core_loop_step:发布与隐私信任入口。
- target_surface / safety_level / autonomy_tier:Release tooling / privacy_sensitive / none。
- spec_required(§8.1):否,不新增产品行为。
- smallest_end_to_end_slice:`check_app_store_release_pack.py --final-submit` 在缺人审材料时失败并列出阻塞项。
- stale_surface_to_remove:无。
- 裁决:PASS。

## S2 · PRD

- 链接:沿用 `docs/dossiers/2026-06-28-app-store-mvp-release.md`。
- 边界(不做):不生成凭证、不上传、不替代人审。
- 验收 Gate:普通 release pack 仍过;final-submit 缺材料时失败。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-app-store-final-submit-gate-plan.md`
- 分阶段 + 反馈环路由:local tests -> release pack -> final-submit expected fail -> dossier 回写。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 硬阻断(已焊进规划):final-submit 必须显式要求 screenshots / demo credentials / ASC credentials。
- 待拍板分叉:无。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 RED: final-submit 被脚本忽略并错误通过。
- [x] T2 GREEN:实现 `--final-submit`、`--screenshot-dir` 和全部阻塞项。
- [x] T3 文档补充最终提交命令。
- [x] T4 验证、回写 App Store dossier、提交。

## S5 · 实现

- 修改 `scripts/check_app_store_release_pack.py`、`backend/tests/test_app_store_release_pack.py`、`docs/release/app-store/submission-pack.md`。

## G3 · 测试闸

- RED: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py::test_app_store_release_pack_final_submit_fails_loud_without_human_materials -q --no-cov`
  - 初始失败:脚本忽略 `--final-submit` 并错误返回 0。
- PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py::test_app_store_release_pack_final_submit_fails_loud_without_human_materials -q --no-cov`
  - 1 passed。
- PASS: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py backend/tests/test_ios_app_store_submission_preflight.py -q --no-cov`
  - 5 passed。
- PASS: `python3 scripts/check_app_store_release_pack.py`
  - 普通 release pack 通过。
- EXPECTED FAIL: `python3 scripts/check_app_store_release_pack.py --final-submit`
  - 返回 1,列出 demo account/password 占位符、缺 ASC credentials、缺 screenshot dir 三个阻塞。
- 2026-06-30 更新:
  - PASS: `APP_STORE_SCREENSHOT_DIR=design/screenshots/app-store/batch5-ready-20260630 python3 scripts/check_app_store_release_pack.py`。
  - EXPECTED FAIL: `python3 scripts/check_app_store_release_pack.py --final-submit --screenshot-dir design/screenshots/app-store/batch5-ready-20260630`
    - 截图闸已通过;仍因 demo account/password 占位符和缺 ASC credentials 返回 1。
- 2026-07-03 更新:
  - PASS: `set -a; source .env; set +a; python3 scripts/check_app_store_release_pack.py --final-submit --screenshot-dir design/screenshots/app-store/batch5-ready-20260630`。
    - 发布机 `.env` 提供 Review demo credentials、审核联系手机号和 ASC credentials;凭证不写入 git。
- PASS: `python3 -m py_compile scripts/check_app_store_release_pack.py scripts/check_ios_app_store_submission.py`

## G4 · 安全闸

- 触发?:未改健康数据读写、认证接口或医疗建议;只改 release gate。
- 裁决:GO。

## S6 · 部署

- 本批不部署。

## G5 · 部署健康闸

- 本地 release gate PASS。
- 加载发布机 `.env` 后 final-submit preflight PASS。

## S7 · 上线验证

- 本地验证:普通 release pack 和 final-submit gate 已能区分日常回归与最终提交。

## G6 · 验证闸(人在环)

- PASS:发布机已具备 demo account / password、审核联系手机号、App Store Connect credentials 和 App Store-ready screenshot directory。
- pending:App Store Connect 页面人工提交、build processing 和审核状态。

## S8 · 沉淀

- App Store MVP release dossier 已记录 Batch 9 final-submit gate 与 2026-06-30 ready 截图候选。
- 状态 -> **shipped-local-gate-final-submit-preflight-passed**。
