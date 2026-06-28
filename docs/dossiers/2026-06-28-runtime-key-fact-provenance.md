# Dossier: Runtime 关键事实 Provenance 摘要

| 字段 | 值 |
|---|---|
| slug | `runtime-key-fact-provenance` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S6 部署 |
| 状态 | shipping |
| 负责 | Codex |
| 反馈环 | backend deploy |

## S0 · 用户需求(逐字)
> 按 PRD 完整执行，先对比 PRD/Plan/Code，走 product-pipeline，直接实现、验证、发布，并回写计划状态。
> 继续执行下两批。
> 继续执行

- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1): 用户在 Today/Agenda/Chat/Watch 看到行动建议时，需要知道关键事实来自哪个真实数据源、何时观测、置信度如何；当前只能看到建议结论和 trajectory context，缺少可解释的来源摘要。
- 锚点用户相关性(35-55 慢病中年男 + Ultra3/RingConn/Garmin): 化验、HealthKit 和设备数据会驱动运动、饮食、用药提醒类建议；可追溯摘要能降低“黑箱健康建议”的不信任和误解风险。

## S1 · Discovery(现状勘察)
- 已有可复用(file:line):
  - `backend/app/models/data_connection.py`: 已有 `DataConnection` / `ConsentGrant` / `ConnectorPolicy` / `ProvenanceRecord`。
  - `backend/app/services/data_connections.py`: 已有 provenance 创建和序列化服务。
  - `backend/app/services/fhir_bundle_import.py`: FHIR Observation 导入已为 `BiomarkerObservation` 写入 provenance。
  - `backend/app/api/devices.py`: HealthKit 导入已为 `HealthKitDailyRecord` 写入 provenance。
  - `backend/app/services/agenda_service.py`: `runtime_context.evidence` 已承载 source、rank_score、trajectory_context 和 confidence。
- 缺什么:
  - `runtime_context.evidence` 还没有把 key facts 关联到 `ProvenanceRecord`。
  - Today top action 无法展示关键事实来源、观测时间、连接器和置信度。
- 硬约束 / 平台·安全边界:
  - 只读摘要，不返回原始报告、raw_hash 或完整 raw metadata。
  - 不新增自治写操作，不改变建议排序，不做医学因果断言。
- 链接: 本 Dossier 小切片，复用 `docs/plans/2026-06-27-health-runtime-governance-plan.md` 中 A 深化项。

