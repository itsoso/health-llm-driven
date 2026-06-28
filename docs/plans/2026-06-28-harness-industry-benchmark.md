# Harness 行业对标 + 反思:你做的够不够好

> Date: 2026-06-28
> 方法: 4 视角并行调研(GitHub 走 `gh` 真搜 + 规范文章 WebFetch)→ 13 条结论对抗验证(3 条被驳回)→ 综合。
> 诚实声明:① X/Twitter 直搜环境未配置,X 思潮经其规范源(12-factor-agents/Anthropic 工程博客等)捕获;② 第 5 视角(frontier-discourse)agent 失败、综合 agent 吐占位垃圾——**这次 workflow 自身的失败,恰好就是下面要点名的"无 checkpoint/无 eval gate"缺口(见末尾的反讽)**;③ 只用已验证事实,不臆造他人功能。

## 直接回答:够好吗?

**在最难的、承重的那一层——够好,而且领先前沿。** 你把几乎没人同时做的四件事做成了:**代码派生防漂移 + CI 闸**、**R4(LLM 永不发出不可逆动作)**、**reviewed-gate + 每条规则证据溯源**、**确定性 fail-closed 引擎当护城河 + 对抗式 verify 阶段**。整个 Claude 原生生态(superpowers / anthropics-skills / VoltAgent / spec-kit / BMAD / LangGraph / Shannon)里**没有一个**把治理做到这个深度。

**但它"该机械的地方还停在散文,该打包的地方还在手抄,该量化的地方还没有 eval"。** 你写出了 superpowers 级的方法论,却像 2024 年的 dotfile 一样分发它;你的最强不变量(R4 / fail-loud / 不准手打计数)活在 CLAUDE.md 散文里——按 Anthropic 自己的排名,那是**最弱**的强制层。

> 一句话:**实质领先,工程化落后。** 改进不是"补能力",是把你已有的强想法**从散文变成强制、从手抄变成打包、从口号变成可量化**。

## 记分卡

| 维度 | 评级 | 依据 |
|---|---|---|
| 治理实质(R4 / 不可逆动作围栏 / 确定性引擎当护城河) | **领先** | 全生态独有;12-factor 是散文原则,你是代码验证的实例 |
| 防漂移(代码派生计数 + CI 闸,IRON LAW) | **领先** | spec-kit/BMAD/OpenSpec 都让 agent 手写架构事实进 MD 然后烂掉;你结构性禁止 |
| reviewed-gate + 证据溯源(逐规则) | **领先** | VerifyWise 在框架级追治理,你在**单条规则**级 |
| 对抗式验证(fan-out→verify→synthesize) | **领先(顶层)** | = Anthropic 排名最强的"换个新模型来证伪"层 |
| agent 质量(接真闸 vs 通用角色) | **领先** | qa-verifier 跑真 pytest/doc-drift;VoltAgent 154 个是无绑定的角色人设 |
| **强制机制(hooks vs 散文)** | **落后** | 你**没有任何 hook**;最强不变量在最弱的 advisory 层 |
| **分发/可移植(plugin/marketplace)** | **落后** | 你的"可复用工厂"靠手抄复制了 4 次;无 plugin.json/marketplace.json |
| **LLM 合成层的 eval** | **落后** | 确定性规则全测;**喂给患者的 LLM 散文零 eval/零 LLM-judge/换模型零回归闸** |
| **编排器运维(checkpoint/budget/trace)** | **落后** | 无持久化恢复、无成本上限、无结构化 trace |
| 规范撰写 + 生命周期工艺 | **持平偏后** | 有 6-Gate 的"形",但 spec 内容欠结构化、无 clarify/analyze 一致性闸、无 scale-adaptive 中档 |
| 记忆系统 | **持平(将触顶)** | 文件式 + 链接是真优势,但整体读入、MEMORY.md 已大,无检索层/选择性 priming |

## 你真正领先的(护城河,几乎独有)

1. **代码派生防漂移 + CI 闸**:`check_doc_drift.py` + `dump_system_map.py` + 无人手改的 `system-map.json`。**全生态没有第二家**让"committed JSON 必须等于代码生成值否则 CI 红"——你把一类文档撒谎**结构性变成不可能**。
2. **R4**:整个 Claude 原生目录里**不存在**。superpowers 的 verification 是"别没证据就声称完成"(诚实纪律),**不是架构上禁止 LLM 发出不可逆动作**。你的 NEVER-graduating 自治阶梯无公开对应物。
3. **确定性 fail-closed + fail-loud 引擎当承重安全层**:吞任何异常就注入 HIGH + 暴露 `failed_rule_count`。Guardrails 的 OnFailAction 是配置项,你的是结构。
4. **加层不减层**作为命名、被守护的不变量(去重路径绝不丢告警):护栏框架里没有这个失败模式纪律。
5. **对抗式 verify 阶段** = Anthropic 排名的**最强**验证层(让没干活的新模型来证伪);你做研究/评审天然在顶层。
6. **接真闸的项目适配 agent**(深度)vs 社区的 154 个通用角色 agent(广度)。**流行 ≠ 好**。

