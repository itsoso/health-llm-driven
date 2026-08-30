import Foundation
import XCTest
@testable import HealthAgentMacCore

final class AgentStreamClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    func testParserAcceptsMobileDataOnlySSEFormat() throws {
        let payload = """
        data: {"event":"agent_start","data":{"conversation_id":42}}

        data: {"event":"token","data":{"content":"你好"}}

        data: {"event":"done","data":{"conversation_id":42,"message_id":9,"completion_status":"complete","model":"commercial/Claude-Opus-4.7","sources_used":["系统知识库"]}}

        """

        let events = try AgentStreamParser.parse(payload)

        XCTAssertEqual(events, [
            .start(conversationID: 42),
            .token("你好"),
            .done(
                conversationID: 42,
                messageID: 9,
                completionStatus: "complete",
                model: "commercial/Claude-Opus-4.7",
                sourcesUsed: ["系统知识库"],
                toolsUsed: [],
                elapsedMs: nil,
                llmRounds: nil
            )
        ])
    }

    func testParserParsesToolsUsedElapsedAndRoundsInDone() throws {
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3,"completion_status":"complete","model":"commercial/Claude-Opus-4.7","selected_model":"commercial/Claude-Opus-4.7","answer_model":"commercial/Claude-Opus-4.7","tool_models":["qwen3.7-max"],"fallback_reasons":["selected_model_tool_stream_failed"],"sources_used":["kb"],"tools_used":["health_query","health_record"],"elapsed_ms":4200,"llm_rounds":2}}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [
            .done(
                conversationID: 5,
                messageID: 3,
                completionStatus: "complete",
                model: "commercial/Claude-Opus-4.7",
                selectedModel: "commercial/Claude-Opus-4.7",
                answerModel: "commercial/Claude-Opus-4.7",
                toolModels: ["qwen3.7-max"],
                fallbackReasons: ["selected_model_tool_stream_failed"],
                sourcesUsed: ["kb"],
                toolsUsed: ["health_query", "health_record"],
                elapsedMs: 4200,
                llmRounds: 2
            )
        ])
    }

    func testParserParsesLLMUsageInDone() throws {
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3,"llm_usage":{"calls":1,"prompt_tokens":1200,"completion_tokens":360,"total_tokens":1560,"cost_usd":0.0004,"items":[{"provider":"tokenplan","model":"qwen3.7-plus","prompt_tokens":1200,"completion_tokens":360,"latency_ms":900,"success":true}]}}}

        """

        let events = try AgentStreamParser.parse(payload)
        guard case .done(_, _, _, _, _, _, _, _, _, _, _, _, _, _, let usage, _, _) = events.first else {
            return XCTFail("expected done event")
        }
        XCTAssertEqual(usage?.calls, 1)
        XCTAssertEqual(usage?.promptTokens, 1200)
        XCTAssertEqual(usage?.completionTokens, 360)
        XCTAssertEqual(usage?.items.first?.model, "qwen3.7-plus")
    }

    func testParserParsesDynamicCardsInDone() throws {
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3,"completion_status":"complete","cards":[{"type":"medical_exam_import_result","render":{"atom":"future_medical_exam_import","reason":"experimental_renderer"},"data":{"exam_id":321,"source":"pdf","items_count":9},"actions":[{"id":"ask-import-review","label":"问阿衡复核","action":"route.open","payload":{"route":"/(tabs)/chat?prompt=复核体检报告"},"style":"primary"}]}]}}

        """

        let events = try AgentStreamParser.parse(payload)

        XCTAssertEqual(events, [
            .done(
                conversationID: 5,
                messageID: 3,
                completionStatus: "complete",
                model: nil,
                sourcesUsed: [],
                toolsUsed: [],
                elapsedMs: nil,
                llmRounds: nil,
                cards: [
                    AgentDynamicCardDescriptor(
                        type: "medical_exam_import_result",
                        render: AgentDynamicCardRenderDescriptor(
                            atom: "future_medical_exam_import",
                            reason: "experimental_renderer"
                        ),
                        data: .object([
                            "exam_id": .int(321),
                            "source": .string("pdf"),
                            "items_count": .int(9)
                        ]),
                        actions: [
                            AgentDynamicCardActionDescriptor(
                                id: "ask-import-review",
                                label: "问阿衡复核",
                                action: "route.open",
                                payload: .object([
                                    "route": .string("/(tabs)/chat?prompt=复核体检报告")
                                ]),
                                style: "primary"
                            )
                        ])
                ]
            )
        ])
    }

    func testParserPreservesExactNamespacedMedicationBatchDecisionInDone() throws {
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3,"completion_status":"complete","cards":[],"write_receipts":[{"operation_id":"water_record:999"}],"safety_alerts":[{"rule_id":"unrelated"}],"medication_batch_decision":{"intent_id":41,"status":"executed","write_receipts":[{"operation_id":"medication_log:101"},{"operation_id":"medication_log:102"}],"safety_alerts":[{"rule_id":"ddi-1"},{"rule_id":"pgx-2"}]}}}

        """

        let events = try AgentStreamParser.parse(payload)
        guard case .done(
            _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, let decision
        ) = events.first else {
            return XCTFail("expected done event")
        }

        XCTAssertEqual(decision?.intentID, 41)
        XCTAssertEqual(decision?.status, .executed)
        XCTAssertEqual(decision?.writeReceipts.count, 2)
        XCTAssertEqual(decision?.safetyAlerts.count, 2)
        XCTAssertEqual(
            decision?.writeReceipts.first?["operation_id"]?.stringValue,
            "medication_log:101"
        )
        XCTAssertEqual(decision?.safetyAlerts.first?["rule_id"]?.stringValue, "ddi-1")
    }

    func testParserFallsBackToLegacyTopLevelMedicationEvidenceOnlyWhenScopedKeysAreAbsent() throws {
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3,"write_receipts":[{"operation_id":"medication_log:101"}],"safety_alerts":[{"rule_id":"legacy-ddi"}],"medication_batch_decision":{"intent_id":41,"status":"executed"}}}

        data: {"event":"done","data":{"conversation_id":5,"message_id":4,"write_receipts":[{"operation_id":"water_record:999"}],"safety_alerts":[{"rule_id":"unrelated"}],"medication_batch_decision":{"intent_id":42,"status":"dismissed","write_receipts":[],"safety_alerts":[]}}}

        """

        let events = try AgentStreamParser.parse(payload)
        guard case .done(
            _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, let legacyDecision
        ) = events.first,
        case .done(
            _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, let exactEmptyDecision
        ) = events.last else {
            return XCTFail("expected two done events")
        }

        XCTAssertEqual(
            legacyDecision?.writeReceipts.first?["operation_id"]?.stringValue,
            "medication_log:101"
        )
        XCTAssertEqual(
            legacyDecision?.safetyAlerts.first?["rule_id"]?.stringValue,
            "legacy-ddi"
        )
        XCTAssertTrue(exactEmptyDecision?.writeReceipts.isEmpty == true)
        XCTAssertTrue(exactEmptyDecision?.safetyAlerts.isEmpty == true)
    }

    func testParserDecodesStatusStageEvents() throws {
        // 真后端阶段事件:首 token 之前零或多次 status。全字段容错。
        let payload = """
        data: {"event":"status","data":{"stage":"vision","detail":null,"round":null}}

        data: {"event":"status","data":{"stage":"thinking","round":1}}

        data: {"event":"status","data":{"stage":"tool","detail":"查询健康数据","round":2}}

        data: {"event":"status","data":{"stage":"synthesis"}}

        data: {"event":"token","data":{"content":"回答"}}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [
            .status(stage: "vision", detail: nil, round: nil),
            .status(stage: "thinking", detail: nil, round: 1),
            .status(stage: "tool", detail: "查询健康数据", round: 2),
            .status(stage: "synthesis", detail: nil, round: nil),
            .token("回答")
        ])
    }

    func testParserTreatsBlankStatusDetailAsNil() throws {
        // detail 为空白 → 归一成 nil(不把空串当中文工具名)。
        let payload = """
        data: {"event":"status","data":{"stage":"tool","detail":"   "}}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [.status(stage: "tool", detail: nil, round: nil)])
    }

    func testParserToleratesUnknownStatusStage() throws {
        // 未知 stage 仍解出 .status(ViewModel 负责兜底到「小巴正在思考…」)。
        let payload = """
        data: {"event":"status","data":{"stage":"future_mystery_stage"}}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [.status(stage: "future_mystery_stage", detail: nil, round: nil)])
    }

    func testParserIgnoresStatusEventWithoutStage() throws {
        // stage 缺失 → 事件无意义,像未知事件一样忽略(不产出 .status)。
        let payload = """
        data: {"event":"status","data":{"detail":"查询健康数据"}}

        data: {"event":"token","data":{"content":"仍然到达"}}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [.token("仍然到达")])
    }

    func testParserDecodesFlatProgressEvents() throws {
        // P0-1 进度事件 (flat 契约): 顶层 type=status 区分, 无 data 包裹。
        // accepted / tool(round+label) / synthesis 都归一到 .status; label 折进 detail。
        let payload = """
        data: {"type":"status","stage":"accepted"}

        data: {"type":"status","stage":"tool","round":1,"label":"查看健康数据…"}

        data: {"type":"status","stage":"synthesis"}

        data: {"event":"done","data":{"conversation_id":7,"message_id":3,"completion_status":"complete","sources_used":[]}}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [
            .status(stage: "accepted", detail: nil, round: nil),
            .status(stage: "tool", detail: "查看健康数据…", round: 1),
            .status(stage: "synthesis", detail: nil, round: nil),
            .done(
                conversationID: 7,
                messageID: 3,
                completionStatus: "complete",
                model: nil,
                sourcesUsed: [],
                toolsUsed: [],
                elapsedMs: nil,
                llmRounds: nil
            ),
        ])
    }

    func testParserFlatProgressLabelPrefersOverDetail() throws {
        // 若 flat 进度事件同时带 label + detail, label 优先折进 detail。
        let payload = """
        data: {"type":"status","stage":"tool","round":2,"label":"联网搜索中…","detail":"ignored"}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [.status(stage: "tool", detail: "联网搜索中…", round: 2)])
    }

    func testParserStillIgnoresUnknownEventTypes() throws {
        // 回归:未知事件类型继续被忽略(back-compat 未受 status 支持影响)。
        let payload = """
        data: {"event":"some_future_event","data":{"foo":"bar"}}

        data: {"event":"token","data":{"content":"正文"}}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [.token("正文")])
    }

    func testStatusTextMapsEveryStageToExpectedKey() {
        XCTAssertEqual(AgentChatViewModel.statusText(stage: "vision", detail: nil, round: nil).key, "Recognizing image…")

        XCTAssertEqual(AgentChatViewModel.statusText(stage: "thinking", detail: nil, round: 1).key, "Reva is thinking…")
        XCTAssertEqual(AgentChatViewModel.statusText(stage: "thinking", detail: nil, round: nil).key, "Reva is thinking…")
        XCTAssertEqual(AgentChatViewModel.statusText(stage: "thinking", detail: nil, round: 2).key, "Reva is organizing thoughts…")
        // thinking + nil/blank detail keeps the round-based template (detail stays nil).
        XCTAssertNil(AgentChatViewModel.statusText(stage: "thinking", detail: nil, round: 1).detail)
        XCTAssertEqual(AgentChatViewModel.statusText(stage: "thinking", detail: "   ", round: 1).key, "Reva is thinking…")

        // thinking + non-blank detail → server phrase verbatim as the key, no %@ detail,
        // no 正在 prefix / template. (Non-streaming commercial models via LangBridge.)
        let nonStreamNotice = "该模型整段生成,需等待完整回答"
        let thinkingDetail = AgentChatViewModel.statusText(stage: "thinking", detail: nonStreamNotice, round: 3)
        XCTAssertEqual(thinkingDetail.key, nonStreamNotice)
        XCTAssertNil(thinkingDetail.detail)

        let tool = AgentChatViewModel.statusText(stage: "tool", detail: "查询健康数据", round: 2)
        XCTAssertEqual(tool.key, "Working: %@…")
        XCTAssertEqual(tool.detail, "查询健康数据")
        XCTAssertEqual(AgentChatViewModel.statusText(stage: "tool", detail: nil, round: nil).key, "Calling a tool…")
        XCTAssertNil(AgentChatViewModel.statusText(stage: "tool", detail: nil, round: nil).detail)

        XCTAssertEqual(AgentChatViewModel.statusText(stage: "synthesis", detail: nil, round: nil).key, "Reva is composing a reply…")

        // P0-1 progress family: accepted → its own phrase.
        XCTAssertEqual(AgentChatViewModel.statusText(stage: "accepted", detail: nil, round: nil).key, "Reva received your message…")
        XCTAssertNil(AgentChatViewModel.statusText(stage: "accepted", detail: nil, round: nil).detail)
        let acceptedDetail = "我先读取睡眠和恢复数据，再判断今天适合的运动强度。"
        XCTAssertEqual(
            AgentChatViewModel.statusText(stage: "accepted", detail: acceptedDetail, round: nil).key,
            acceptedDetail
        )
        // tool with a folded progress label renders via the same Working: %@… template.
        let progressTool = AgentChatViewModel.statusText(stage: "tool", detail: "查看健康数据…", round: 1)
        XCTAssertEqual(progressTool.key, "Working: %@…")
        XCTAssertEqual(progressTool.detail, "查看健康数据…")

        // 未知 stage 兜底
        XCTAssertEqual(AgentChatViewModel.statusText(stage: "future_mystery_stage", detail: nil, round: nil).key, "Reva is thinking…")
    }

    func testStatusTextLocalizesToChinese() {
        // View 用 appText/L10n 解析出的中文文案对齐契约表。
        XCTAssertEqual(L10n.text("Reva received your message…", language: .zh), "已收到，正在准备…")
        XCTAssertEqual(L10n.text("Recognizing image…", language: .zh), "正在识别图片…")
        XCTAssertEqual(L10n.text("Reva is thinking…", language: .zh), "小巴正在思考…")
        XCTAssertEqual(L10n.text("Reva is organizing thoughts…", language: .zh), "正在整理思路…")
        XCTAssertEqual(L10n.text("Calling a tool…", language: .zh), "正在调用工具…")
        XCTAssertEqual(L10n.text("Reva is composing a reply…", language: .zh), "正在整理回答…")
        // tool detail 插值:格式串 + 中文工具名 → 正在<detail>…
        let template = L10n.text("Working: %@…", language: .zh)
        XCTAssertEqual(String(format: template, "查询健康数据"), "正在查询健康数据…")

        // thinking + detail 走 verbatim 分支:map 出的 key 是完整中文短语,L10n 未登记
        // 则透传原样(zh 与 en 都不加模板/前缀),detail 为 nil 不触发 %@ 插值。
        let nonStreamNotice = "该模型整段生成,需等待完整回答"
        let mapped = AgentChatViewModel.statusText(stage: "thinking", detail: nonStreamNotice, round: 3)
        XCTAssertNil(mapped.detail)
        XCTAssertEqual(L10n.text(mapped.key, language: .zh), nonStreamNotice)
        XCTAssertEqual(L10n.text(mapped.key, language: .en), nonStreamNotice)
    }

    @MainActor
    func testViewModelMapsStatusStagesToLiveStatusAndClearsOnFirstToken() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 3))
            continuation.yield(.status(stage: "thinking", detail: nil, round: 1))
            continuation.yield(.status(stage: "tool", detail: "查询健康数据", round: 2))
            continuation.yield(.token("正文开始"))
            continuation.yield(.done(
                conversationID: 3, messageID: 4,
                completionStatus: "complete", model: "m", sourcesUsed: [],
                toolsUsed: [], elapsedMs: nil, llmRounds: nil
            ))
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))
        await model.send("分析")

        // 首 token / done 到达后 live status 已清空 → View 退回时间轮换兜底。
        XCTAssertNil(model.liveStatusText)
        XCTAssertNil(model.liveStatusDetail)
    }

    @MainActor
    func testLiveReasoningSnippetsRollingWindowStaysWithinCap() async {
        // 新后端在首 token 前把模型实时推理片段作为 thinking.detail 每 ~1.5s 下发一条 ——
        // 片段每条都不同,会一路 append。滚动窗必须把 live trace 收在 maxLiveThinkingSteps
        // 以内(丢最旧、留最新),否则长推理流会把列表撑爆。
        var events: [AgentStreamEvent] = [.start(conversationID: 9)]
        for i in 1...12 {
            events.append(.status(stage: "thinking", detail: "推理片段\(i)", round: 1))
        }
        // done 不带 thinking_steps(老后端路径)→ 完成时把已封顶的 liveThinkingSteps
        // 回填进消息,便于在 done 后观测最终封顶结果。
        events.append(.done(
            conversationID: 9, messageID: 1,
            completionStatus: "complete", model: "m", sourcesUsed: [],
            toolsUsed: [], elapsedMs: nil, llmRounds: nil
        ))
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            for event in events { continuation.yield(event) }
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))
        await model.send("分析")

        let steps = model.messages.last(where: { $0.role == .assistant })?.thinkingSteps ?? []
        XCTAssertEqual(steps.count, AgentChatViewModel.maxLiveThinkingSteps, "12 条片段被滚动窗收到 cap 内")
        XCTAssertLessThanOrEqual(steps.count, AgentChatViewModel.maxLiveThinkingSteps)
        XCTAssertEqual(steps.last, "推理片段12", "保留最新片段")
        XCTAssertEqual(steps.first, "推理片段5", "丢最旧:12 条留最后 8 条 → 从第 5 条起")
        XCTAssertFalse(steps.contains("推理片段1"), "最旧片段已被滚动窗淘汰")
    }

    @MainActor
    func testViewModelHoldsToolStatusBeforeFirstToken() async throws {
        // 在 stream 尚未收到首 token / done 之前观测:tool 阶段的 status 已被映射到
        // liveStatusText(证明 status 立即生效、未被 60ms token 节流吞掉)。用一个
        // 不自动结束的 stream + 并发 send,yield 两个 status 后在完成前断言。
        let box = StreamContinuationBox()
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            box.continuation = continuation
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))
        let sendTask = Task { await model.send("分析") }

        box.continuation?.yield(.start(conversationID: 3))
        box.continuation?.yield(.status(stage: "thinking", detail: nil, round: 1))
        box.continuation?.yield(.status(stage: "tool", detail: "查询健康数据", round: 2))

        // 让消费循环处理已排队的事件后再断言(尚未 finish → live status 仍在)。
        try await pollUntil { model.liveStatusText == "Working: %@…" }
        XCTAssertEqual(model.liveStatusText, "Working: %@…")
        XCTAssertEqual(model.liveStatusDetail, "查询健康数据")

        box.continuation?.finish()
        await sendTask.value

        // stream 结束后清空,退回时间轮换兜底。
        XCTAssertNil(model.liveStatusText)
        XCTAssertNil(model.liveStatusDetail)
    }

    @MainActor
    func testViewModelHoldsVerbatimThinkingDetailBeforeFirstToken() async throws {
        // 非流式商业模型(Opus/GPT/Gemini via LangBridge)会先发一条带 detail 的
        // thinking status;detail 是完整中文短语,须原样显示(不加 正在 / 不套模板)。
        // liveStatusText == 原短语,liveStatusDetail == nil(不触发 %@ 插值)。
        let notice = "该模型整段生成,需等待完整回答"
        let box = StreamContinuationBox()
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            box.continuation = continuation
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))
        let sendTask = Task { await model.send("分析") }

        box.continuation?.yield(.start(conversationID: 7))
        box.continuation?.yield(.status(stage: "thinking", detail: notice, round: 1))

        try await pollUntil { model.liveStatusText == notice }
        XCTAssertEqual(model.liveStatusText, notice)
        XCTAssertNil(model.liveStatusDetail)

        box.continuation?.finish()
        await sendTask.value

        XCTAssertNil(model.liveStatusText)
        XCTAssertNil(model.liveStatusDetail)
    }

    /// Spins the run loop until `condition` holds or a short timeout elapses.
    /// Used to observe main-actor state a concurrent stream mutates.
    @MainActor
    private func pollUntil(
        timeout: TimeInterval = 2.0,
        _ condition: @MainActor () -> Bool
    ) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition() {
            if Date() > deadline {
                XCTFail("condition not met before timeout")
                return
            }
            try await Task.sleep(nanoseconds: 5_000_000)
        }
    }

    @MainActor
    func testViewModelClearsLiveStatusOnStreamError() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 3))
            continuation.yield(.status(stage: "thinking", detail: nil, round: 1))
            continuation.yield(.error("boom"))
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))
        await model.send("分析")

        XCTAssertNil(model.liveStatusText)
        XCTAssertNil(model.liveStatusDetail)
    }

    func testParserToleratesMissingToolsUsed() throws {
        // 后端 tools_used 未上线前缺失 → 解析为空数组(容错,不崩)
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3,"completion_status":"complete"}}

        """
        let events = try AgentStreamParser.parse(payload)
        XCTAssertEqual(events, [
            .done(
                conversationID: 5,
                messageID: 3,
                completionStatus: "complete",
                model: nil,
                sourcesUsed: [],
                toolsUsed: [],
                elapsedMs: nil,
                llmRounds: nil
            )
        ])
    }

    @MainActor
    func testViewModelWritesDoneMetaIntoStreamingMessage() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 9))
            continuation.yield(.token("回答正文"))
            continuation.yield(.done(
                conversationID: 9,
                messageID: 1,
                completionStatus: "complete",
                model: "commercial/Claude-Opus-4.7",
                selectedModel: "commercial/Claude-Opus-4.7",
                answerModel: "commercial/Claude-Opus-4.7",
                toolModels: ["qwen3.7-max"],
                fallbackReasons: ["selected_model_tool_stream_failed"],
                sourcesUsed: ["系统知识库"],
                toolsUsed: ["health_query"],
                elapsedMs: 3300,
                llmRounds: 2
            ))
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))
        await model.send("分析")

        let assistant = model.messages.last
        XCTAssertEqual(assistant?.role, .assistant)
        // meta 写进了「那条消息对象」,不只是全局
        XCTAssertEqual(assistant?.model, "commercial/Claude-Opus-4.7")
        XCTAssertEqual(assistant?.selectedModel, "commercial/Claude-Opus-4.7")
        XCTAssertEqual(assistant?.answerModel, "commercial/Claude-Opus-4.7")
        XCTAssertEqual(assistant?.toolModels, ["qwen3.7-max"])
        XCTAssertEqual(assistant?.fallbackReasons, ["selected_model_tool_stream_failed"])
        XCTAssertEqual(assistant?.elapsedMs, 3300)
        XCTAssertEqual(assistant?.llmRounds, 2)
        XCTAssertEqual(assistant?.sourcesUsed, ["系统知识库"])
        XCTAssertEqual(assistant?.toolsUsed, ["health_query"])
        XCTAssertEqual(assistant?.completionStatus, "complete")
        XCTAssertTrue(assistant?.hasMeta ?? false)
    }

    func testAgentChatMessageDecodesLegacySnapshotWithoutMetaFields() throws {
        // 老版本快照(无 meta 字段)必须能解码,新字段降级为默认值
        let legacy = """
        {"id":"\(UUID().uuidString)","role":"assistant","content":"旧回答"}
        """
        let msg = try JSONDecoder().decode(AgentChatMessage.self, from: Data(legacy.utf8))
        XCTAssertEqual(msg.content, "旧回答")
        XCTAssertEqual(msg.remoteImageURLs, [])
        XCTAssertNil(msg.model)
        XCTAssertEqual(msg.sourcesUsed, [])
        XCTAssertEqual(msg.toolsUsed, [])
        XCTAssertNil(msg.cardType)
        XCTAssertNil(msg.cardData)
        XCTAssertFalse(msg.hasMeta)
    }

    func testAgentChatMessageRoundTripsMetaThroughCodable() throws {
        let original = AgentChatMessage(
            role: .assistant,
            content: "答",
            model: "m",
            elapsedMs: 2000,
            llmRounds: 2,
            sourcesUsed: ["kb"],
            toolsUsed: ["health_query"],
            completionStatus: "complete",
            remoteImageURLs: ["https://example.test/api/v1/upload/files/chat/dinner.jpg"]
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AgentChatMessage.self, from: data)
        XCTAssertEqual(decoded, original)
    }

    func testAgentChatMessageRoundTripsDynamicCardThroughCodable() throws {
        let original = AgentChatMessage(
            role: .assistant,
            content: "",
            toolsUsed: ["medical_exam_import"],
            cardType: "medical_exam_import_result",
            cardData: .object([
                "exam_id": .int(321),
                "exam_date": .string("2026-06-18"),
                "hospital_name": .string("Test Lab"),
                "items_count": .int(9),
                "abnormal_count": .int(2),
                "review_required": .bool(true),
                "safety_note": .string("OCR/AI 解析结果需要复核后再用于判断。")
            ]),
            cardActions: [
                AgentDynamicCardActionDescriptor(
                    id: "ask-import-review",
                    label: "问阿衡复核",
                    action: "route.open",
                    payload: .object([
                        "route": .string("/(tabs)/chat?prompt=复核体检报告")
                    ]),
                    style: "primary"
                )
            ])

        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AgentChatMessage.self, from: data)

        XCTAssertEqual(decoded, original)
        XCTAssertEqual(decoded.cardData?["exam_id"]?.intValue, 321)
        XCTAssertEqual(decoded.cardData?["hospital_name"]?.stringValue, "Test Lab")
        XCTAssertEqual(decoded.cardData?["review_required"]?.boolValue, true)
        XCTAssertEqual(decoded.cardActions.first?.label, "问阿衡复核")
        XCTAssertEqual(decoded.cardActions.first?.payload?["route"]?.stringValue, "/(tabs)/chat?prompt=复核体检报告")
    }

    func testAgentChatMessageRoundTripsDynamicCardRenderMetadataThroughCodable() throws {
        let original = AgentChatMessage(
            role: .assistant,
            content: "",
            cardType: "runtime_agenda",
            cardRender: AgentDynamicCardRenderDescriptor(
                atom: "future_runtime_agenda",
                reason: "experimental_renderer"
            ),
            cardData: .object([
                "horizon_days": .int(7),
                "next_action": .object([
                    "title": .string("晚餐后步行 15 分钟")
                ])
            ])
        )

        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AgentChatMessage.self, from: data)

        XCTAssertEqual(decoded, original)
        XCTAssertEqual(decoded.cardRender?.atom, "future_runtime_agenda")
        XCTAssertEqual(decoded.cardRender?.reason, "experimental_renderer")
    }

    func testAgentChatMessageDecodesSnakeCaseDynamicCardSnapshot() throws {
        let snapshot = """
        {
          "id": "\(UUID().uuidString)",
          "role": "assistant",
          "content": "",
          "card_type": "medical_exam_import_result",
          "card_data": {
            "exam_id": 88,
            "source": "pdf"
          }
        }
        """

        let decoded = try JSONDecoder().decode(AgentChatMessage.self, from: Data(snapshot.utf8))

        XCTAssertEqual(decoded.cardType, "medical_exam_import_result")
        XCTAssertEqual(decoded.cardData?["exam_id"]?.intValue, 88)
        XCTAssertEqual(decoded.cardData?["source"]?.stringValue, "pdf")
    }

    func testParserCapturesToolArgumentsAndResultsForInspection() throws {
        let payload = """
        event: tool_call
        data: {"tool":"query_lab_indicators","args":"{\\\"days\\\":7}","round":2}

        event: tool_result
        data: {"tool":"query_lab_indicators","success":true,"preview":"查到 3 条指标","result":"完整指标结果"}

        """

        let events = try AgentStreamParser.parse(payload)

        XCTAssertEqual(events, [
            .toolDetails(AgentToolEvent(
                name: "query_lab_indicators",
                success: nil,
                arguments: "{\"days\":7}",
                preview: nil,
                result: nil,
                round: 2
            )),
            .toolDetails(AgentToolEvent(
                name: "query_lab_indicators",
                success: true,
                arguments: nil,
                preview: "查到 3 条指标",
                result: "完整指标结果",
                round: nil
            ))
        ])
    }

    func testAgentStreamClientPostsMessageAndYieldsEvents() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/agent/stream")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token")
            XCTAssertEqual(
                request.value(forHTTPHeaderField: "X-Reva-Client-Caps"),
                "genui-v1, genui-components-v1, genui-table-v1"
            )
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["message"] as? String, "分析今天状态")
            XCTAssertEqual(body?["conversation_id"] as? Int, 7)
            let timeContext = try XCTUnwrap(body?["client_time_context"] as? [String: Any])
            XCTAssertFalse((timeContext["client_now_iso"] as? String ?? "").isEmpty)
            XCTAssertFalse((timeContext["timezone"] as? String ?? "").isEmpty)
            XCTAssertNotNil(timeContext["timezone_offset_minutes"] as? Int)

            let data = """
            data: {"event":"agent_start","data":{"conversation_id":7}}

            data: {"event":"token","data":{"content":"已收到"}}

            data: {"event":"done","data":{"conversation_id":7,"message_id":10,"completion_status":"complete"}}

            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = AgentStreamClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        var events: [AgentStreamEvent] = []
        for try await event in client.stream(message: "分析今天状态", conversationID: 7) {
            events.append(event)
        }

        XCTAssertEqual(events, [
            .start(conversationID: 7),
            .token("已收到"),
            .done(conversationID: 7, messageID: 10, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil)
        ])
    }

    @MainActor
    func testAgentChatViewModelSubmitEligibilityTrimsWhitespaceButAllowsStreamingQueue() {
        let model = AgentChatViewModel()

        XCTAssertFalse(model.canSubmit("   \n  "))
        XCTAssertTrue(model.canSubmit("如何正确测量腰围?"))

        model.isStreaming = true
        XCTAssertTrue(model.canSubmit("如何正确测量腰围?"))
    }

    @MainActor
    func testAgentChatViewModelPreparesAndConsumesDraft() {
        let model = AgentChatViewModel()

        model.prepareDraft("  基于 9p21 给我行动建议  ")

        XCTAssertEqual(model.consumePreparedDraft(), "基于 9p21 给我行动建议")
        XCTAssertNil(model.consumePreparedDraft())
    }

    @MainActor
    func testAgentChatViewModelPreparesContextDraftInFreshConversation() {
        let model = AgentChatViewModel()
        let previousContext = AgentContextItem(
            sourceID: "knowledge:previous",
            sourceKind: "knowledge_document",
            title: "旧知识上下文",
            summary: "上一轮分析留下的上下文"
        )
        let newContext = AgentContextItem(
            sourceID: "genomic:rs10572724",
            sourceKind: "genomic_finding",
            title: "9p21 心血管风险",
            summary: "rs10572724 AA screening",
            payload: [
                "rsid": "rs10572724",
                "genotype": "AA",
                "risk_level": "high"
            ]
        )

        model.messages = [
            AgentChatMessage(role: .user, content: "旧问题"),
            AgentChatMessage(role: .assistant, content: "旧回答")
        ]
        model.conversationID = 42
        model.addContextItem(previousContext)

        model.prepareDraftForNewConversation("  基于 9p21 给我行动建议  ", contextItem: newContext)

        XCTAssertTrue(model.messages.isEmpty)
        XCTAssertNil(model.conversationID)
        let draft = model.consumePreparedDraft()
        XCTAssertTrue(draft?.contains("基于 9p21 给我行动建议") == true)
        XCTAssertTrue(draft?.contains("当前上下文") == true)
        XCTAssertTrue(draft?.contains("9p21 心血管风险") == true)
        XCTAssertTrue(draft?.contains("rs10572724 AA screening") == true)
        XCTAssertTrue(draft?.contains("risk_level=high") == true)
        XCTAssertEqual(model.contextItems.map(\.id), [newContext.id])
    }

    @MainActor
    func testAgentChatViewModelPreparesMultipleContextItemsInFreshConversation() {
        let model = AgentChatViewModel()
        let categoryContext = AgentContextItem(
            sourceID: "genomic_category:disease_risk",
            sourceKind: "genomic_category",
            title: "疾病风险",
            summary: "22 个位点，高 6，中 6",
            payload: [
                "category": "disease_risk",
                "high_count": "6"
            ]
        )
        let findingContext = AgentContextItem(
            sourceID: "genomic_finding:rs10572724",
            sourceKind: "genomic_finding",
            title: "9p21 心血管风险",
            summary: "rs10572724 AA screening",
            payload: [
                "rsid": "rs10572724",
                "genotype": "AA"
            ]
        )

        model.prepareDraftForNewConversation(
            "请分析这个基因分类",
            contextItems: [categoryContext, findingContext, findingContext]
        )

        let draft = model.consumePreparedDraft()
        XCTAssertTrue(draft?.contains("当前上下文") == true)
        XCTAssertTrue(draft?.contains("1. 疾病风险") == true)
        XCTAssertTrue(draft?.contains("2. 9p21 心血管风险") == true)
        XCTAssertTrue(draft?.contains("high_count=6") == true)
        XCTAssertTrue(draft?.contains("rsid=rs10572724") == true)
        XCTAssertEqual(model.contextItems.map(\.id), [categoryContext.id, findingContext.id])
    }

    @MainActor
    func testAgentChatViewModelStreamsAssistantReply() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 77))
            continuation.yield(.token("第一段"))
            continuation.yield(.token("第二段"))
            continuation.yield(.done(
                conversationID: 77,
                messageID: 88,
                completionStatus: "complete",
                model: "commercial/Claude-Opus-4.7",
                sourcesUsed: ["系统知识库"],
                toolsUsed: [],
                elapsedMs: nil,
                llmRounds: nil
            ))
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))

        await model.send("分析今天状态")

        XCTAssertEqual(model.conversationID, 77)
        XCTAssertFalse(model.isStreaming)
        XCTAssertEqual(model.messages.map(\.role), [.user, .assistant])
        XCTAssertEqual(model.messages.last?.content, "第一段第二段")
        XCTAssertEqual(model.lastCompletionStatus, "complete")
        XCTAssertEqual(model.lastModel, "commercial/Claude-Opus-4.7")
        XCTAssertEqual(model.lastSourcesUsed, ["系统知识库"])
    }

    @MainActor
    func testAgentChatViewModelQueuesSecondSubmitWithoutCancellingCurrentStream() async {
        let firstBox = StreamContinuationBox()
        let secondBox = StreamContinuationBox()
        let service = SequencedAgentStreamService(streams: [
            AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
                firstBox.continuation = continuation
            },
            AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
                secondBox.continuation = continuation
            },
        ])
        let model = AgentChatViewModel(streamService: service)

        model.submit("第一条")
        await Task.yield()
        firstBox.continuation?.yield(.start(conversationID: 77))
        await Task.yield()

        XCTAssertTrue(model.isStreaming)
        XCTAssertTrue(model.canSubmit("第二条"))

        model.submit("第二条")

        XCTAssertEqual(model.messages.map(\.role), [.user, .assistant, .user, .assistant])
        XCTAssertEqual(model.messages[2].content, "第二条")
        XCTAssertEqual(model.messages[3].content, "小巴处理中，已加入队列。")
        XCTAssertEqual(service.messages, ["第一条"])

        firstBox.continuation?.yield(.token("第一条回答"))
        firstBox.continuation?.yield(.done(conversationID: 77, messageID: 88, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil))
        firstBox.continuation?.finish()

        for _ in 0..<20 where service.messages.count < 2 {
            try? await Task.sleep(nanoseconds: 10_000_000)
        }

        XCTAssertEqual(service.messages, ["第一条", "第二条"])
        XCTAssertEqual(model.queuedTurnCount, 0)

        secondBox.continuation?.yield(.token("第二条回答"))
        secondBox.continuation?.yield(.done(conversationID: 77, messageID: 89, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil))
        secondBox.continuation?.finish()

        for _ in 0..<20 where model.isStreaming {
            try? await Task.sleep(nanoseconds: 10_000_000)
        }

        XCTAssertEqual(model.messages.last?.content, "第二条回答")
        XCTAssertFalse(model.isStreaming)
    }

    @MainActor
    func testAgentChatViewModelCoalescesManyTokensWithoutLoss() async {
        // 真 token 流式:大量碎 token 快速到达。节流合批(~60ms)不能丢字 ——
        // 最终内容必须等于全部 token 拼接(收尾 flushPendingTokens 落盘)。
        let parts = (1...50).map { "片\($0)·" }
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 1))
            for p in parts { continuation.yield(.token(p)) }
            continuation.yield(.done(
                conversationID: 1, messageID: 2,
                completionStatus: "complete", model: "m", sourcesUsed: [],
                toolsUsed: [], elapsedMs: nil, llmRounds: nil
            ))
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))

        await model.send("hi")

        XCTAssertEqual(model.messages.last?.content, parts.joined())
        XCTAssertFalse(model.isStreaming)
    }

    @MainActor
    func testAgentStructuredCommandParserBuildsConfirmableActionAndHidesRawJSON() {
        let messageID = UUID(uuidString: "11111111-1111-1111-1111-111111111111")!
        let content = """
        好的，我来帮你删除最后一条饮食记录。
        {"name":"health_manage","parameters":{"action":"delete","record_type":"diet","record_id":625}}
        """

        let actions = AgentStructuredCommandParser.proposedActions(in: content, messageID: messageID)
        let displayText = AgentStructuredCommandParser.displayText(for: content)

        XCTAssertEqual(actions.count, 1)
        XCTAssertEqual(actions.first?.messageID, messageID)
        XCTAssertEqual(actions.first?.toolName, "health_manage")
        XCTAssertEqual(actions.first?.parameters["action"], "delete")
        XCTAssertEqual(actions.first?.parameters["record_type"], "diet")
        XCTAssertEqual(actions.first?.parameters["record_id"], "625")
        XCTAssertEqual(actions.first?.title, "删除饮食记录 #625")
        XCTAssertTrue(displayText.contains("好的，我来帮你删除最后一条饮食记录。"))
        XCTAssertFalse(displayText.contains(#""name""#))
        XCTAssertFalse(displayText.contains("health_manage"))
    }

    @MainActor
    func testDisplayTextStripsClaimEvidenceMarkers() {
        let content = "TT 基因型酶活约 30% [claim:c_mthfr_c677t_hcy_folate_boundary]，但这不是诊断。"
        let out = AgentStructuredCommandParser.displayText(for: content)
        XCTAssertFalse(out.contains("[claim:"), "裸 claim 标记应被剥离")
        XCTAssertFalse(out.contains("c_mthfr_c677t_hcy_folate_boundary"))
        XCTAssertTrue(out.contains("TT 基因型酶活约 30%"))
        XCTAssertTrue(out.contains("但这不是诊断。"))
        XCTAssertFalse(out.contains("  "), "剥离后不应留下双空格")
    }

    @MainActor
    func testAgentChatViewModelTurnsAssistantJSONCommandIntoConfirmableActionContext() async throws {
        let service = CapturingAgentStreamService()
        service.streams = [
            AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
                continuation.yield(.start(conversationID: 77))
                continuation.yield(.token("""
                已识别到可执行记录操作。
                {"name":"health_manage","parameters":{"action":"update","record_type":"diet","record_id":625,"calories":650}}
                """))
                continuation.yield(.done(conversationID: 77, messageID: 88, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil))
                continuation.finish()
            },
            AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
                continuation.yield(.done(conversationID: 77, messageID: 89, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil))
                continuation.finish()
            }
        ]
        let model = AgentChatViewModel(streamService: service)

        await model.send("把这餐热量改成一半")

        let assistantMessage = try XCTUnwrap(model.messages.last)
        XCTAssertEqual(model.proposedActions.count, 1)
        XCTAssertEqual(model.proposedActions.first?.title, "更新饮食记录 #625")
        XCTAssertFalse(model.displayContent(for: assistantMessage).contains(#""parameters""#))

        let action = try XCTUnwrap(model.proposedActions.first)
        await model.confirmProposedAction(action)

        XCTAssertEqual(model.proposedActions.first?.status, .confirmed)
        XCTAssertTrue(service.messages.last?.contains("请执行我刚确认的健康管理动作") ?? false)
        let latestContext = try XCTUnwrap(service.extraContexts.last)
        let context = try XCTUnwrap(latestContext)
        let data = try XCTUnwrap(context.data(using: .utf8))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let contextItems = try XCTUnwrap(json["context_items"] as? [[String: Any]])
        let contextItem = try XCTUnwrap(contextItems.last)
        XCTAssertEqual(contextItem["source_kind"] as? String, "agent_proposed_action")
        let payload = try XCTUnwrap(contextItem["payload"] as? [String: String])
        XCTAssertEqual(payload["tool_name"], "health_manage")
        XCTAssertEqual(payload["action"], "update")
        XCTAssertEqual(payload["record_id"], "625")
    }

    @MainActor
    func testAgentChatViewModelTracksToolExecutionTimeline() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 77))
            continuation.yield(.tool(name: "knowledge_search", success: nil))
            continuation.yield(.tool(name: "knowledge_search", success: true))
            continuation.yield(.tool(name: "health_manage", success: false))
            continuation.yield(.done(conversationID: 77, messageID: 88, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil))
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))

        await model.send("分析并执行")

        XCTAssertEqual(model.toolActivities.map(\.name), ["knowledge_search", "health_manage"])
        XCTAssertEqual(model.toolActivities.map(\.status), [.succeeded, .failed])
        XCTAssertEqual(model.toolActivities.last?.displayTitle, "health_manage failed")
    }

    @MainActor
    func testAgentChatViewModelMergesToolResultIntoRunningToolForDetailInspection() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 77))
            continuation.yield(.toolDetails(AgentToolEvent(
                name: "query_lab_indicators",
                success: nil,
                arguments: "{\"days\":7}",
                preview: nil,
                result: nil,
                round: 1
            )))
            continuation.yield(.toolDetails(AgentToolEvent(
                name: "query_lab_indicators",
                success: true,
                arguments: nil,
                preview: "查到 3 条指标",
                result: "完整指标结果",
                round: nil
            )))
            continuation.yield(.done(conversationID: 77, messageID: 88, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil))
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))

        await model.send("查询指标")

        XCTAssertEqual(model.toolActivities.count, 1)
        let activity = try! XCTUnwrap(model.toolActivities.first)
        XCTAssertEqual(activity.name, "query_lab_indicators")
        XCTAssertEqual(activity.status, .succeeded)
        XCTAssertEqual(activity.arguments, "{\"days\":7}")
        XCTAssertEqual(activity.resultText, "完整指标结果")
        XCTAssertEqual(activity.round, 1)
    }

    @MainActor
    func testAgentChatViewModelMarksPartialWhenStreamFailsAfterTokens() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 77))
            continuation.yield(.token("已有部分内容"))
            continuation.finish(throwing: URLError(.timedOut))
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))

        await model.send("分析今天状态")

        XCTAssertFalse(model.isStreaming)
        XCTAssertEqual(model.runState, .partial)
        XCTAssertEqual(model.messages.last?.content, "已有部分内容")
        XCTAssertTrue(model.canRetry)
    }

    @MainActor
    func testAgentChatViewModelMarksFailedWhenStreamReturnsNoAssistantContent() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.finish(throwing: URLError(.notConnectedToInternet))
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))

        await model.send("分析今天状态")

        XCTAssertFalse(model.isStreaming)
        XCTAssertEqual(model.runState, .failed)
        XCTAssertEqual(model.messages.map(\.role), [.user, .assistant])
        XCTAssertFalse(model.messages.last?.content.isEmpty ?? true)
        XCTAssertTrue(model.canRetry)
    }

    @MainActor
    func testAgentChatViewModelRetriesLastPromptAfterFailure() async {
        let service = SequencedAgentStreamService(streams: [
            AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
                continuation.finish(throwing: URLError(.timedOut))
            },
            AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
                continuation.yield(.start(conversationID: 91))
                continuation.yield(.token("重试成功"))
                continuation.yield(.done(conversationID: 91, messageID: 2, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil))
                continuation.finish()
            }
        ])
        let model = AgentChatViewModel(streamService: service)

        await model.send("分析今天状态")
        XCTAssertEqual(model.runState, .failed)

        await model.retryLastMessage()

        XCTAssertEqual(service.messages, ["分析今天状态", "分析今天状态"])
        XCTAssertEqual(model.runState, .completed)
        XCTAssertEqual(model.messages.last?.content, "重试成功")
        XCTAssertFalse(model.canRetry)
    }

    @MainActor
    func testAgentChatViewModelIncludesAttachmentsAndWebSearchInExtraContext() async throws {
        let service = CapturingAgentStreamService()
        let model = AgentChatViewModel(streamService: service)
        model.webSearchEnabled = true
        model.selectModel("commercial/Gemini-3.1-Pro-Preview")
        model.addAttachment(.init(
            url: URL(fileURLWithPath: "/tmp/wegene.txt"),
            name: "wegene.txt",
            sourceKind: .genomeText,
            sha256: "sha256:abc"
        ))

        await model.send("基于这个文件分析")

        let context = try XCTUnwrap(service.extraContext)
        let data = try XCTUnwrap(context.data(using: .utf8))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["model_id"] as? String, "gemini-3.1-pro")
        XCTAssertEqual(json["web_search_requested"] as? Bool, true)
        let attachments = try XCTUnwrap(json["attachments"] as? [[String: Any]])
        XCTAssertEqual(attachments.first?["source_kind"] as? String, "genome_txt")
        XCTAssertEqual(attachments.first?["source_hash"] as? String, "sha256:abc")
    }

    @MainActor
    func testAgentChatViewModelImportsMedicalAttachmentsBeforeStreaming() async throws {
        let service = CapturingAgentStreamService()
        let labUpload = StubLabUploadService(result: LabUploadResult(
            message: "图片 OCR 导入成功",
            examID: 321,
            examDate: "2026-06-18",
            examType: "biochemistry",
            hospitalName: "Test Lab",
            itemsCount: 9,
            abnormalCount: 2,
            conclusionsCount: nil,
            conclusion: "LDL 偏高"
        ))
        let model = AgentChatViewModel(streamService: service, labUploadService: labUpload)
        let url = URL(fileURLWithPath: "/tmp/lab-photo.png")
        model.addAttachment(.init(
            url: url,
            name: "lab-photo.png",
            sourceKind: .medicalFile,
            sha256: "sha256:lab"
        ))

        await model.send("解释这份化验单")

        XCTAssertEqual(labUpload.importedURLs, [url])
        let context = try XCTUnwrap(service.extraContext)
        let data = try XCTUnwrap(context.data(using: .utf8))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let imports = try XCTUnwrap(json["lab_report_imports"] as? [[String: Any]])
        XCTAssertEqual(imports.first?["exam_id"] as? Int, 321)
        XCTAssertEqual(imports.first?["file_name"] as? String, "lab-photo.png")
        XCTAssertEqual(imports.first?["items_count"] as? Int, 9)
        XCTAssertEqual(imports.first?["abnormal_count"] as? Int, 2)
        XCTAssertEqual(imports.first?["source_hash"] as? String, "sha256:lab")
    }

    @MainActor
    func testAgentChatViewModelAttachesMedicalImportDynamicCardToAssistantMessage() async throws {
        let service = CapturingAgentStreamService()
        let labUpload = StubLabUploadService(result: LabUploadResult(
            message: "图片 OCR 导入成功",
            examID: 321,
            examDate: "2026-06-18",
            examType: "biochemistry",
            hospitalName: "Test Lab",
            itemsCount: 9,
            abnormalCount: 2,
            conclusionsCount: 1,
            conclusion: "LDL <script>alert(1)</script> 偏高"
        ))
        let model = AgentChatViewModel(streamService: service, labUploadService: labUpload)
        model.addAttachment(.init(
            url: URL(fileURLWithPath: "/tmp/lab-photo.png"),
            name: "lab-photo.png",
            sourceKind: .medicalFile,
            sha256: "sha256:lab"
        ))

        await model.send("解释这份化验单")

        let assistant = try XCTUnwrap(model.messages.last)
        XCTAssertEqual(assistant.cardType, "medical_exam_import_result")
        XCTAssertEqual(assistant.cardData?["exam_id"]?.intValue, 321)
        XCTAssertEqual(assistant.cardData?["source"]?.stringValue, "image")
        XCTAssertEqual(assistant.toolsUsed, ["medical_exam_import"])

        let html = try XCTUnwrap(model.renderedTranscript().last?.bodyHTML)
        XCTAssertTrue(html.contains("体检报告已导入"))
        XCTAssertTrue(html.contains("9 项指标"))
        XCTAssertTrue(html.contains("2 项异常"))
        XCTAssertFalse(html.contains("<script"))
        XCTAssertTrue(html.contains("&lt;script&gt;alert(1)&lt;/script&gt;"))
    }

    @MainActor
    func testAgentChatViewModelSendsFoodPhotoToAgentWithoutLabImport() async throws {
        // A meal photo classifies as `.image`, so it must NOT hit the lab-report
        // import path at all, and its bytes must reach `/agent/stream` as a chat
        // image so the multimodal/food path can run.
        let service = CapturingAgentStreamService()
        let labUpload = FailingLabUploadService()
        let model = AgentChatViewModel(streamService: service, labUploadService: labUpload)

        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("health-mac-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }
        let photo = tempDir.appendingPathComponent("lunch.jpg")
        try Data([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10]).write(to: photo)
        model.addAttachment(.init(url: photo, name: "lunch.jpg", sourceKind: .image, sha256: "sha256:lunch"))

        await model.send("记录午餐")

        XCTAssertEqual(labUpload.importedURLs, [], "food photo must not be routed to lab import")
        XCTAssertNil(model.errorMessage, "lab-import must never abort a food-photo turn")
        let images = try XCTUnwrap(service.imagesSeen.last)
        XCTAssertEqual(images.count, 1, "the photo bytes must reach /agent/stream")
        XCTAssertEqual(images.first?.type, "jpeg")
        XCTAssertFalse(images.first?.base64.isEmpty ?? true)
        XCTAssertEqual(model.messages.first(where: { $0.role == .user })?.content, "记录午餐")
    }

    @MainActor
    func testAgentChatViewModelDoesNotAbortWhenLabImportFails() async throws {
        // A genuine .medicalFile whose OCR fails (「无法识别」/422) must be skipped,
        // NOT throw and abort the whole send.
        let service = CapturingAgentStreamService()
        let labUpload = FailingLabUploadService()
        let model = AgentChatViewModel(streamService: service, labUploadService: labUpload)
        model.addAttachment(.init(
            url: URL(fileURLWithPath: "/tmp/not-a-lab.pdf"),
            name: "not-a-lab.pdf",
            sourceKind: .medicalFile,
            sha256: "sha256:pdf"
        ))

        await model.send("这是什么")

        XCTAssertEqual(labUpload.importedURLs.count, 1, "import was attempted for the .medicalFile")
        XCTAssertNil(model.errorMessage, "a failed lab import must not abort the turn")
        XCTAssertEqual(service.messages, ["这是什么"], "the turn still reached /agent/stream")
    }

    @MainActor
    func testAgentChatViewModelStreamsFoodPhotoAsSingleImageBase64Field() throws {
        // The encoded request must use the backend's single-image fields
        // (image_base64 + image_type), matching mobile's contract.
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("health-mac-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }
        let photo = tempDir.appendingPathComponent("meal.png")
        let bytes = Data([0x89, 0x50, 0x4E, 0x47])
        try bytes.write(to: photo)
        let model = AgentChatViewModel(streamService: CapturingAgentStreamService())
        model.addAttachment(.init(url: photo, name: "meal.png", sourceKind: .image, sha256: "sha256:meal"))

        let images = model.buildChatImages(excludingImportedHashes: [])
        XCTAssertEqual(images.count, 1)
        XCTAssertEqual(images.first?.type, "png")
        XCTAssertEqual(images.first?.base64, bytes.base64EncodedString())

        let request = AgentStreamRequest(message: "记录午餐", images: images)
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        XCTAssertEqual(json?["image_base64"] as? String, bytes.base64EncodedString())
        XCTAssertEqual(json?["image_type"] as? String, "png")
        XCTAssertNil(json?["images"], "a single image must use image_base64, not images[]")
    }

    @MainActor
    func testAgentChatViewModelAlwaysRequestsStructuredMarkdownReplies() async throws {
        let service = CapturingAgentStreamService()
        let model = AgentChatViewModel(streamService: service)

        await model.send("分析今天状态")

        let context = try XCTUnwrap(service.extraContext)
        let data = try XCTUnwrap(context.data(using: .utf8))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["client"] as? String, "mac")
        XCTAssertEqual(json["response_format"] as? String, "markdown")
        let instruction = try XCTUnwrap(json["desktop_markdown_response_instruction"] as? String)
        XCTAssertTrue(instruction.contains("Markdown"))
        XCTAssertTrue(instruction.contains("按问题完整展开必要的证据"))
        XCTAssertFalse(instruction.contains("正文控制在 500 字以内"))
        XCTAssertTrue(instruction.contains("不确定性边界"))
    }

    @MainActor
    func testAgentChatViewModelIncludesSelectedContextItemsInExtraContext() async throws {
        let service = CapturingAgentStreamService()
        let model = AgentChatViewModel(streamService: service)
        let item = AgentContextItem(
            sourceID: "genomic:rs10572724",
            sourceKind: "genomic_finding",
            title: "9p21 心血管风险",
            summary: "rs10572724 AA screening",
            payload: [
                "rsid": "rs10572724",
                "genotype": "AA",
                "risk_level": "high"
            ]
        )

        model.addContextItem(item)
        model.addContextItem(item)

        await model.send("基于已选上下文分析")

        XCTAssertEqual(model.contextItems.count, 1)
        let context = try XCTUnwrap(service.extraContext)
        let data = try XCTUnwrap(context.data(using: .utf8))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let contextItems = try XCTUnwrap(json["context_items"] as? [[String: Any]])
        XCTAssertEqual(contextItems.count, 1)
        XCTAssertEqual(contextItems.first?["source_id"] as? String, "genomic:rs10572724")
        XCTAssertEqual(contextItems.first?["source_kind"] as? String, "genomic_finding")
        XCTAssertEqual(contextItems.first?["title"] as? String, "9p21 心血管风险")
        let payload = try XCTUnwrap(contextItems.first?["payload"] as? [String: String])
        XCTAssertEqual(payload["risk_level"], "high")
    }

    @MainActor
    func testAgentChatViewModelSavesAppliesAndDeletesContextBundles() {
        let model = AgentChatViewModel()
        let gene = AgentContextItem(
            sourceID: "genomic:rs10572724",
            sourceKind: "genomic_finding",
            title: "9p21 心血管风险",
            summary: "rs10572724 AA screening"
        )
        let knowledge = AgentContextItem(
            sourceID: "knowledge:apoB",
            sourceKind: "knowledge_document",
            title: "ApoB 轨迹",
            summary: "LDL-C/ApoB evidence"
        )

        model.addContextItem(gene)
        model.addContextItem(knowledge)

        let bundle = model.saveCurrentContextBundle(named: "血脂-基因闭环")
        model.clearContextItems()
        model.applyContextBundle(bundle)

        XCTAssertEqual(model.savedContextBundles.map(\.name), ["血脂-基因闭环"])
        XCTAssertEqual(model.savedContextBundles.first?.itemCount, 2)
        XCTAssertEqual(model.contextItems.map(\.id), [gene.id, knowledge.id])

        model.deleteContextBundle(bundle)

        XCTAssertTrue(model.savedContextBundles.isEmpty)
    }

    @MainActor
    func testAgentChatViewModelPersistsAndRestoresConversationHistory() async {
        let suiteName = "AgentHistory-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let historyStore = UserDefaultsAgentConversationStore(defaults: defaults)
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 42))
            continuation.yield(.token("历史回答"))
            continuation.yield(.done(conversationID: 42, messageID: 8, completionStatus: "complete", model: "claude", sourcesUsed: ["kb"], toolsUsed: [], elapsedMs: nil, llmRounds: nil))
            continuation.finish()
        }
        let model = AgentChatViewModel(
            streamService: StaticAgentStreamService(stream: stream),
            conversationStore: historyStore
        )

        await model.send("分析今天")

        XCTAssertEqual(model.conversationHistory.count, 1)
        XCTAssertEqual(model.conversationHistory.first?.conversationID, 42)
        XCTAssertEqual(model.conversationHistory.first?.messages.map(\.content), ["分析今天", "历史回答"])

        let restored = AgentChatViewModel(conversationStore: historyStore)

        XCTAssertEqual(restored.messages.map(\.content), ["分析今天", "历史回答"])
        XCTAssertEqual(restored.conversationID, 42)
        XCTAssertEqual(restored.conversationHistory.count, 1)

        restored.startNewConversation()

        XCTAssertTrue(restored.messages.isEmpty)
        XCTAssertNil(restored.conversationID)
        XCTAssertEqual(restored.conversationHistory.count, 1)

        restored.loadConversation(restored.conversationHistory[0])

        XCTAssertEqual(restored.messages.last?.content, "历史回答")
        XCTAssertEqual(restored.conversationID, 42)
    }
}

private struct StaticAgentStreamService: AgentStreamServicing {
    let stream: AsyncThrowingStream<AgentStreamEvent, Error>

    func stream(message: String, conversationID: Int?, extraContext: String?, images: [AgentChatImage]) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        stream
    }
}

/// Holds an AsyncThrowingStream continuation so a test can drive events by hand
/// and observe view-model state mid-stream (before finishing).
private final class StreamContinuationBox: @unchecked Sendable {
    var continuation: AsyncThrowingStream<AgentStreamEvent, Error>.Continuation?
}

private final class CapturingAgentStreamService: AgentStreamServicing, @unchecked Sendable {
    nonisolated(unsafe) var extraContext: String?
    nonisolated(unsafe) var extraContexts: [String?] = []
    nonisolated(unsafe) var messages: [String] = []
    nonisolated(unsafe) var imagesSeen: [[AgentChatImage]] = []
    nonisolated(unsafe) var streams: [AsyncThrowingStream<AgentStreamEvent, Error>] = []

    func stream(message: String, conversationID: Int?, extraContext: String?, images: [AgentChatImage]) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        self.extraContext = extraContext
        self.extraContexts.append(extraContext)
        self.messages.append(message)
        self.imagesSeen.append(images)
        if !streams.isEmpty {
            return streams.removeFirst()
        }
        return AsyncThrowingStream { continuation in
            continuation.yield(.done(
                conversationID: conversationID,
                messageID: 1,
                completionStatus: "complete",
                model: nil,
                sourcesUsed: [],
                toolsUsed: [],
                elapsedMs: nil,
                llmRounds: nil
            ))
            continuation.finish()
        }
    }
}

private final class SequencedAgentStreamService: AgentStreamServicing, @unchecked Sendable {
    nonisolated(unsafe) var streams: [AsyncThrowingStream<AgentStreamEvent, Error>]
    nonisolated(unsafe) var messages: [String] = []

    init(streams: [AsyncThrowingStream<AgentStreamEvent, Error>]) {
        self.streams = streams
    }

    func stream(message: String, conversationID: Int?, extraContext: String?, images: [AgentChatImage]) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        messages.append(message)
        if streams.isEmpty {
            return AsyncThrowingStream { continuation in continuation.finish() }
        }
        return streams.removeFirst()
    }
}

private final class StubLabUploadService: LabUploadServicing, @unchecked Sendable {
    nonisolated(unsafe) var importedURLs: [URL] = []
    let result: LabUploadResult

    init(result: LabUploadResult) {
        self.result = result
    }

    func importReport(fileURL: URL) async throws -> LabUploadResult {
        importedURLs.append(fileURL)
        return result
    }
}

/// A lab-upload service that always fails, mirroring the backend 422 「无法识别」
/// a non-lab image triggers. Used to prove the send path stays alive.
private final class FailingLabUploadService: LabUploadServicing, @unchecked Sendable {
    nonisolated(unsafe) var importedURLs: [URL] = []

    func importReport(fileURL: URL) async throws -> LabUploadResult {
        importedURLs.append(fileURL)
        throw APIError.httpStatus(422, "无法识别")
    }
}
