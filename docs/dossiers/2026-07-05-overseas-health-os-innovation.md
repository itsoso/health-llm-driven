# Dossier: Overseas Health OS Innovation And Benchmark

| 字段 | 值 |
|---|---|
| slug | `overseas-health-os-innovation` |
| 创建日期 | 2026-07-05 |
| 当前阶段 | S7 验证 |
| 状态 | implemented-local-gate |
| 负责 | Codex |
| 反馈环 | product-pipeline / offline eval / benchmark seed |

## S0 · 用户需求

> 形成规划，并且实现

承接前序讨论:如果小巴要切海外市场,不能只做通用健康问答,也不应直接以重型 Health OS 冷启动。更合理的切口是“拍照/语音记餐 + 可穿戴恢复状态 + 体检/报告/用药事实 + 低摩擦行动闭环”,用评测证明国产模型加个人数据能在特定健康管理场景超过通用商用模型。

## G1 · 准入裁决

- first_class_objects:`DietRecord`, `HealthTwin`, `HealthProblem`, `HealthProtocol`, `HealthAgendaItem`, `ExecutionEvent`
- core_loop_step:拍照/语音/报告输入 -> 个人化健康上下文 -> 安全边界 -> 动态行动卡片 -> 记录/计划/复盘
- target_surface / safety_level / autonomy_tier:Mobile/Watch/Mac/Web / health advice boundary / manual-confirm
- smallest_end_to_end_slice:先落规划 + 离线 benchmark suite,不立即接入真实海外竞品或 live LLM。
- 裁决:PASS。

## S2/S3 · 计划

1. 形成海外市场进入规划,明确 wedge、竞品分层、MVP、评测方法和里程碑。
2. RED:新增 `overseas_health_os` eval suite 测试,要求能加载种子 case、跑通基线、识别低质量/越界候选。
3. GREEN:新增确定性 runner/scorer、YAML 数据集、baseline。
4. 回写计划状态。

## G2 · 风险压测

- 不在本切片调用真实 LLM、外部竞品或用户数据,避免成本、隐私和不稳定性进入 CI。
- 不改变医疗建议运行时,只建立评测和规划。
- scorer 必须覆盖安全边界:不诊断、不开方、不调药、不把红旗症状当饮食记录。
- 裁决:PASS。

## G3 · 测试闸

- RED:`cd backend && DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/python -m pytest tests/test_overseas_health_os_eval_suite.py -q --no-cov`
  - 失败原因:缺少 `_score_overseas_health_os`。
- PASS:同一命令。
  - 3 passed。
- PASS:`cd backend && DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/python -m eval run --suite overseas_health_os`
  - `overseas_health_os: 5/5 pass (100.0%), avg_score=1.000, avg_latency=0ms`

## G4 · 安全闸

- 只新增离线评测和文档,不触达生产用户数据。
- 评测内置 `safety_boundary` 维度,红旗胃肠出血 case 必须升级,不能进入饮食记录。
- 裁决:GO。

## S7 · 本次交付物

- `docs/plans/2026-07-05-overseas-health-os-market-entry-plan.md`
- `backend/eval/datasets/overseas_health_os.yaml`
- `backend/eval/baselines/overseas_health_os_main.json`
- `backend/tests/test_overseas_health_os_eval_suite.py`
- `backend/eval/runner.py`

## S8 · 后续沉淀

- 下一批把 lbclaw / ChatGPT / 阿福 / 小巴的同题输出接入同一个 case schema,先人工采样,再考虑自动化。
- 再下一批把 `overseas_health_os` 纳入 release gate 的可选质量闸,避免早期 UI/饮食链路改动破坏 Health OS 差异化。

## S7 · 第二批交付物(2026-07-05)

- 范围:Task 3 Meal Health Loop 的文本记餐动态 UI 最小闭环。
- 后端:`diet_draft` 卡片增加结构化 `next_meal_detail`,并下发 `ui.inline.expand` 的“看下一餐建议”动作。
- Mobile:`DietDraftCard` 支持原地展开下一餐建议,保留确认写入、修正和低打扰交互。
- 安全边界:确认写入仍需 manual-confirm;新增 action 只做本地展开,不写库、不跳页、不调用外部服务。
- PASS:`cd backend && DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/python -m pytest tests/test_inline_cards_runtime_agenda.py tests/test_inline_cards_intake_dedup.py -q --no-cov`
  - 26 passed。
- PASS:`cd mobile && ./node_modules/.bin/jest --runTestsByPath services/__tests__/chatCardActions.test.ts components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx components/chat/cards/__tests__/registry.test.tsx --runInBand --silent=false`
  - 3 suites passed,80 tests passed。

## S8 · 下一批剩余

- 小巴对话内拍照直接生成 `diet_draft`,减少跳转到饮食页再拍照的链路。
- 确认写入后展示更明确的今日饮食进度反馈卡。
- 进入 Task 4:Wearable Context Summary,把 7 天 sleep/HRV/RHR/activity 摘要注入饮食建议。

## S7 · 第三批交付物(2026-07-05)

- 范围:Task 4 Wearable Context Summary 的后端最小闭环。
- 新增:`backend/app/services/health_context_summary.py` 生成 7 日 sleep/HRV/RHR/activity 聚合摘要、`data_gap` 和隐私边界。
- Agent:轻量健康上下文追加 `[可穿戴7日摘要]`,给 LLM 只传聚合状态和建议偏置,不传原始逐日/分钟级数据。
- 饮食卡:记录后的“下一餐建议”读取同一份恢复态;睡眠/恢复差时改为温和、足蛋白、补水、避免大热量缺口;恢复好时按正常蛋白和蔬菜目标推进。
- 安全边界:不新增自动写库、不诊断、不处方;可穿戴缺数据时降级为 `data_gap`,不强行个性化。
- RED:`cd backend && DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/python -m pytest tests/test_wearable_context_summary.py -q --no-cov`
  - 失败原因:缺少 `app.services.health_context_summary`,轻量上下文没有 `[可穿戴7日摘要]`。
- PASS:`cd backend && DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/python -m pytest tests/test_wearable_context_summary.py -q --no-cov`
  - 3 passed。
- PASS:`cd backend && DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/python -m pytest tests/test_health_context_lite.py tests/test_post_record_quality.py tests/test_agent_executor_health_query_wearable.py -q --no-cov`
  - 21 passed。

## S8 · 下一批剩余(更新)

- 小巴对话内拍照直接生成 `diet_draft`,减少跳转到饮食页再拍照的链路。
- 确认写入后展示更明确的今日饮食进度反馈卡。
- 将 Apple Health/HealthKit 授权、同步新鲜度和 `data_gap` 原因前端化。
- 饮食建议卡显式展示数据来源和置信度,与 Quality Metrics 的 data-source citation coverage 对齐。
- 进入 Task 5:Lab-Aware Advice Boundary,把 HbA1c/血脂/ALT/GGT/H. pylori/胃镜事实与 advice guard 联动。
