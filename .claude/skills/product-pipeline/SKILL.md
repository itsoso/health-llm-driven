---
name: product-pipeline
description: "复元产品全生命周期总指挥:把一句用户需求,经『需求→PRD→规划→需求分解→研发→测试→部署→上线验证』串成一条可追溯、可失败、可恢复的流水线。当用户说『我想要 X』『把这个需求走一遍流程』『从需求到上线』『立项 X』『push X to production end-to-end』时用本 skill。它不重造实现/部署能力,而是用 Gate 编排已有的 discovery 工作流 / health-harness-orchestrator / deploy·ota·testflight·safety-gate skill / council-review。"
---

# 复元 Product Pipeline — 从需求到上线验证的总指挥

> **流程契约单一真源 = [`docs/specs/product-pipeline-contract.md`](../../../docs/specs/product-pipeline-contract.md)**(agent 中立:双环 + 6 道 Gate + Dossier + 失败即停 + 反馈环纪律)。本 SKILL 是 **Claude Code 对该契约的具体编排实现**(怎么 fan-out、调哪个 sub-skill、用 Workflow 工具)——**契约定标准,本文定 Claude 怎么落**。项目级触发绑定见 [`docs/agent-skill-binding.md`](../../../docs/agent-skill-binding.md);Codex/Cursor/其他 agent 经 `AGENTS.md §12/§13` / `reva-product-governance-spec.md §9.6` 读同一份契约,用自己的工具满足同一套 Gate。契约改了,本文同步。

> **定位**:这是**产品级**总指挥,坐在 `health-harness-orchestrator`(开发级团队编排)**之上**。
> - 本 skill 拥有**前半段**(需求→PRD→规划→需求分解)+ **全程的 Gate 与 Dossier**。
> - **后半段(实现→测试→评审→部署→验证)委托给已有零件,绝不重造**:`health-harness-orchestrator`、`backend-deploy` / `mobile-ota` / `mobile-testflight-release`、`safety-gate` / `safety-privacy-reviewer`、`qa-verifier`、`council-review`。
> - 何时**不**用本 skill:单文件小修 / 纯文档 / 机械改动 → 直接做或用单个 `Agent`;只做实现+上线(需求已定)→ 直接用 `health-harness-orchestrator`。

**Governance boundary:**本 adapter 只在 Router 选中 `feature` 时作为
`primary_controller`;委托 `health-harness-orchestrator` 时复用 same parent run
与同一 Dossier,绝不创建第二个完成状态。

## 核心理念(读这段就懂为什么这样设计)

1. **Gate 而非 Stage**:每个阶段之间有一道**能失败、能 STOP** 的闸。流水线的价值在闸,不在线。
2. **双环**:**定义环**(S0–S3,便宜/可逆/纯文档)与**交付环**(S4–S8,昂贵/有闸)分开 —— 先把定义吵清楚再进昂贵交付。
3. **最便宜的 kill 前置**:准入(G1)+ 可行性/安全压测(G2)在写代码前跑。
4. **Dossier 作脊柱**:每 feature 一份档案,串起全链 + 每道 Gate 裁决 + 状态 → 追溯 + 可恢复。
5. **人在环**:G1 准入、G2 待拍板、G5 真机/发布、G6 验证 —— 显式 STOP 问用户,不偷偷自治。
6. **反馈环纪律**:长动作异步、OTA-vs-EAS 路由、测试不 `| tail`、部署前集成闸 + Codex capstone、部署后健康分自动回滚。

## 流水线总览

```
              ┌──────────────── 定义环(便宜 · 可逆 · 纯文档)────────────────┐
 用户需求 ─▶ S0 Intake ─▶ S1 Discovery ─▶[G1 准入]─▶ S2 PRD ─▶ S3 规划 ─▶[G2 可行性+安全压测]
              建 Dossier   现状图 fan-out   §8 RequirementAdmission   docs/prd  docs/plans  跨家族对抗评审
                                            (PASS/REFRAME/REJECT)                        (待拍板 STOP 问人)
                                                                                              │
              ┌──────────────── 交付环(昂贵 · 有闸)──────────────────────────────────────┘
              ▼
 S4 需求分解 ─▶ S5 实现 ─▶[G3 测试闸]─▶[G4 安全闸]─▶ S6 部署 ─▶[G5 部署健康闸]─▶ S7 上线验证 ─▶[G6 验证闸]─▶ S8 沉淀
  plan→分支/任务  harness   集成闸+capstone  safety-gate   deploy/ota   健康分≥阈值     prod 验证        真机/anchor    memory+档案归档
  (写进 Dossier)  orchestrator (真红回 S5)  (BLOCK 回 S5) testflight    (自动回滚)      +回路闭合       (FAIL→回滚)
```

