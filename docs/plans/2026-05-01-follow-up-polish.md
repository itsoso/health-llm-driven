# 记忆与推理可见化 v1 — Follow-up Polish

> 从 2026-05-01 记忆/推理可见化 v1 的 code quality review 里累积的 non-blocking 项. 批准上线了但值得下次碰到同一文件时顺手清理.

**来源**: Task 1.1–9 review 过程中 reviewers 标的 "flag, not block"
**原则**: 只在"下次碰这个文件的时候顺手修"级别. 不单开 sprint 做这批.

---

## Mobile (dark mode / UX)

### M1. Reasoning Sheet 硬编码色彩 (Task 3 flag)

**文件**: `mobile/components/reasoning/ExplainSheet.tsx` + `ExplainButton.tsx`

**问题**: 硬编码了 `#EEF2FF / #4F46E5 / #fff / #111827 / #6B7280 / #D1D5DB / #9CA3AF / #B91C1C`. 在 dark mode 下白底白字显眼 bug.

**修复**: 全部走 `useTheme().c`. 参考 `mobile/app/(tabs)/journal/index.tsx:145` 的模式 — `const { c } = useTheme(); const styles = useMemo(() => createStyles(c), [c]);`

**估时**: 15 分钟

### M2. Specialist 详情页错误态 (Task 7 flag)

**状态**: ✅ 已完成

**文件**: `mobile/app/specialist/[name].tsx`

**问题**: `useSpecialistScorecard` 报错时页面静默为空 (no spinner, no message). 用户以为在 loading.

**修复**: 
```tsx
{q.isError && <Text>加载失败: {q.error?.message ?? '网络问题'}, 下拉重试</Text>}
```

**估时**: 5 分钟

### M3. 详情页 name 缺失边界 (Task 7 flag)

**状态**: ✅ 已完成

**文件**: `mobile/app/specialist/[name].tsx:62`

**问题**: 若 URL 乱输 (deep link 错了), `useLocalSearchParams` 返 `{}`, `label = "未知"`, 页面显示标题"未知 成绩单" 无内容.

**修复**: `if (!name) { router.back(); return null }` 或显示"specialist 未知, 返回首页"按钮.

**估时**: 5 分钟

### M4. Journal 无主题 bucket entries 4+ 不可见 (Task 5 flag)

**状态**: ✅ 已完成，采用推荐方案 (a)

**文件**: `mobile/app/(tabs)/journal/index.tsx`

**问题**: 无主题 bucket 只 preview 前 3 条, "+ N 条更多..." 但卡片不可点 (null thread_id). 超出 3 条的 entries 用户看不到.

**修复选项**:
- (a) 后端 `/clinical-journal/timeline` 把 null bucket entries 限 3 条, 去掉 "+ N" 提示
- (b) Mobile 允许点击 "+ N 条更多..." 就地展开
- (c) 单独页 `/journal/orphans` 列所有无主题 entries

推荐 (a), 最诚实.

**估时**: 15 分钟 (选 a)

### M5. 死代码 `useCaseList` / `useRecentEntries` (Task 5 flag)

**状态**: ✅ 已完成

**文件**: `mobile/hooks/useClinicalJournal.ts`, `mobile/services/clinicalJournal.ts`

**问题**: 这两 hook + 对应 `listCases` / `recentEntries` service + `CaseSummary` / `RecentEntry` 类型, 自从 Task 5 Journal tab 改用 `useJournalTimeline` 后**零消费者**. 仅 `useCaseDetail` 仍被 `journal/[id].tsx` 用.

**修复**: 删除 `useCaseList`, `useRecentEntries`, `listCases`, `recentEntries`, `CaseSummary`, `RecentEntry`. 保留 `useCaseDetail` + `getCaseDetail` + `CaseDetail` + `JournalEntry`.

**估时**: 10 分钟 (一次 grep 就能确认没有引用)

---

## Backend (quality / safety)

### B1. POST /client-events 的 meta 无大小限制 (Task 9 flag)

**文件**: `backend/app/api/client_events.py`

