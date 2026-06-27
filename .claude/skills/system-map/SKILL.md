---
name: system-map
description: "系统透明化层:维护一张『永远当前、agent 一遍读懂』的系统全景 —— 目标/能力/规划/架构/未来 + 多端×UI×业务流×系统流。当用户说『这系统是什么/有哪些能力/架构是什么/产品全景/系统现状/onboard 这个项目/系统地图/system map』,或任何 agent 开工前要秒懂现状时,先读 docs/system-map/INDEX.md。本 skill 定义该地图的结构、防漂移机制、与 product-pipeline 的读写闭环;它不重写已有权威文档,而是把它们 INDEX 化 + 给『结构』加代码生成的当前性。"
---

# System Map — 系统透明化层(agent-first 永远当前)

> **一句话**:让任意 agent **读一个入口(`docs/system-map/INDEX.md`)就知道「这系统有什么、在哪、怎么扩」**,且不会过时。
> **铁律(命根子)**:一个事实只允许两种状态 —— ① **从代码生成进无人手改的文件**(`docs/_generated/system-map.json`),或 ② **带 `last-reviewed` 日期的纯叙事**(显式不含 live 数字)。**致命的第三态——手打 live 数字进叙事——结构性禁止**(实证:它害死了 ARCHITECTURE `(51 条)`、PRODUCT_ROADMAP 当日写错 `56`)。

## 产物

```
docs/system-map/
├── INDEX.md          ← agent 先读。read-order + 6 facet 指针 + 三层分治 + 防漂移
└── product-map.md    ← 多端 × UI × 业务流 × 系统流(叙事 + last-reviewed)
docs/_generated/
└── system-map.json   ← 代码派生:计数 + roster。无人手改;scripts/dump_system_map.py 生成
scripts/dump_system_map.py   ← 生成器(复用 check_doc_drift 扫描器,确定性输出)
scripts/check_doc_drift.py   ← CI 已跑;新增校验 committed JSON == 代码(不符即红)
```

多数 facet **不在 system-map 里重写**,INDEX 指向已有权威文档(governance/PRD/ARCHITECTURE/surface-inventory)。本 skill 的价值 = 入口 + 防漂移 + 维护协议。

## 三层分治

| 层 | 内容 | 真源 | 漂移 |
|---|---|---|---|
| **A 叙事** | 目标/规划理由/为什么/流程/端 roster | INDEX + facet 文档(`last-reviewed`) | 靠新鲜度门 + S8 回写 |
| **B 代码生成** | 一切计数 + roster | `docs/_generated/system-map.json` | **零** |
| **C 在途** | 当前在做的 feature | `docs/dossiers/` | 零 |

## 防漂移机制(已实现)

1. **生成器** `scripts/dump_system_map.py` —— 复用 `check_doc_drift.py` 的扫描器(单一真源),输出确定性 JSON(全 sorted、无时间戳)。改代码后跑它重新生成。
2. **CI 闸** `check_doc_drift.py`(CI 已跑)新增:`build_map()` 重算 vs committed `docs/_generated/system-map.json`,不符即 exit 1。**地图与代码不符 → CI 红 → product-pipeline G3 拦住,物理上无法带漂移上线。** 另加 regex 补丁堵 `规则分类(N 条)` 子标题漏检(Hook 3)。
3. **叙事新鲜度**:每个叙事文档 front-matter `last-reviewed: YYYY-MM-DD`;读者据此判断「叙事是否可信、计数永远信 `_generated`」。
4. **在途**:`docs/dossiers/` 由 product-pipeline 写,天然当前。

## 与 product-pipeline 闭环(不靠自觉)

- **S1 Discovery 读地图**:实现新功能前读 INDEX 秒懂现状。
- **S8 沉淀写回**:① B 层 —— 改代码必跑 `dump_system_map.py` 提交(否则 G3 红);② A 层 —— 动了某 facet 域则更新该文档 + bump `last-reviewed`。
- **关键**:enforcement 在 **G3**(硬闸,JSON 不符即红,不可跳),authorship 在 **S8**。别只靠 S8(它是最易跳的末步)。

## Agent 读法

INDEX 顶部 READ ORDER:① 能力/目标 → INDEX 表;② 功能在哪/怎么连 → product-map;③ 地图可不可信 → `_generated/system-map.json`(它是计数真源);④ 怎么扩 → product-pipeline 契约;⑤ 当前在做 → dossiers。每文档 YAML front-matter + 稳定锚点,LLM 不靠猜。

## 加一类新「会漂的结构」时

把它从 A 叙事挪进 B 代码生成:① `dump_system_map.py` 加一个 `build_map()` 字段(复用/新增 check_doc_drift 扫描器);② 跑生成器更新 JSON;③ check_doc_drift 的等值比对自动覆盖(无需改比对逻辑);④ 叙事里删掉手打的该数字,改引用 `_generated`。

## 跨 agent / 跨项目

- 本仓:`CLAUDE.md` doc-map + `AGENTS.md` 指向 `docs/system-map/INDEX.md`(agent 开工先读)。
- 跨项目:透明化标准与 `product-pipeline-contract.md` 并列(全局 `~/work/personal/PRACTICES/`);每项目建自己的 `docs/system-map/INDEX.md` + `dump_system_map.py` 填本项目实情。

## 边界

- 不重写 PRD/ARCHITECTURE/governance —— 只 INDEX 化 + 加防漂移。
- 只钉「代码可生成的计数」进 CI;叙事用 `last-reviewed`,不钉 CI(否则逼出假 bump)。
- 纯本地工具项目可极简(只 INDEX + 端表)。

## 演进

每 feature 上线(S8)更新地图;每发现一类新「会漂的结构」按上面 4 步挪进 B 层。地图越用越准。**实证**:本 skill 首次落地,regex 补丁即逮到 main 上 ARCHITECTURE `(51 条)` 真漂移(代码 63)。
