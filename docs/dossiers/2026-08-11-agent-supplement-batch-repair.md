# Dossier: 小巴补剂批量记录修复

| 字段 | 值 |
|---|---|
| slug | `agent-supplement-batch-repair` |
| 创建日期 | 2026-08-11 |
| 当前阶段 | S3 规划 |
| 状态 | defining |
| 负责 | Codex |
| 反馈环 | Backend deploy + Mobile true-path verification |

## S0 · 用户需求（逐字）

> 优化这个页面 点击完成 无效 出现了英文
>
> 全部已服用
>
> 记录下来，刚才打了一个喷嚏。
>
> 记录下来，吃了一粒甘氨酸镁和一粒褪黑素。
>
> 修复

- 谁用 / 解决什么 / 现在怎么绕过: Mobile 小巴用户自然语言记录补剂；目前多补剂和全量确认无法完成，只能逐项手工记录。
- 锚点用户相关性: 补剂执行记录是 Health OS 的 `WriteIntent -> ExecutionEvent -> HealthTwin` 闭环。

## S1 · Discovery（现状勘察）

- 已有可复用:
  - `AgentExecutor` 的 verified receipt、写计划和回合终态。
  - `health_record(record_type=supplement)` 及其用户隔离的补剂定义/打卡流程。
  - capability policy 的健康目标授权和 server-owned provenance。
  - reminder continuation 的紧邻上下文收紧模式。
- 根因证据:
  - 意图分类正确识别 supplement write；目标解析却把“记录下来”残留的“下来”当作补剂名。
  - 补剂目标解析只返回一个名称；dispatch 投影固定选择第一个名称。
  - “全部已服用”当前轮没有显式目标，也没有服务端所有者范围内的上下文授权集合。
  - 模型零工具调用时，确定性简单记录兜底不覆盖 supplement，最终落入通用缺字段文案。
- 已排除:
  - 喷嚏记录在同一 UI 成功，说明移动端发送、通用健康写入和回执展示链路可用。
  - 顶部“上一轮未完成”是后端真实终态的展示，不是按钮点击事件失效。
- 链接: `docs/plans/2026-08-11-agent-supplement-batch-repair-design.md`

## G1 · 准入裁决

- first_class_objects: `WriteIntent`, `ExecutionEvent`, `HealthTwin`
- core_loop_step: 用户确认执行 → 补剂事件 → verified receipt / Twin
- target_surface / safety_level / autonomy_tier: Backend, Mobile consumed / privacy-sensitive health write / unchanged
- spec_required: no — 聚焦现有写入能力的 bugfix，设计文档和 dossier 足够。
- smallest_end_to_end_slice: 两个显式补剂逐项写入 + 紧邻“全部已服用”写入活动补剂 + 无上下文负例。
- stale_surface_to_remove: 明确补剂写入后的通用“补充类型和值”回退。
- **裁决**: PASS —— 恢复既有主循环，不扩产品范围或医疗自治。
- 用户确认: ☑（用户明确要求“修复”）

## S2 · PRD

- 链接: 采用 focused design `docs/plans/2026-08-11-agent-supplement-batch-repair-design.md`，不新建重复 PRD。
- 验收:
  - 两个明确补剂名分别持久化且各有回执；
  - “全部已服用”仅在高置信紧邻上下文生效，目标来自当前用户活动定义；
  - 模型漏工具调用时仍能安全完成；
  - 无上下文继续澄清，药物与其他用户数据不受影响；
  - 完成态不再显示通用缺字段提示或内部英文枚举。
- 边界: 无 DB migration、无客户端合同、无药物批量写入、无提示词单点依赖。
- 未决问题: 无；用户已批准确定性修复方向。

## S3 · 规划

- 设计: `docs/plans/2026-08-11-agent-supplement-batch-repair-design.md`
- 实施计划: pending。
- 路由: Backend TDD → policy/executor implementation → safety review → main push → backend deploy → true-path verification。
- 长杆: 在不信任助手文本和模型字段的前提下传递“全部补剂”的 owner-scoped 授权集合。

## G2 · 可行性 + 安全压测

- 评审方式: Codex source trace + exact phrase reproduction。
- 硬阻断:
  - “全部”只能在紧邻明确补剂确认语境生效；
  - 名称只能来自当前用户活动补剂定义；
  - 每项必须走现有 gateway 和 verified receipt；
  - 不得把 supplement 扩成 medication 或直接绕过工具写库；
  - 部分失败不得宣称全部完成。
- 方案取舍: 采用解析器 + 服务端上下文授权 + 确定性兜底；拒绝 prompt-only 和 parser-only。
- **裁决**: PASS —— 可复用现有写入契约，无 schema 或跨端破坏性变更。
- 用户确认: ☑

## S4 · 研发任务分解

- [ ] T1 修复多补剂目标解析和逐调用投影，补单元测试。
- [ ] T2 增加收紧的全量补剂续接与 owner-scoped 授权集合。
- [ ] T3 增加零工具调用时的一次性确定性补剂兜底。
- [ ] T4 集成测试、静态/治理检查、独立安全评审。
- [ ] T5 main push、backend deploy、生产路径验证。

## S5 · 实现

- 分支: `main`（按项目默认工作流）。
- commits: pending。
- 实现结果: pending。

## G3 · 测试闸

- targeted/integration/static/doc checks: pending。
- main CI: pending。
- **裁决**: pending。

## G4 · 安全闸

- 触发: 健康数据写入、上下文授权、用户数据隔离。
- reviewer / findings: pending。
- **裁决**: pending。

## S6 · 部署

- 路由: backend-only deploy；无客户端代码变化，不需要 Mobile OTA。
- 部署 SHA / 回滚点: pending。

## G5 · 部署健康闸

- 健康分 / startup scan / route smoke: pending。
- **裁决**: pending。

## S7 · 上线验证

- 锚点路径: “记录下来，吃了一粒甘氨酸镁和一粒褪黑素”与紧邻上下文后的“全部已服用”。
- 结果 / 测试数据清理: pending。

## G6 · 验证闸（人在环）

- production true path / 真机确认: pending。
- **裁决**: pending。

## S8 · 沉淀

- system map / contracts / release notes: pending；若无架构结构变化只更新 dossier。
- 状态: defining。
