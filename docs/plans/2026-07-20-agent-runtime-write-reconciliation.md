# Agent Runtime Write Reconciliation Implementation Plan

> 按 TDD 执行；每一批先看到预期失败，再写最小实现。生产 circuit 在整个实施期保持 paused，canary 保持 0%。

## Task 1 · 预期资源类型

- [x] 在 ToolSpec/Registry 为可核对写入声明预期 `resource_type`。
- [x] 让 Runtime claim 在业务 dispatch 前保存并校验该类型。
- [x] 测试: diet write claim 为 `diet_record`；类型不一致拒绝；Runtime ledger 不出现正文。

## Task 2 · 下游幂等键

- [x] 增加 write-operation 请求作用域。
- [x] Executor dispatch managed write 时设置 scope，结束时可靠 reset。
- [x] localhost diet POST 接收 `Idempotency-Key: <operation_id>`。
- [x] 测试: managed diet write 带稳定 key；read/unmanaged 请求不带；并发 task 不串键；重复 key 只产生一条饮食记录。

## Task 3 · 资源级核对与结算

- [x] 建立 resolver registry，首批只注册 `diet_record` create。
- [x] diet resolver 以 `(user_id, client_action_id)` 查记录并返回 verified-effect / verified-no-effect / unknown。
- [x] 增加 Runtime reconciliation settle 方法和 content-free 事件。
- [x] recovery scanner 在进入最终未决后调用 resolver，并保证 resolver 故障不绕过 rollout circuit。
- [x] 测试: 写后退出可 replay；写前退出可重试；宽限内不判无副作用；未知资源继续 reconciliation；数据库错误不放行。

## Task 4 · 显式旧事故结算

- [x] 增加管理员鉴权的 opaque operation resolution API。
- [x] 只允许 `verified_effect` 或 `verified_no_effect`，要求 verification method 与 reason code，不接收健康正文。
- [x] 幂等、审计、owner isolation 和非法状态测试。

## Task 5 · 饮食 correction 意图与路由

- [x] 增加 quantity-correction semantic signal，不依赖单一关键词。
- [x] 将有餐次目标的“少吃/只吃部分/实际数量”分类为 `mutate/diet/update`。
- [x] fast route 使用 `health_manage`，复用唯一目标校验，禁止 fallback create。
- [x] 测试生产原句、分数绑定边界、唯一目标和歧义目标正反例。

## Task 6 · 验证与发布

- [x] SQLite focused Runtime/Agent/diet tests。
- [x] 真实 PostgreSQL 状态机、并发、resolver、图片饮食事务和 migration tests。
- [x] CI 新增真实 PostgreSQL migration upgrade、重复执行、行锁和 Runtime 语义硬门。
- [x] Agent conversation、照片饮食、intent、ToolGateway 回归。
- [x] Ruff、diff check、system-map drift、Dossier consistency。
- [x] 独立安全复审；最终结论无 P0/P1，仅提交本任务文件。
- [x] 合并主干和 CI 全绿后通过 `deploy.sh` 部署；保持 paused/0%。
- [ ] 用应用服务结算当前旧 operation，再做单账号 read/write/worker interruption 演练并重新裁决 G5/G6。
  - [x] 旧 operation 已通过应用服务结算为 `verified_no_effect`；生产不再存在 `reconciliation_required` Run/operation。
  - [ ] Runtime circuit 仍暂停且 `AGENT_RUNTIME_MODE=off`；单账号受控 read/write/worker interruption 演练待显式开启 canary 后执行。

## Task 7 · 多写入重试身份与流式诚实性

- [x] 为每笔逻辑写入增加独立 `logical_operation_key_hash` 账本字段与 PostgreSQL/SQLite 迁移。
- [x] Executor 使用顺序无关的业务目标键；exact fingerprint 优先兼容旧 operation 和参数未变化的重试。
- [x] 重试按 lineage 精确 replay / retry，不再按 tool/resource scope 猜测。
- [x] retry 无法映射到原计划的新增写入以 `retry_plan_mismatch` fail closed，不执行副作用。
- [x] migration 回填旧 operation lineage，升级前记录可 exact replay，不触发唯一约束冲突。
- [x] operation 保存首次创建 attempt 编号，retry 计划校验只比较历史 attempt，不误伤当前 retry 的后续写入。
- [x] 同一餐不同食物使用不同业务目标；同一 Run 内若没有明确餐次/时间/照片区分证据则合并记录或 fail closed，不能仅凭模型重述新增副作用。
- [x] 同日同餐同名食物按两个明确不同的 `meal_time` 区分；可选 `food_id` 不切换业务身份。
- [x] 规范化日期+餐次范围和照片/时间区分器独立落哈希账本；别名、缺省日期、区分器单边出现、类型变化或文本同时重述均不会绕过判重。
- [x] Runtime fingerprint、logical identity 与 diet dispatch 共用 canonical payload；等价日期/餐次/时间/参数层级重放返回既有回执。
- [x] 照片饮食的确认控制字段不进入 fingerprint 或业务 payload，不因模型补写 `confirmed` 制造新身份。
- [x] diet API 删除 `record_date` 静默换日，历史补录日期与 Runtime ledger 保持一致。
- [x] 旧 operation 不从可变 `attempt_id` 猜测首次轮次；`created_attempt_no=NULL` 保持 fail closed。
- [x] mutation turn 整轮缓冲模型正文，第二笔失败时不泄漏第一笔或第二笔的未验证成功 preamble。
- [x] 增加同 Run 两笔写入、参数重建、首笔成功次笔无副作用、首笔成功次笔失败的回归测试。
