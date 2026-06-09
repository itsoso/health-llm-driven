# 设计文档：Agent Operating Harness（编码智能体操作工具架）

> 状态：**设计稿，待评审**。本文档设计的是"**开发期的编码智能体（Claude Code / Cursor）如何在本仓库高效、安全地工作**"的操作工具架 —— 参考截图里另一项目的 harness 落地结构 + 业界最佳实践，落到本仓库的现实（monorepo + 已有 1001 行 AGENTS.md + 23 个散落 docs + 仓库外的 ~/.claude 记忆）。

---

## 0. 先消歧：本仓库有两个"harness",不是一回事

这是动手前**必须先钉死**的一件事,否则重构会误伤现有资产。

| | **Product LLM Harness** | **Agent Operating Harness**（本设计） |
|---|---|---|
| 是什么 | 产品里的健康 AI agent 怎么造 | 编码 agent 在这个**仓库**里怎么干活 |
| 关心 | source-aware path / verification before write / tool schema / memory 注入 / streaming | 导航 / 验证闸门 / 计划生命周期 / 经验沉淀 |
| 落在哪 | **现有 `docs/HARNESS.md`（551 行,保持不动）** | CLAUDE.md + AGENTS.md + docs 结构 + scripts + 新增 `harness/` |
| 截图对应 | — | 截图讲的就是**这个** |

**为什么必须分清**:名字撞了。截图把操作层叫 `harness/` + `AGENTS.md`;我们把产品层叫 `HARNESS.md`。本设计**不碰** `docs/HARNESS.md`,只在它顶部加一句"我是产品方法论,不是操作工具架"的消歧指针。

---

## 1. 截图的 4 根支柱 → 本仓库现状 → 差距

截图("Harness 落地完成")提炼出 4 根支柱。逐一对照本仓库:

| # | 支柱 | 截图做法 | 本仓库现状 | 差距 |
|---|---|---|---|---|
| 1 | **薄入口导航** | `AGENTS.md` 85 行 = agent 入门第一站 | `CLAUDE.md` 554 行 + `AGENTS.md` **1001 行**(硬规则) | 两个入口都胖;AGENTS.md 把"导航"和"安全/日志/测试/部署硬规则"混成一坨 1001 行,新 agent 要滚很久才知道去哪 |
| 2 | **主题分片参考** | `docs/{ARCHITECTURE,DEVELOPMENT,PRODUCT_SENSE}.md` | `docs/` 有 **23 个顶层 md** + `ARCHITECTURE.md`(41KB) | 有料但散:STRATEGY/FUTURE_ROADMAP/ROADMAP_*/NEXT-WEEK-*/RELEASE_*/IMPORT_PIPELINE_*/APPLE_WATCH_* 平铺,没有"读哪个"的分片边界 |
| 3 | **统一验证管道** | `scripts/validate.py` 4 步 0.8s | 只有 `scripts/check_doc_drift.py` + 分散的 `pytest`/`lint`/`tsc` | **无单命令闸门**;反馈环靠人记一串命令 |
| 4 | **工作记忆** | `harness/{tasks,trace,memory}` committed | 记忆在 **`~/.claude/.../memory/`(仓库外)** + `docs/plans/`(44 个文件) | 记忆不随 PR 走、CI/他人/他 agent 读不到;plans 无 active/completed 生命周期 |

> 注:`docs/design-salience-unification.md`(本季产物)已经是"design-docs / ADR"的雏形,只是还没有正式的家。

---

## 2. 业界最佳实践（对照,佐证每条动作）

