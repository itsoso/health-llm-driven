# Dossier: 小巴补剂批量记录修复

| 字段 | 值 |
|---|---|
| slug | `agent-supplement-batch-repair` |
| 创建日期 | 2026-08-11 |
| 当前阶段 | G5（Backend PASS；Mobile OTA BLOCKED） |
| 状态 | blocked |
| 负责 | Codex |
| 反馈环 | Backend deploy + Mobile OTA + true-path verification |

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
- 实施计划: `docs/plans/2026-08-11-agent-supplement-batch-repair.md`。
- 路由: Backend TDD → policy/executor implementation → Mobile 可点击性修复 → safety review → main push → backend deploy + Mobile OTA → true-path verification。
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

- [x] T1 修复多补剂目标解析和逐调用投影，补单元测试。
- [x] T2 增加收紧的全量补剂续接与 owner-scoped 授权集合。
- [x] T3 增加零工具调用时的一次性确定性补剂兜底。
- [x] T4 集成测试、静态/治理检查、独立安全评审。
- [x] T5 关闭首次 main CI 暴露的集成闸、再次 push、backend deploy。
- [ ] T6 EAS 资产处理恢复后重试 Mobile OTA，并由用户完成真机验证。

## S5 · 实现

- 分支: `main`（按项目默认工作流）。
- commits: `7fa4a3851`（设计）、`2331b5419`（计划）、`01cf9e856`（多目标解析）、`cf4cc6d9c`（上下文批量持久化）、`0e50779de`（安全加固）、`2e21330bf`（发布闸修复）、`88fe449d6`（锁定依赖生成客户端类型）；并通过 `3f568666b` 合并当时的 `origin/main`。
- 实现结果:
  - 显式多补剂语句按名称拆成独立、可去重的 `health_record(supplement)` 调用；不把单个剂量错误复制给多个目标。
  - “全部已服用”只在紧邻助手明确询问“是否全部记为已服用”时启用，目标由服务端按 `user_id + is_active` 查询补剂定义。
  - owner-scoped 名称通过 opaque provenance 进入既有 policy、gateway、planned write 和 verified receipt 链路；集合外名称在 dispatch 前阻断。
  - 模型未发工具或只发部分目标时，服务端一次性补齐确定性调用；已有写回执后不盲目重试，部分失败不会宣称全部成功。
  - 安全评审 fast-follow：全量确认必须锚定最后一问；计数目标使用独立实体边界，阻断 D/D3、D-3、铁/铁观音等短名吞长名；相似已登记名称先澄清，不自动创建重复定义。
  - 补剂打卡 INFO 日志仅记录用户 ID 和补剂定义 ID，不再输出完整补剂名称。
  - Mobile 小巴页顶部三个操作保持 18px 视觉图标，但点击目标恢复到 iOS 建议的 44×44，并扩大 hit slop；避免视觉紧凑导致实际难点。
  - 首次主干 CI 揭示的相邻真实入口一并收口：自然语言“登记”识别、容器量词饮水记录、illness canonical read registry；过期测试数据改为满足现行精确授权，不放宽生产 policy。

## G3 · 测试闸

- targeted/integration/static/doc checks:
  - 初始相关全量集成：`2479 passed, 7 warnings`（224.27s，0 failed）。
  - 合并远端主干后关键锚点：`11 passed, 6 warnings`（2.14s，0 failed）。
  - 安全修复后的最终相关集成：`2487 passed, 7 warnings`（105.95s，0 failed）。
  - 首次 main push：CI run `31560724255` 如实失败；失败项包含主干既存的 Mobile 44pt 合同、OpenAPI 类型漂移、中文“登记”、自然饮水量词和若干已被精确写入授权淘汰的测试场景，未进入部署。
  - CI 定向复核：agent f-h `297 passed`；voice/watch `162 passed`；Mobile Jest `295 suites / 2574 tests passed`；Mobile TypeScript 与 design token gate 通过。
  - 最大 Agent i-z 分片第一次复核如实暴露 1 个过期测试目标（`6295 passed / 1 failed / 3 skipped`）；改为显式、可授权药名后第二次全量复核 `6296 passed / 3 skipped / 0 failed`（356.34s）。
  - Frontend production build 通过；ESLint `0 errors`（33 个既存 warnings）；OpenAPI 两端类型由当前 schema 重新生成。
  - 高风险 LLM live gate：invariants `12/12`、health agent core `50/50`、真实 orchestrator model `5/5`（avg score `0.92`）、trajectory contract `12/12`、trajectory goldens `9/9`，exit 0。
  - Ruff：`All checks passed!`。
  - 文档漂移：架构一致；dossier consistency：`105 份 dossier 全自洽`；`git diff --check`：通过。