## 真缺口(已验证,按价值排序)

| # | 缺口 | 谁证明它是真缺口 |
|---|---|---|
| 1 | **没有 hooks** —— 最强不变量(R4/fail-loud/不准手打计数)只在 CLAUDE.md 散文里=Anthropic 排名**最弱**的 advisory 层;`check_doc_drift` 还只在 CI(提交后)跑 | Anthropic「Claude Code best practices」明排:in-prompt < /goal < **Stop hook(确定性,阻断到通过为止)** < verification subagent。"hooks 是确定性的、保证动作发生;CLAUDE.md 是 advisory"。你**有最弱和最强,跳过了中间的 Stop-hook 强制层** |
| 2 | **LLM 合成层零 eval** —— 确定性规则全测,但**喂给患者的 LLM 散文**无 promptfoo 式声明 eval、无 LLM-judge、换模型(qwen/glm/minimax/claude 按用户切)**零回归闸** | promptfoo/langfuse/Hamel:你**独有**做 LLM-judge 的两个稀缺前提(已有命名领域专家=创始人 + reviewed-gate 文化),却没用 |
| 3 | **Workflow 工具无持久化/无预算/无 trace** —— 崩了/OOM/被打断就全丢;对抗 verify 成本无上限;crown-jewel 的 verify 阶段事后不可审计 | LangGraph 头号支柱"持久执行、从断点恢复";Shannon 用 Temporal replay + 硬 token 预算 + OTel。**直接违背你自己的「反馈环优先」** |
| 4 | **没打包成 plugin** —— "可复用工厂"=手抄复制 4 次;不跨 harness 可移植 | superpowers 出 `marketplace.json` + `.codex/.cursor/.kimi` manifest;anthropics/skills 走 `/plugin marketplace add`。你跑 Claude+Codex+Cursor 却单仓库 |
| 5 | **spec 工艺 + 生命周期** —— spec 内容欠结构化;无 clarify/analyze 跨产物一致性闸;无 scale-adaptive 中档;无命名的 correct-course | spec-kit:`spec-template` 强制独立可测的分级用户故事 + `[NEEDS CLARIFICATION]` + 只读 `/analyze`(constitution 冲突=CRITICAL);BMAD:Quick/Method/Enterprise 三档 + `correct-course` + retrospective |
| 6 | **记忆将触顶** —— 整体读入,MEMORY.md 已大,无选择性 priming/检索层 | metaswarm `bd prime --files/--keywords`("长到上千条不烧 context");Letta 核心(常驻)+ archival(检索)分层 |
| 7 | **输入/检索侧无护栏** —— SafetyGuardian 只在输出/执行侧;输入 PII/PHI 不脱敏、KnowledgeLibrarian RAG 路径无 grounding 校验 | NeMo Guardrails 的 input/dialog/retrieval/output rail 分类法点名你的覆盖洞 |
| 8 | **自改进是手动的** —— 你靠人注意到模式后手抄沉淀 | metaswarm 自动检测会话里的"用户重复/用户推翻/摩擦点"并**提议新 skill**;你缺这个**检测**步(但你的 reviewed-gate 晋级步更优) |

## 该抄什么(来源 → 怎么融入)

