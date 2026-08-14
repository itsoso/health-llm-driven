# Dossier: 发布流水线全链路提速

| 字段 | 值 |
|---|---|
| slug | `release-pipeline-acceleration` |
| 创建日期 | 2026-08-11 |
| 当前阶段 | G4 bootstrap trust BLOCK |
| 状态 | blocked |
| 负责 | Codex |
| 反馈环 | 本地脚本测试 / CI / Simulator / offline evidence / 公开未认证 HTTPS |

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
- 边界：不做跨发布 OTA 缓存；不跳数据库/迁移/schema/健康/回滚闸；Simulator 不替代
  第三方与物理设备能力。当前仓库 harness 只可跑 iOS Simulator，物理 iOS 验收冻结。
- 未决问题：无。

### 2026-08-12 scope correction

实现中发现原设计只把 `apps/mac/**` 分类为“人工 Mac build”，却没有给正式 Mac 下载
建立签名、公证、不可变制品、原子切换、恢复、回滚与公共路由证据。这不是可留给文档
备注的小缺口：当前用户要求覆盖完整发布提效，而一个未受控的生产 surface 会绕过统一
发布锁与 G5/G6。因此流程退回 S2/S3/G2，补入 Developer ID DMG 正式发布（明确不含
Mac App Store/TestFlight）、一次性 nginx route bootstrap 和跨 surface 远端 lease。
更新后的设计与任务见原 design/plan 的 Task 9–10。

### 2026-08-12 automatic-release entrypoint correction

独立安全评审进一步证明：问题不只在 ASC cohort 或 Mac recovery，而在整个 same-UID
writable repo 的 bootstrap trust。以下攻击面均已真实复现：

- `refs/replace` 保持表面 HEAD SHA、改变解析 tree；
- shared `.git/info/attributes` + local clean/smudge filter 替换执行文件，同时 status clean、
  HEAD/tree 看似 canonical；
- `.git/info/exclude` 隐藏 untracked import shadow，在 `release.py` 标准库 import 前执行；
- `BASH_ENV`、`PYTHONPATH`/`sitecustomize` 在 repo 内 shell/Python guard 之前执行。

后续 Bash hostile-caller 复核又证明：caller 可在 `BASH_ENV` 中预定义 `exit`/`builtin`
function，故顶部 rc78 只能作为 ordinary-invocation negative marker。`deploy.sh` 与
`_run-mobile-tf.sh` 的历史 writer 必须处于 literal-false、语法级不可达 tombstone；
runtime/operator 禁止 source/extract/eval。隔离测试可抽取 marker fixture 做无 writer/网络的
协议回归，但不构成 release proof。`release-dmg.sh` 整个入口（含原 preflight/proof）冻结，read-only checker
必须另立不含 writer code 的文件。该语法级 tombstone 仍不是 production trust root；外部
root-owned `env -i` launcher 仍是解冻前置。

因此 backend/frontend 也不再例外。server backend/frontend/env/restart/push/evidence/reset/
coordinator、所有 Mobile OTA/native/EAS/ASC、Mac route/publish/recovery 与 legacy
raw SSH/direct upload/server-build **release** 旁路全部在 mutation 前 exit 78。manual release
Gate 仅表示 STOP/BLOCK，不能转成 release helper、vendor CLI 或人工 SSH 发布。

