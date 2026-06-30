# Dossier: App Store Release Narrative Gate

| 字段 | 值 |
|---|---|
| slug | `app-store-release-narrative-gate` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / release-pack gate |

## S0 · 用户需求(逐字)

> 继续

本切片承接本周计划的“继续清理 App Store 高可见截图/审核叙事与当前 UI 的差异”。目标不是新增产品能力,而是让 App Store 高可见文案与当前 `阿衡` UI、底部导航和“健康参谋”定位一致。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `scripts/check_app_store_release_pack.py`:提交包一致性检查。
  - `docs/release/app-store/submission-pack.md`:App Store metadata 真源。
  - `docs/release/app-store/review-notes.zh-CN.md`:审核员测试路径真源。
  - `docs/release/app-store/screenshot-runbook.md`:截图叙事和人工 QA checklist。
- 缺口:
  - 现有 release pack 已锁定 App name、隐私、截图 ready gate 和 final-submit gate,但没有校验高可见文案是否回退到旧品牌/旧定位。
  - submission keywords 仍包含 `健康助理`,与已确定的一句话主张“你的健康参谋”不一致。
- 硬边界:
  - 不改 App Store Connect 上传流程、不生成 demo credentials、不触发 build。
  - `HealthPilot` 作为内部代号仍可在 internal-only 行出现,本批只拦截用户可见旧叙事。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`AssistantPersona`, `ProvenanceRecord`
- core_loop_step:发布材料 -> 用户理解核心动线 -> App Store 审核。
- target_surface / safety_level / autonomy_tier:Release docs/tooling / low(copy consistency) / none。
- spec_required(§8.1):否,不新增用户行为或写路径。
- smallest_end_to_end_slice:release pack 对 stale public positioning fail-loud。
- stale_surface_to_remove:App Store metadata 中 `健康助理` 等旧定位词。
- 裁决:PASS。

## S2 · PRD

- 链接:沿用 `docs/dossiers/2026-06-28-app-store-mvp-release.md` 与本周计划。
- 边界(不做):不改变产品能力、不改变技术命名、不提交 App Store。
- 验收 Gate:release pack 能拒绝旧品牌、旧 tab、旧定位。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-app-store-release-narrative-gate-plan.md`
- 分阶段 + 反馈环路由:TDD -> release pack -> docs 回写。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - 不能把工程历史名一刀切禁用,否则会误伤 internal-only 说明。
  - 只校验 release docs,不碰截图二进制或发布凭证。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 RED:新增测试,期望 release narrative helper 拒绝旧词和旧 tab。
- [x] T2 GREEN:实现 `validate_release_narrative` 并接入 release pack main。
- [x] T3 收敛 App Store keywords。
- [x] T4 回写 plan / dossier / weekly plan。

## S5 · 实现

- `scripts/check_app_store_release_pack.py`:新增 narrative gate。
- `backend/tests/test_app_store_release_pack.py`:新增 stale public positioning 回归测试。
- `docs/release/app-store/submission-pack.md`:keywords 从 `健康助理` 收敛为 `阿衡` / `健康参谋`。

## G3 · 测试闸

- RED: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py -q --no-cov`
  - 初始失败:`validate_release_narrative` 不存在。
- PASS:同一命令。
  - 4 passed。

## G4 · 安全闸

- 触发?:否。仅发布文案和 release tooling,不改健康建议、写路径、认证、隐私数据处理或医疗边界。
- 裁决:GO。

## S6 · 部署

- 本批不部署。

## G5 · 部署健康闸

- 本地 release gate 通过。无线上部署。

## S7 · 上线验证

- 本地验证:release pack 可在日常回归中阻断旧品牌/旧定位回流到 App Store 材料。

## G6 · 验证闸(人在环)

- App Store 最终提交仍需用户提供 demo credentials、ASC credentials 和 App Store-ready screenshots。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续:继续 Daily Artifact 主屏视觉走查、Chat card 成功反馈和最终截图/审核材料。
