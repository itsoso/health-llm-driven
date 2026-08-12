# Agent Supplement Batch Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让显式多补剂记录和紧邻确认后的“全部已服用”稳定产生逐项、用户隔离、带 verified receipt 的补剂写入，并消除错误的通用缺字段回退。

**Architecture:** capability policy 负责从当前轮解析并授权多个显式补剂目标；AgentExecutor 负责识别收紧的全量确认续接、从当前用户活动定义构建 server-owned 授权集合，并在模型零工具调用时生成一次性确定性 `health_record(supplement)` 调用。所有调用继续经过现有 gateway、写计划和 receipt 校验，不新增直写路径。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、pytest、现有 Agent Kernel / ToolGateway / AgentExecutor。

---

### Task 1: 固化显式多补剂解析失败

**Files:**
- Modify: `backend/tests/test_agent_kernel_capability_policy.py`
- Modify: `backend/app/services/agent_kernel/capability_policy.py`

**Step 1: Write the failing tests**

增加三个回归断言：

- “记录下来，吃了一粒甘氨酸镁和一粒褪黑素”不得授权名称“下来”；
- `甘氨酸镁` 和 `褪黑素` 两个独立工具调用均被允许；
- dispatch projection 为每个调用保留其已授权的规范名称，而非都覆盖为第一个名称。

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest -q tests/test_agent_kernel_capability_policy.py -k 'supplement and (multiple or explicit or projection)'`

Expected: FAIL，展示“下来”误提取、第二目标未授权或被投影成第一目标。

**Step 3: Write minimal implementation**

修改 `_named_item_targets` 和 `_project_authorized_dispatch_payload`：清理写入动作残留、拆分补剂并列连接词、去重，按本次已授权请求目标投影。

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest -q tests/test_agent_kernel_capability_policy.py -k 'supplement'`

Expected: PASS，且既有补剂别名/grounding 负例保持通过。

**Step 5: Commit**

```bash
git add backend/app/services/agent_kernel/capability_policy.py backend/tests/test_agent_kernel_capability_policy.py
git commit -m "fix(agent): parse multiple supplement targets"
```

### Task 2: 固化收紧的“全部已服用”续接

**Files:**
- Modify: `backend/tests/test_agent_executor_fast_routing.py`
- Modify: `backend/tests/test_agent_simple_record_goal_guard.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/agent_kernel/capability_policy.py`

**Step 1: Write the failing tests**

覆盖：

- 当前轮“全部已服用”且上一条助手明确询问“全部 N 种补剂是否都记录为已服用”时，识别为 supplement write continuation；
- 无上一轮、上一轮不是补剂全量确认、或当前短语模糊时不授权；
- 上下文目标只能来自当前 `user_id` 的活动 `SupplementDefinition`，停用项和其他用户项不进入集合；
- server-owned 集合内名称通过 goal guard，集合外名称和 medication 继续拒绝。

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest -q tests/test_agent_executor_fast_routing.py tests/test_agent_simple_record_goal_guard.py -k 'supplement_all or all_taken'`

Expected: FAIL，当前实现无法构建 owner-scoped continuation 授权。

**Step 3: Write minimal implementation**

- 新增纯函数识别当前完成短语和紧邻助手确认语句；
- 在当前回合查询 `SupplementDefinition.user_id == user_id` 且 `is_active` 的名称，稳定去重；
- 将集合保存在 Executor 当前回合内部状态，并通过现有 server-authorized health-record provenance 接入 policy；
- 执行器 supplement grounding 只对该精确集合放行，不信任模型或助手提供的名称。

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest -q tests/test_agent_executor_fast_routing.py tests/test_agent_simple_record_goal_guard.py -k 'supplement or all_taken'`

Expected: PASS。

**Step 5: Commit**

```bash
git add backend/app/services/agent_executor.py backend/app/services/agent_kernel/capability_policy.py backend/tests/test_agent_executor_fast_routing.py backend/tests/test_agent_simple_record_goal_guard.py
git commit -m "fix(agent): authorize contextual supplement completion"
```

### Task 3: 增加零工具调用的确定性补剂兜底