**问题**: `EventIn.meta: Optional[Dict[str, Any]]` — 恶意/bug client 可塞任意 JSON. Auth 和白名单已限制风险, 但原则上应限大小.

**修复**: 加 Pydantic v2 validator:
```python
from pydantic import field_validator

@field_validator("meta")
@classmethod
def _meta_size_limit(cls, v):
    if v is None:
        return v
    import json
    if len(json.dumps(v)) > 2048:
        raise ValueError("meta too large (max 2KB)")
    return v
```

**估时**: 10 分钟

### B2. `/reasoning-trace` endpoint 文件内 inline import (Task 2.2 flag)

**文件**: `backend/app/api/reasoning_trace.py`

**问题**: `from app.services.reasoning_explainer import ...` 放在函数体上方, `# noqa: E402`. 经 reviewer 独立 grep 确认 `reasoning_explainer` 不依赖 `reasoning_trace`, 没有循环 import. inline 是多余的.

**修复**: 移到文件顶部 imports 区, 删 noqa.

**估时**: 2 分钟

### B3. 缺少观测 log 在 /reasoning-trace endpoints (Task 2.2 flag)

**文件**: `backend/app/api/reasoning_trace.py`

**问题**: 两条新 endpoints (`/safety/{audit_id}`, `/specialist/{audit_id}`) 没有 logger.info 埋点. Task 9 埋点走 client_events 表, 但服务端行为日志对 ops debug 有价值.

**修复**: 每个 handler 顶 `logger.info("[reasoning-trace] %s audit_id=%d", ...)`

**估时**: 5 分钟

### B4. `ActionCard.graded_at` 未 index (Task 8 Celery Health review)

**文件**: `backend/app/models/action_card.py`

**问题**: `celery_health.py::_probe_last` 查 `action_card.graded_at >= since` 做 outcome_grader 探测. 当前 `graded_at` 无 index, 48h 窗口在 PG 上是全表扫. 数据量小时 ok, 但长期要加.

**修复**: migration `CREATE INDEX ix_action_cards_graded_at ON action_cards(graded_at) WHERE graded_at IS NOT NULL;`

**估时**: 10 分钟 (partial index 省空间, 避 NULL 行)

### B5. `has_soap` 语义只看 S+P (Task 4 journal/timeline review)

**文件**: `backend/app/api/clinical_journal.py` (journal_timeline endpoint)

**问题**: `has_soap = bool(subjective AND plan)`, 忽略 O 和 A. 意图是"有非 stub 人工/AI 产出", 但字段名 `has_soap` 误导.

**修复**: 重命名为 `has_actionable = ...` 或加注释说明 S+P 的语义 (O 来自 Twin dump, A 来自 specialist findings, 自动填充).

**估时**: 5 分钟 + 相关 Mobile 代码 (`TimelineEntry` 类型) 同步改

---

## 建议执行顺序

**零碎时间** (M2/M3/B2/B3/B5): 总共不到 30 分钟, 下次有 10 分钟空隙就批处理.

**同一文件捎带** (M1 dark mode, B4 index): 等 Reasoning Sheet 或 Celery Health 有其他改动时顺手.

**需要设计决策** (M4 bucket 可见性, B1 meta 限制): 看观察期数据 — 如果用户真看到了 SOAP bucket 的 "+N 条", 再决定怎么展开; 如果 client_events 真收到大 payload, 再加限制.

**纯技术债** (M5 死代码删): 一次 grep 就删, 任何空闲时间.

---

## 不做 (evaluated but not worth doing)

- **Frontend i18n**: CJK-first 产品, Chinese 硬编码在 v1 合理. 只有真的要做海外/多语言 UI 时才回来.
- **Reasoning trace 时间旅行**: 当场解释够了, 看观察期数据才知道是否有人真想回放历史.
- **Mobile batch events endpoint**: 埋点量小, 1 event 1 POST 简单透明, 批量引入 client-side 队列复杂度不值.
- **Celery health 动态注册**: 5 任务硬编码够用, 允许动态注册 = 维护一个 DSL = 更多东西可以坏.
