<!-- system-map INDEX. 维护规则见 .claude/skills/system-map/SKILL.md。
     叙事区改完更新本文件顶部 last-reviewed;代码派生数字**绝不手写在这里**,只引用 docs/_generated/。 -->
---
doc: system-map/INDEX
last-reviewed: 2026-06-27
generated-sources:
  - docs/_generated/system-map.json
  - docs/_generated/mobile-access-map.json
extend-via: docs/specs/product-pipeline-contract.md
---

# System Map — 复元 Reva 系统全景(agent 先读这个)

> **这是任意 agent / 大模型理解「本系统是什么、在哪、怎么扩」的统一入口。** 不重写已有权威文档,只 INDEX 化 + 给「结构」加代码派生的当前性。维护机制(三层分治 / 防漂移 / 与流水线闭环)见 [`.claude/skills/system-map/SKILL.md`](../../.claude/skills/system-map/SKILL.md)。

## READ ORDER FOR AGENTS(按需读,别全读)

1. **想知道这系统是什么/能做什么** → 下方「facet 2 能力」+「facet 1 目标」。
2. **想知道某功能在哪个端/怎么连** → [`product-map.md`](product-map.md)(多端 × UI × 业务流 × 系统流)。
3. **想知道 Mobile 每个页面怎么走、用户动线是否合理** → [`mobile-access-map.md`](mobile-access-map.md) + [`docs/_generated/mobile-access-map.json`](../_generated/mobile-access-map.json)。
4. **想确认地图此刻可不可信** → [`docs/_generated/system-map.json`](../_generated/system-map.json)(代码派生,CI 校验;它是计数/roster 的唯一真源)。
5. **想扩一个功能** → [`product-pipeline-contract.md`](../specs/product-pipeline-contract.md)(需求→上线 6 道 Gate;S1 用本地图当现状输入)。
6. **想知道当前在做什么** → `docs/dossiers/`(在途 feature)。

## 三层分治(防漂移的核心)

| 层 | 哪些内容 | 真源 | 会漂吗 |
|---|---|---|---|
| **A 叙事** | 目标/规划理由/为什么/流程叙事 | 本文件 + 各 facet 文档(带 `last-reviewed`) | 靠新鲜度门 + S8 回写 |
| **B 代码生成** | 一切计数、roster、Mobile 页面/边/旅程图谱 | `docs/_generated/system-map.json` + `docs/_generated/mobile-access-map.json`(生成器输出,`check_doc_drift.py` CI 校验) | **零**(代码即真源) |
| **C 在途** | 当前在做的 feature | `docs/dossiers/`(product-pipeline 脊柱) | 零(流水线在写) |

**铁律**:任何计数(规则数/specialist 数/路由数/…)**只准从 `docs/_generated/system-map.json` 引用,绝不手打进任何叙事**。手打的数字必漂(实证:ARCHITECTURE 曾 `(51 条)`、PRODUCT_ROADMAP 当日写错 `56`)。

## 6 facet × 权威位置

| facet | 权威文档(点过去,不重写) | 层 |
|---|---|---|
| **1 系统目标/北极星** | [`reva-product-governance-spec.md`](../specs/reva-product-governance-spec.md) §1/§3/§4 · [`reva-personal-health-os-prd.md`](../prd/reva-personal-health-os-prd.md) §1 | A |
| **2 产品能力** | 一等对象:governance §5(11 个)· 多 agent fleet:[`ARCHITECTURE.md`](../ARCHITECTURE.md) §四 + [`CLAUDE.md`](../../CLAUDE.md) · roster/计数:`_generated/system-map.json` · 成熟度:[AS-IS PRD](../prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md) §1.4 | A+B |
| **3 产品规划** | [`PRODUCT_ROADMAP.md`](../PRODUCT_ROADMAP.md)(战略 H1–H4)· 近期 Phase:AS-IS PRD §7 · 在途:`docs/dossiers/` | A+C |
| **4 系统架构** | [`ARCHITECTURE.md`](../ARCHITECTURE.md) + CLAUDE.md §Architecture(计数由 `check_doc_drift` 钉) | A+B |
| **5 未来规划** | reva-personal-health-os-prd.md §10 待拍板 · AS-IS PRD §3/§10 | A |
| **6 产品地图(多端×UI×流)** | [`product-map.md`](product-map.md) + [`mobile-access-map.md`](mobile-access-map.md) + [surface-ownership-inventory](../specs/active/2026-06-26-surface-ownership-inventory.md) + ARCHITECTURE §5 系统流 | A+B |

## 当前代码派生快照

计数与 roster 只读 [`docs/_generated/system-map.json`](../_generated/system-map.json)。Mobile 页面节点、导航边、用户旅程和 IA 评估只读 [`docs/_generated/mobile-access-map.json`](../_generated/mobile-access-map.json)。Mobile 展示层读取同源生成的 `mobile/constants/systemMap.generated.ts` 与 `mobile/constants/mobileAccessMap.generated.ts`;不要把 live 数字复制进本文。

## 维护(不靠自觉 —— 见 SKILL)

- **B 层**:改系统结构后跑 `python scripts/dump_system_map.py`;改 Mobile 路由/入口/静态跳转后跑 `python scripts/dump_mobile_access_map.py`;`check_doc_drift.py`(CI 已跑)校验,不符即红 → 物理上无法带漂移上线(product-pipeline G3)。
- **A 层**:动了某 facet 域 → 更新该 facet 文档 + bump `last-reviewed`(product-pipeline S8)。
- **新一类「会漂的结构」**:把它从 A 叙事挪进 B 代码生成 + 加一条 `dump_system_map.py` 字段 + drift 检查。
