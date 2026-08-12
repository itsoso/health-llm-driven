# Dossier: 发布流水线全链路提速

| 字段 | 值 |
|---|---|
| slug | `release-pipeline-acceleration` |
| 创建日期 | 2026-08-11 |
| 当前阶段 | S5 实现/验证 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | 本地脚本测试 / CI / Simulator / shadow production proofs |

## S0 · 用户需求（逐字）

> 全部都优化

- 谁用 / 解决什么 / 现在怎么绕过：研发与发布操作者需要在不削弱安全 Gate 的前提下缩短验证、OTA 和部署时间；当前依靠人工选择发布路径、重复测试与全量部署。
- 锚点用户相关性：更快且更可靠地向真实 iOS 用户交付修复，减少因发布路径选择错误导致的等待与风险。

## S1 · Discovery

- `scripts/run-all-tests.sh` 串行执行，并存在运行中测试输出管道与 lint 放行缺口。
- `deploy.sh` 只接受 `main` 分支，不能直接使用永久 detached release worktree；新 frontend SHA 仍不能安全走 `-f`。
- `scripts/mobile-ota.sh` 在瞬时上传失败后重新运行完整 EAS export，且发布成功依赖文本解析。
- 上次设置发布的 backend/frontend/KB 输入树均未变化，自动规划本应选择 OTA-only。
- 服务器安全 Gate 很强，不得用简单 Git SHA 缓存跳过数据库、schema、runtime 或健康验证。
- 现有 XCTest 具备已登录启动与隐私入口验证，但缺 GPS 城市和 Settings 路由矩阵。

## G1 · 准入裁决

- first_class_objects：发布 artifact、验证证据、部署事务；属于研发运营对象，不新增用户健康对象。
- core_loop_step：实现 → 验证 → 安全部署 → 上线验证。
- target_surface / safety_level / autonomy_tier：研发工具链；高发布影响；生产 mutation 仍须显式 `publish`，默认 manual confirm。
- spec_required：是，涉及跨端发布职责和安全 Gate。
- smallest_end_to_end_slice：Mobile-only diff 自动得到 OTA-only 计划，并完成可复用验证与结构化 OTA 复证。
- stale_surface_to_remove：人工凭记忆选择 `deploy.sh`/OTA；串行且弱退出码的一键测试路径。
- **裁决：PASS。用户已确认“全部都优化”。**

## S2/S3 · Tech Spec 与规划

- 设计：`docs/plans/2026-08-11-release-pipeline-acceleration-design.md`
- 计划：`docs/plans/2026-08-11-release-pipeline-acceleration.md`
- 边界：不做跨发布 OTA 缓存；不跳数据库/迁移/schema/健康/回滚闸；模拟器不替代第三方与真机能力。
- 未决问题：无。

## G2 · 可行性与安全压测

- 采用保守分类器，未知路径 BLOCK；native 命中抑制 OTA。
- 验证凭证绑定 tree、命令、依赖、工具链和日志；CI 仍绑定当前 commit。
- OTA 缓存仅在单次事务内复用，避免远程 EAS 环境漂移。
- 服务器 proof 是优化提示；缺失、损坏或漂移时执行原全量步骤。
- 服务器复用以 off/shadow/on 分阶段开启；数据库、迁移、schema、lease、runtime、health、rollback 永不跳过。
- **裁决：PASS。用户已确认进入全部实施。**

## S4 · 研发任务

- [x] T1 变更分类与统一发布入口。
- [x] T2 永久干净 release worktree、跨 worktree 发布锁与 schema-v2 共享事务状态。
- [x] T3 并行验证与 tree-hash 凭证工具；planner 在本地可命中完整 tree/profile/
  lock/toolchain/log/TTL 证明，CI 始终对当前 commit 重跑。
- [x] T4 OTA 单次导出复用、结构化复证、私有审计与回滚修正。
- [x] T5 Python/frontend 服务端 step proof（生产默认 shadow）。
- [x] T6 System KB 增量 import/reindex 与 shadow whole-import proof；外部 digest marker
  不再绕过 DB mutation phase。
- [x] T7 GPS/Settings 模拟器自动冒烟代码与安全分类；真实 Simulator
  XCTest 尚未执行，仍属于 G3 待完成证据。
- [ ] T8 CI、文档、独立评审与发布验证。
- 分支：`codex/release-pipeline-acceleration`；已在 2026-08-12 重放到最新
  `origin/main`，提交前还会再次 fetch/rebase 并重跑受影响 Gate。

## G3 · 测试闸

- 基线：`scripts/test_mobile_fast_feedback_scripts.py` + `scripts/test_deploy_script.py`，144 passed。
- 2026-08-12 focused release suite：
  `python3 -m pytest -q scripts/test_release_pipeline.py scripts/test_run_all_tests.py scripts/test_validation_credential.py scripts/test_mobile_ota.py scripts/test_ios_acceptance_harness.py scripts/test_release_ci_contract.py`
  → **92 passed in 123.79s**。
- 以上只证明 T1–T4/T7 的脚本/合同；尚未包含 T5/T6 的
  `scripts/test_release_step_proof.py`，也未执行真实 Simulator XCTest、`validate.py
  --full` 或生产 shadow proof。
- 当前裁决：**PENDING**；不得用 focused green 代替最终 G3。

补充恢复后证据（2026-08-12）：

- System KB 增量/导入/锁/协议聚焦回归：**56 passed, 2 skipped**；skip 仅为当前
  非 PostgreSQL 环境不具备的真实 advisory-lock 并发用例。
- 并行协调器、验证凭证、iOS harness 与 CI 接线：**59 passed**；随后协调器自身
  9 项独立复跑通过。
- OTA 合同回归：**58 passed**；部署/proof/System KB 合同回归：**170 passed**；
  release transaction 完整回归：**139 passed**。三组漂移均已按 TDD 修复并独立提交。
- `bash -n`（deploy/release/OTA/协调器）、Python 编译、Ruby harness 生成器语法与
  `git diff --check` 已通过；完整 CI release invariant、`validate.py --full` 和真实
  Simulator XCTest 仍待执行，因此 G3 保持 PENDING。

## G4 · 安全闸

- 触发：生产发布与回滚控制面，需独立安全评审。
- 当前裁决：待实现后评审。

## S6/G5/S7/G6/S8

- 待实现、验证与发布后填写。
