# Dossier: Mac Chat Latency Waterfall

| 字段 | 值 |
|---|---|
| slug | `mac-chat-latency-waterfall` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S7 上线验证 |
| 状态 | shipped-local |
| 负责 | Codex |
| 反馈环 | TDD / SwiftPM tests / Mac package install |

## S0 Intake

用户连续要求继续优化阿衡对话体验。本切片承接后端 `agent_executor` pre-LLM 阶段级埋点,把 Mac 对话页的“总耗时”升级为可展开的阶段耗时瀑布图,让用户和研发 agent 能看到时间花在 prompt 组装、首 token、生成、工具执行还是编排子树。

## G1 · 准入裁决

裁决: PASS.

- 对象: `ChatMessage`, `AgentRunProgress`, `AgentTrace`.
- core_loop_step:用户提问 -> Agent 执行 -> 可观测耗时 -> 定位慢点 -> 后续优化模型/工具/上下文组装。
- safety_level: read_only observability;不新增健康建议、不新增写路径。
- autonomy_tier: no_write.

## G2 · 可行性 + 安全压测

裁决: PASS.

- 老后端或历史消息没有 `perf` 时必须保持 footer 原行为。
- `perf_pre_llm` 只作为中途提示暂存,最终瀑布图以 `done.perf` / `message.meta.perf` 为准。
- 所有进入 HTML 的动态文本继续走 `escape(_:)`,防止工具名或模型名带 HTML 注入。
- 快照 UI 测试不是本切片裁判,Mac skill 指定核心裁判为 `swift build` + `swift test --filter HealthAgentMacCoreTests`。

## S4/S5 · 实现

- 新增 `MessagePerf` 模型,容错解析 `total_ms`, `pre_llm_ms`, `pre_llm_stages`, `llm_ttft_ms`, `llm_full_ms`, `rounds`, `orchestrator_tool_ms`。
- `AgentStreamParser` 支持 `perf_pre_llm` 和 `done.perf`。
- `AgentChatMessage` / 会话历史加载支持持久化 `message.meta.perf`。
- `ChatTranscriptHTML.metaFooterHTML` 支持可折叠 latency waterfall,无 perf 时保持兼容。
- `chat-transcript.html` 新增瀑布图 CSS。
- `ChatTranscriptWebView` 新增 SwiftUI preview fixtures,方便离线检查快路径和编排子树耗时。

## G3 · 测试闸

裁决: PASS.

```bash
swift test --package-path apps/mac --filter MessagePerfTests
# Executed 17 tests, with 0 failures
```

```bash
swift test --package-path apps/mac --filter 'MessagePerfTests|AgentStreamClientTests|ChatTranscriptHTMLTests|RevaUIBlockTests'
# Executed 92 tests, with 0 failures
```

```bash
swift test --package-path apps/mac --filter HealthAgentMacCoreTests
# Executed 293 tests, with 1 test skipped and 0 failures
```

Known non-blocking full-suite issue:

```bash
swift test --package-path apps/mac
# Build complete; failed only in snapshot suites:
# SpO2WeekCardSnapshotTests precision 0.9894 < 0.99
# WearablePanelViewSnapshotTests rendered height drift 400x104 vs 400x100 / 400x270 vs 400x266
```

These snapshot failures are outside the touched Chat transcript / stream parser surface and are documented as local manual snapshot drift.

## G4 · 安全闸

裁决: GO.

- Read-only observability only.
- No write endpoints, medication logic, diagnosis logic, HealthKit permissions, or account/auth changes.
- HTML renderer continues escaping dynamic text.

## G5 · 部署健康

裁决: PASS.

```bash
apps/mac/scripts/package-app.sh --install --open
# Build of product 'HealthAgentMac' complete
# Packaged apps/mac/dist/HealthAgentMac.app
# Installed /Applications/阿衡.app
```

Runtime check:

```bash
pgrep -fl '阿衡|HealthAgentMac'
# 19882 /Users/liqiuhua/work/personal/health-llm-driven/apps/mac/dist/HealthAgentMac.app/Contents/MacOS/HealthAgentMac
```

Known warnings:

- Swift production build still emits existing warnings in `FeatureViews.swift` and `AgentChatViewModel.swift`; none are introduced by the `MessagePerf` / transcript waterfall surface.

## G6 · 上线验证

裁决: PASS for local Mac install.

- `/Applications/阿衡.app` was replaced by the newly packaged build.
- The running app process is using the freshly built `apps/mac/dist/HealthAgentMac.app` binary.

## S8 · 沉淀

- 后续可把 `livePreLLMPerf` 做成流式“组装中...”提示。
- 后续可把耗时瀑布图指标送入 Trace/后台仪表盘,用于批量定位慢工具和慢 specialist。
