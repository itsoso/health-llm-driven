# ETH Staking Daily Report Design

日期: 2026-07-23  
状态: v1，用户已确认  
范围: ETH2 主机上的 validator `1331`、Besu、Lighthouse、ETH Ops API、Telegram

## 1. 目标

在不接触 validator 私钥、助记词或 keystore 的前提下，为 ETH2 上的质押节点建立一条可审计的收益与健康闭环：

- 按北京时间自然日统计 validator 共识层余额变化。
- 归因该 validator 提议区块产生的 execution priority fees。
- 归因可验证的 builder / MEV payment。
- 按报告生成时的 ETH/CNY 汇率折算人民币。
- 每天北京时间 09:01 发送 Telegram 日报。
- 节点或数据异常即时发送 Telegram 告警，并在恢复后通知。
- 向外部 agent 提供只读、可撤销授权的 staking skill。

## 2. 边界判断

该能力属于同机基础设施与个人金融运维，不属于 Reva Personal Health OS 的健康对象、核心循环或健康数据权限域。

因此：

- 运行时实现放在独立 `/opt/eth-ops` 边界。
- 不新增 `HealthProblem`、`HealthProgram`、`HealthAgendaItem` 等健康对象。
- 不把质押收益写入 health PostgreSQL。
- health 仓库仅保存经确认的设计、实施计划和上线 Dossier。
- 外部 skill 不进入 `backend/skills` 健康技能目录，避免外部 agent 将金融运维误认为健康能力。

## 3. 已有现状

ETH2 已运行：

- `eth1.service`：唯一 Besu execution client。
- `besu.service`：已改为 `eth1.service` 的 systemd 别名。
- `lighthouse-beacon.service` 与 `lighthouse-validator.service`。
- validator index `1331`，状态 `active_ongoing`。
- `/opt/eth-ops/openclaw-health.sh`：节点健康 JSON。
- `/opt/eth-ops/openclaw-alert.sh`：每 3 分钟健康检查及本机告警日志。
- `/opt/eth-ops/openclaw-api.py`：本机只读健康/告警 API 及旧式 token 管理。
- Prometheus、Grafana、node exporter。

现有缺口：

- 无收益历史基线与自然日结算。
- 无 proposer → execution block → priority fee / MEV 的归因链。
- 无 Telegram 日报和异常推送。
- 旧 OpenClaw API 把初始化凭据写入源码，管理响应可能返回完整 token，不能直接扩展为对外 skill。
- 现有健康检查把脚本执行失败与真实节点故障混在一起，告警记录未直接投递。

## 4. 推荐架构

```text
Lighthouse Beacon API ─┬─ validator balance/status
                       ├─ proposer duties / proposed blocks
                       └─ missed attestations / sync status

Besu JSON-RPC ─────────┬─ execution block and receipts
                       ├─ priority fee attribution
                       └─ builder payment evidence

ETH/CNY rate provider ─── report-time exchange rate

                 ┌──────────────────────────┐
                 │ eth-staking-report       │
                 │ snapshots + attribution  │
                 │ SQLite + JSON report     │
                 └────────────┬─────────────┘
                              │
                 ┌────────────┴─────────────┐
                 │                          │
          Telegram 09:01             Read-only skill API
          + anomaly alerts           scoped token + audit
```

实现优先使用 Python 标准库和现有主机组件，持久化采用独立 SQLite 文件。该 SQLite 只保存公开链上事实、汇率和投递记录，不保存任何签名材料。

## 5. 收益口径

### 5.1 统计窗口

- 时区：`Asia/Shanghai`。
- 日报时间：每天 09:01。
- 报告窗口：前一北京时间自然日 `[00:00:00, 24:00:00)`。
- 日初快照：每天 00:01；另保留每小时快照用于补偿和诊断。
- 第一份正式日报需要两个边界快照；数据不足时发送“基线建立中”，不伪造 0 收益。

### 5.2 共识层

主口径：

```text
consensus_delta_eth = ending_validator_balance - starting_validator_balance
```

同时记录：

- validator status；
- slashed；
- attestation 成功/失败/未知；
- proposer duty 与实际提议；
- 边界快照 slot 和采样时间。

快照偏离自然日边界时，报告明确给出实际采样时间。缺失边界数据时状态为 `incomplete`，不外推。

### 5.3 Execution priority fees

只统计 validator `1331` 在窗口内实际提议的 execution blocks。

每个 execution block 的 priority fees：

```text
sum(receipt.gasUsed * (receipt.effectiveGasPrice - block.baseFeePerGas))
```

规则：

- 使用 proposer duty / beacon block execution payload 证明该区块属于 validator `1331`。
- 不能仅按 fee recipient 地址余额变化统计，避免把普通转账或其他 validator 收益混入。
- receipt 或 block 缺失时标记该区块 `incomplete`，日报列出缺口。

### 5.4 MEV / builder payment