- main CI: run `31563459784`，44/44 jobs 完成，结论 `success`。
- **裁决**: PASS。

## G4 · 安全闸

- 触发: 健康数据写入、上下文授权、用户数据隔离。
- reviewer / findings: 独立 safety/privacy review；首轮发现并阻断 3 个 P1（混合语境误授权、子串匹配写错对象、部分失败误报完成）和 1 个日志隐私 P2，均已修复。后续对 10 组末问句、重叠名、Unicode/内部标点边界做对抗复核；最终无可达、可复现 P0/P1。
- 复核证据: 对抗矩阵符合预期；审查定向测试 `9 passed`，`git diff --check` 通过；owner scope、短名澄清、精确分流和部分失败终态均保持有效。
- **裁决**: GO。

## S6 · 部署

- 路由: 后端标准 deploy + Mobile production OTA（纯 TS/UI 点击目标修复）。
- Backend: 从干净主干部署精确 SHA `88fe449d6d903135dac2135beb46f2736100afc9`；发布后远端主干增加的 `0d26c23cf` / `d2b187a99` 只有文档，不改变运行包。
- Backend 回滚点: `ab0a07d93eba5eaf43bfa8f2097c498195c7a3ee`，部署前 schema probe 通过。
- Mobile OTA: production/runtime `1.3.3`。Hermes 首次上传、一次自动重试、no-bytecode fallback 和一次独立强制 no-bytecode 重试均被 EAS 资产处理超时拒绝；没有生成 group/update ID，manifest 与生产锚点未改写。
- Mobile 当前已知可用回滚锚点: group `08d4b60a-19c2-4420-8e18-d92011ad8797` / iOS update `019ff3c1-413c-7c6d-851c-975617ecdc09`（commit `a0e9b3199a3c100f682f537464685272e4853ef7`）。

## G5 · 部署健康闸

- Backend: 42MB 数据库备份、Force-RLS 完整性、237 表恢复演练、站外 age 归档哈希/HMAC 真实性全部通过；managed migrations 无新增。
- Backend: 精确 SHA 核验，三轮健康度 `60/60 PASS`，runtime-only KB guard/staged contract 通过，906 文档/向量重建，Skills `22 = 22`，backend socket/service 与 Celery worker/beat 均 active。
- External smoke: `/api/v1/health` 返回 200 healthy；未鉴权 admin system-map 与 voice write 均返回 401。
- Mobile: EAS asset processing 连续超时，未形成可发布 artifact；旧 update 保持可用。
- **裁决**: BLOCK —— Backend 子闸 PASS，但完整 release 的 Mobile OTA 未完成；回到 S6 等待 EAS 恢复后重试，不带红进入 G6。

## S7 · 上线验证

- 锚点路径: “记录下来，吃了一粒甘氨酸镁和一粒褪黑素”与紧邻上下文后的“全部已服用”。
- 工具侧结果: Backend 路由在线且写入口保持鉴权；没有使用真实用户健康数据做自动 smoke，也没有产生待清理记录。
- 真机结果: pending；等待 Mobile OTA 后由用户在真实账号验证。

## G6 · 验证闸（人在环）

- production true path / 真机确认: pending。
- **裁决**: BLOCKED by G5 Mobile OTA；尚未进入。

## S8 · 沉淀

- system map / contracts / release notes: 系统现状与功能/架构图已在同一主干的 System Map 系列提交更新；本切片无新架构计数，只更新 dossier。
- 状态: Backend shipped；Mobile OTA blocked，保留可重试断点与回滚锚点。
