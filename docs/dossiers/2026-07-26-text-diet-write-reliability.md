# Dossier: 文本饮食写入可靠性

| 字段 | 值 |
|---|---|
| slug | `text-diet-write-reliability` |
| 创建日期 | 2026-07-26 |
| 当前阶段 | G6 上线验证 |
| 状态 | deployed-awaiting-functional-verification |
| 负责 | Codex |
| 反馈环 | Backend pytest / backend deploy |

## S0 · 用户需求（逐字）

> 最基本的保存饮食都不行了

生产失败原句：

```text
记录午餐5个虾100克大黄鱼200克哈密瓜
```

用户明确给出餐次和食物后，Agent 没有保存，而是要求补充记录类型和值。

## S1 · 现状勘察

- 意图分类已正确识别为 `write / diet / create`。
- Agent Kernel 的 `simple_health_record` 只覆盖饮水和症状，没有覆盖明确文本餐食。
- 模型若返回文字而没有结构化工具调用，确定性回退无法构建饮食 payload，最终错误进入通用澄清文案。
- 饮食 API 与数据库不是故障层；最小契约已支持
  `record_date + meal_type + food_items`。

## G1 · 准入裁决

- classification: reliability restoration
- first_class_objects: `WriteIntent`、`ExecutionEvent`
- core_loop_step: explicit observation -> verified diet execution event
- target_surface: Agent Backend source of truth；Mobile/Mac/Web 共用
- safety_level: L3 health data
- autonomy_tier: 当前轮明确写入意图；不扩大原有自治范围
- success_metric: 明确单餐文本 exactly-one verified diet write
- smallest_end_to_end_slice: 单一餐次 + 非空食物内容
- **裁决：PASS。** 恢复现有 Agent Native 饮食记录闭环，不新增产品面。

## S2 · PRD

- 维护性修复，不新增 PRD；以现有 Personal Health OS 捕获与 `WriteIntent`
  契约为准。
- 边界：不解析多餐为一次写入；不为缺失食物猜测；不改变药物或临床写入边界。

## S3 · 规划

1. 把明确单餐文本编译为当前轮拥有的 typed goal。
2. 模型漏调工具时生成唯一确定性 `health_record(diet)`。
3. 模型食物改写与当前输入不一致时，以用户输入覆盖。
4. 只有取得 verified `diet_record` receipt 才报告成功。
5. 用 exact production sentence、歧义、日期、重复写和回执做回归。

## G2 · 可行性与安全压测

- 缺食物、多餐、否定、疑问和无效日期保持 fail-closed。
- 明确取消在 IntentFrame 降为非写入，并由 Capability Policy 二次阻断。
- 显式但不存在的日期生成需要澄清的 Goal，任何 mutation 均被阻断。
- 模型营养估算仅在餐次和归一化食物身份等价时保留。
- 确定性调用仍通过 ToolGateway、参数校验、幂等 checkpoint、业务 API 和 receipt。
- 已有 receipt 时不再生成 fallback，避免重复写入。
- **裁决：PASS。** 不放宽 Runtime circuit、确认策略、数据库或客户端契约。

## S4 · 研发任务

- [x] T1 typed diet goal 与日期/餐次/食物提取。
- [x] T2 模型漏调工具时的确定性写入回退。
- [x] T3 用户 payload 权威化与等价营养估算合并。
- [x] T4 verified diet receipt 后置条件。
- [x] T5 exact production sentence 与相邻风险回归。
- [x] T6 修复主干已有 OpenAPI 客户端类型漂移。
- [x] T7 修复独立审查发现的日期静默改写与食物偏好误判。
- [x] T8 修复非法显式日期回退今天及取消语句绕过工具策略。
- [x] T9 修复确定性短确认误截断复合分析的多模型回归。

## Gate 状态

- G3 测试：**PASS**
  - Agent 目标、guard、postcondition、force-tool、日期 guard、完成状态、
    Capability Policy、ToolGateway、饮食 adapter 和最小 API 契约：
    308 passed。
  - Python bytecode compilation、Ruff、Mobile TypeScript 与
    `git diff --check` 通过。
  - CI `agent-i-z` 首轮发现多模型工具调用完成后被错误短路为
    `已记录午餐。`；短确认现只适用于服务端确定性补偿写入。
  - 修复后按 CI 原命令运行完整 `agent-i-z` 分片：
    532 passed、3 skipped；Ruff、`py_compile` 与 `git diff --check` 通过。
  - 覆盖生产原句、常见文本变体、缺食物、多餐、模型漏调工具、模型改写、
    等价营养估算、确定性 fallback、verified receipt、食物偏好和日期拒绝。
  - 真实模型隔离回归通过：invariants 12/12、health_agent_core 50/50、
    orchestrator 5/5、trajectory contract 11/11，实际模型
    `MiniMax-M2.5`。
  - GitHub CI
    [30196655971](https://github.com/itsoso/health-llm-driven/actions/runs/30196655971)
    attempt 2 全部通过；`backend-test-p` 首次受 runner 超时影响，按同一命令本地
    350 passed，并在失败任务重跑后通过。
- G4 安全：**PASS**
  - 首轮独立审查发现并阻断两项风险：无效/远日期被静默改成今天，
    以及「不要辣／别放香菜／需要少盐」被误判为取消记录。
  - 已改为错误日期 fail-loud 且保留原值；食物偏好继续写入，
    只有「不要记录午餐…」等明确撤销才阻止写入。
  - 第二轮独立审查又发现非法显式日期仍可在 Goal 编译时回退今天，
    以及取消语句可能绕过 deterministic fallback 后由模型直接调用工具；
    已分别改为 clarification Goal + policy block，以及 intent + policy 双重阻断。
  - 最终独立复审结论：**GO**。生产原句、偏好词、明确取消、非法日期、
    exactly-once 和 verified receipt 五类边界均成立，无新增 P0/P1。
- G5 部署健康：**PASS**
  - 从干净 `main` 部署提交
    `ad617eab0ab7282cfdf1e2978a7e2ea685e9a1dd`。
  - 生产数据库备份与恢复演练通过，受控迁移无待执行项。
  - 部署脚本健康度 58/60、Skills 22/22、远端版本核验通过。
- G6 上线验证：**IN PROGRESS**
  - 公网 `/api/v1/health` 返回 `healthy`，API、PostgreSQL、Redis、
    Celery 均为 `connected/running`。
  - 未经明确授权不在生产创建真实用户饮食测试记录；等待用户用原句完成最终
    功能验证。
