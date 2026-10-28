# 小气候 Prompt 契约优化

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | 第二轮 Prompt 投影实施与 G3 验证 |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 准入

裁决：PASS。用户要求执行现有 Prompt 系统复盘中的改进。复用既有
`GoalSpec`、`OwnedReadScope`、Pi 与 Tool Gateway，不新增健康数据读取范围、
写入权限、自动执行能力、诊断或治疗建议。第一批只处理任务契约投影、查询工具
说明真源和“小气候”人格一致性。

## 实现范围

- `health_query` 的完整说明和任务级精简说明由同一份结构化维度注册表生成；
  完整说明与改造前逐字节一致。编辑标题或排版不再使查询投影静默失效。
- 已绑定的体重、HRV、体检、基因、用药等已知维度可以复用同一安全投影；未知维度
  或非 canonical schema 继续保留完整工具说明，参数 schema、授权工具集合和 Gateway
  校验不变。
- 本人只读范围统一渲染为一个任务契约，明确逐项完成、不得扩大用户/日期/维度、
  查询失败不可使用旧记录或历史回答替代。契约不包含 user_id、run_id 或健康原始值。
- system、工具决策、空答重试和反馈处理统一使用“小气候”人格；移除“唯一入口”措辞，
  明确不得主动扩大为用户未请求的健康分析。

## G3 增量证据

- 首次聚焦运行因本机未设置 SQLite 测试 URL 而尝试连接本地 PostgreSQL，连接拒绝；
  未计为通过。按仓库测试配置显式使用 `DATABASE_URL=sqlite:///:memory:` 后执行。
- Prompt、投影与快路由聚焦：80 passed。
- Prompt 架构、本人读取投影、预算、冻结质量契约、读取合成、血氧截图回归、读取完成、
  日历绑定：219 passed、2 skipped。两项 skip 为既有环境限定，不作为 PostgreSQL 证明。
- 合入最新主干后扩大运行 Prompt、快路由、本人读取契约、血氧截图和读取完成相关套件：
  796 passed。该结果使用 SQLite，只证明本次服务层行为，不替代 PostgreSQL 或完整 CI。
- 新注册表生成的完整 `health_query` description 与改造前均为 3133 字符且逐字节一致。
  当前任务级三工具投影相对完整三工具字符量：血氧减少 33.60%，体重减少 38.37%，
  体检减少 26.25%，睡眠加饮食减少 36.46%。这是静态请求体测量，不代表生产账单或延迟。
- `py_compile` 与 `git diff --check` 通过。完整 CI、真实模型 Gate、独立安全复核、部署和
  用户路径验收不能由上述局部证据替代。
- 合入后 `system-map-check.sh`、277 份 dossier 一致性检查、tracked-file 高置信秘密扫描
  均通过。
- 独立安全复核在原候选 `58118ed12f46b18f4b63f408336af41d5f11cc70` 上执行：
  242 passed，裁决 GO；合入最新 `main` 后仅基线增加不相交的前端品牌导航提交，最终
  候选又按精确 SHA 复核，服务与测试 blob 无漂移，242 passed，裁决仍为 GO。
- `harness_llm_regression_gate.py --include-live-llm --json` 两次均显示离线 invariant
  12/12、core 50/50、trajectory 12/12、golden 9/9 通过；5 个真实模型编排用例全部因
  `recipient_not_disclosed` 阻断。第二次仅加载根目录既有环境配置，确认其中没有模型
  提供方配置；未读取线上环境或输出任何凭据，不继续盲目重试。
- 隔离环境的全量 backend pytest 收集到 36062 个用例；该运行范围超出本变更的本地
  快速验证预算，在约 2% 处人工中止，不计为通过。最终发布仍要求精确 SHA 的完整 CI。
- 首次推送候选的完整 CI `40692003884` 在阻断性 Ruff 检查发现多模型读取限制分支缺少
  `read_scope_notices` 局部导入（F821）；该候选不得部署。最小修复复用同模块既有函数，
  122 项多模型与 Prompt 回归通过；修复候选须重新绑定豁免、独立复核并完整重跑 CI。

## 安全边界

- Prompt 投影只发生在授权工具过滤之后；不增加工具，不修改参数 schema，不执行工具。
- 日期、本人范围与维度来自服务端冻结的 `OwnedReadScope`；模型输出仍经 Pi/Gateway。
- 未改变 SpO2、用药、补剂、基因或体检的医疗处置规则。缺失/失败仍显式披露，不能当正常。
- 测试只使用合成语句和固定日期；不读取或修改真实健康数据，不记录凭据。

