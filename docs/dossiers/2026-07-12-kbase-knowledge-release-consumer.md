# Dossier: KBase Knowledge Release Consumer

| 字段 | 值 |
|---|---|
| slug | `kbase-knowledge-release-consumer` |
| 创建日期 | 2026-07-12 |
| 当前阶段 | S5 实现 |
| 状态 | implementation_complete |
| 负责 | Codex |
| 反馈环 | KBase Release API / System KB draft review / KBAudit |

## Correct Course

- [ ] Correction Block

## S0 · 用户需求（逐字）

> 继续执行

承接已上线的 KBase 生产端闭环，把 `health-llm-driven` 接成正式消费者。目标是增量消费不可变 Release，不再依赖反复读取可变整包导出。

## S1 · Discovery（现状勘察）

- Health 已有整包导入、草稿、人工审核和发布门。
- KBase 已提供 Release 列表、详情和反馈 API。
- 旧同步任务可作为回滚路径，不应与新同步重复调度。

## G1 · 准入裁决

- first_class_objects：Knowledge Release、System KB draft、KBAudit cursor。
- core_loop_step：采集/分析/质量发布 -> Health 增量同步 -> 人工审核 -> serving。
- safety_level：高；知识可能进入健康建议上下文。
- smallest_end_to_end_slice：一个 Release 进入草稿并留下可恢复游标，不直接发布。
- **裁决：PASS**。边界清楚且复用既有安全门。

## S2 · PRD

- Release 必须为 `quality.decision=pass`。
- `usage_policy=evidence_only` 必须完整保留。
- 同步失败不得推进游标；同步成功也不得伪造 `used` 反馈。
- serving 继续要求 Health 人工审核。

## S3 · 规划

- 实施计划：`docs/plans/2026-07-12-kbase-knowledge-release-consumer.md`。
- 回滚：不配置 `DEDAO_KBASE_RELEASE_BASE_URL` 时继续使用原整包导入。

## G2 · 可行性 + 安全压测

- 复用现有 artifact compiler、draft writer 和 review gate。
- 新消费端严格校验 schema、quality、usage policy 和 claim ID 唯一性。
- 复用现有 Celery 入口，避免双任务竞争同一 artifact 目录。
- **裁决：PASS**。

## S4 · 研发任务分解

- [x] T1 Release 列表、详情和反馈客户端。
- [x] T2 Release 到 System KB 草稿映射。
- [x] T3 KBAudit 增量游标与定时入口复用。
- [x] T4 fail-closed 与回归测试。
- [ ] T5 生产配置、真实同步和审核包验证。

## S5 · 实现

- 新增外部 integrations 适配器，避免扩大 System KB 服务职责。
- 新增 `DEDAO_KBASE_RELEASE_BASE_URL` 与批大小配置。
- 现有同步任务在 Release URL 存在时优先增量 Release，否则保留旧导出路径。
- 只在草稿落盘和审计提交后推进游标。

## G3 · 测试闸

- Release consumer + legacy importer：`9 passed`。
- 既有 dedao review API 回归：`6 passed`。
- system-map/doc drift 与 `git diff --check`：PASS。
- 仓库没有 `scripts/privacy-smoke.sh`；已执行变更范围路径/凭据扫描，未新增私密值。
- **裁决：PASS**。

## G4 · 安全闸

- 非 pass、错误 schema、重复 claim ID 均 fail-closed。
- `evidence_only`、release ID、内容哈希、引用 ID 和 draft 状态均保留。
- import 不发送虚假 `used` 反馈；实际回答引用反馈留给后续运行时接线。
- **裁决：PASS**。

## S6 · 部署

- 尚未部署；需要配置生产 KBase URL 与 bearer token 后走标准发布入口。

## G5 · 部署健康闸

- **裁决：PENDING**。等待合并、部署和任务健康检查。

## S7 · 上线验证

- 待验证真实 Release 被拉取、审核包可见、serving 未自动改变、第二次同步返回 up-to-date。

## G6 · 验证闸

- **裁决：PENDING**。不能以本地模拟服务代替线上认证链路。

## S8 · 沉淀

- 实施与回滚边界已记录；上线验证后补充真实 release ID 和审计证据。