每道 Gate 失败 → 回到指定上游阶段,**绝不带红/带 BLOCK 往下走**。

## Dossier — 流水线脊柱(第一步永远先建它)

每个 feature 一份 `docs/dossiers/<YYYY-MM-DD>-<slug>.md`(可追溯、入库、可恢复)。模板见 `.claude/skills/product-pipeline/dossier-template.md`。它记录:① 用户原话需求(逐字)② 每阶段产出物的链接(PRD/plan/分支/PR/部署 SHA)③ 每道 Gate 的裁决(PASS/REFRAME/REJECT/BLOCK + 依据)④ 当前阶段 + 状态 ⑤ 待拍板决策 ⑥ 沉淀。
- **任何 session 接手先读 Dossier 当前状态,从那一阶段继续**(可恢复)。
- Gate 裁决必须写进 Dossier(诚实:REJECT/BLOCK 也写,不藏)。

## Workflow Run Ledger — 可恢复执行脊柱

进入交付环(S4+)且存在跨代理 fan-out / 长验证 / 对抗评审时,用文件型 ledger 记录 checkpoint、预算和 trace:

```bash
python3 scripts/harness_workflow_trace.py init \
  --kind product-pipeline \
  --dossier docs/dossiers/<date>-<slug>.md \
  --budget-tokens <hard-limit> \
  --label "<short label>"
```

- 将输出 `run_path` 写进 Dossier;原始 JSONL 留在本地 `docs/_generated/harness-runs/`,不要提交。
- 用一等 trace 命令记录派生与裁决:`spawn --run <run_path> --phase "S5" --agent backend-engineer --task-id <task-id>`;`verdict --run <run_path> --phase "G3" --agent qa-verifier --task-id <task-id> --status passed|failed|blocked`。普通检查点仍用 `event --event checkpoint --phase "S5"`。
- 返回码 `2` 表示预算将超限,按 Gate 纪律 STOP,回 S3/S4 缩小范围或让用户拍板。
- 恢复时先 `summary --run <run_path>`,用 `latest_checkpoint`、`open_agents`、`open_tasks` 定位断点,不要靠记忆重跑整条链。

---

## 阶段 × Gate 详解(每条注明:做什么 / 复用什么 / 产出物 / Gate)

### S0 · Intake(需求录入)
- **做什么**:把用户需求**逐字**记进新建 Dossier;补一句「谁用、解决什么、现在怎么绕过」(feature-plan 四问的 Q1)。
- **产出物**:`docs/dossiers/<date>-<slug>.md`(状态=intake)。
- **人在环**:若需求模糊到无法判定范围 → 先问清(2–3 问),别带着歧义往下。

### S1 · Discovery(现状勘察 · 并行)
- **做什么**:在写任何 PRD 前,把需求触及的子系统**现状**摸清(已有什么可复用、缺什么、硬约束、安全/平台边界)。
- **复用**:`Workflow` 工具跑「fan-out 现状图 readers(`Explore`/对应 engineer agent,READ-ONLY)+ 跨家族对抗评审 critics」(参考 `reva-prd-discovery` 工作流模式:5 现状图 + 平台可行性/安全合规/范围排序 3 评审)。grep 已有 skill/agent/模块,**连接 > 新建**。
- **选择性 priming**:需要历史上下文时,先用 `python3 scripts/harness_memory_prime.py --keywords <repo/module/domain> --limit 8` 检索 `MEMORY.md` 行号证据;只把命中的少量条目写进 Dossier,不要整份 memory 入上下文。需要更窄召回时加 `--require-all`。
- **产出物**:现状图 + 评审写进 Dossier「Discovery」节(带 file:line)。
- **关键**:平台/安全硬限在此暴露(如「表冠长按系统独占」「healthkit_import 零 consent 校验」)—— 越早越便宜。

