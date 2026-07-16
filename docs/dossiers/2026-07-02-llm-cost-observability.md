# Dossier: LLM 成本与性能剖析

| 字段 | 值 |
|---|---|
| slug | `llm-cost-observability` |
| 创建日期 | 2026-07-02 |
| 当前阶段 | S8 上线验证 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | TDD / backend pytest / web+mobile tsc / backend deploy / mobile OTA |

## 用户原话

- "我升级了套餐，用了一个月698的，帮我做下Token的费用的统计和度量，给Admin用户开放全局的监控，每个用户的使用情况以及全局使用情况"
- "记录一下每一次调用的Token使用情况，输入token和输出token，并且在端上做简要输出（mac web mobile 上，归入到成本和性能剖析的逻辑里边）"
- "类似于mac app上做的透视"
- "继续执行"
- "可以 按照顺序执行"
- "我的计费逻辑是怎样的，如何估算Token成本的，我走的是阿里云的TokenPlan，月订阅费是 698 元 RMB。"
- "我还是想直接看到多少钱，帮我做转化"
- "可以"

## G1 · 准入裁决

- 对象:`AgentRunProgress`, `ChatMessage`, `AdminObservability`, `ProvenanceRecord`。
- core_loop_step:用户/管理员观察 Agent 调用 → 定位成本、延迟、失败 → 继续优化模型和上下文。
- safety_level:operational_observability;不新增健康建议、不新增写路径。
- autonomy_tier:no_write。
- spec_required:否,沿用既有 LLM 用量账本和 Admin 监控。
- 裁决:PASS。

## 范围

- 最小切片:
  - 保留既有 `llm_usage_logs` 调用级账本和 `/admin/llm-performance`。
  - 增加失败调用的错误摘要字段，支撑 429/额度/鉴权/上游错误诊断。
  - 增加 Admin 最近逐次调用明细。
  - Web/Mobile 对话透视面板展示失败摘要。
  - 增加 TokenPlan 月度预算阈值、用量水位、 projected 月用量与 Admin 告警。
  - 增加 LLM 失败分类和显式配置备用模型的一跳恢复,避免普通异常静默吞掉或随机换模型产生额外成本。
  - 增加单次回复 `run_id` trace,串联 backend 账本、Admin run detail、Web/Mobile/Mac 端上透视。
- 安全边界: 只记录上游错误摘要，长度限制 500，不记录 prompt、响应正文、密钥或完整请求体。
- 成本边界: 自动恢复只在 `LLM_RECOVERY_MODEL_ID` 显式配置且可用时触发;不从 registry 随机挑选可用模型。

## 现状发现

- 已有 `backend/app/models/llm_usage.py` 和 `backend/app/services/llm/usage_tracker.py` 记录调用级 token/cost。
- 已有 `backend/app/api/admin_llm.py` 汇总全局、用户、模型、调用方、失败样本。
- 已有 Mac/Web/Mobile 单次回复透视面板消费 `llm_usage` 和 `perf`。
- 缺口: 失败样本没有 `error_type/error_code/error_message`；Admin 没有逐次调用列表；端上透视不显示失败摘要。
- 第二轮缺口: Admin 缺预算水位/超额预警；额度错误只能失败不能恢复；单次回复和后台账本缺稳定 trace id。

## 交付记录

- 后端:
  - `llm_usage_logs` 新增 `error_type/error_code/error_message`。
  - `usage_tracker` 在普通和流式 LLM 调用失败时提取上游错误摘要并写入账本。
  - `/api/v1/admin/llm/performance-failures` 返回错误摘要。
  - `/api/v1/admin/llm/recent-calls` 返回最近逐次调用明细。
- Web:
  - `/admin/llm-performance` 增加最近逐次调用表。
  - 对话透视面板展示失败摘要。
- Mobile:
  - 对话透视面板展示失败摘要。
- 第二轮:
  - `llm_usage_logs` 新增 `run_id/error_class/recovery_action/recovery_model`。
  - `usage_tracker` 增加 request 级 run trace、失败分类和显式备用模型恢复。
  - `/api/v1/admin/llm/usage-dashboard` 增加 `quota_guard`。
  - `/api/v1/admin/llm/runs/{run_id}` 增加单次 run 明细。
  - Web/Mobile/Mac 透视面板展示 run trace 和恢复摘要。

## G2 · 可行性 + 安全压测