**Files:**
- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`
- Modify: `backend/tests/test_agent_executor_completion_status.py`
- Modify: `backend/app/services/agent_executor.py`

**Step 1: Write the failing tests**

模拟模型返回纯文本且无 tool call：

- 显式两个补剂名时生成两个 `health_record(supplement)` 调用；
- 全量确认续接时为当前用户全部活动补剂生成逐项调用；
- 每项成功后均有正资源 ID receipt，回合 `completion_status=complete`，不含 `record_intent_no_tool`；
- 无上下文“全部已服用”不生成工具调用；
- 兜底一回合最多一次，不能重复写入。

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest -q tests/test_agent_stream_no_false_record_claim.py tests/test_agent_executor_completion_status.py -k 'supplement and (fallback or all_taken or multiple)'`

Expected: FAIL，模型零工具调用仍进入通用缺字段回退。

**Step 3: Write minimal implementation**

在现有 simple-record deterministic fallback 邻近增加补剂调用 builder：从当前轮显式目标或 server-owned 全量集合生成稳定、去重的逐项工具调用；仅在无 receipt、无工具调用且未尝试过时触发一次。

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest -q tests/test_agent_stream_no_false_record_claim.py tests/test_agent_executor_completion_status.py -k 'supplement or record_intent_no_tool'`

Expected: PASS。

**Step 5: Commit**

```bash
git add backend/app/services/agent_executor.py backend/tests/test_agent_stream_no_false_record_claim.py backend/tests/test_agent_executor_completion_status.py
git commit -m "fix(agent): persist supplement batches deterministically"
```

### Task 4: 集成验证、文档回填与安全闸

**Files:**
- Modify: `docs/dossiers/2026-08-11-agent-supplement-batch-repair.md`

**Step 1: Run focused regression suites**

Run:

```bash
cd backend
pytest -q tests/test_agent_kernel_capability_policy.py tests/test_agent_executor_fast_routing.py tests/test_agent_simple_record_goal_guard.py tests/test_agent_stream_no_false_record_claim.py tests/test_agent_executor_completion_status.py tests/test_supplement_evidence.py tests/test_write_receipt_identity.py
```

Expected: PASS。

**Step 2: Run static and governance checks**

Run:

```bash
cd backend
ruff check app/services/agent_executor.py app/services/agent_kernel/capability_policy.py tests/test_agent_kernel_capability_policy.py tests/test_agent_executor_fast_routing.py tests/test_agent_simple_record_goal_guard.py tests/test_agent_stream_no_false_record_claim.py tests/test_agent_executor_completion_status.py
cd ..
python scripts/check_doc_drift.py
python backend/scripts/check_dossier_consistency.py
git diff --check
```

Expected: 全部 exit 0。

**Step 3: Independent safety review**

按 `.claude/skills/safety-gate/SKILL.md` 审查用户隔离、健康写入授权、部分失败语义、模型字段伪造和药物越界；任何 BLOCK 回到对应实现任务，不带红继续。

**Step 4: Update dossier and commit**

把实际测试结果、review 发现与 G3/G4 裁决写入 dossier。

```bash
git add docs/dossiers/2026-08-11-agent-supplement-batch-repair.md
git commit -m "docs(agent): record supplement repair gates"
```

### Task 5: 推送、部署和上线验证

**Files:**
- Modify: `docs/dossiers/2026-08-11-agent-supplement-batch-repair.md`

**Step 1: Verify branch and push main**

Run:

```bash
git status --short --branch
git log -1 --oneline
git push origin main
```

Expected: push succeeds without staging unrelated workspace files。

**Step 2: Deploy backend from a clean main checkout**

运行项目根 `deploy.sh` 的 backend-only 路径，记录目标 SHA、回滚 SHA、备份与 health score。工作区存在他人改动时使用基于目标 main SHA 的干净临时 clone，不清理或暂存他人文件。

**Step 3: Verify production path**

检查后端健康、启动错误和 `/api/v1/agent/stream` 鉴权 smoke；在获授权的真实路径执行两句锚点验证，确认逐项 verified receipt、回合完成以及无英文内部字段。任何合成健康记录按 owner + exact ID 精确清理。

**Step 4: Update dossier and push final evidence**

回填 S6/G5/S7/G6；若还需用户真机确认，将 G6 保持 pending，不伪装为 shipped。

```bash
git add docs/dossiers/2026-08-11-agent-supplement-batch-repair.md
git commit -m "docs(agent): record supplement repair delivery"
git push origin main
```