| 实践 | 来源 | 落到本设计 |
|---|---|---|
| **AGENTS.md 约定** — 根目录一个薄 AGENTS.md,子目录可各放一个就近覆盖 | agentsmd 约定(Codex/Cursor 等采用) | §3 monorepo 每根目录就近放 CLAUDE.md/AGENTS.md;根入口收薄 |
| **CLAUDE.md 要短、分层、import** | Anthropic Claude Code 记忆指南 | 入口只放导航 + doc map,细节下沉到分片文件 |
| **Context engineering / progressive disclosure** | Anthropic(HARNESS.md §0 已引) | 同一原则用在"agent 读文档":薄入口 → 按任务深读,而非一次塞 1001 行 |
| **单命令验证闸门**(pre-commit = CI) | 业界 CI 主流 | §4 `validate` 聚合所有确定性检查,反馈环压到秒级(契合项目"反馈环优先"规矩) |
| **ADR(架构决策记录)** | Michael Nygard ADR | `design-docs/` 给设计决策一个留痕的家 |
| **Plan 生命周期 active/completed** | 截图 + 看板实践 | `exec-plans/{active,completed}` 把"在做/已做"分开,completed 作可追溯历史 |
| **Learned-memory loop**(踩坑→沉淀→下次主动联想) | 截图 `harness/memory` + 用户 ~/.claude 记忆规矩 | §5 Q2:in-repo 让 CI/他人/他 agent 也能读,但要防双真相源 |

---

## 3. 适配本仓库的目标结构（monorepo,5 根)

**关键差异**:截图是单 Electron app;我们是 pnpm workspace + 4 个非 workspace 根(`backend`/`frontend`/`mobile`/`mcp-server`/`packages/mini-program`)。所以**就近导航**比单 app 更重要——每根目录的 agent 指引不一样。

```
/CLAUDE.md              ← Claude Code 薄入口(已是;瘦身为纯导航 + doc map + 消歧块)
/AGENTS.md              ← Cursor/通用 agent 入口(瘦身:导航 + 指向分片硬规则,不再内联 1001 行)
/docs/
  HARNESS.md            ← 【不动】产品 LLM 方法论(顶部加消歧指针)
  ARCHITECTURE.md       ← 已存在(41KB,后续可瘦/拆,本期不强求)
  DEVELOPMENT.md        ← 新建:命令 / 调试 / 数据位置(从 CLAUDE.md§命令 + DEPLOY + TROUBLESHOOTING 抽)
  PRODUCT_SENSE.md      ← 新建:定位 / 支柱 / 明确不做的事(从 STRATEGY-2026 + FUTURE_ROADMAP 抽)
  governance/           ← AGENTS.md 9 章硬规则分片:security/logging/testing/perf/privacy/commit/incident/deploy/db.md
  design-docs/          ← ADR:design-salience-*.md 迁入;以后新设计都进这
  exec-plans/
    active/             ← 进行中(docs/plans 的活跃项迁入)
    completed/          ← 已完成(含 ROADMAP_* / NEXT-WEEK-* / RELEASE_* 历史)
  reference/            ← 低频参考归档(APPLE_WATCH_* / MULTI_DEVICE / GENETIC_MODULE / IMPORT_PIPELINE_*)
/scripts/
  validate.py           ← 统一闸门:聚合 check_doc_drift + lint + 关键 pytest 子集 + mobile tsc
/harness/               ← 新增(in-repo 工作记忆,随 PR 走) —— 待 §5 Q2 拍板
  tasks/  trace/  memory/
backend/CLAUDE.md       ← 就近:pytest 两 env / venv / 路由分包(已有内容,可下沉)
mobile/CLAUDE.md        ← 就近:本地 Sim vs EAS 异步 / OTA(已散在根 CLAUDE.md,可下沉)
```

**核心理念**(契合项目复杂度预算「删代码 > 写代码」):操作 harness **主要是把已有资产重新组织**(分片 + 分流) + **加一个 validate + 一个 memory loop**,**不是新造一套框架**。新增的真正"代码"只有 `validate.py` 和 `harness/` 目录。

---

## 4. 迁移映射（非破坏,分阶段;每阶段独立可评审)

**Phase 1 — 消歧 + 薄入口指针(零删除,零风险)**
- `CLAUDE.md` / `AGENTS.md` / `docs/HARNESS.md` 顶部各加一句"我是谁 / 不是谁 / 去哪找 X"。
- 建立 doc map(读哪个文件做哪件事),内容先不动,只加指针。**可立即做。**

**Phase 2 — 分片硬规则(独立 worktree)** — Q3 已定:**先拆三章**
- 先把**最常踩的三章(安全 §1 / 测试 §3 / 部署 §8)** → `docs/governance/{security,testing,deploy}.md`,`AGENTS.md` 对应章收缩成一句导航 + 指针。其余 6 章后续再拆,**不一次拆 9 章**。
- ⚠️ `check_doc_drift.py` 的 `EXPECTED` 钉死了 AGENTS 相关数字 → **同 PR 更新**,否则 CI 挂(这是项目明文规矩)。

