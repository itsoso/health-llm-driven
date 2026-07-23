# Dossier: ETH 质押收益日报、异常告警与外部只读 Skill

| 字段 | 值 |
|---|---|
| slug | `eth-staking-report` |
| 创建日期 | 2026-07-23 |
| 当前阶段 | S3 规划 |
| 状态 | defining |
| 负责 | Codex / user |
| 反馈环 | ETH2 shadow run → Telegram canary → systemd timer |

## Correct Course

- [ ] Correction Block

## S0 · 用户需求（逐字）

> health所在机器上还有ETH的质押服务，查看下是否有相关的健康检查服务，每天给我一个收益的报告，如果有异常再给我一些告警，开放skills，供外部调用，也发送到telegram

后续确认：

> 统计 validator 共识层余额变化，还要合并 execution tips/MEV，并折算成人民币

> 09:01发送

- 谁用 / 解决什么 / 现在怎么绕过：节点所有者需要每天看到可复算的质押收益与节点异常；当前只能查看本机健康 JSON、Grafana 和日志，无自然日收益结算与 Telegram 投递。
- 锚点用户相关性：不属于 Reva 健康产品锚点用户能力；属于同机独立基础设施和个人金融运维。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `/opt/eth-ops/openclaw-health.sh`：Beacon、Besu、validator、资源健康 JSON。
  - `/opt/eth-ops/openclaw-alert.sh`：每 3 分钟采集、告警去重、本机 JSON 日志。
  - `/opt/eth-ops/openclaw-api.py`：本机健康和告警 API。
  - `backend/app/services/notification/telegram_push.py`：health 产品已有 Telegram 发送经验，但新能力不直接依赖 health runtime。
  - `backend/skills/*/SKILL.md`：health 第一方运行时技能发布模式，仅参考 manifest 结构，不把金融能力混入该目录。
- 主机实查：
  - `eth1.service` 运行 Besu；重复的 `besu.service` 已于 2026-07-23 改为 `eth1.service` 别名。
  - Lighthouse beacon/validator、Prometheus、Grafana、node exporter active。
  - validator index `1331`，`active_ongoing`，未 slashed。
  - 当前健康检查为 healthy。
- 缺什么：收益基线、proposer execution 归因、MEV 证据、CNY 汇率、Telegram 投递、外部只读 skill、安全 token 管理。
- 硬约束 / 安全边界：
  - 不读取、复制或暴露 validator keystore、助记词、签名 key、JWT。
  - 外部 skill 只读，不提供 restart、withdraw、sign 或交易。
  - 旧 OpenClaw API 存在源码内初始化凭据和管理响应返回完整 token 的问题；开放外部访问前必须整改并轮换。
  - 未知收益不得当 0，不可把 fee recipient 普通入账误算为 MEV。

## G1 · 准入裁决

- classification：`infrastructure`
- first_class_objects：不映射健康一等对象；明确隔离为 ETH Ops 基础设施。
- core_loop_step：不进入 Reva 健康核心循环。
- target_surface / safety_level / autonomy_tier：ETH2 backend + Telegram + external agent；financial/privacy sensitive；只读，无写自治。
- spec_required：是，新增通知环、外部 API 契约和金融统计口径。
- smallest_end_to_end_slice：自然日快照 → 可复算收益 → 09:01 Telegram → 只读查询。
- stale_surface_to_remove：旧 OpenClaw API 不安全 token 行为需要替换；健康检查和 Grafana保留。
- **裁决：REFRAME → PASS** —— 不作为 Health OS 产品功能，实现隔离到 `/opt/eth-ops`。
- 用户确认：已于 2026-07-23 确认设计。

## S2 · PRD / 设计

- 链接：`docs/plans/2026-07-23-eth-staking-report-design.md`
- 边界：不修改 validator/Besu/Lighthouse 密钥和链数据；不提供金融交易；不写 health DB。
- 验收 Gate：数字可复算、Telegram 到达、外部接口最小权限、无 secret 泄漏、质押链路保持 healthy。
- 未决问题：无。默认复用目标 Telegram chat，但通过独立 root-only EnvironmentFile 注入。

## S3 · 规划

- 链接：实施计划待创建并在本节回填。
- 分阶段：安全整改 → 纯函数/TDD → 采集与持久化 → Telegram → 外部 skill → shadow → 部署。
- 长杆：MEV 可归因证据、自然日边界数据完整性、旧 API 凭据轮换。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge + deterministic fixtures。
- 硬阻断：
  - 外部开放前必须移除源码凭据、完整 token 回显并轮换旧 key。
  - MEV 无证据时必须显示 unknown。
  - 需要 shadow run 和 Telegram canary 后才启用 09:01 timer。
- 待拍板分叉：无。
- **裁决：待实施计划与一致性检查后确认。**

## S4 · 研发任务分解

- 待实施计划完成后填写。

## S5 · 实现

- 尚未开始。

## G3 · 测试闸

- 尚未执行。

## G4 · 安全闸

- 触发：消息、认证、外部 API、金融数据与凭据。
- 裁决：待安全复验。

## S6 · 部署

- 路由：ETH2 独立 `/opt/eth-ops` systemd services/timers；不运行 health `deploy.sh`。
- 部署 SHA / 回滚点：待部署。

## G5 · 部署健康闸

- 待执行。

## S7 · 上线验证

- 待执行。

## G6 · 验证闸

- 待用户确认 Telegram 日报和外部 skill 实际可用。

## S8 · 沉淀

- 待完成。
