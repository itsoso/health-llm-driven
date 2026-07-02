# Dossier: Admin LLM Run Trace Drill-down

| 字段 | 值 |
|---|---|
| slug | `admin-llm-run-drilldown` |
| 创建日期 | 2026-07-02 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | Quick Flow / TDD / frontend vitest+tsc / deploy |

## 用户原话

- "继续"

## G1 · 准入裁决

- 对象:`AdminObservability`, `AgentRunProgress`, `ProvenanceRecord`。
- core_loop_step:管理员从异常成本/失败调用定位到单次回复的模型调用链,再决定模型、预算或提示词优化。
- safety_level:operational_observability;不新增健康建议、不新增写路径。
- autonomy_tier:no_write。
- spec_required:否,沿用既有 Admin LLM 账本和 run detail API。
- smallest_end_to_end_slice:Admin `/admin/llm-performance` 最近调用/失败调用中的 `run_id` 可点击,打开同页详情面板展示 calls、failed_calls、tokens、latency、每轮模型/错误/恢复信息。
- 裁决:PASS。

## 现状发现

- 后端已提供 `/api/v1/admin/llm/runs/{run_id}` 并有测试覆盖。
- Admin 页面已展示 `run_id`,但目前只是短文本,不能 drill-down。
- 缺口是 UI 消费 run detail API、加载/404/error 状态和一屏可读的调用链。

## G2 · 可行性 + 安全压测

- 只读 Admin 页面增强,不触碰健康建议、用药、诊断、数据写入、通知或用户端主路径。
- 请求继续沿用 Admin token;无新增权限面。
- 错误摘要沿用后端已脱敏/截断字段,不展示 prompt/response 正文。
- 裁决:PASS。

## 计划

1. RED:为 run detail 的标题/状态/汇总 helper 写前端测试。
2. GREEN:实现 helper 与 Admin 页面详情面板。
3. VERIFY:跑 targeted vitest、frontend tsc、dossier consistency。
4. SHIP:提交、推送、部署 Web/Backend(前端页面改动)并回写上线证据。

## 交付记录

- 新增 `frontend/src/app/admin/llm-performance/llmRunTrace.ts`,集中处理 run detail 标题、汇总、状态色和每轮调用行。
- 新增 `llmRunTrace.test.ts`,覆盖失败+恢复 run、纯成功 run、调用链行格式。
- `/admin/llm-performance` 最近失败调用和最近逐次调用中的 `run_id` 变为可点击。
- 点击后同页展开 Run Trace 面板,展示总调用数、失败数、tokens、延迟、恢复动作和每轮模型/错误/恢复信息。

## G3 · 测试闸

- 裁决:PASS。

```bash
pnpm --dir frontend test -- src/app/admin/llm-performance/llmRunTrace.test.ts
# 35 files passed / 187 tests passed
```

```bash
pnpm --dir frontend exec tsc --noEmit
# exit 0
```

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai ./backend/.venv/bin/python backend/scripts/check_dossier_consistency.py
# 37 dossiers self-consistent
```

## G4 · 安全闸

- 只读 Admin observability;未新增健康建议、医疗判断、写路径、通知或用户端暴露面。
- 继续使用既有 Admin token 和后端错误摘要字段。
- 裁决:GO。

## G5/G6 · 部署与上线验证

- 代码提交: `e0f51f72`。
- Web/Backend 部署: `./deploy.sh -y`。
- 部署健康度: `55/60 ✅ PASS`。
- 前端构建: `/admin/llm-performance` bundle 已生成并重启 `health-frontend` PM2。
- 线上验证:
  - `https://health.executor.life/api/v1/health` 返回 `healthy`。
  - `https://health.executor.life/admin/llm-performance` 返回 HTTP 200。
- 注意: 部署完成后 `origin/main` 出现并发提交 `8e760bec`(KB provenance lineage),不属于本轮部署证据。
- 裁决:GO。

## 验证记录

- 2026-07-02: Run Trace drill-down 已上线;Admin 可从失败调用/最近调用点击 `run_id` 查看本次回复的 LLM 调用链。
