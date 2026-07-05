# Agent-Operable Module Contract(Agent 操作面契约)

> Status: active paradigm v1
> Date: 2026-07-02
> Owner: Reva / Personal Health OS
> 起因: 实测"记录这个补剂(正官庄红参液)"— agent 识别/分析全对,却因补剂库
> 无 agent 建档通路而回"系统暂不支持,请去补剂管理页面手动添加"。
> Related: `docs/specs/active/2026-06-29-agent-native-dynamic-ui-atomic-capabilities.md`(前端原子能力)·
> `docs/HARNESS.md` · `AGENTS.md` · task #43(注册表+CI 闸落地)

## 1. Decision

**每个一等对象默认对 Agent 可操作(增删改查),不可操作是需要说明理由的例外。**
但实现方式**不是**每个模块手写一套 CRUD skills —— 仓库已有通用三件套
(`health_record` 写 / `health_query` 读 / `health_manage` 列/改/删),真正的
失败类是**覆盖空洞**:medication 有"未注册自动建档",supplement 没有,直到
用户在生产里撞上才暴露。所以本契约的核心是:

> **把"Agent 能对哪个对象做什么操作"从隐式代码事实,变成一张机器可校验的
> 注册表 + CI 闸 —— 空洞在 CI 红,不在用户嘴里。**

## 2. 反模式(本契约要终结的)

- ❌ 模块先做 UI,Agent 通路"以后再说" → 用户对着小巴说"帮我加",被推回手动页面。
- ❌ 每个模块各造一套专属 skill/工具 → 工具数爆炸,弱模型选不对工具。
- ❌ 能力有没有、全靠 grep 代码才知道 → medication/supplement 这类不对称静默存在。
- ❌ 新增写操作不定确认档位 → 要么全都二次询问(体验差),要么医疗级裸写(R4 破)。

## 3. 契约内容

### 3.1 操作面注册表(单一真源,machine-readable)

每个一等对象在注册表登记(建议落 `backend/app/services/agent_ops_registry.py`,
纯数据,同 `pgx_cpic_table` 风格):

```yaml
supplement_definition:
  create:  { via: health_record(supplement 自动建档), confirm: auto, undo: DELETE /supplements/definitions/{id} }
  read:    { via: health_query(dimension=supplement) }
  list:    { via: health_manage(list) }
  update:  { via: health_manage(update) }
  delete:  { via: health_manage(delete), confirm: typed_only }
medication:
  create:  { via: health_record(medication 自动建档), confirm: never_auto }   # 恒确认前置
  ...
opt_out 示例:
genetic_profile:
  create: { opt_out: "基因数据只能走文件导入+人审,agent 不得代写" }
```

### 3.2 确认档位(per-op,沿用 2026-07-02 通道感知体系)

| 档位 | 语义 | 例 |
|---|---|---|
| `auto` | 任何通道直接写,回显+可撤销 | water/diet/supplement 打卡、补剂建档 |
| `typed_only` | 打字通道免确认;语音/未声明通道确认前置 | symptom/rhinitis |
| `never_auto` | 恒确认前置(医疗级/不可逆/资金) | medication/dose/prescription/financial |

档位判定三问:可逆吗?医疗级吗(喂 DDI/PGx/剂量决策)?写错的失败方向是
over-alarm(安全)还是 under-alarm(危险)?

### 3.3 硬要求(每个 create/update/delete 通路)

1. **回显带对象号**:"已把「X」加入补剂库(补剂号 88,说「撤销」可移除)"——
   撤销回合快路由折叠上下文后,模型必须还有 id 可用(2026-07-02 撤销死环教训)。
2. **撤销通路真实存在**且在 health_manage delete 映射里注册。
3. **fail-loud 不静默**:找不到/建失败给友好兜底+原因,绝不吞;LLM 传错参数
   报合法值清单让它自纠(health_query 教训)。
4. **安全耦合只增不减**:写入喂安全规则的对象(补剂→DSI、用药→DDI),agent
   可写=安全脑覆盖面变大,这是**支持**开放 create 的理由,不是反对。
5. **SKILL.md 同步**:executor 内置通路和 `backend/skills` 同一能力,
   改一边必改另一边(本次:supplement 自动建档同 PR)。

### 3.4 CI 闸(落地后生效,task #43)

扩展 `check_doc_drift` 模式:遍历一等对象清单(governance §8),断言注册表
里 create/read/list/update/delete 五格**每格要么有通路、要么有带理由的
opt_out**;新增一等对象没登记 → CI 红。工具 schema 的 record_type/dimension
枚举与注册表比对,防"注册了但工具不认识"。

