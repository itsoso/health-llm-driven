# 小气候 Prompt 契约优化

| 字段 | 值 |
| --- | --- |
| 状态 | ota_baseline_migration_ready_for_g4 |
| 当前阶段 | 第三轮回答投影的 283 原生基线迁移与重新发布 |
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

## 2026-10-28 第三轮：最近一周请求质量与回答投影

生产库最近七天的只读、去标识化聚合得到 98 个首答配对，其中 91 个来自管理员账号，
只能用于发现系统断点，不能外推普通用户完成率。96 个带结构化任务结果的回合中，
53 个完成、23 个阻断、13 个失败、6 个等待补充、1 个部分完成；模型生成成功不能替代
任务完成。个人健康查询的启发式分类样本为 14 个，其中 4 个完成，且 P95 约 129.53 秒。
50 条回复带有“本轮/信息来源/未逐项核验/模型推断”等过程性表达。

当前 `main` 已经具备前三项 P0 基础：`OwnedReadScope`/`DailyReadPlan` 服务端读取计划，
受限读取修复与 Gateway 失败关闭，以及由 `turn_outcome` 驱动的 Mobile 终局状态；本轮不再
新建平行 `RequestPlan` 或放宽读取语法。最新线上候选之后只有 4 个请求、1 个会话，样本不足，
没有作质量改善声明。

本轮实施回答投影去重：服务端保存的完整回答、复制内容与安全审计文本不变；Mobile 只在
终态回答已经有结构化 `answer_evidence` 或来源面板时，识别 `guidance_validator` 固定生成的
来源前缀，并把它移入现有“回答依据”展开面板的“回答边界”。允许标签采用封闭白名单；
未知标签、没有依据面板、流式回复或只有前缀没有正文时保持原文，防止静默隐藏安全边界。

### G3 增量证据

- RED：新增终态回答投影用例首轮 1 failed / 44 passed，失败证明固定来源前缀仍与结论合并
  显示，且展开面板没有对应边界。
- 初次实现本地 GREEN：`ChatBubbleStreaming` 与 `AnswerEvidencePanelUi` 共 55 passed；首次
  独立 G4 在加入一项边界测试后的同范围结果为 56 passed。
- 扩大 Chat 组件回归：27 suites、423 tests 全部通过；既有模拟错误场景产生预期 console
  警告，不是测试失败。
- Mobile TypeScript `tsc --noEmit` 通过；设计 token 闸通过，raw hex 由基线 599 降至 595，
  未新增漂移。
- 独立 G4 首轮指出失败、打断或业务未完成的回复仍可能折叠来源边界。补充 9 个 RED 后，
  6 种非完成业务终局与 `error`、`interrupted` 均复现该问题，无障碍提示也缺少医生确认
  归因；复制原始全文用例已通过。
- 修复后仅 `terminalStatus=complete` 且生成未失败/打断的回复可折叠固定来源前缀。独立复核
  新鲜运行两套聚焦测试共 66 项通过，覆盖全部非完成终局、医生确认归因、无障碍提示和
  复制原文。

### 安全边界

- 不改后端提示词、工具说明、工具集合、读写授权、健康数据、医疗建议或终局分类。
- 不从正文猜测任意来源；只识别服务端当前固定的五个来源标签，格式漂移时回退原文。
- 依据面板仍保留来源边界，折叠按钮的无障碍提示会朗读该边界，复制与服务端历史仍保留
  完整原始回答。只有明确业务完成且生成未失败/打断的回复可折叠；任何未完成终局都保留
  行内边界。
- 发布前仍需精确提交的独立 G4、完整 CI 和目标发布闸；本地组件测试不构成上线证明。

### G4 断点

- 候选 `07feb2805c6ec53a5dfe6652375cdef72573b2e3` 的首次独立复核为 NO-GO，原因是折叠条件
  未绑定业务终局与生成完成状态。该候选不得发布。