| 抄谁 | 抄什么 | 怎么融入你的 harness |
|---|---|---|
| **obra/superpowers** hooks.json + Anthropic Stop-hook 层 | SessionStart hook + PreToolUse/Stop hook | 加 `.claude/hooks/`:① SessionStart 注入一行"读 system-map/INDEX + 遵守 AGENTS.md R4/fail-loud";② 把**已写好的** `check_doc_drift` 包成 PreToolUse/Stop hook,本地提交就阻断,而非 CI 事后红。**你已经写了那个确定性检查,只是触发太晚** |
| **Hamel(critique-shadowing)+ promptfoo + langfuse** | LLM-judge + 声明式 eval + trace→dataset→eval 回归闸 | 让创始人对一批 synthesis trace 给二元 pass/fail + 书面 critique → 建 LLM-judge(你独有这俩前提)→ promptfoo YAML 按 intent(safety/labs/reco)断言 R4 不处方/加层不减层 → 换模型/改 prompt 时当回归闸 |
| **LangGraph + Shannon + 12-factor F6** | 持久 checkpoint / 暂停恢复 / token 预算 / OTel trace | Workflow 工具持久化 fan-out 状态(每分支输入/部分结果/verify 裁决)→ 崩溃可 resume;每 run 硬 token 上限 + 模型回退;每次 spawn/verdict/synthesize 发 JSONL trace |
| **superpowers marketplace.json + anthropics/skills** | plugin 打包 + 跨 harness manifest | 把 domain-rule-factory + product-pipeline + system-map 打成私有 plugin(`marketplace.json` + per-project adapter),`/plugin install` 装,取代手抄 |
| **spec-kit** | `spec-template` + `/clarify` + 只读 `/analyze` | S2/S4 用 spec-kit 的分级独立可测用户故事 + `[NEEDS CLARIFICATION]`;G3 前加一道**只读**跨产物一致性闸(PRD↔Plan↔分解必须自洽) |
| **BMAD** | scale-adaptive 中档 + correct-course | 在"全 6-Gate"和"单文件降级"之间加一档命名"Quick Flow"(只 tech-spec,但 G3/G4/G5 仍强制);加一等 `correct-course` 重基线 Dossier |
| **metaswarm** | 选择性 priming + 摩擦自动检测 | 给每条 feedback_*.md 打 affected-files+keywords tag,按需 prime;扫会话检测"用户重复/推翻"自动**提议**新规则(晋级仍走你的 reviewed-gate) |
| **NeMo Guardrails** | rail 分类法当覆盖清单 | 补 input rail(PII/PHI 入日志前脱敏)+ retrieval rail(RAG chunk grounding 校验) |
| **VerifyWise** | 轻量风险登记册 | 用你自己的 system-map IRON-LAW 风格:把治理债(如 PIPL consent 缺口)做成一个代码派生 JSON,结构性可见可审,而非一行 memory 备注 |

## 排序后的改进(价值/工作量)

1. **Hooks(P0,低工本,最高价值)**:把**已存在的** doc-drift + R4/fail-loud 不变量包成 PreToolUse/Stop hook + SessionStart bootstrap。你已经写了确定性检查,只是让它更早、更机械地触发。单点最高 value/effort。
2. **LLM 层 eval + LLM-judge(P0,中,高)**:promptfoo 声明 eval + Hamel critique-shadowing(创始人当 judge)+ 换模型回归闸。让"证伪工厂"哲学**对 LLM 层也成立**,不只对确定性层。你今天按用户切模型零闸=已知活风险。
3. **Workflow 持久化 + 预算 + trace(P1,中)**:checkpoint/resume + token 上限 + JSONL trace。本 session 已两次被它咬(PRD review 被打断全丢、这次综合 agent 挂)。
   - 2026-06-28 implementation note:已新增 `scripts/harness_workflow_trace.py` 文件型 JSONL ledger,支持 `init/event/summary`、硬 token budget、`budget_exceeded` 返回码 2、checkpoint summary;并已接入 `health-harness-orchestrator` / `product-pipeline` 使用说明。下一步若继续深化,应把 subagent spawn/verdict 自动写入该 ledger,而不是只靠人工命令。
4. **plugin 打包(P1,中)**:marketplace.json + per-project adapter,终结手抄 4 次。
   - 2026-06-28 implementation note:已新增 repo-local Codex plugin `plugins/reva-health-harness` 与 `.agents/plugins/marketplace.json`,打包 `product-pipeline` / `health-harness-orchestrator` / workflow trace CLI;并新增测试确保 plugin manifest、marketplace entry、打包 skill 与源文件保持一致。
5. **spec-kit/BMAD 工艺借鉴(P2)**:spec-template + /clarify + 只读 /analyze 一致性闸 + scale-adaptive 中档 + correct-course。
6. **记忆检索/选择性 priming(P2)**:MEMORY.md 触顶前上 metaswarm tag-prime 或 Letta 核心+archival。
7. **输入/检索护栏(P2,健康专属)**:NeMo 分类法补 input PII 脱敏 + RAG grounding。

## 前沿会怎么批评你(最诚实的一刀)

> "你把 superpowers 级方法论写出来了,却:① 用**散文**强制本该 hook 强制的不变量;② 像 **dotfile** 分发本该 plugin 分发的可复用工厂;③ 在你整套'可量化证伪工厂'哲学最该有 eval 的地方(喂给患者的 LLM 输出)**零 eval**。你对确定性规则严苛到牙齿,对自己产出的 LLM 散文却只有口头纪律。"

这一刀准。好消息:三条都不是"补能力",是把你**已有的强东西**从 advisory 变 enforced、从 bespoke 变 packaged、从口号变 measured。

## 反讽(这次 session 自己证明了缺口)

这份对标的 workflow **自己**:第 5 视角 agent 失败、综合 agent 吐占位垃圾、丢了一个 lens;更早 PRD review workflow 被你一打断就**全丢重跑**。这正是缺口 #3(无 checkpoint/恢复)和缺口 #2(无 eval gate 兜底质量)的活体演示——**你的工具链在你自己手里就栽在它最该补的两个洞上。** 先补这两个,比抄任何 spec 模板都值。
