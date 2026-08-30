---
doc: privacy-governance
last-reviewed: 2026-08-29
---

# 隐私治理

## 数据分级

- L1 公开：公开配置和静态内容。
- L2 内部：聚合统计；需访问控制。
- L3 机密：健康与行为数据；需加密、隔离和访问审计。
- L4 绝密：密码、Token、密钥；最小权限，不得明文持久化或进入日志。

## 用户隔离与审计

所有用户数据读写都必须绑定认证用户/租户。敏感数据导出、管理员动作、授权和凭证变化必须鉴权并记录审计证据；审计内容同样要脱敏。

## 锁屏推送

iOS 锁屏会显示 title/body，且 payload 经过 APNs。具体药名、补剂名、化验项目名和诊断名可反推健康状况，因此：

- 锁屏可见 title/content 只到类别级，例如“用药提醒”“补剂提醒”“化验指标提醒”。具体名称与剂量只放安全的 data payload，并在解锁后的应用内渲染。
- Safety Guardian 的 ddi/dsi/pgx/labs/problem_red_lines 统一使用 `app/services/notification/push_privacy.safety_alert_push_text`；vitals/cgm/symptoms 等急性时效信息按现有规则处理。
- LLM 自由生成推送必须在截断前经过 `push_privacy.llm_push_backstop`。扫描覆盖药名、补剂名和可反推诊断的治疗类别；扫描异常时 fail closed 到泛化文案，推送不因护栏故障丢失。
- 用户自己输入、仅推给本人设备的文本可按现有产品契约透传；系统代写时仍不得拼接敏感名称。
- 同类泛化标题可能相同，生产者必须在 `data.rule_id` 提供稳定去重键，避免 title 去重误吞合法提醒。

新增出口必须接同一 choke point，并测试敏感文案被泛化、良性文案逐字节透传；过度泛化也是缺陷。
