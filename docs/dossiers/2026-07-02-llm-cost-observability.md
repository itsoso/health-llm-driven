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
- 安全边界: 只记录上游错误摘要，长度限制 500，不记录 prompt、响应正文、密钥或完整请求体。

## 现状发现

- 已有 `backend/app/models/llm_usage.py` 和 `backend/app/services/llm/usage_tracker.py` 记录调用级 token/cost。
- 已有 `backend/app/api/admin_llm.py` 汇总全局、用户、模型、调用方、失败样本。
- 已有 Mac/Web/Mobile 单次回复透视面板消费 `llm_usage` 和 `perf`。
- 缺口: 失败样本没有 `error_type/error_code/error_message`；Admin 没有逐次调用列表；端上透视不显示失败摘要。

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

## G2 · 可行性 + 安全压测

- 沿用现有账本，不引入新第三方。
- 错误摘要做长度限制，不写 prompt、响应正文、密钥或完整请求体。
- 只读观测，不改变 LLM 业务路径和健康建议边界。
- 裁决:PASS。

## G3 · 测试闸

- 裁决:PASS。

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai ./backend/.venv/bin/python -m pytest backend/tests/test_llm_usage_tracker.py backend/tests/test_admin_llm_usage_dashboard.py -q --no-cov
# 11 passed
```

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai ./backend/.venv/bin/python -m pytest backend/tests/test_managed_migrations.py -q --no-cov
# 7 passed
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

## G4 · 安全闸

- 无健康建议路径变更。
- 无用药、诊断、基因、化验、CGM、HealthKit 写路径变更。
- 新增字段为运维错误摘要,限制 500 字符。
- 裁决:GO。

## G5/G6 · 部署与上线验证

- 代码提交: `7c57350e`。
- Web/Backend 部署: `./deploy.sh -y`。
- 受控迁移: `20260702_180000_add_llm_usage_error_context` 已应用。
- 部署健康度: `60/60 ✅ PASS`。
- Skills manifest: 本地 22 = 线上 22。
- Mobile OTA: production channel, runtime `1.3.1`, update group `df0e5731-3476-4510-b506-7133a51940c2`, iOS update `019f214f-7c92-7ce7-8439-d0c141eb7d78`。
- 线上验证:
  - `https://health.executor.life/api/v1/health` 返回 `healthy`。
  - `https://health.executor.life/admin/llm-performance` 返回 HTTP 200。
- 裁决:GO。

## 验证记录

- 2026-07-02: 已完成测试、部署、线上健康检查和 Mobile OTA。