- 已按复核要求补齐失败测试并收紧条件；须对修复后的精确提交重新独立复核。取得 GO 前
  不 push、不部署、不发布 OTA。
- 修复实现与证据修正后的精确提交 `b6933ca8b1abf13719c69dc275dc0d631588b7b9`
  已获独立 G4 GO；新鲜聚焦结果为 2 suites / 66 tests，未发现新的安全、隐私、无障碍、
  复制或证据完整性阻断。后续仅记录该裁决的文档提交不得改变已复核的实现与测试 blob。

### 精确主干、后端与 OTA 断点

- 回答投影最终候选 `1c25e80c7b5b294c25325cc9f669c6522709e0f6` 的 GitHub CI
  `40721325610` 为 32/32 成功；trusted release validate `40723576435` 成功。
- 首次后端发布 `40723747892` 在领取发布权和部署前因只读 SSH 公钥校验失败而终止，未部署；
  保留该失败且没有重放。既有受审授权轮换完成后，新后端操作 `40724626399` 成功。
- 生产只读回执为 `SUCCEEDED`，receipt SHA256
  `0cd7a8a975098fa2d7b1bbc6147dced095b43bd4b71c7163b2804383aaf16801`；服务器源码精确匹配
  候选且 clean，backend/worker/beat active，loopback 与公网健康为 200，匿名会话接口为 401，
  business lease 已释放。
- trusted OTA validate `40725884212` 在无凭据源码预检阶段以
  `native_source_incompatible` 阻断；制品准备、claim、服务器 RPC 与 vendor publish 均未执行。
  该失败不可重发，后续基线修复必须形成新 SHA 并重新走全部 Gate。

### 283 原生基线迁移

- TestFlight 283 的 EAS build `ea1dda2a-86b3-4e46-adf8-b2b024465154` 精确绑定源码
  `ae7a5972921ee9d51eec2c90c7893e6941d2d7ff`、runtime 1.3.6、production channel、STORE
  profile 与 bundle `life.executor.health`；fingerprint 为
  `0f13707a06be8ea69d9a8f083e4c38edfa08cbe4`，Apple 处理状态 `VALID`，内部 TestFlight
  状态 `IN_BETA_TESTING`。
- IPA SHA256 为 `14545db4331b53e6f9d1f39a55d93e19db21f5a0df147a83f71bdd74dd935fcd`；签名 team、
  既有生产 entitlement 范围、源码与 workflow 绑定均已有脱敏回执。没有操作真机或真实健康数据。
- 新源码准入基线固定为 283，同时 vendor 实时闭集必须精确包含 279–283 五个已审 build；
  任何缺失、额外 build、source SHA、fingerprint、runtime、profile、channel 或 bundle 漂移都阻断。
- 当前回答投影候选相对 283 源码的移动端差异只有 `AnswerEvidencePanel.tsx`、
  `ChatBubble.tsx` 与对应测试，均属于已有 OTA 允许的 TS/TSX 路径，没有原生或未知输入。
- TDD RED 在旧实现上得到 46 failed / 173 passed，覆盖旧基线、缺少 283 与基线指纹错配；
  实现后聚焦发布器回归为 219 passed。完整 release invariants、精确提交 G4、主干 CI、后端与
  新 trusted OTA validate/publish 仍待后续 Gate，不以本地单测冒充发布完成。
- 基线迁移提交 `c041f702783768fb1b5ae969cf7eac126d3e60f2` 的首次独立 G4 为 NO-GO：
  前向准入仍把 281/282 的历史品牌摘要当作活动例外，283 后代可把五项图标/配置恢复为旧字节。
  该提交不得发布。修复将历史摘要只留在历史证据中，283 后所有原生、依赖和基线品牌路径的
  任何 diff 都要求新原生基线；新增完整 Git 后代测试逐项恢复旧 app.json、icon、splash、
  adaptive icon 与 favicon，必须由 `validate_source` 失败关闭。修复后的精确提交须重新 G4。
