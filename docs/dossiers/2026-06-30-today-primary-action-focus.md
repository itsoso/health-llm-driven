# Dossier: Today Primary Action Focus

| 字段 | 值 |
|---|---|
| slug | `today-primary-action-focus` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S5 实现 |
| 状态 | implemented-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile Jest / later OTA or QR |

## S0 · 用户需求

> 开干

承接上一轮未完成清单和用户截图反馈:首页比较凌乱,没有重点,行动无法确认和执行,内容重复。

## S1 · Discovery

- `docs/plans/2026-06-29-weekly-release-execution-plan.md` 把 Mobile Daily Artifact / 健康日序主线列为 P1,验收是首页只突出一个 top action。
- `mobile/components/home/DynamicTodayRenderer.tsx` 会把 DynamicView 中所有可渲染 section 都展开。
- 后端 DynamicView 可能同时返回 `daily_artifact` 与 `runtime_agenda`;在首页连续展开后,用户会看到一个今日行动和一张 7 天运行时计划大卡,主次冲突。

## G1 · 准入裁决

- first_class_objects:`HealthAgendaItem`, `ExecutionEvent`, `ProvenanceRecord`
- core_loop_step:今日状态 -> 今日最重要行动 -> 完成/跳过/问阿衡。
- target_surface / safety_level / autonomy_tier:Mobile Today / low UI clarity / manual_confirm unchanged。
- spec_required:否,不新增健康建议、写路径或跨端合同。
- smallest_end_to_end_slice:首页 DynamicView 有 Daily Artifact 时,不再展开 runtime agenda 大卡。
- 裁决:PASS。

## S2/S3 · 计划

- 计划:`docs/plans/2026-06-30-today-primary-action-focus-plan.md`
- 不做:不改后端 DynamicView 合同;不删除 runtime agenda 卡片;不处理 App Store 凭证/截图人审。

## G2 · 可行性 + 安全压测

- 这是前端渲染收敛,不触碰 HealthKit、用药、处方、诊断、认证、DB 或写路径。
- `runtime_agenda` 卡仍保留在 registry 和数据合同中,只是 Today 首页不再与主行动并列展开。
- 裁决:PASS。

## S4/S5 · 实现

- RED:把 `DynamicTodayRenderer` 测试改成期望首页只展示 Daily Artifact,不展示 `runtime_agenda`。
- GREEN:`DynamicTodayRenderer` 检测到任一 `daily_artifact` 时过滤 `runtime_agenda` section card。
- 同步首页回归测试中对 DynamicView 的旧断言。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/home/__tests__/DynamicTodayRenderer.test.tsx --runInBand`
  - 初始失败:`7天验证节奏` 仍被渲染。
- PASS:同一命令。
  - 2 passed。
- PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath 'app/(tabs)/__tests__/home.test.tsx' components/home/__tests__/DailyArtifactCard.test.tsx components/home/__tests__/DynamicTodayRenderer.test.tsx --runInBand`
  - 3 suites passed,33 tests passed。

## G4 · 安全闸

- 未改健康建议生成、写动作、数据采集、认证、隐私或医疗边界。
- 裁决:GO。

## S6/S7 · 部署与上线验证

- 本批尚未部署。属于 Mobile JS/TS UI 行为变更,可随下一次 OTA 或二维码包发布。
- 真机待验:首页只出现 Daily Artifact 主行动,不再直接展开 7 天计划大卡。

## S8 · 沉淀

- 本周计划新增第十二批切片。
