# TokenPlan 人民币成本可见性 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 TokenPlan 每次调用和聚合用量转换为人民币套餐容量成本，并在 Mobile、Web、Mac、Admin 统一展示。

**Architecture:** 后端在 `usage_tracker` 的单次调用 choke point 计算 Credits 与人民币容量成本，通过现有 `llm_usage` 附加字段传到三端。Admin 使用同一价格规则构建 SQL 聚合，保留按量价对照，但不再把原始 Token 等权当作成本。

**Tech Stack:** FastAPI、SQLAlchemy、pytest、React/TypeScript、React Native、Swift Package/XCTest。

---

### Task 1: 定义后端人民币换算契约

**Files:**
- Modify: `backend/tests/test_llm_usage_tracker.py`
- Modify: `backend/app/services/llm/usage_tracker.py`
- Modify: `backend/app/config.py`

1. 写失败测试，断言 TokenPlan 调用返回 Credits、容量成本、来源和套餐参数。
2. 运行聚焦测试并确认因字段缺失而失败。
3. 增加人民币价格表、阶梯选择、缓存折扣和 `Credits × 月费/额度` 换算。
4. 运行聚焦测试并确认通过。

### Task 2: 接入 Agent 响应与历史消息

**Files:**
- Modify: `backend/tests/test_agent_send_observability.py`
- Modify: `backend/app/services/agent_send_meta.py`

1. 写失败测试，断言非流式 `meta.cost_estimate` 同时包含套餐折算和按量对照。
2. 保持字段纯附加，缺少套餐估算时返回 `null` 而非 `0`。
3. 运行 Agent 观测测试。

### Task 3: 修正 Admin 成本视图

**Files:**
- Modify: `backend/tests/test_admin_llm_usage_dashboard.py`
- Modify: `backend/app/api/admin_llm.py`
- Modify: `frontend/src/app/admin/llm-performance/page.tsx`

1. 写失败测试，断言 Admin 返回窗口容量成本和估算 Credits。
2. 复用同一模型价格规则生成 SQL 聚合。
3. Admin 首屏显示固定月费、容量折算、按量对照和节省估算。
4. 运行后端与前端聚焦测试。

### Task 4: Mobile 与 Web 人民币主显示

**Files:**
- Modify: `mobile/utils/__tests__/chatTransparency.test.ts`
- Modify: `mobile/utils/chatTransparency.ts`
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `frontend/src/components/assistant/chatTransparency.test.ts`
- Modify: `frontend/src/components/assistant/chatTransparency.ts`
- Modify: corresponding Web transparency renderer

1. 先将测试期望改为 `约¥...` 主标题和无金额 Token 明细，确认失败。
2. 增加套餐折算、按量对照和 Token 三层展示。
3. 运行 Jest、Vitest 与 TypeScript 检查。

### Task 5: Mac 人民币主显示

**Files:**
- Modify: `apps/mac/Tests/HealthAgentMacCoreTests/ChatTranscriptHTMLTests.swift`
- Modify: `apps/mac/Sources/HealthAgentMacCore/LLMUsageProfile.swift`
- Modify: `apps/mac/Sources/HealthAgentMacCore/ChatTranscriptHTML.swift`

1. 写失败 XCTest，断言折叠态人民币优先、Token 进入详情。
2. 扩展 DTO 并实现与 Web/Mobile 一致的文案。
3. 运行 `swift test`。

### Task 6: 文档、集成验证和发布

**Files:**
- Modify: `docs/dossiers/2026-07-02-llm-cost-observability.md`
- Modify: `docs/llm_cost_metric.md`

1. 更新成本口径和 Gate 记录。
2. 运行后端聚焦 pytest、Mobile Jest/tsc、Frontend Vitest/tsc、Mac XCTest、doc drift 和 `git diff --check`。
3. 仅提交本功能文件并推送 `main`。
4. 后端/Web 部署后验证健康端点和 Admin 页面；Mobile 走 production OTA；Mac 重新打包、安装并启动。

