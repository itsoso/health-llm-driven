# Dossier: 无慢性训练基线时禁止 ACWR 过载误报

| 字段 | 值 |
|---|---|
| slug | `acwr-false-overload` |
| 创建日期 | 2026-07-27 |
| 当前阶段 | S7 上线验证 |
| 状态 | production-validation |
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
2. 建立共享 ACWR assessment，区分“已观测的休息日”和“设备未同步”，并要求近期及慢性窗口达到可信覆盖。
3. Twin 和 Run Episode 共用该 assessment。
4. Twin 显式携带 ACWR 可靠性，Safety Rule 拒绝不可靠或与零急性负荷冲突的比率。

## G2 · 可行性 + 安全压测
- 漏报风险:不能简单禁用 ACWR；有连续三周基线的真实突增正例必须保留。
- 假阳性风险:近期无训练、单条新同步、同步覆盖不足、异常数值和极小慢性基线均不得发布比率。
- **裁决**:PASS。

## S5 · 实现
- 新增 `backend/app/services/training_load_metrics.py` 作为 ACWR 单一计算入口。
- `ExerciseRecoveryService` 使用用户本地日期，只读取 `WorkoutRecord`，并将所有来源统一换算成时长/心率推导的 TRIMP；不再混用 Garmin 私有负荷与推导值。
- 普通 Garmin 日健康记录不再被当成“训练已同步”的覆盖证据；无法区分“无训练”和“未同步”时一律返回 `insufficient_data_coverage`，不生成安全告警。
- 可靠基线必须覆盖之前三个独立周、至少三个活跃日且 21 日推导负荷不低于 30；负数、NaN、Inf 或畸形输入 fail-closed。
- Run Episode 直接复用 `ExerciseRecoveryService`，不再维护第二套日期和负荷提取逻辑。
- Episode 的无时区时间先附着用户时区再转 UTC，并以落库后的本地 `workout_date` 计算 ACWR。
- Twin 传递 `acwr_reliable` 与不可用原因，Safety Guardian 的高负荷和低负荷规则均拒绝不可靠比率。
- Safety Guardian 另有非有限数、零急性负荷一致性保护；“完全无训练”仅在专用训练覆盖信号明确证明 7 日均已观测时才可提示。
- Twin / Safety 缓存分别升到 `v2` / `v3`，Twin 写失效会同步清除派生 Safety 报告。
- 手工运动增删改、Garmin 同步以及心率/GPS/分圈补全均会使 Twin 与派生 Safety 缓存失效。
- Safety 行动卡仅对 ACWR 规则做定向 reconciliation：规则消失时归档，真实风险复发时重新激活；不影响其他安全卡。

## G3 · 测试闸
- TDD 红灯:单条近期负荷旧实现得到 `4.00`；首场跑步 Episode 同样得到 `4.00`；不可靠字段未贯穿 Twin 时安全规则仍触发。
- 首轮定向回归:训练负荷、Twin、Safety、Episode、运动计划、对话建议等 `414 passed`。
- 安全整改后核心回归:`151 passed`；扩大到全部 Twin、Safety、行动卡、运动与恢复模块的回归:`432 passed`。
- 全量回归基线:首轮运行到 31% 时 `2729 passed, 3 skipped`，按 `maxfail=5` 停止；4 项因沙箱禁止本地 HTTP 监听失败，1 项为与本改动无关的既有补剂同日 upsert 失败。复跑时该补剂协议幂等失败可单文件稳定复现（`8 passed, 1 failed`），与 ACWR 改动文件和调用链无交集。
- 第二次独立评审整改后的 TDD 定向回归:`37 passed`，覆盖 Garmin 同步缓存失效、统一 TRIMP、缺失覆盖、异常输入、用户本地日期和 ActionCard 生命周期。
- 扩大回归:Safety、Twin、Workout、Episode、ActionCard 共 `301 passed`。
- 第三轮评审整改 TDD:中央 Garmin writer 缓存失效用例先稳定失败，整改后定向 `5 passed`；Safety、Twin、Workout、Episode、ActionCard 扩大回归 `161 passed`。
- 静态检查:`py_compile` 与 `git diff --check` 通过。
- 阻断级 Ruff (`F821,F822,E9`) 通过。
- doc drift:`scripts/check_doc_drift.py` 通过，生成事实已同步。
- **裁决**:绿。

## G4 · 安全闸
- 触发:Safety Guardian 训练负荷规则和对外健康建议。
- 首轮独立评审:`NO-GO`。阻断项为旧缓存缺少 reliability 时仍可能触发、Safety 派生缓存未随 Twin 失效、旧 ACWR 行动卡不会归档；同时指出时区、NaN/Inf、休息周与缺失数据混淆、Episode 口径漂移。
- 整改:Safety 只接受 `acwr_reliable is True`；版本化并联动失效缓存；加入 ACWR 卡片生命周期 reconciliation；观测覆盖允许一个真实休息周但拒绝缺失同步；拒绝异常数值与极小慢性基线；统一用户时区和 Episode 计算入口。
- 第二轮独立评审:`NO-GO`。阻断项为普通 Garmin 日数据伪造训练覆盖、运动写入/同步未完整失效缓存、负数负荷回落到时长、供应商负荷与推导 TRIMP 混量纲、缺失覆盖被误判为零训练、Episode 无时区时间按 UTC 解释、Safety 缺最终有限数检查。
- 第二轮整改:训练覆盖与日健康数据解耦；所有 Workout 写入口联动失效；统一推导 TRIMP；异常输入全链 fail-closed；缺失覆盖不再产生“本周零运动”；Episode 使用用户本地日期；Safety 最终消费点再次验证有限数。
- 第三轮独立评审:`NO-GO`。发现 `WorkoutSyncService` 的中央写入出口未失效缓存，导致认证同步、定时任务和跑后分析等调用方可能继续读取最长 300 秒的旧 Safety 结果。
- 第三轮整改:缓存失效下沉到中央 Garmin writer；只有成功持久化新增或补全活动时才清理 Twin、Safety 和预生成建议，无数据变化时不清理；调用方自动继承该不变量。
- 第四轮独立复审:`GO`。验证新增、更新/补全、无变化及提交后异常路径；确认中央失效链覆盖 Twin、全部 Safety 参数缓存及启用状态下的 pregen。
- **裁决**:GO。

## S6 · 部署
- 路由:backend-deploy。
- 2026-07-28 按项目部署治理完成生产发布；敏感备份、目标、版本与回滚证据保留在受控部署审计中，不写入版本库。

## G5 · 部署健康闸
- 部署脚本健康检查、线上版本核验与只读外部冒烟检查均通过；详细证据保留在受控部署审计中。
- **裁决**:PASS。

## S7 · 上线验证
- 真实路径:近期无训练或基线不足时不再出现 ACWR 高风险卡；真实有基线过载仍可触发。
- 自动验证:生产服务、依赖和版本均已核验；重启使旧进程内 Twin/Safety 缓存失效。
- 用户路径:待用户下一次安全报告或 Agent 对话验证，不应再产生新的 `ACWR=4.00` 误报。历史对话中已保存的旧告警内容不会改写。

## G6 · 验证闸
- **裁决**:待用户真机确认。

## S8 · 沉淀
- 单条近期训练造成 `ACWR=4.00` 是窗口耦合的数学上限，不是高可信过载证据。
- ACWR 必须携带基线充分性语义，所有消费方只能读取已通过可靠性门的比率。