EAS channel→branch mapping 可能漂移或共用，不能证明 preview/development 不触达 production；
因此所有 OTA/rollback channel writer 也冻结。进一步核查确认 `release.py`/`release.sh`
plan/validate 会进入 root SSH 与带 `EXPO_TOKEN` 的 EAS channel observation，故它们与 publish
一并在 network/credential 前 earliest exit 78；`release_production_state` 的 `server`、
`server-under-lock`、`mobile` 联网模式和 deploy status/logs/inspect 也冻结。仅保留 offline
evidence parser、公开未认证 HTTPS、本地 Metro/iOS Simulator/test，以及
`mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 对现成 IPA 生成离线检视
metadata/report；不生成 install manifest、安装二维码或可安装承诺。bare
`--no-upload`、自动 archive/export/signing/provisioning/install、`mobile-fast-device.sh`、
`mobile-local-device.sh` 与
`-allowProvisioningUpdates` 均冻结；Mac 仅 compile/test，不做签名/公证 package。
`mobile/package.json` 的 `npm run ios` 固定走 Simulator wrapper；不得向 npm/Expo 追加
`--device`。wrapper 只接受 `simctl` 可用清单中的 Simulator 名称或 UDID，并在调用 Xcode
前解析、锁定 exact Simulator UDID；物理 iOS repo CLI、签名、安装和验收均冻结。
`run_ios_real_device_acceptance.sh` 的历史名称不授予真机权限，当前也只接受 exact
available Simulator UDID；未来物理验收必须由解冻后的仓库外获权人工证据流程完成。
Android 尚不是 shipped/audited Mobile surface；`npm run android`/`expo run:android` 会自动
native generation、debug signing 与 ADB install，且缺少 exact-iOS-Simulator 目标守门，
所以 repo entry 也 earliest exit 78，无 native CLI 例外。
`check_app_store_release_pack.py --final-submit` 会登录 production reviewer 并取得可写 bearer
token，亦冻结；只保留 non-final-submit 静态 pack 与纯静态 iOS config check。它们不能形成
G5/G6 或 App Store submission 授权。
重新启用必须另立 dossier，落地 repo-external、
root-owned launcher（fixed interpreter、`env -i` allowlist、canonical archive/tree 的仓库外
materialization），补齐 authority/recovery，并重新通过独立 G4。

范围收窄裁决：server-local DB migration/setup/admin utilities 不是自动 release entrypoint，
不宣称冻结。它们只可在生产主机的独立、显式、获权 manual-admin 事件中运行并留审计；
任何自动 release 入口不得调用，当前 blocked release 也不得伪装成 admin event。

## G2 · 可行性与安全压测

- 采用保守分类器，未知路径 BLOCK；native 命中抑制 OTA。
- 验证凭证绑定 tree、命令、依赖、工具链和日志；CI 仍绑定当前 commit。
- OTA 缓存仅在单次事务内复用，避免远程 EAS 环境漂移。
- 服务器 proof 是优化提示；缺失、损坏或漂移时执行原全量步骤。
- 服务器复用以 off/shadow/on 分阶段开启；数据库、迁移、schema、lease、runtime、health、rollback 永不跳过。
- Mac 正式发布要求 clean exact `origin/main`、显式单调 version/build、Developer ID
  签名、公证、挂载复验、immutable-first/current-second；远端结果不明确时保留 exact
  transaction 供恢复，不能从较新的 main 猜测或重建恢复语义。
- backend/frontend/Mac route/Mac release 共用严格远端 lease；部分创建、未知条目、错误
  metadata、清理失败或 terminal proof 不完整一律 BLOCK。正式 Mac 状态存在后禁止移除
  nginx 下载路由；G5/G6 必须独立验证 public HTTPS bytes。
- **裁决：PASS。用户已确认进入全部实施。**

## S4 · 研发任务

- 恢复验证 Run Ledger：`docs/_generated/harness-runs/18c933b8473b.jsonl`（本地生成物，不提交）。

- [x] T1 变更分类与统一发布入口。
- [x] T2 永久干净 release worktree、跨 worktree 发布锁与 schema-v2 共享事务状态。
- [x] T3 并行验证与 tree-hash 诊断凭证工具；同 UID 本地凭证永远不能授权跳过，
  planner/publish 均完整运行 blocking validation，CI 始终对当前 commit 重跑。
- [x] T4 OTA 单次导出复用、结构化复证、私有审计与回滚修正。
- [x] T5 Python/frontend 服务端 step proof（生产默认 shadow）。
- [x] T6 System KB 增量 import/reindex 与 shadow whole-import proof；外部 digest marker
  不再绕过 DB mutation phase。
- [x] T7 GPS/Settings 模拟器自动冒烟代码与安全分类；真实 Simulator
  XCTest 尚未执行，仍属于 G3 待完成证据。
- [x] T8a 统一 Git-common-dir kernel lock、验证/每次 mutation 前后的生产复探、
  backend finalized marker + systemd PID 运行态证明、frontend PM2/BUILD_ID 原子回执。
- [x] T8b 所有 OTA/rollback channel 与 production native 自动 writer 安全冻结；EAS
  mapping 无可信 preview 隔离，transaction 协议只保留 mock/test，最终 frozen snapshot
  纳入完整 G3。
- [x] T8c Mac Developer ID/immutable/current/stable/恢复/回滚/nginx 协议代码保留，但所有
  自动 Mac production release entrypoint 及 direct Python/nginx production CLI 已在
  production path/lock/network 前冻结；不把协议测试记为正式 Mac 发布。唯一代码级例外是
  strict non-root + explicit test mode + 固定 non-production roots（macOS `/private/tmp` 或
  `/private/var/folders`；其他平台 `/tmp`，忽略 caller `TMPDIR`）的 protocol test，以及
  同样受此隔离条件约束、只生成本地候选元数据的 `create-candidate`；二者均无 production
  authority。
- [x] T8d 更正：backend/frontend automatic release entrypoint 也冻结；现有严格协议不能
  解决 same-UID bootstrap。
- [x] T9 CI 接线、完整文档、frozen-snapshot negative verification 与本地完整验证；
  不做 production 发布。远端 CI 与 source integration 仍须绑定集成后的 exact commit，
  不能由本地绿色替代。
- 分支：`codex/release-pipeline-acceleration`；已在 2026-08-12 重放到当时的
  `origin/main`。2026-08-14 source integration 前再次执行 `git fetch origin main`，确认
  `origin/main` 为 `c9b6f0fb4`、当前分支 ahead 20 / behind 0，且远端主干是当前分支祖先，
  因而无需 rebase；受影响 Gate 已在下方最新冻结快照中重新验证。
- 2026-08-13 最终 scope 审计识别出 13 个 Mac snapshot PNG 为宿主渲染/测试污染，
  不属于本 feature 源码范围；它们保留在工作树但必须排除在任何 source integration 之外。
  source integration 前的 fresh-fetch ancestry 核对为相对 `origin/main` ahead 20 /
  behind 0；任何后续集成仍须重新 fetch，不能把本次引用当成永久主干当前性证明。

## G3 · 测试闸

- 基线：`scripts/test_mobile_fast_feedback_scripts.py` + `scripts/test_deploy_script.py`，144 passed。
- 2026-08-12 focused release suite：
  `python3 -m pytest -q scripts/test_release_pipeline.py scripts/test_run_all_tests.py scripts/test_validation_credential.py scripts/test_mobile_ota.py scripts/test_ios_acceptance_harness.py scripts/test_release_ci_contract.py`
  → **92 passed in 123.79s**。
- 以上只证明 T1–T4/T7 的脚本/合同；尚未包含 T5/T6 的
  `scripts/test_release_step_proof.py`，也未执行真实 Simulator XCTest、`validate.py
  --full` 或生产 shadow proof。
- 当时的阶段性裁决：**PENDING**；不得用 focused green 代替最终 G3。当前裁决见本节末尾。

补充恢复后证据（2026-08-12）：

- System KB 增量/导入/锁/协议聚焦回归：**56 passed, 2 skipped**；skip 仅为当前
  非 PostgreSQL 环境不具备的真实 advisory-lock 并发用例。
- 并行协调器、验证凭证、iOS harness 与 CI 接线：**59 passed**；随后协调器自身
  9 项独立复跑通过。
- OTA 合同回归：**58 passed**；部署/proof/System KB 合同回归：**170 passed**；
  release transaction 完整回归：**139 passed**。三组漂移均已按 TDD 修复并独立提交。
- 最终加固回归：OTA 完整文件 **58 passed**；release transaction 完整文件
  **147 passed**；validation credential **26 passed**；exact dependency + deploy
  **138 passed**；rollback **38 passed**。新增覆盖跨进程 OTA transaction 接管、
  完整分页、无证据 reconciliation、receipt 路径别名、artifact evidence 语义、
  production ambient override 清除、validation proof fd 安全边界和 exact venv inventory。
- 该阶段的 `bash -n`（deploy/release/OTA/协调器）、Python 编译、Ruby harness 生成器语法与
  `git diff --check` 已通过；当时完整 CI release invariant、`validate.py --full` 和真实
  Simulator XCTest 尚未执行，因此阶段性 G3 保持 PENDING。后续本地完整证据与当前 BLOCK
  裁决见本节末尾。
- 历史只读 runtime observation：backend `88fe449d6d903135dac2135beb46f2736100afc9`
  已绑定 finalized transaction marker 与 backend/Celery PID identity；当前历史
  frontend 无 runtime receipt，探针按 `None` 明确视为未知；冻结期不得用 full deploy
  补建，也不能把 checkout SHA 冒充 frontend runtime。
- 阶段漂移与独立 surface baseline 新增回归通过；release transaction 当前完整文件
  **172 passed in 358.82s**。原生 cohort 闸合入后必须重新跑最终全量，故 G3 仍为 PENDING。
- 原生 binary cohort 与 production state 聚焦回归曾分别通过；Mac nginx 聚焦回归
  **23 passed**，包含“存在任一正式 receipt/journal/current 时 route rollback 在读取或
  修改 nginx 前拒绝”；production state 聚焦回归 **35 passed**，包含固定 HTTPS origin
  的 current/immutable/stable marker、投影、size 与流式 hash 证明。这些都是 mutable
  snapshot 的局部证据，Mac publisher/统一 lease 尚在加固，冻结后必须全部重跑。

2026-08-13 frozen-snapshot 收口证据：

- exact CI `release-invariants` 合跑：**1285 passed in 2217.73s**；独立 release planner
  **211 passed**、production state **74 passed**、Mac receipt **166 passed**、Mac nginx
  **32 passed**。Mac Swift `swift build` 通过，Core tests **449 tests / 0 failures / 1 skipped**。
- iOS acceptance harness 的离线合同 **33 passed**，但唯一可用 Simulator
  `D62288F8-33F6-4F79-9200-085ED814A274`（`Reva UI QA`）处于 Shutdown，且无法取得
  app-installed / pre-authenticated 证据；因此未启动设备、未注入 GPS、未执行 XCTest，
  更未连接、安装或签名真机包。真实 Simulator acceptance 仍为环境 **BLOCK**。
- shell/Python/Ruby 语法、system-map/doc drift、Dossier 一致性与 scoped
  `git diff --check` 均通过；这些证据不替代完整验证或 Simulator acceptance。
- 首次 `scripts/validate.py --full` 在
  `backend/tests/test_agenda_bid_multidose.py` 确定性挂起，人工安全中断后 exit 130；该次
  **不是 PASS**。根因是全量入口强制 in-memory SQLite，而 Twin Phase B 忽略调用方
  Session、通过 `SingletonThreadPool` 在四个 worker 中创建/回收全局连接，形成 SQLite
  mutex 与 CPython GIL 锁反转。
- 修复保持 PostgreSQL 最多四 worker 并行；SQLite 或 Connection bind 改为串行复用调用方
  Session，PostgreSQL worker 仅继承调用方已存在的 `db.info['app_user_id']`，缺失时保持
  fail-closed。新增 bind/RLS 合同 **4 passed**，完整 Twin builder **73 passed**，Twin/agenda
  聚焦组合 **86 passed**，更宽 release+runner+Twin/agenda 组合 **306 passed in 537.09s**；
  Python 编译与 scoped diff check 通过，独立复核裁决 GO。
- 本地完整验证已改为严格复用 CI 的 **43 个** backend shard：CI workflow 是 pytest
  公共参数与 shard 清单的唯一真源；本地默认四并发，每 shard 600 秒 deadline，只有真实
  timeout 可重试一次。协调器强制 canonical test env、精确覆盖全部 `test_*.py`、只允许
  固定 Twin 互补 selector，并以独占私有目录、`O_NOFOLLOW` 与原 open FD 保护日志写入和
  failure tail。新增缺失的 `web-session-security` CI shard；环境注入、selector 漏测、父/叶
  symlink 与日志回读竞态负例均已转绿。协调器/外层日志/CI 合同组合最终
  **79 passed**，独立复核裁决 scoped GO。
- 2026-08-13/14 首次最新矩阵全量自然结束为 **exit 1 / 480.8s**；唯一失败是矩阵自己的
  direct-entry 测试继承外层 `REVA_BACKEND_SHARD_LOG_DIR`，内层按独占目录安全契约拒绝复用。
  夹具改为独立临时日志目录后，纽约宿主时区又暴露 `test_log_taken` 误用 server-local
  `date.today()`；生产语义实际为 `get_user_today(db, user_id)`。两处都按真实契约修正，
  纽约时区 k–m shard **981 passed / 4 skipped**，独立时区复核 GO。
- 最新冻结快照执行
  `backend/venv/bin/python scripts/validate.py --full` 自然 **exit 0**：system-map、
  Dossier consistency、git diff、frontend、mobile 与全部 backend shard 通过；墙钟
  **1056.5s**，无 deadlock、无 timeout retry。私有证据目录：
  `/Users/liqiuhua/work/personal/health-llm-driven/.git/reva-release-state/logs/validate-1786681114784398000-37629`。
  `ruff` 仍按既有契约 report-only，不是 blocking Gate。

当前 G3 裁决：**BLOCK**。完整本地验证已经绿色；剩余阻断项是一个由操作者手动启动、
已安装且已登录的 Simulator 上的真实 acceptance。不得通过真机、签名、归档、生产账号或
仅离线 harness 旁路。远端 CI 仍须在 source integration 后绑定 exact commit 运行，不能把
当前本地证据写成主干 CI 结果。

## G4 · 安全闸

- 触发：生产发布与回滚控制面，需独立安全评审。
- 独立评审已完成多轮 mutable review，发现并推动修复 OTA 跨调用身份断链、分页遗漏、
  receipt/artifact 伪造边界、release state 覆盖、validation credential TOCTOU 与
  production ambient override。Mac/统一远端 lease 扩展评审又发现 exact-A recovery、
  acquire→bind→stage crash window、mutation-before-delegation、active-owner 防窃取、
  rollback immutable proof、version/build high-water、exact allowlist/root metadata、
  tombstone unlock 与 cleanup failure 可见性等阻断项。最终 bootstrap review 又证明 Git
  replace/info attributes+filter/untracked import shadow/BASH_ENV/PYTHONPATH/sitecustomize 可在
  repo 内 source guard 之前改变执行语义。当前架构无法在同一 writable repo 内修复，故
  当前裁决：**BLOCK**。解冻工作必须转入新 dossier 与独立 G4。

2026-08-13 最终独立复核对当前仓库内 frozen snapshot 的 direct/import writer、固定解释器、
hostile `PATH`、non-root test authority 与固定临时根边界给出 **local scoped G4 GO**；这只
证明冻结实现没有已知仓库内回退。same-UID writable repo 外的启动/sitecustomize/checkout
trust root 仍无可信 authority，故整体 G4 继续 **BLOCK**，不得据此解冻任何 production writer。

## S6/G5/S7/G6/S8

- S6：所有 repo 自动 remote/vendor release entrypoints 与 release bypasses frozen；ordinary
  invocation 预期 exit 78，writer-bearing shell legacy 语法级不可达。该 rc 不是 hostile
  source trust proof；未部署。manual-admin utilities 未被调用，也不构成部署。
- `deploy.sh --inspect-release-lock` 也在读取 lock/env 前冻结并预期 exit 78。仅做最终输出
  脱敏仍不足：`SHELLOPTS=xtrace`/`BASH_ENV` 可在 repo guard 前捕获变量。锁状态须等待
  repo-external root-owned inspector；raw SSH/helper 不是兜底。
- G5：**BLOCK**。没有获准的 production mutation；repo production observation 也冻结，
  offline evidence/公开未认证 HTTPS 不是部署健康证据。
- S7：未准入。local/offline/公开观察不能写成生产上线验证。
- G6：**BLOCK**。没有 public/anchor 上线闭环。
- App Store submission：**BLOCK**。不得 reset review account、选择 build、改 ASC 或提交。
- S8：仅沉淀本轮证据；Dossier 保持 `blocked`，不得标 `shipped`/`complete`。
