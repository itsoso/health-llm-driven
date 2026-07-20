# Mobile 今日行动管理 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复“管理今日行动”无法返回和列表不可管理的问题，建立只面向今日、可完成闭环并能返回小巴的行动管理页。

**Architecture:** 后端动态卡片把今日模式的管理入口从隐藏 `/alerts` 改到根 Stack `/agenda`。Mobile 重构 `/agenda` 为今日管理页，复用现有议程查询和确认写回接口，并集中处理分组、返回兜底、缓存刷新和用户操作菜单。

**Tech Stack:** FastAPI/Python, React Native 0.83, Expo Router 55, TanStack Query, Jest/RNTL

---

### Task 1: 修正动态卡片路由契约

**Files:**
- Modify: `backend/app/services/inline_cards.py`
- Modify: `backend/tests/test_inline_cards_runtime_agenda.py`
- Modify: `backend/tests/test_today_dynamic_view.py`

1. 先把测试期望改为今日模式 `payload.route == "/agenda"`。
2. 运行两个测试文件，确认因当前仍返回 `/alerts` 而失败。
3. 修改 runtime agenda action builder，使今日和完整计划统一进入 `/agenda`，但保留不同标签。
4. 重跑测试，确认通过。

### Task 2: 建立今日列表的纯函数合同

**Files:**
- Create: `mobile/utils/todayAgendaManagement.ts`
- Create: `mobile/utils/__tests__/todayAgendaManagement.test.ts`

1. 先写失败测试，覆盖待处理/已处理分组、优先级排序、内部标签清理和深链返回目标。
2. 运行单测确认 RED。
3. 实现最小纯函数：`groupTodayAgendaItems`、`cleanAgendaTitle`、`resolveAgendaBackRoute`。
4. 重跑单测确认 GREEN。

### Task 3: 补齐写回 Hook

**Files:**
- Modify: `mobile/hooks/useAgenda.ts`
- Create: `mobile/hooks/__tests__/useAgendaManagement.test.ts`

1. 先写失败测试，要求完成或跳过成功后同步失效 `agenda`、`timeline`、`daily-artifact`、`today-dynamic-view` 查询。
2. 扩展 mutation 参数支持 `status` 和 `skipReason`，仍调用现有 `/agenda/complete`。
3. 写入失败保持 fail-loud，由页面展示错误。
4. 重跑 Hook 测试。

### Task 4: 重构 `/agenda` 为今日行动管理页

**Files:**
- Modify: `mobile/app/agenda.tsx`
- Create: `mobile/app/__tests__/agenda.test.tsx`

1. 先写页面失败测试：可见返回按钮、今日分组、完成、跳过、稍后、调整和深链返回兜底。
2. 用原生 Stack 语义和 `Pressable` 重做紧凑顶部。
3. 使用虚拟列表渲染今日事项，不再在首屏展开七天运行时和重复智能排序面板。
4. 每行提供一个明确主操作与原生/平台菜单；跳过原因需二次确认。
5. 操作成功更新列表，失败显示可重试状态。
6. 重跑页面测试与 Agenda 相关回归。

### Task 5: 导航、文档与发布验证

**Files:**
- Modify: `mobile/app/_layout.tsx`
- Modify: `docs/system-map/mobile-nav-map.md`
- Modify: `docs/dossiers/2026-07-20-mobile-today-actions-management.md`
- Regenerate: `docs/_generated/mobile-nav-graph.json`（若生成器检测到结构变化）

1. 把 `/agenda` 显式注册为根 Stack 页面，启用 iOS 返回手势。
2. 更新 Mobile 动线文档，废弃“小巴今日行动 -> 全量 alerts”链路。
3. 运行 Jest、TypeScript、设计检查和 doc drift。
4. 在模拟器验证：小巴进入、操作、返回、列表刷新。
5. 仅在所有 Gate 通过后提交、推送并执行 production OTA。

