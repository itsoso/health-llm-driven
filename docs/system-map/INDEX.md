<!-- system-map INDEX. 维护规则见 .claude/skills/system-map/SKILL.md。
     叙事区改完更新本文件顶部 last-reviewed;代码派生数字**绝不手写在这里**,只引用 docs/_generated/。 -->
---
doc: system-map/INDEX
last-reviewed: 2026-08-29
generated-source: docs/_generated/system-map.json
generated-agent-context: docs/_generated/system-map-agent-context.md
extend-via: docs/specs/product-pipeline-contract.md
skill-binding: docs/agent-skill-binding.md
skill-governance: docs/governance/agent-skill-governance.md
---

# System Map — 复元 Reva 系统全景(全局任务入口)

> **这是理解「本系统是什么、在哪、怎么扩」的统一入口，不是每个任务的固定税。** 仓库研发先经 Router；已知路径的小任务直接做零跳查询，全局 onboarding / 架构 / 跨域任务才先读本页和轻量摘要。维护机制见 [`.claude/skills/system-map/SKILL.md`](../../.claude/skills/system-map/SKILL.md)。

## READ ORDER FOR AGENTS(按需读,别全读)

1. **先经 Router 判断是否需要地图** → `python3.12 scripts/check_agent_skill_governance.py recommend --mode <mode>`；非仓库元任务跳过本页。
2. **已知局部直接查询** → 用 `python3.12 scripts/system_map_context.py --path/--entity/--flow/--keyword ... --depth 0`；确需上下游再提高 depth，结果超预算时缩小 selector。
3. **全局任务加载有界认知** → onboarding、系统全景或跨域设计才读 [`system-map-agent-context.md`](../_generated/system-map-agent-context.md)，然后做局部查询。
4. **想知道这系统是什么/能做什么** → 下方「facet 2 能力」+ [`product-map.md`](product-map.md#3-当前功能清单代码核验) 当前功能清单。
5. **想知道某功能在哪个端/怎么连** → [`product-map.md`](product-map.md)(多端 × UI × 业务流 × 系统流)。
6. **想确认地图此刻可不可信或只看计数** → [`docs/_generated/system-map.json`](../_generated/system-map.json)，或运行 `python3.12 scripts/system_map_context.py --counts`。
   管理员需要可视化查看时 → `/admin/system-map`（复用现有管理员登录与权限；数据仍来自同一生成物）。
7. **想扩一个功能** → [`product-pipeline-contract.md`](../specs/product-pipeline-contract.md)(需求→上线 6 道 Gate;S1 用本地图当现状输入)。
8. **想知道当前在做什么** → `docs/dossiers/`(在途 feature)。

**证据优先级：代码与测试 > 代码派生 System Map > 受审声明 > 带新鲜度的叙事。地图不能替代源码和测试验证。** 查询结果给出的是下一步应打开的 source path；命中 `partial`/`declaration` 时必须按警告回到源码。若摘要或地图缺失/陈旧,先跑 `./scripts/system-map-check.sh`;闸门仍失败则停用地图,直接调查代码、测试和注册表。CI 能验证生成物与接线,不能证明模型真的读过。

## 三层分治(防漂移的核心)

| 层 | 哪些内容 | 真源 | 会漂吗 |
|---|---|---|---|
| **A 叙事** | 目标/规划理由/为什么/流程叙事 | 本文件 + 各 facet 文档(带 `last-reviewed`) | 靠新鲜度门 + S8 回写 |
| **B 生成结构** | 代码派生计数/注册表 + v2 typed entities/relations/coverage + Agent 轻量派生视图 | `docs/_generated/system-map.json`(canonical) + `docs/_generated/system-map-agent-context.md`(派生；同一生成器与中央 harness 校验) | 已纳入的生成字段等值防漂移 |
| **C 在途** | 当前在做的 feature | `docs/dossiers/`(product-pipeline 脊柱) | 零(流水线在写) |

**铁律**:任何计数(规则数/specialist 数/路由数/…)**只准从 `docs/_generated/system-map.json` 引用,绝不手打进任何叙事**。手打的数字必漂(实证:ARCHITECTURE 曾 `(51 条)`、PRODUCT_ROADMAP 当日写错 `56`)。

## 6 facet × 权威位置

| facet | 权威文档(点过去,不重写) | 层 |
|---|---|---|
| **1 系统目标/北极星** | [`reva-product-governance-spec.md`](../specs/reva-product-governance-spec.md) §1/§3/§4 · [`reva-personal-health-os-prd.md`](../prd/reva-personal-health-os-prd.md) §1 | A |
| **2 产品能力** | 当前功能与代码锚点:[`product-map.md`](product-map.md#3-当前功能清单代码核验) · 一等对象:governance §5 · 多 agent fleet:[`ARCHITECTURE.md`](../ARCHITECTURE.md) §四 + [`CLAUDE.md`](../../CLAUDE.md) · roster/计数:`_generated/system-map.json` · 成熟度:[AS-IS PRD](../prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md) §1.4 | A+B |
| **3 产品规划** | [`PRODUCT_ROADMAP.md`](../PRODUCT_ROADMAP.md)(战略 H1–H4)· 近期 Phase:AS-IS PRD §7 · 在途:`docs/dossiers/` | A+C |
| **4 系统架构** | [`ARCHITECTURE.md`](../ARCHITECTURE.md) + CLAUDE.md §Architecture + 管理员只读视图 `/admin/system-map`（计数与结构由 generated artifact 钉） | A+B |
| **5 未来规划** | reva-personal-health-os-prd.md §10 待拍板 · AS-IS PRD §3/§10 | A |
| **6 产品地图(多端×UI×流)** | [`product-map.md`](product-map.md) + [surface-ownership-inventory](../specs/active/2026-06-26-surface-ownership-inventory.md) + ARCHITECTURE §5 系统流 | A+B |
| **6b Mobile 动线知识图谱**(页面/动线/合理性审计/IA 重设计) | [`mobile-nav-map.md`](mobile-nav-map.md) + 代码派生图 [`_generated/mobile-nav-graph.json`](../_generated/mobile-nav-graph.json)(`mobile/scripts/dump_nav_graph.py` 生成) | A+B |

## 当前代码派生快照

生成文件中已列出的计数、roster、实体、关系与覆盖度以 [`docs/_generated/system-map.json`](../_generated/system-map.json) 为唯一真源；形状见 [`system-map.schema.json`](../_generated/system-map.schema.json)。本 INDEX 不手写任何会漂移的架构数字。`partial`/`declaration` 不是缺陷隐藏，而是明确机器发现边界。

## 维护(不靠自觉 —— 见 SKILL)

- **B 层**:改结构后跑 `python3.12 scripts/dump_system_map.py` 同时生成 canonical JSON 与 Agent 摘要,再跑 `./scripts/system-map-check.sh`；它使用独立 Python 3.12 `.venv`，统一验证 Schema、语义、两个生成物等值、Mobile nav 与 doc drift。
- **A 层**:动了某 facet 域 → 更新该 facet 文档 + bump `last-reviewed`(product-pipeline S8)。
- **新一类「会漂的结构」**:把它从 A 叙事挪进 B 生成结构，补静态扫描或受审 declaration、source/coverage、contract 测试与 drift 检查。
