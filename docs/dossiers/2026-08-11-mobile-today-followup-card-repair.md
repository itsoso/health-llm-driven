# Dossier: Mobile 今日复查行动卡修复

| 字段 | 值 |
|---|---|
| slug | `mobile-today-followup-card-repair` |
| 创建日期 | 2026-08-11 |
| 当前阶段 | S6（G4 GO，待 Backend deploy 与 Mobile 发布） |
| 状态 | shipping |
| 负责 | Codex |
| 类型 | bugfix / medical-boundary UI / write-capability repair |
| 计划 | `docs/plans/2026-08-11-mobile-today-followup-card-repair.md` |

## Correct Course

- [x] 2026-08-11 首轮独立 G4 评审判定 BLOCK：复查行动会无条件复用时间线 `nowItem.deep_link`，可能被同时存在的补水行动带到错误页面；Daily Plan 完成能力也仍向契约消费者声明 `/agenda/complete` 错误端点。
- [x] 范围回退并整改：复查语义先于无来源关联的时间线深链；Daily Artifact 按来源声明并调用 Agenda / Daily Plan 各自的真实写端点；新增真实调用分流和错误深链回归。
- [x] 整改提交 `ae7302674` 后重新执行独立 G4，最终 GO；GO 前未 push、Backend deploy 或 production OTA。

## 需求与现象

- 真机截图中，今日行动复查卡展示内部指标 `follow_up_completed`。
- 点击“完成”无有效结果。
- 期望复查事项进入明确的处理流程；真正支持写入的行动完成后立即反馈并刷新。

## G1 · 准入

- **裁决: PASS。**
- 对象: `HealthAgendaItem`、`HealthProblem`、`ExecutionEvent`。
- Surface: Mobile Today；后端仍是行动能力真源。
- 分类: 修复现有闭环，不新增医疗结论或处方行为。

## G2 · 可行性与安全压测

- 根因 1: `trajectoryDisplay.ts` 缺少 `follow_up_completed` 中文映射。
- 根因 2: Smart Agenda 对所有 due/overdue 来源声明 `can_complete=true`，但 `/agenda/complete` 明确拒绝 `health_problem`，测试契约要求返回 400。
- 安全裁决: 不允许为了让按钮“成功”而把 `HealthProblem` 标成 resolved，也不允许在没有复查结果时伪造临床复查完成事实。
- 最小方案: 后端只为存在真实写路径的来源声明可完成；移动端兼容旧后端并做防御，复查主动作改为“处理复查”并进入现有 `/medical-exams`；协议/用药/补剂和 Daily Plan 分别走其真实端点。
- **裁决: PASS。**

## S5 · 实现

- [x] 后端收紧 Smart Agenda `can_complete` 来源能力。
- [x] Mobile 增加 Daily Artifact 完成目标解析，阻止不受支持来源进入写请求。
- [x] 复查卡显示“处理复查”，进入现有复查/化验工作流。
- [x] `follow_up_completed` 显示为“复查完成情况”，验证句改为“后续确认复查是否完成”。
- [x] 真正完成成功后显示中文 Toast，并刷新 Today、Agenda 与 Daily Plan 缓存。

## G3 · 测试闸

- RED 已确认:
  - Mobile 复现英文指标和错误“完成”按钮，3 个断言按预期失败。
  - Backend 纯函数断言复现 `health_problem.can_complete=True`。
- GREEN 已确认:
  - Mobile 定向回归: 5 suites / 47 tests PASS（行动卡、错误深链防护、Agenda / Daily Plan 真实写入分流、指标文案、Daily Artifact 转换与 Dynamic Today Renderer）。
  - 合并远端 `48841b571` 后联合回归: 8 suites / 62 tests PASS（本切片 5 suites + Chat Chrome 3 suites）；TypeScript 与合并后变更文件 ESLint 继续 PASS。
  - Mobile TypeScript `--noEmit`: PASS；变更文件 ESLint: PASS。
  - Backend 新增能力与端点所有权契约测试直接执行: PASS；变更模块 `py_compile`: PASS。
  - `scripts/check_doc_drift.py`: PASS；`git diff --check`: PASS。
- 本地完整 FastAPI pytest fixture 启动未在合理时间内完成，原因是应用级 provider 初始化；本次不把它记为通过，发布阶段继续以 Backend 部署健康检查作为集成闸补充证据。
- **裁决: PASS。** 本次变更路径的定向契约、静态检查与文档漂移检查均已覆盖。

## G4 · 安全闸

- 首轮独立 safety/privacy reviewer: BLOCK；发现复查路由可被无关 `nowDeepLink` 劫持，以及 Daily Plan 契约端点错误。
- 整改后独立复评确认两个阻断项均已关闭，未发现 P0/P1；普通 `health_problem` 不会只因来源类型被误判为复查，权威写入失败不会产生成功回执。
- 非阻断残余风险: 宽泛的 `EXAM_WORDS`（含“指标”）可能把少量非复查行动导向复查页；极快重复点击可能重复 append-only Artifact 遥测，但 Agenda / Daily Plan 权威完成写入均幂等，不会重复完成或改变医疗状态。
- 重点: 不伪造复查完成；不改变 HealthProblem 状态；复查路由不受无关当前项影响；写入来源与端点严格一致；失败可见。
- **裁决: GO。**

## G5 · 部署健康闸

- 待 Backend 部署与健康检查。

## G6 · 上线验证

- 待 Mobile production OTA 与真机冷启动验证。