**Phase 3 — plans 生命周期**
- `docs/plans/`(44 个)分流到 `exec-plans/active|completed`;`ROADMAP_*` / `NEXT-WEEK-*` / `RELEASE_*` 进 `completed`。

**Phase 4 — 统一 validate** — Q4 已定:**手动 + CI,pre-commit 暂不强制**
- `scripts/validate.py` 聚合:`check_doc_drift` + `ruff`/`eslint` + **关键 pytest 子集**(非全量,保反馈环 **< 5s**) + `mobile tsc`。
- 触发:**手动 `python scripts/validate.py` + CI 共用同一脚本**;pre-commit hook 暂不强制(先验证够快,稳定后再 opt-in 自动化)。

**Phase 5 — in-repo `harness/`** — Q2 已定:**导出目标,非平行手写库**
- `tasks/`(`.gitignore` 内容、留 `README`) / `trace/`(失败日志)。
- `memory/` **只作 `~/.claude/.../memory/` 项目级条目的单向导出目标**(生成物,文件头标注"自动导出,勿手改"),**不作 committed 的平行手写记忆**,避免与 home 记忆双真相源发散。

---

## 5. 风险 + 待决

**风险**

| # | 风险 | 缓解 |
|---|---|---|
| 1 | **造平行系统**(违复杂度预算) | 操作 harness = 重组现有 + 一个 validate + 一个 memory loop,不引第三套规范文件 |
| 2 | 分片 AGENTS.md 撞 `check_doc_drift` 钉死的数字 | **已验证不撞**(Phase 2):`check_doc_drift.py` 的 `_doc_texts()` 只读 `CLAUDE.md` + `docs/ARCHITECTURE.md`,**根本不扫 AGENTS.md** —— 分片任何章节都无需改 `EXPECTED`。仍先在 worktree 跑一遍确认零新增 fail(已做:与拆前同 5 条 ARCHITECTURE Celery 漂移,无新增) |
| 3 | 迁移动文件路径 → CLAUDE.md/AGENTS.md/README 里相对链接断 | 迁移脚本顺带 grep-改引用;Phase 1 的 doc map 用稳定锚点 |
| 4 | **in-repo memory 与 ~/.claude memory 双真相源发散** | 这正是本季 salience 教训的**同型问题**(两套引擎判同一件事会发散)。见 Q2 —— 要么单一来源,要么定向单向导出 |
| 5 | 并发 checkout 分支翻转(MEMORY) | **全部阶段(含 Phase 1)在独立 `git worktree`** —— Phase 1 虽零删除,但改的是 **tracked** 文件(CLAUDE.md/AGENTS.md/HARNESS.md),在翻转的主 checkout 里编辑会被并发 commit 误带/丢失。唯一安全的是新建 untracked 文件(如本设计文档) |

**决策(已定,2026-05-31)**

1. **Q1 命名** ✅ 操作层**不**新增顶层 "HARNESS" 概念;沿用 `CLAUDE.md`/`AGENTS.md` 作入口,新增 `harness/` 仅作工作记忆目录。
2. **Q2 in-repo memory** ✅ **不**建 committed 的平行手写库;`harness/memory/` 只作 `~/.claude` 项目级条目的**单向导出目标**(生成物,勿手改),防双真相源。
3. **Q3 分片激进度** ✅ **先拆三章**(安全/测试/部署),其余后续,不一次拆 9 章。
4. **Q4 validate 触发** ✅ **手动 + CI 共用,pre-commit 暂不强制**;反馈环目标 **< 5s**(pytest 子集)。

---

## 6. 本步交付物

- 本设计文档(`docs/design-agent-operating-harness.md`)。
- 评审通过后:**Phase 1(消歧块 + doc map)零风险可立即做**;Phase 2+ 在独立 worktree 分批,每批一个可评审 PR。

> 不做(本期边界):不重写 `docs/HARNESS.md`;不瘦身 `ARCHITECTURE.md` 内容(只归位);不引入新的 lint 框架(复用 ruff/eslint/tsc/check_doc_drift)。
</content>
