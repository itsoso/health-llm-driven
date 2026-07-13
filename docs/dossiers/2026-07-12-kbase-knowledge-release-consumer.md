# Dossier: KBase Knowledge Release Consumer

| 字段 | 值 |
|---|---|
| slug | `kbase-knowledge-release-consumer` |
| 创建日期 | 2026-07-12 |
| 当前阶段 | S8 沉淀 |
| 状态 | production_verified |
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
- [x] T5 生产配置、真实同步和审核包验证。

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

- 消费端合并提交：`1ece62f04e9517d6a7ad8186dc183c8a59ddad14`。
- 生产已配置 KBase Release URL 与 bearer token；档案只记录配置存在，不记录凭据值。
- 标准部署入口完成数据库备份、System KB 重建和服务重启。

## G5 · 部署健康闸

- 部署健康检查：`60/60 PASS`。
- `health-backend`、`celery-worker`、`celery-beat` 均为 `active`。
- 服务器侧健康接口确认 API、数据库、Redis 和 Celery 均已连接。
- **裁决：PASS**。

## S7 · 上线验证

- 首次生产同步拉取 1 个 Release：`release-43a7dbb5062e51e383597c1452dfe5b187a2ce8b78690915f18cb1bc8819bcbb`。
- 首次结果为 `draft_written`，游标推进到该 Release；审核门返回 `serving_allowed=false`。
- 阻断原因包含 `draft_artifacts_present`、`unreviewed_artifacts_present` 和 `manifest_not_reviewed`，未自动进入 serving。
- 紧接着第二次同步返回 `up_to_date`、`release_count=0`，验证增量游标和幂等行为。

## G6 · 验证闸

- 已通过线上认证链路拉取真实 Release，并验证草稿门和二次同步。
- **裁决：PASS**。

## S8 · 沉淀

- 实施、回滚边界、真实 Release 游标和生产门禁证据均已记录。
- 后续由人工审核草稿；在审核通过前不得将该 Release 用于健康 serving。