- 沿用现有账本，不引入新第三方。
- 错误摘要做长度限制，不写 prompt、响应正文、密钥或完整请求体。
- 只读观测，不改变 LLM 业务路径和健康建议边界。
- 裁决:PASS。

## G3 · 测试闸

- 裁决:PASS。

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai ./backend/.venv/bin/python -m pytest backend/tests/test_llm_usage_tracker.py backend/tests/test_admin_llm_usage_dashboard.py -q --no-cov
# 15 passed
```

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai ./backend/.venv/bin/python -m pytest backend/tests/test_managed_migrations.py -q --no-cov
# 7 passed
```

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai ./backend/.venv/bin/python -m pytest backend/tests/test_agent_executor_fast_routing.py -q --no-cov
# 51 passed
```

```bash
npm --prefix mobile test -- --runInBand utils/__tests__/chatTransparency.test.ts
# 4 passed
```

```bash
pnpm --dir frontend test -- src/components/assistant/chatTransparency.test.ts
# 34 files passed / 183 tests passed
```

```bash
npx tsc --noEmit
# mobile exit 0
```

```bash
pnpm --dir frontend exec tsc --noEmit
# exit 0
```

```bash
npm run generate-types # frontend
npm run generate-types # mobile
# OpenAPI 类型已同步
```

## G4 · 安全闸

- 无健康建议路径变更。
- 无用药、诊断、基因、化验、CGM、HealthKit 写路径变更。
- 新增字段为运维错误摘要,限制 500 字符。
- 自动恢复只处理 quota/rate-limit/timeout/5xx 等基础设施失败;auth/unknown 不恢复。
- 备用模型必须显式配置,避免成本不可控。
- 裁决:GO。

## G5/G6 · 部署与上线验证

- 代码提交: `7c57350e`。
- Mac 端补充提交: `b4b6f7b9`。
- Web/Backend 部署: `./deploy.sh -y`。
- 受控迁移: `20260702_180000_add_llm_usage_error_context` 已应用。
- 部署健康度: `60/60 ✅ PASS`。
- Skills manifest: 本地 22 = 线上 22。
- Mobile OTA: production channel, runtime `1.3.1`, update group `df0e5731-3476-4510-b506-7133a51940c2`, iOS update `019f214f-7c92-7ce7-8439-d0c141eb7d78`。
- Mac 本地发布: `apps/mac/scripts/package-app.sh --install --open` 已安装 `/Applications/阿衡.app`，进程 `HealthAgentMac` 已运行。
- 线上验证:
  - `https://health.executor.life/api/v1/health` 返回 `healthy`。
  - `https://health.executor.life/admin/llm-performance` 返回 HTTP 200。
- 第二轮扩展提交: `ca919f18`。
- 第二轮 Web/Backend 部署: `./deploy.sh -y`。
- 第二轮部署健康度: `60/60 ✅ PASS`。
- 第二轮受控迁移: `20260702_190000_add_llm_usage_recovery_trace` 已被生产迁移账本识别。
- 第二轮 Mobile OTA: production channel, runtime `1.3.1`, update group `9871448a-b0f3-4941-bf20-956ea5785b29`, iOS update `019f2176-0f41-7eeb-99fc-385107d16a23`。
- 第二轮 Mac 本地发布: `apps/mac/scripts/package-app.sh --install --open` 已安装 `/Applications/阿衡.app`, `HealthAgentMac` 进程已运行。
- 第二轮线上验证:
  - `https://health.executor.life/api/v1/health` 返回 `healthy`。
  - `https://health.executor.life/admin/llm-performance` 返回 HTTP 200。
- 裁决:GO。

## 验证记录

- 2026-07-02: 已完成测试、部署、线上健康检查和 Mobile OTA。
- 2026-07-02: 第二轮已完成预算水位、恢复 trace、三端透视验证、Web/Backend 部署、Mobile OTA 与 Mac 重启。

## 2026-07-16 · 人民币容量成本扩展

- 当前阶段:S3 规划。
- 状态:building。
- 设计:`docs/plans/2026-07-16-tokenplan-rmb-cost-visibility-design.md`。
- 计划:`docs/plans/2026-07-16-tokenplan-rmb-cost-visibility-plan.md`。
- G1:PASS。复用 `AdminObservability` 与 `ChatMessage`，只增加成本解释，不新增健康行为或写路径。
- G2:PASS。主金额采用 `Credits × ¥698 / 100000`；Credits 暂按公开模型人民币价格估算并始终标记“约”，按量价保留为对照，原始 Token 不降精度。