MEV 只统计存在链上证据且可归因到该 proposer block 的付款：

- 优先识别 execution payload 中 builder 向 configured fee recipient 的显式付款。
- 若本机存在 mev-boost / relay trace，再用 relay evidence 交叉验证。
- 无可靠证据时返回 `unknown`，不得把任意入账猜作 MEV。
- 报告分别展示 `priority_fees_eth`、`mev_payment_eth` 与 `execution_total_eth`。

### 5.5 人民币折算

- 保存报告生成时的 `ETH/CNY` 汇率、provider、抓取时间。
- 折算：

```text
total_cny = total_eth * eth_cny_rate
```

- 汇率失败不阻断 ETH 日报；人民币字段显示“暂不可用”并产生数据质量 warning。
- 不使用 LLM 生成或猜测汇率。
- 所有面向用户的数值最多 2 位小数；ETH 原始精度在机器接口中保留，Telegram 展示使用适合 ETH 的固定小数精度，避免极小收益被显示为 0。

## 6. Telegram

日报模板：

```text
ETH 质押日报｜2026-07-22（北京时间）

总收益: 0.00xxxx ETH（约 ¥xx.xx）
共识层: +0.00xxxx ETH
Priority fees: +0.00xxxx ETH
MEV: +0.00xxxx ETH / 未确认

Validator: active_ongoing
Attestations: 成功 x / 漏签 x / 未知 x
提议区块: x
节点: healthy
汇率: ¥xx,xxx.xx / ETH（provider，09:01）
数据完整性: complete / incomplete
```

告警规则至少覆盖：

- beacon / execution API unreachable；
- `el_offline`、optimistic head、同步距离持续异常；
- validator 非 `active_ongoing` 或 slashed；
- attestation 漏签；
- proposer duty 未产块；
- Besu/Lighthouse 服务不 active 或出现重启增长；
- peers 低于阈值；
- 磁盘、内存达到阈值；
- 收益采集、汇率、Telegram 投递失败。

同类告警 30 分钟去重，恢复时发送 recovery。日报与告警使用独立幂等键，重跑不会重复投递。

Telegram token 和 chat id 通过 root-only `EnvironmentFile` 注入，权限 `0600`；不写入源码、SQLite、日志或 skill 输出。

## 7. 外部 Skill

提供独立 `staking-report` skill manifest，能力仅为：

- `staking_health`
- `staking_daily_report`
- `staking_rewards_range`
- `staking_alerts`

安全约束：

- 只读，无 restart、withdraw、sign、key-management 或交易能力。
- bearer token 仅保存哈希，明文只在创建时显示一次。
- token 支持 scope、过期、撤销和名称。
- 默认仅监听 `127.0.0.1`，由 Nginx TLS 反代。
- 每次调用记录 token id、scope、路径、时间、状态码和来源 IP，不记录 Authorization。
- 速率限制和响应大小上限。
- CORS 使用显式 allowlist，不使用 `*`。
- API 永不返回 validator pubkey 以外的签名材料、JWT、Telegram token、管理 secret 或完整 bearer token。

旧 OpenClaw API 的硬编码初始化 key 与返回完整 token 的管理响应必须在开放 skill 前整改并轮换。

## 8. 失败处理

- 采集失败：该字段 `unknown/incomplete`，日报照常发送并附 warning。
- 收益归因不完整：不把未知值当 0，也不合并进总收益。
- 汇率失败：发送 ETH 收益，人民币显示不可用。
- Telegram 失败：本地保留 pending delivery，指数退避重试，超过上限写 critical alert。
- SQLite 写失败：fail-loud，禁止发送带错误数字的“成功日报”。
- 脚本并发：文件锁保证 snapshot/report/alert 单实例。
- 所有外部 HTTP 调用设置连接和总超时。

## 9. 验证

单元测试：

- 自然日窗口和时区边界。
- 共识余额正负变化与缺失基线。
- priority fee 精确计算。
- proposer block 归属和非本 validator 区块排除。
- MEV 已确认、未知和普通转账误判反例。
- CNY 折算与汇率失败降级。
- Telegram 文案、幂等和告警去重。
- token 哈希、scope、撤销、过期和敏感字段不泄漏。

集成验证：

- 用录制的 Beacon/Besu fixture 生成确定性日报。
- ETH2 上 shadow run，不发送 Telegram，只生成报告。
- 手工发送一次 Telegram canary。
- 连续观察至少一个完整自然日快照与 09:01 调度。
- 外部 API 未授权返回 401、越权 scope 返回 403、授权只读调用返回 200。

上线 Gate：

- 质押服务、RPC、beacon、validator 均保持 healthy。
- 日报数字可由原始快照和区块证据复算。
- Telegram canary 到达目标 chat。
- 无 token/secret 出现在代码、日志、API 响应或版本控制。
- 回滚只停止新增 timer/API，不修改 validator、Besu、Lighthouse 数据和密钥。

