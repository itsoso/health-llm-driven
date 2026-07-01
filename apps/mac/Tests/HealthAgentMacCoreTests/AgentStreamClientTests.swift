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

    func testParserParsesDynamicCardsInDone() throws {
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3,"completion_status":"complete","cards":[{"type":"medical_exam_import_result","data":{"exam_id":321,"source":"pdf","items_count":9}}]}}

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
                        data: .object([
                            "exam_id": .int(321),
                            "source": .string("pdf"),
                            "items_count": .int(9)
                        ])
                    )
                ]
            )
        ])
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
            ])
        )

        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AgentChatMessage.self, from: data)

        XCTAssertEqual(decoded, original)
        XCTAssertEqual(decoded.cardData?["exam_id"]?.intValue, 321)
        XCTAssertEqual(decoded.cardData?["hospital_name"]?.stringValue, "Test Lab")
        XCTAssertEqual(decoded.cardData?["review_required"]?.boolValue, true)
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
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Reva-Client-Caps"), "genui-v1, genui-components-v1")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["message"] as? String, "分析今天状态")
            XCTAssertEqual(body?["conversation_id"] as? Int, 7)

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
    func testAgentChatViewModelSubmitEligibilityTrimsWhitespaceAndStreaming() {
        let model = AgentChatViewModel()

        XCTAssertFalse(model.canSubmit("   \n  "))
        XCTAssertTrue(model.canSubmit("如何正确测量腰围?"))

        model.isStreaming = true
        XCTAssertFalse(model.canSubmit("如何正确测量腰围?"))
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
        XCTAssertTrue(instruction.contains("不要输出密集长段落"))
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

    func stream(message: String, conversationID: Int?, extraContext: String?) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        stream
    }
}

private final class CapturingAgentStreamService: AgentStreamServicing, @unchecked Sendable {
    nonisolated(unsafe) var extraContext: String?
    nonisolated(unsafe) var extraContexts: [String?] = []
    nonisolated(unsafe) var messages: [String] = []
    nonisolated(unsafe) var streams: [AsyncThrowingStream<AgentStreamEvent, Error>] = []

    func stream(message: String, conversationID: Int?, extraContext: String?) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        self.extraContext = extraContext
        self.extraContexts.append(extraContext)
        self.messages.append(message)
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

    func stream(message: String, conversationID: Int?, extraContext: String?) -> AsyncThrowingStream<AgentStreamEvent, Error> {
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
