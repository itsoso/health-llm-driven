---
name: system-map
description: "系统透明化层:维护一张『永远当前、agent 一遍读懂』的系统全景 —— 目标/能力/规划/架构/未来 + 多端×UI×业务流×系统流。当用户说『这系统是什么/有哪些能力/架构是什么/产品全景/系统现状/onboard 这个项目/系统地图/system map』,或任何 agent 开工前要秒懂现状时,先读 docs/system-map/INDEX.md。本 skill 定义该地图的结构、防漂移机制、与 product-pipeline 的读写闭环;它不重写已有权威文档,而是把它们 INDEX 化 + 给『结构』加代码生成的当前性。"
---

# System Map — 系统透明化层(agent-first, generated-current)

> **一句话**:让任意 agent **读一个入口(`docs/system-map/INDEX.md`)就知道「这系统有什么、在哪、怎么扩」**，并能区分已验证的生成字段与需要人工复核的叙事。
> **铁律(命根子)**:一个事实只允许两种状态 —— ① **从代码生成进无人手改的文件**(`docs/_generated/system-map.json`),或 ② **带 `last-reviewed` 日期的纯叙事**(显式不含 live 数字)。**致命的第三态——手打 live 数字进叙事——结构性禁止**(实证:它害死了 ARCHITECTURE `(51 条)`、PRODUCT_ROADMAP 当日写错 `56`)。

## 产物

```
docs/system-map/
├── INDEX.md          ← agent 先读。read-order + 6 facet 指针 + 三层分治 + 防漂移
└── product-map.md    ← 多端 × UI × 业务流 × 系统流(叙事 + last-reviewed)
docs/_generated/
├── system-map.json          ← v2 生成物:计数/roster + typed entities/relations/coverage
├── system-map-agent-context.md ← 每个 coding agent 开工必读的有界全局摘要(同图派生)
├── system-map.schema.json   ← Draft 2020-12 固定契约
└── mobile-nav-graph.json    ← Mobile 页面与静态导航边
docs/system-map/declarations.json ← 无法可靠扫描的稳定组件/资源/关系声明(不含计数)
scripts/dump_system_map.py          ← 确定性生成器
scripts/system_map_context.py       ← 只读局部图查询(path/entity/flow/keyword,0–2 层)
scripts/check_system_map.py         ← JSON Schema + 语义 + 生成物 + Mobile nav + doc drift 中央闸
scripts/system-map-check.sh         ← 本机 Python 3.12 独立 .venv 入口
```

多数 facet **不在 system-map 里重写**,INDEX 指向已有权威文档(governance/PRD/ARCHITECTURE/surface-inventory)。本 skill 的价值 = 入口 + 防漂移 + 维护协议。

## 三层分治

| 层 | 内容 | 真源 | 漂移 |
|---|---|---|---|
| **A 叙事** | 目标/规划理由/为什么/流程/端 roster | INDEX + facet 文档(`last-reviewed`) | 靠新鲜度门 + S8 回写 |
| **B 生成结构** | 计数/roster + `schema_version` + typed `entities`/`relations`/`coverage` | `docs/_generated/system-map.json` | **所覆盖的生成字段零漂移** |
| **C 在途** | 当前在做的 feature | `docs/dossiers/` | 零 |

## v2 契约与覆盖边界

- `schema_version: "2.0"`；实体类型受控为 component/surface/api/resource/job，关系类型同样由 contract 白名单裁决。
- 每个实体和关系必须带 `source` 与 `coverage`。`complete` 只表示该扫描器在声明范围内完整；`partial` 明示动态注册等限制；`declaration` 表示事实来自受审声明而非代码推导。
- JSON Schema 负责形状，`scripts/system_map_contract.py` 负责唯一 ID、已解析端点、排序和关系语义。两层都通过才可服务。
- 生成器当前纳入的结构字段可被等值检查；叙事、新鲜度和未纳入扫描器的动态行为**不宣称零漂移**，仍靠 `last-reviewed` 与 coverage limitations 表达。

## 防漂移机制(已实现)

