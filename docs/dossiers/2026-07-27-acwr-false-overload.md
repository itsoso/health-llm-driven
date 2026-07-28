# Dossier: 无慢性训练基线时禁止 ACWR 过载误报

| 字段 | 值 |
|---|---|
| slug | `acwr-false-overload` |
| 创建日期 | 2026-07-27 |
| 当前阶段 | G4 安全 |
| 状态 | shipping |
| 负责 | Codex |
| 反馈环 | backend deploy |

## S0 · 用户需求（逐字）
> 训练负荷过载数据有误 我最近没有锻炼

- 谁用 / 解决什么:近期无训练或慢性训练基线不足的 Reva 用户，不应收到 `ACWR=4.00` 高风险误报。
- 锚点用户相关性:错误健康告警会直接破坏 SafetyGuardian 的可信度，并可能给出不适用的训练建议。

## S1 · Discovery（现状勘察）
- `backend/app/services/exercise_recovery_service.py`:旧公式用 `(7 日均值)/(28 日均值)`，28 日窗口包含最近 7 天；单条近期负荷且此前无基线时数学结果固定为 `4.00`。
- `backend/app/agents/safety_guardian/rules/training_load.py`:旧规则只判断 `ACWR > 1.5`，不验证近期负荷与基线可靠性。
- `backend/app/services/episode/run_episode_parser.py`:存在第二套相同数学行为的 ACWR 计算。
- 硬约束:低可信数据必须 fail-closed 为“不计算”，但真实具备连续基线的负荷突增仍必须告警。

## G1 · 准入裁决
- first_class_objects:`SafetyGuardian`, `HealthTwin`。
- core_loop_step:wearable/workout data -> HealthTwin -> Safety Gate。
- target_surface / safety_level / autonomy_tier:backend / high / deterministic。
- spec_required:否，属于既有 SafetyGuardian 行为纠错。
- smallest_end_to_end_slice:统一 ACWR 可靠性判断，并覆盖 Twin、Episode、Safety Rule。
- **裁决**:PASS。

## S3 · 规划
1. 先用回归测试复现单条近期负荷得到 4.00。
2. 建立共享 ACWR assessment，要求最近 7 天有负荷且此前三个周窗口均有慢性基线。
3. Twin 和 Run Episode 共用该 assessment。
4. Twin 显式携带 ACWR 可靠性，Safety Rule 拒绝不可靠或与零急性负荷冲突的比率。

## G2 · 可行性 + 安全压测
- 漏报风险:不能简单禁用 ACWR；有连续三周基线的真实突增正例必须保留。
- 假阳性风险:近期无训练、单条新同步、基线集中在单周均不得发布比率。
- **裁决**:PASS。

## S5 · 实现
- 新增 `backend/app/services/training_load_metrics.py` 作为 ACWR 单一计算入口。
- `ExerciseRecoveryService` 对低可信比率返回 `acwr=None`, `acwr_zone=unknown` 和明确不可用原因。
- Run Episode 改用同一计算入口。
- Twin 传递 `acwr_reliable` 与不可用原因，Safety Guardian 的高负荷和低负荷规则均拒绝不可靠比率。
- Safety Guardian 另有零急性负荷一致性保护，避免陈旧缓存比率继续触发。

## G3 · 测试闸
- TDD 红灯:单条近期负荷旧实现得到 `4.00`；首场跑步 Episode 同样得到 `4.00`；不可靠字段未贯穿 Twin 时安全规则仍触发。
- 定向回归:训练负荷、Twin、Safety、Episode、运动计划、对话建议等 `414 passed`。
- 全量回归基线:运行到 31% 时 `2729 passed, 3 skipped`，按 `maxfail=5` 停止；4 项因沙箱禁止本地 HTTP 监听失败，1 项为与本改动无关的既有补剂同日 upsert 失败。
- 静态检查:`py_compile` 与 `git diff --check` 通过。
- doc drift:`scripts/check_doc_drift.py` 通过，生成事实已同步。
- **裁决**:绿。

## G4 · 安全闸
- 触发:Safety Guardian 训练负荷规则和对外健康建议。
- 评审:待独立 safety reviewer。
- **裁决**:待定。

## S6 · 部署
- 路由:backend-deploy。
- 部署 SHA / 回滚点:待提交。

## G5 · 部署健康闸
- 健康分:待部署。
- prod smoke:待部署。

## S7 · 上线验证
- 真实路径:近期无训练或基线不足时不再出现 ACWR 高风险卡；真实有基线过载仍可触发。
- 结果:待生产验证。

## G6 · 验证闸
- **裁决**:待用户真机确认。

## S8 · 沉淀
- 单条近期训练造成 `ACWR=4.00` 是窗口耦合的数学上限，不是高可信过载证据。
- ACWR 必须携带基线充分性语义，所有消费方只能读取已通过可靠性门的比率。