### 3.5 与前端原子能力契约的关系

`AtomicCapability`(2026-06-29 spec)管**展示与动作声明**;本契约管**后端
操作面**。同一对象两张表通过 object_type 对齐:卡片能挂的 action 必然对应
注册表里一个已登记操作 —— 前端白名单(ALLOWED_ACTIONS)与后端注册表将来
同源生成,杜绝 `ui.inline.expand` 式"后端发新动作、客户端静默丢"的漂移。

## 4. RequirementAdmission 增补字段

新功能准入(governance §8)增加一行:

```yaml
agent_operations: full | read_only | opt_out(<理由>)
```

默认 `full`;选 `read_only`/`opt_out` 必须给理由(医疗边界/人审要求/不可逆)。

## 5. First Application(随本 spec 同 PR 落地)

- ✅ `supplement_definition.create`:supplement 记录分支镜像 medication 自动
  建档(查无→POST /supplements/definitions→打卡→回显带补剂号+撤销出口);
  3 项契约测试(自动建档/已注册不重复建/建档失败友好兜底);SKILL.md 同步。
- 📋 task #43:注册表 + CI 闸 + 存量对象盘点(哪些对象哪些格还是空洞)。

## 6. Non-Goals

- 不为每对象手写专属工具(通用三件套 + 注册表驱动,工具数不膨胀)。
- 不给 agent 开"绕过确认档位"的口子:档位由注册表定,LLM/prompt 改不了。
- opt_out 对象(基因导入、账号删除、支付类)不因本契约被迫开放。

## 落地状态(2026-07-03)

task #43 已落地:

- **注册表**:`backend/app/services/agent_ops_registry.py`(纯数据,pgx_cpic_table
  风格;与前端 `atomic_capability_registry.py` 通过 object_type 对齐,见 §3.5)。
- **CI 闸**:`backend/tests/test_agent_ops_registry.py` —— 全部 source-derived
  (AST 扫 `agent_executor` 的 record_type 分支 / manage 映射 / query dimension
  + 直接 import 活的 `_FAST_RECORD_*_CONFIRM_KINDS`),注册表与 executor 双向
  比对,任一侧单改 → CI 红。随 backend pytest 在 CI 每次跑。

### 盘点出的空洞(均已在注册表显式挂账,gap/opt_out 字段)

1. **waist / sleep / excretion**:health_manage list/update/delete 有,
   health_record **create 缺** ——"记腰围 82"走不通(UI 有录入口)。
2. **supplement(打卡记录)**:create 有(auto),**list/update/delete 缺**
   (health_manage 只映射了 supplement_definition);后果:auto 写入的当日打卡
   **无撤销通路**(undo 只能撤自动建档的定义),违反 §3.3 硬要求 2,已用
   `undo_gap` 挂账。
3. **goal**:UI 有(web goals 页 / mobile Goals),agent 三件套零通路(整对象 gap)。
4. **medical_exam**:指标级读 OK(canonical 层);报告级 list 无通路。
5. **intervention_cycle**:status/start 有(专属工具);历史列表/参数调整/取消
   无通路。
6. **慢路径确认门不齐**:mood / supplement_group / garmin_sync 不在 AUTO 集
   (快路由 fail-closed 恒确认),但慢路径(quality 模型直调)无
   `_confirm_or_describe` —— 与 medication 修过的洞同类,未修。
7. **死代码**:`_exec_health_record` 的 `record_map["supplement"]` 不可达
   (supplement 分支恒 return)。
8. **per-op confirm 只在 create 有执行机制**(快路由 gate);§3.1 示例里
   delete 的 `typed_only` 档位尚无 executor 执行点,注册表如实只在 create
   登记 confirm。

### 确认档位现状(镜像 executor 活集合,CI 强制)

- `auto`:water / weight / blood_pressure / diet / exercise / reminder / supplement
- `typed_only`:symptom / rhinitis
- `never_auto`:illness / medication(executor NEVER 集∩注册面)+ fail-closed
  兜底(mood / supplement_group / garmin_sync / intervention_cycle)

### opt_out 登记

genetic_profile 建档/改删(导入+人审)· medical_exam 数值(人工核对管线)·
health_query 聚合面(只读)· garmin_sync / supplement_group 的记录管理
(触发/批量动作,非记录对象)。