### G1 · 准入 Gate(governance §8 RequirementAdmission)— **人在环 STOP**
- **依据**:`docs/specs/reva-product-governance-spec.md` §8。逐字段过 `RequirementAdmission` 卡:映射 ≥1 一等对象、命中核心循环某步、`safety_level`、`autonomy_tier`(新写默认 `manual_confirm`)、`spec_required`(§8.1 触发:新用户可见行为/新安全行为/新跨端契约/新写路径/新通知环/新一等对象)、`smallest_end_to_end_slice`、`stale_surface_to_remove`。
- **裁决**:**PASS**(进 S2)/ **REFRAME**(范围不符 → 改写需求回 S0)/ **REJECT**(映射不到核心循环 → 不做,记 Dossier)。
- **STOP 问人**:把准入裁决 + 任何 REFRAME/REJECT 理由给用户确认后再进 S2。

### S2 · PRD(产品需求)
- **做什么**:合成 PRD,**引用不重述**权威 `docs/prd/reva-personal-health-os-prd.md`(R1–R18/北极星/一等对象);走 feature-plan 四问 + ASCII 数据流;声明边界、不变量、验收 Gate、待拍板。
- **复用**:discovery 现状图 + G1 准入卡 + 四问模板(`~/work/personal/PRACTICES/feature-plan.md`)。已 specced 的需求(如 R4/R5/R6/R18)**引 R 号,不重 spec**。
- **未决用标记,别脑补**(借 spec-kit):任何拿不准的点写 `[NEEDS CLARIFICATION: <问题>]` 留在 PRD/Dossier 里;在进交付环(S4)前必须**清零**(由 /clarify 顺序追问解决)。带着未解标记进昂贵交付 = 返工源,被 G2 出口闸拦。
- **产出物**:`docs/prd/<date>-<slug>.md`,链接进 Dossier。

### S3 · 规划(分阶段实施计划)
- **做什么**:把 PRD 落成**分阶段 + 四问 + ASCII + 验收 + 测试闸 + OTA/EAS 路由**的计划;高风险面写 task-by-task spec(参考本仓 `2026-06-27-reva-...experience-plan.md` §13 的 W0–W5 粒度:每 task = 目标/文件/逐步/安全不变量/验收/测试/反馈环)。
- **复用**:PRD + 现状图;**重排序原则**:数据/底座先行、最便宜 felt-value 先出、长杆先 de-risk(spike)。
- **产出物**:`docs/plans/<date>-<slug>.md`,链接进 Dossier。

### G2 · 可行性 + 安全压测 Gate — **人在环 STOP(待拍板)**
- **做什么**:在进昂贵交付前,用**跨家族对抗**压测规划:平台可行性(诚实:做不到的别承诺)、R4/R15/Write 承重墙/PIPL 合规、范围排序。
- **复用**:`council-review` skill(Claude×Codex 三方)或 `codex` challenge,或 discovery 工作流的 critic 阶段。
- **裁决**:抓到的硬阻断/reframe 焊进规划;**待拍板分叉 STOP 问用户**(如「watch 对话做一问一答还是多轮」「HK 后台先 spike 再投 EAS?」)。PASS 后才进 S4。

#### G2 出口 · 定义环一致性闸(spec-kit 只读 /analyze)— 进交付环前必过
定义环出了 PRD↔Plan↔Dossier 三件套,**进昂贵交付前先验它们自洽**(否则 plan 落了 PRD 没提的、或 Dossier 引了不存在的 spec、或带着未解问题就开工):
- **确定性子集(硬闸)**:`python backend/scripts/check_dossier_consistency.py` —— ① 进交付环(状态∈building/shipping/shipped 或 阶段≥S4)不留未解 `[NEEDS CLARIFICATION]` ② 引用的 `docs/{prd,plans,specs}/*.md` 锚点必须存在 ③ Gate↔阶段自洽(进交付环则 G1=PASS;shipped 无任何 Gate 判失败——裁决词表对齐 template:GO/绿=过、REJECT/BLOCK/NO-GO/真红/红/FAIL/失败/自动回滚=失败,**无法识别的裁决词在 shipped 下 fail-closed 报警**)④ front-matter 不可解析=fail-loud 报。**运行方式**:G2 出口手动跑同一命令;仓库分发的 `scripts/validate.py`、`.pre-commit-config.yaml`、`.github/workflows/ci.yml` 已把它作为 blocking gate 与 doc-drift 同级执行。版本化的 `.claude/hooks/` 作为 Claude 本机更早的 PreToolUse/SessionStart 提醒与早闸层,但权威跨环境阻断仍以 pre-commit/CI/validate 为准。
- **语义子集(LLM 只读)**:跑一个**只读** /analyze pass(`Explore` agent 或 council),核 PRD 的目标/一等对象/验收在 plan 与分解里**都有对应**,无 plan 凭空多出 PRD 没授权的范围;冲突按严重度标(违反不变量=CRITICAL)。
- **裁决**:任一不过 → 回 S2/S3 补,**不进 S4**。