## G4 与发布断点

- 当前候选基于最新 `origin/main` 重新应用，无代码冲突；运行时代码已经冻结，最终
  精确 SHA 由外部发布回执记录，避免在 commit 内自引用。
- `scripts/harness_llm_change_gate.py` 判定本次修改必须具备真实模型评测。由于本机没有
  已披露的模型接收方，发布只能在取得有效运行配置后通过，或由用户对最终精确 SHA
  明确批准一次性 `HARNESS_LIVE_LLM_EVAL_WAIVED_SHA`。不得把离线通过写成真实模型通过。
- 在该 Gate 解决前不 push、不 deploy；解决后仍须运行精确 SHA 完整 CI、后端发布与
  健康/匿名鉴权探针。此次为后端 Prompt 变更，不触发 OTA、原生包或 App Store 重传。

## 2026-10-28 第二轮：结果回答与工具指南去重

线上已发布的 `6a5d74ba63c03f1ed5ca70067a4644ebd99de803` 已具备结构化维度注册表、
`OwnedReadScope` 契约和任务级工具投影。继续检查真实组装链后发现两处仍可确定性删除的
重复：

- 服务端已完成取数、封闭工具的只读回答阶段，仍携带只用于意图规划和工具选择的
  `本轮任务边界` 与 `健康近况与用药意图`。
- 同一个已绑定维度指南同时复制到 `health_query` 和 `health_query_batch` 的 description。

实现将仓库中既有、未上线的只读回答实验提升为应用层纯函数，并保留字节哈希
失效保护：只有 `static_rules_only + synthesis_only` 的已封闭只读回答可以删除已审核
规划块；任何策略文本、布局或调用条件漂移都回退到完整 Prompt。临床来源、结果/失败
证据、R4、紧急指引、数据合理性、非因果与回答组织均保留。

工具说明投影在同轮同时提供 canonical `health_query` 时，`health_query_batch` 仅保留批查
计划、聚合、单位、未知值和错误契约，并明确复用同轮单查的维度与医疗限制。若单查
工具缺失、被封闭或 schema 非 canonical，批查继续携带完整维度指南，不依赖不存在的参照。

### 增量证据

- 行为 RED：7 项新测试失败，包括未存在的生产回答投影和仍重复的批查维度指南；同轮其余
  69 项通过。
- 聚焦 GREEN：Prompt 分段、工具投影、真实 Pi/Gateway/DB 组合实验与结果回答实验
  共 90 项通过。合成用例覆盖有数据、空数据和读取失败，未改变 Gateway 请求、回执、
  存储回答、终局状态和失败重试预算。
- 只读回答 system Prompt 从 2,721 字符降到 2,064，减少 24.15%。
- 已绑定工具载荷相对第一轮投影再减少：血氧 8.99%，睡眠＋饮食 7.02%，体检
  12.94%。这些是静态字符量，不冒充生产 Token 账单、延迟或真实模型质量。

- 扩大相关回归共 1,587 项通过（6 个既有依赖告警），覆盖 Prompt、真实 Pi/Gateway/DB
  组合、预算、本人读取范围、血氧截图、读取完成与多维查询。补充 benchmark/metrics
  套件 35 项通过；Pi 单项首次因干净克隆未安装 Node 依赖在候选逻辑前失败，接入锁定
  `pi-runtime/node_modules` 后 1 项通过，临时链接已删除且不进入提交。
- 只读回答配对 benchmark 为 dry-run，候选标记
  `production_runtime_candidate`，计划调用 16 次但未发起模型请求；写路径保持完整 Prompt。
- 离线 LLM Gate 通过：trajectory 12/12、golden 9/9、无模型费用；它不冒充真实模型评测。
- 阻断性 Ruff（F821/F822/E9）、`py_compile`、`git diff --check`、277 份 Dossier 一致性
  与完整 `system-map-check.sh` 均通过，System Map 生成物无变化。

独立 G4、真实模型 Gate（或最终精确 SHA 豁免）与精确 SHA CI 尚未完成。本轮不改工具权限、
参数 schema、Pi/Gateway 决策、用户/日期/维度绑定、写入或医疗处置规则。
