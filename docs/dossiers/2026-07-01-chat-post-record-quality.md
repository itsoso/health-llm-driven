# Dossier: 阿衡对话记录后的高质量动态反馈

| 字段 | 值 |
|---|---|
| slug | `chat-post-record-quality` |
| 创建日期 | 2026-07-01 |
| 当前阶段 | S6 部署 |
| 状态 | shipping |
| 负责 | Codex |
| 反馈环 | backend pytest / mobile Jest+tsc+lint / web vitest+tsc+lint / mac swift test / backend deploy / mobile OTA |

## S0 · 用户需求(逐字)

> 对比下回复质量 review 代码 思考如何进一步提升优化
> 走方案 A
> 思考如何提升回复质量
> 可以
> 还有其他优化点吗
> 全部都做

- 谁用 / 解决什么:阿衡用户在对话里快速记录饮食、运动和健康事件后，需要系统给出“已记录 + 个性化判断 + 今日进度 + 下一步动作”，而不是泛泛的列表式回复。
- 锚点用户相关性:35–55 慢病/亚健康用户更需要低负担、可确认、可执行、不过界的健康参谋反馈。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/services/agent_executor.py` 已有 fast-record 工具执行和流式输出入口。
  - `mobile/components/chat/cards/RecordQualityCard.tsx` 已有 `record_quality` 卡片渲染骨架。
  - `frontend/src/components/assistant/inlineCards/` 已有动态卡片注册表。
  - `apps/mac/Sources/HealthAgentMacCore/ChatTranscriptHTML.swift` 已有 Mac 动态卡片 HTML 渲染入口。
- 缺什么:
  - 记录后反馈没有稳定服务层，无法复用用户画像、今日饮食累计和下一步动作。
  - 多条记录容易“最后一条覆盖前面”，回复缺少聚合总结。
  - Web/Mac 缺少 `record_quality` 同类动态卡片。
  - 移动卡片没有展示 metrics/progress，用户难以判断是否真的执行和下一步做什么。
- 硬约束:
  - 不做诊断、处方、调药或因果判定。
  - 所有写入仍由既有工具和用户意图触发；卡片只做解释、路由和确认后的下一步。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`ExecutionEvent`, `HealthAgendaItem`, `InterventionCycle`, `HealthTwin`
- core_loop_step:记录 → 反馈 → 行动 → 后续验证
- target_surface / safety_level / autonomy_tier:Mobile Chat + Web Chat + Mac Chat / 健康建议低风险边界 / manual_confirm
- spec_required(§8.1):否，沿用 Chat 动态 UI 卡片与交互卡片既有产品能力
- smallest_end_to_end_slice:用户在阿衡对话记录午餐或俯卧撑 → 后端生成 `record_quality` → 三端渲染进度/风险/下一步
- stale_surface_to_remove:无
- **裁决**:PASS —— 命中核心闭环，且不提升自治风险

## G2 · 可行性 + 安全压测

- 评审方式:Codex implementation review
- 硬阻断(已焊进规划):
  - 不能让 LLM 直接生成任意写操作 endpoint。
  - 卡片不能把“建议”表述为诊断、处方或治疗。
  - 快速记录后的回复必须 fail-loud，不能吞掉工具 JSON 泄漏或多记录聚合错误。
- **裁决**:PASS

## S4 · 研发任务分解

- [x] T1 后端抽出 post-record quality 服务层，聚合用户画像、今日饮食和下一步动作。
- [x] T2 fast-record 工具执行后用结构化质量回复替代泛泛自然语言。
- [x] T3 Mobile `record_quality` 增加 metrics/progress/行动路由渲染。
- [x] T4 Web/Mac 注册并渲染同一类动态卡片。
- [x] T5 增加后端、移动、Web、Mac 相关测试。
- [ ] T6 部署后记录 SHA、健康分、OTA 标识和线上 smoke。

## S5 · 实现

- 分支/commit:待提交
- 关键文件:
  - `backend/app/services/post_record_quality.py`
  - `backend/app/services/agent_executor.py`
  - `mobile/components/chat/cards/RecordQualityCard.tsx`
  - `frontend/src/components/assistant/inlineCards/cards.tsx`
  - `apps/mac/Sources/HealthAgentMacCore/ChatTranscriptHTML.swift`

## G3 · 测试闸

- 后端:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_post_record_quality.py backend/tests/test_agent_fast_record_reply.py -q`
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_agent_stream_raw_json_leak.py backend/tests/test_diet.py -q`
- Mobile:
  - `npm --prefix mobile test -- --runTestsByPath components/chat/cards/__tests__/registry.test.tsx`
  - `npm --prefix mobile test -- --runTestsByPath utils/__tests__/dietDate.test.ts`
  - `cd mobile && npx tsc --noEmit`
  - `npm --prefix mobile run lint`
- Web:
  - `npm --prefix frontend test -- src/components/assistant/inlineCards/__tests__/registry.test.tsx`
  - `cd frontend && npx tsc --noEmit`
  - `npm --prefix frontend run lint`
- Mac:
  - `swift test --package-path apps/mac --filter ChatTranscriptHTMLTests`
- Repo:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python scripts/check_doc_drift.py`
  - `git diff --check`
- 结果:
  - 后端相关测试:42 passed, 9 warnings
  - Mobile Jest:44 passed
  - Web Vitest:22 passed
  - Mac Swift:29 passed
  - Mobile/Web tsc:exit 0
  - Mobile/Web lint:exit 0(既有 warnings, 无 errors)
  - doc-drift:PASS
  - `git diff --check`:exit 0
- **裁决**:绿

## G4 · 安全闸

- 触发:健康数据、饮食/运动建议、对话写路径。
- 安全边界:
  - 文案只做健康管理提醒和记录解释，不替代医生诊断、治疗或处方。
  - action payload 只给既有路由，不新增自治外部执行。
  - 用户画像读取仅在当前用户上下文内进行。
- **裁决**:GO

## S6/G5/G6 · 部署与上线验证

- 后端/Web 部署:待执行
- Mobile OTA:待执行
- Mac 本地验证:待执行
- 线上 smoke:待执行

## S8 · 沉淀

- 记录后反馈应成为所有快速记录技能的统一出口；后续新增记录类型时优先扩展 `post_record_quality`，避免各端复制 prompt 文案。