## G1 · 准入裁决(governance §8 RequirementAdmission)
- first_class_objects: `ProvenanceRecord`, `DataConnection`, `HealthAgendaItem`, `HealthTrajectory`
- core_loop_step: Observe -> Decide -> Act 中的 Decide 可解释性增强
- target_surface / safety_level / autonomy_tier: Backend runtime agenda API / privacy_sensitive / none
- spec_required(§8.1): yes，复用 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`
- smallest_end_to_end_slice: FHIR biomarker provenance 进入 `/api/v1/agenda/range?mode=runtime` top action `runtime_context.evidence.provenance`
- stale_surface_to_remove: 无
- **裁决**: PASS —— 已映射到一等对象和核心循环，只读增强且不扩大写路径。
- 用户确认: 已由“继续执行”授权进入后续批次。

## S2 · PRD
- 链接: `docs/prd/reva-personal-health-os-prd.md`
- 引用的权威 R 号(不重 spec): R1/R4/R15 相关的真实数据、可解释、安全边界原则。
- 边界(不做): 不做连接中心 UI、不做撤权删除、不做更多 provider 采集、不输出原始报告内容。
- 验收 Gate: runtime top action 对 LDL 这类化验关键事实返回最小 provenance 摘要。

## S3 · 规划
- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 分阶段 + 反馈环路由(OTA/EAS): 后端 API 合同切片；不触发 mobile OTA 和 native build。
- 长杆 / spike: JSONB metadata 不做 DB 侧复杂查询，先用 canonical biomarker code 关联 `BiomarkerObservation -> ProvenanceRecord`。

## G2 · 可行性 + 安全压测
- 评审方式: Codex self-challenge
- 硬阻断(已焊进规划): 不暴露 `raw_hash`、不返回完整 source metadata、不把 missing provenance 当作 actionable 医疗结论。
- **待拍板分叉(STOP 问人)**: 无，本切片只读且用户要求继续。
- **裁决**: PASS

## S4 · 研发任务分解
- 跨端 API 契约(`_workspace/`): 复用既有 agenda runtime response，在 `runtime_context.evidence.provenance` 增加只读对象。
- 任务表(每条链接回规划 task · OTA/EAS · 触及层 · 需 spec?):
  - [x] T1 后端测试：runtime top action 包含 FHIR biomarker provenance 摘要。
  - [x] T2 后端实现：Agenda runtime evidence 根据 trajectory/verify metrics 关联 `BiomarkerObservation` provenance。
  - [x] T3 文档回写：计划和 rolling runtime spec 标记本切片已完成。
- 并发检查(`git fetch` + `gh pr list`,没被抢先): 已执行；开放 PR 为 `claude/causal-honesty-floor`、`fix/ddi-pgx-cpic-safety`、`fix/hla-a3101-proxy-guardrail`、`feat/medication-add-safety-check`，未抢占本 runtime provenance 切片。

## S5 · 实现
- 委托: Codex
- 分支(off origin/main)/ commit: `codex/rolling-runtime-next-slice` / 待提交

## G3 · 测试闸
- 集成闸(CI 模式 `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`,**不 `| tail`**):
  - RED：`backend/tests/test_agenda_range_complete.py::test_runtime_context_includes_key_fact_provenance_for_biomarker` 先失败于 `KeyError: 'provenance'`。
  - GREEN：同测试通过。
  - `backend/tests/test_agenda_range_complete.py`：`12 passed`。
  - `backend/tests/test_agenda_range_complete.py backend/tests/test_data_connections.py backend/tests/test_fhir_bundle_import.py backend/tests/test_healthkit_adapter.py --no-cov`：`30 passed`。
  - `backend/tests/test_watch_actions.py backend/tests/test_watch_summary.py backend/tests/test_inline_cards_runtime_agenda.py backend/tests/test_daily_artifact.py --no-cov`：`47 passed`。
  - `python -m compileall -q backend/app/services/agenda_service.py backend/tests/test_agenda_range_complete.py`：通过。
  - `scripts/check_doc_drift.py`：系统 Python 因缺依赖失败；项目 venv Python 重跑通过，确认 CLAUDE.md + ARCHITECTURE.md 数字与代码一致。
- main CI 真实色(`gh run list`):未查
- Codex 跨家族 capstone(高风险):不触发，未改药物/基因/用药写路径或安全规则。
- **裁决**:绿

## G4 · 安全闸
- 触发(用药/基因/化验/消息/safety/认证/写路径)?: 化验 provenance 只读摘要，privacy_sensitive。
- 评审: 自查 + 测试确保不返回 raw_hash/完整 metadata；实现只读，不改变排序、不新增医疗建议、不新增写路径。
- **裁决**:GO

## S6 · 部署
- 路由: backend-deploy
- 序: 后端 deploy；不需要 generate-types；不需要 OTA。
- 部署 SHA / 回滚点: 待定

## G5 · 部署健康闸
- 健康分(阈值 35,低于自动回滚): 待定
- prod smoke: 待定
- **裁决**:待定

## S7 · 上线验证
- 真实路径验证(curl / 健康分 / 真机 / anchor 视角): 待定
- 结果(相关非因果措辞): 待定

## G6 · 验证闸(人在环)
- 需求在 prod 对 anchor 用户真成立?: 待定
- 真机/发布用户确认: 不涉及真机发布
- **裁决**:待定

## S8 · 沉淀
- 新坑沉淀到(agent 定义 / skill / memory): 待定
- 文档同步(ARCHITECTURE.md / doc-drift EXPECTED / parity 表): 计划/spec 回写；无架构计数变更。
- 状态 -> **shipped**: 待定