### S4 · 需求分解(规划 → 研发分支/任务)
- **做什么**:把规划的阶段拆成**具体研发任务**(每任务链接回规划某 task);定**跨端 API 契约**(请求/响应 shape)写进 `_workspace/`;`TaskCreate` 建任务;判定每任务 **OTA vs EAS**、触及层(frozen core/agent fleet/mutable business)、是否需 feature spec(§8.1)。
- **并发检查**:`git fetch` + `gh pr list` —— 本仓库并发多,先确认没被别的分支/agent 抢先([[project_concurrent_agents_check_main_first]])。
- **产出物**:Dossier「研发任务」节(任务表 + 契约 + 分支策略 + workflow `run_path`)。

### S5 · 实现 — **委托 `health-harness-orchestrator`**
- **做什么**:把 S4 任务交给开发团队编排器(计划→实现 fan-out:`backend-engineer`‖`mobile-engineer`‖`mac-engineer`‖`frontend-engineer`)。
- **隔离**:并发 agent 切分支 → 有状态编辑用 `git worktree`(显式 commit hash 建,见 `using-git-worktrees`);别把 build+push 放进同一并行批次([[project_shared_worktree_use_git_worktree]])。从 `origin/main` 干净起分支。
- **产出物**:分支 + commit,记进 Dossier。
- **Trace**:每个 agent 派生用 `spawn`,G3/G4 裁决用 `verdict`,阶段 checkpoint 用 `event`;中断后从 ledger summary 的 `open_agents/open_tasks` 恢复。

### G3 · 测试 Gate
- **做什么**:`qa-verifier` 跑对应闸门(pytest/doc-drift/tsc/jest/swift/前端 vitest+page-freeze);**部署前集成闸**:全增量测试 CI 模式合跑(`DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`),**直读 passed/failed,绝不 `| tail`**([[feedback_pytest_pipe_masks_exit_code]]);查 `gh run list --branch main` 真实色。高风险面加一次 **Codex 跨家族 capstone**([[feedback_autonomous_campaign_integration_gate_and_crossfamily_capstone]])。
- **裁决**:真红 → 回 S5 对应实现者;假红(本地 Redis/runner 假死/已知并发红)→ 标注不动测试([[project_backend_test_redis_pollution]])。**带红绝不进 S6。**

### G4 · 安全 Gate(producer-reviewer)
- **触发**:改动碰 用药/基因/化验/CGM/消息/Safety 规则/对外健康建议/认证/CORS/写路径 → 必经。
- **复用**:`safety-gate` skill 或 `safety-privacy-reviewer` agent。
- **裁决**:阻断项整改 + 复审才放行;新安全行为(如 on-watch LLM)需 spec + 对抗测试。**BLOCK 回 S5。**

### S6 · 部署 — **委托 deploy/ota/testflight skill**
- **路由**(feature-plan 项目约束):
  - 后端改动 → `backend-deploy`(`deploy.sh -b`,从干净 worktree track origin/main + scp 真 prod .env,[[project_deploy_b_from_clean_worktree]])。
  - mobile JS/TS 改动 → `mobile-ota`(从 origin/main 干净 worktree 打整包,[[feedback_verify_agent_landed_and_ota_from_clean_main]])。
  - native/app.json/Info.plist/新 module/SDK → `mobile-testflight-release`(EAS build,**异步,不等**)。
- **序**:**先后端 deploy → `npm run generate-types`(若改 schema)→ 再 mobile OTA**。
- **产出物**:部署 SHA + 回滚点写进 Dossier。

### G5 · 部署健康 Gate
- **做什么**:`deploy.sh` 部署后自动跑 `system_health_score.py`(阈值 `DEPLOY_SCORE_THRESHOLD=35`,低于自动回滚);+ prod 活体 smoke(`systemctl is-active` + 真实路由 curl 期望 200/401 + 启动日志无 error + 新迁移表/列 ssh 实查存在)。
- **裁决**:健康分 < 阈值 → 已自动回滚 → 回 S5 修;smoke 异常 → 调查([[project_medication_phase_advance_blocked]] 的 deploy 复验范式)。

### S7 · 上线验证
- **做什么**:在 prod 用**真实使用路径**验证需求达成(curl 关键端点 / 健康分 / **真机或 anchor 用户视角** —— mobile/watch 改动用户在真机验,见 Dossier 验收清单)。把结果归因「相关非因果」措辞。
- **产出物**:验证记录写进 Dossier。