1. **生成器** `scripts/dump_system_map.py` —— 复用 `check_doc_drift.py` 的扫描器(单一真源),输出确定性 JSON(全 sorted、无时间戳)。改代码后跑它重新生成。
2. **Mobile 导航硬闸** `python mobile/scripts/dump_nav_graph.py --check` —— 只读比较，不在检查模式覆盖生成物。
3. **中央验证** `./scripts/system-map-check.sh` —— 强制 Python 3.12，在根目录独立 `.venv` 安装 pinned `jsonschema`，再串行执行 Schema/语义验证、System Map 等值、Mobile nav 等值和 doc drift。依赖哈希未变化时复用环境。
4. **CI / pre-commit / validate.py** —— 都调用同一中央检查路径；CI 使用已安装依赖的 Python，不在 runner 内另建 `.venv`。
5. **叙事新鲜度**:每个叙事文档 front-matter `last-reviewed: YYYY-MM-DD`;读者据此判断叙事是否可信。

## 与 product-pipeline 闭环(不靠自觉)

- **S1 Discovery 读地图**:实现新功能前读 INDEX 秒懂现状。
- **S8 沉淀写回**:① B 层 —— 改代码先跑生成器，再跑 `./scripts/system-map-check.sh` 并提交生成物；② A 层 —— 动了某 facet 域则更新该文档 + bump `last-reviewed`。
- **关键**:enforcement 在 **G3**(硬闸,JSON 不符即红,不可跳),authorship 在 **S8**。别只靠 S8(它是最易跳的末步)。

## Agent 读法

所有 coding agent 固定按以下顺序启动:① `AGENTS.md`;② `docs/system-map/INDEX.md`;③ `docs/_generated/system-map-agent-context.md` 加载有界全局认知;④ 用 `python3.12 scripts/system_map_context.py` 按任务查询局部上下游;⑤ 打开结果中的 source path 和附近测试,再制定计划或形成结论。常用示例:

```bash
python3.12 scripts/system_map_context.py --entity component.mobile --depth 0
python3.12 scripts/system_map_context.py --flow agent-chat
python3.12 scripts/system_map_context.py --path backend/app/api/
python3.12 scripts/system_map_context.py --keyword notification --depth 0
```

**证据优先级：代码与测试 > 代码派生 System Map > 受审声明 > 带新鲜度的叙事。地图不能替代源码和测试验证。** `partial`/`declaration` 命中必须按 `VERIFY SOURCE` 警告回到代码。宽查询超过上限会显式失败,agent 应缩小 selector/depth,不能要求静默截断。摘要/查询只是 canonical `_generated/system-map.json` 的派生视图,不构成第二真源。

管理员可在 `/admin/system-map` 查看同一份 canonical 生成物；API `/api/v1/admin/system-map` 与页面都复用现有管理员权限。研发 agent 直接读仓库生成物,不调用管理员 API。CI 能验证摘要当前、确定且入口接线存在,但不能证明模型真的读过；地图闸门失败时停用地图并回到代码、测试和注册表调查。

## 加一类新「会漂的结构」时

把它从 A 叙事挪进 B 生成结构:① `dump_system_map.py` 增加静态扫描或在 `declarations.json` 加受审声明；② 补 source/coverage 和 contract 测试；③ 跑生成器更新 JSON；④ 跑 `./scripts/system-map-check.sh`；⑤ 叙事里删掉重复动态事实，改引用 `_generated`。

## 跨 agent / 跨项目

- 本仓:`CLAUDE.md` doc-map + `AGENTS.md` 指向 `docs/system-map/INDEX.md`(agent 开工先读);研发 skill 触发绑定见 `docs/agent-skill-binding.md`。
- 跨项目:透明化标准与 `product-pipeline-contract.md` 并列(全局 `~/work/personal/PRACTICES/`);每项目建自己的 `docs/system-map/INDEX.md` + `dump_system_map.py` 填本项目实情。

## 边界

- 不重写 PRD/ARCHITECTURE/governance —— 只 INDEX 化 + 加防漂移。
- 只钉已进入生成器/声明契约的结构字段；叙事用 `last-reviewed`，不把 narrative freshness 假装成机器证明。
- 纯本地工具项目可极简(只 INDEX + 端表)。

## 演进

每 feature 上线(S8)更新地图;每发现一类新「会漂的结构」按上面 4 步挪进 B 层。地图越用越准。**实证**:本 skill 首次落地,regex 补丁即逮到 main 上 ARCHITECTURE `(51 条)` 真漂移(代码 63)。
