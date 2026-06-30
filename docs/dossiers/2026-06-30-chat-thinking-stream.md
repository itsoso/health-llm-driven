# Dossier: Chat Thinking Stream

| 字段 | 值 |
|---|---|
| slug | `chat-thinking-stream` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S7 上线验证 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | TDD / mobile Jest / tsc / mobile OTA |

## S0 Intake

用户要求:“继续优化 阿衡对话页面输出思考过程流式输出”。

## S1 Discovery

- 后端 `/agent/stream` 已实时输出 `agent_start`、`tool_call`、`tool_result`、`token`、`done`。
- Mobile `streamChat` 已解析这些事件,但成功工具事件基本静默。
- `useChatEngine` 已有 streaming assistant placeholder 和 token 合并逻辑。
- `ChatBubble` streaming 期已降级为 plain text,避免 Markdown 重渲卡顿。

## G1 · 准入裁决

裁决: PASS.

- 对象: `ChatMessage`, `AgentRunProgress`, `DynamicUICard`。
- core_loop_step:用户提问 -> 阿衡读取上下文/工具 -> 流式反馈进度 -> 输出最终建议/卡片。
- safety_level: read_only UI transparency; no new medical write path。
- autonomy_tier: no_write。
- spec_required: no,复用既有 SSE 和 Mobile chat 合同。

## S2/S3 · 计划

- 设计:`docs/plans/2026-06-30-chat-thinking-stream-design.md`
- 计划:`docs/plans/2026-06-30-chat-thinking-stream-implementation-plan.md`

## G2 · 可行性 + 安全压测

裁决: PASS.

- 不新增后端接口或数据库结构。
- 不暴露模型原始 chain-of-thought。
- 不展示工具参数、用户隐私字段或内部技术栈。
- 前端只消费现有事件并生成安全摘要。

## S4/S5 · 实现

- RED: `chatStream` 解析安全 thought 摘要。
- RED: `useChatEngine` 将 thought 事件独立累积到 `thinkingSteps`。
- RED: `ChatBubble` 渲染“思考中”面板,且 streaming 期仍不挂载 rich Markdown。
- GREEN: 通过 `StreamEvent.thought`、`UIMessage.thinkingSteps`、`ThinkingStepsPanel` 完成。

## G3 · 测试闸

裁决: PASS.

```bash
pnpm --dir mobile exec jest mobile/services/__tests__/chatStream.test.ts --runInBand
# 7 passed
```

```bash
pnpm --dir mobile exec jest mobile/hooks/__tests__/useChatEngine.test.ts --runInBand
# 8 passed
```

```bash
pnpm --dir mobile exec jest mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx --runInBand
# 3 passed
```

```bash
pnpm --dir mobile exec jest mobile/services/__tests__/chatStream.test.ts mobile/hooks/__tests__/useChatEngine.test.ts mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx --runInBand
# 3 suites passed, 18 tests passed
```

```bash
pnpm --dir mobile exec tsc --noEmit
# exit 0
```

```bash
git diff --check
# exit 0
```

## G4 · 安全闸

裁决: GO.

- 只改 Mobile 流式显示。
- 无新增写接口、用药建议、诊断逻辑或健康数据查询权限。
- 思考摘要是固定映射文案,不是模型私有推理文本。

## G5 · 部署健康

裁决: PASS.

- Git: `f0cf901a feat(chat): stream safe thinking progress` pushed to `origin/main`.
- Backend deploy: not needed; no backend code, schema, migration, or runtime contract change.
- Mobile OTA: production branch, runtime `1.3.1`, update group `60164289-3469-491b-b084-2dec4b4b0d41`, iOS update `019f183f-3422-7e4a-acbc-6def655b50ac`.

## G6 · 上线验证

裁决: PASS.

- EAS dashboard: https://expo.dev/accounts/itsoso/projects/health-pilot/updates/60164289-3469-491b-b084-2dec4b4b0d41
- Device rollout: app will fetch the new bundle on cold start or after backgrounding for 30s+.

## S8 · 沉淀

- 后续可把高频工具名映射扩展为更细的健康领域标签,但仍不显示参数。
- 可以加入折叠状态,避免长回复占据过多首屏。