### G6 · 验证 Gate — **人在环(真机/发布由用户确认)**
- **裁决**:需求在 prod 对 anchor 用户真成立 → **PASS(回路闭合)**;不成立 → 记缺口 → 回 S5 或回滚。真机/发布类必经用户确认([[feedback_mobile_testflight_use_local_archive]])。

### S8 · 沉淀
- **做什么**:把本轮新坑沉淀回**对应 agent 定义 / 本 skill / memory**(harness 是演进系统);更新 `docs/ARCHITECTURE.md` + `check_doc_drift.py` EXPECTED(若加 model/规则/分区);更新 mobile/Web parity 表;Dossier 状态 → **shipped**。
- **摩擦检测**:需要判断是否该沉淀新规则时,先跑 `python3 scripts/harness_friction_scan.py --input docs/dossiers/<date>-<slug>.md --json`(也可指向会话导出/计划文件)。它只输出「用户重复/纠正真源/反复追问完成」等候选证据和 suggested_rule,**不自动改 memory 或 skill**;晋级仍必须走 reviewed gate / 手动记忆更新。

---

## 失败即停一览(诚实,不带病上线)

| Gate | 失败信号 | 动作 |
|---|---|---|
| G1 准入 | 映射不到核心循环/一等对象 | REJECT/REFRAME,记 Dossier,STOP 问人 |
| G2 可行性+安全 | 平台不可行 / R4·R15·PIPL 违反 | 焊进规划 reframe;待拍板 STOP |
| G3 测试 | 真红 / main CI 红 | 回 S5;**绝不 `\| tail` 吞退出码** |
| G4 安全 | BLOCK 项 | 回 S5 整改 + 复审 |
| G5 部署健康 | 健康分 < 35 | 已自动回滚 → 回 S5 |
| G6 验证 | prod 不达成 | 记缺口 → 回 S5 或回滚 |

## 降级与并行

- **Quick Flow(中档)**:介于全 6-Gate 与单文件小修之间。适用:单 surface、无新一等对象、无新 DB/写自治/医疗安全行为、可在 1 个 Dossier + 1 页 tech-spec 内说清的用户可见改动。做法:S0/S1 轻量化,S2 PRD + S3 规划合并为「tech-spec」,但 G1/G2/G3/G4/G5/G6 的裁决仍写进 Dossier。
- **单文件降级**:纯机械/纯文档/无用户行为改变的小修,可跳 S1 大 discovery(直接小范围 grep)、PRD+规划合一页、单 agent 实现。但 **Gate 不可跳**(尤其 G3/G4/G5)。
- **升级为全流程**:Quick Flow 中一旦发现跨端契约、新写路径、认证/CORS、R4/R15/PIPL、安全规则、长期数据模型或无法在 1 页 tech-spec 内解释清楚,立即升级为全流程,回 S1/S2 补 discovery/PRD/规划。
- **correct-course**:实现或评审中若发现旧基线错误、scope 必须变、Gate 假设被证伪,不要在原计划上静默漂移;在 Dossier 增加 **Correction Block**(触发/旧基线/新基线/回退阶段/需重跑 Gate),更新 PRD/Plan 后从指定阶段继续。若回到 S2/S3,必须重跑 G2 出口一致性闸。
- **并行**:定义环的 discovery readers 并行;交付环的多端实现 fan-out 并行;长动作(EAS/deploy)异步触发不等。
- **可恢复**:任何中断后,读 Dossier「当前阶段 + 状态」从断点续。

## 与现有 skill 的边界(别撞车)

| 想做 | 用 |
|---|---|
| 一句需求走完整个产品生命周期 | **本 skill** |
| 需求已定,只做实现→上线 | `health-harness-orchestrator` |
| 只部署后端 / 推 OTA / 发 TestFlight | `backend-deploy` / `mobile-ota` / `mobile-testflight-release` |
| 只做敏感改动安全闭环 | `safety-gate` |
| 只做三方对抗评审 | `council-review` |
| 加 Safety 规则 / Specialist / 迁移 / 修 doc-drift | `extend-safety-or-specialist` / `add-managed-migration` / `doc-drift-fix` |

## 演进

本 skill 是演进系统。每跑完一条 feature,把新坑(新 Gate 失败模式 / 新复用机会 / 新反馈环纪律)沉淀回本文件或对应下游 skill/agent。
