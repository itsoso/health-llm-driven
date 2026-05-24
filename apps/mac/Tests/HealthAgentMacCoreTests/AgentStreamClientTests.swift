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
                sourcesUsed: ["系统知识库"]
            )
        ])
    }

    func testAgentStreamClientPostsMessageAndYieldsEvents() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/agent/stream")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token")
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
            .done(conversationID: 7, messageID: 10, completionStatus: "complete", model: nil, sourcesUsed: [])
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
                sourcesUsed: ["系统知识库"]
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
    func testAgentChatViewModelTracksToolExecutionTimeline() async {
        let stream = AsyncThrowingStream<AgentStreamEvent, Error> { continuation in
            continuation.yield(.start(conversationID: 77))
            continuation.yield(.tool(name: "knowledge_search", success: nil))
            continuation.yield(.tool(name: "knowledge_search", success: true))
            continuation.yield(.tool(name: "health_manage", success: false))
            continuation.yield(.done(conversationID: 77, messageID: 88, completionStatus: "complete", model: nil, sourcesUsed: []))
            continuation.finish()
        }
        let model = AgentChatViewModel(streamService: StaticAgentStreamService(stream: stream))

        await model.send("分析并执行")

        XCTAssertEqual(model.toolActivities.map(\.name), ["knowledge_search", "knowledge_search", "health_manage"])
        XCTAssertEqual(model.toolActivities.map(\.status), [.running, .succeeded, .failed])
        XCTAssertEqual(model.toolActivities.last?.displayTitle, "health_manage failed")
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
                continuation.yield(.done(conversationID: 91, messageID: 2, completionStatus: "complete", model: nil, sourcesUsed: []))
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
        XCTAssertEqual(json["model_id"] as? String, "commercial/Gemini-3.1-Pro-Preview")
        XCTAssertEqual(json["web_search_requested"] as? Bool, true)
        let attachments = try XCTUnwrap(json["attachments"] as? [[String: Any]])
        XCTAssertEqual(attachments.first?["source_kind"] as? String, "genome_txt")
        XCTAssertEqual(attachments.first?["source_hash"] as? String, "sha256:abc")
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
}

private struct StaticAgentStreamService: AgentStreamServicing {
    let stream: AsyncThrowingStream<AgentStreamEvent, Error>

    func stream(message: String, conversationID: Int?, extraContext: String?) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        stream
    }
}

private final class CapturingAgentStreamService: AgentStreamServicing, @unchecked Sendable {
    nonisolated(unsafe) var extraContext: String?

    func stream(message: String, conversationID: Int?, extraContext: String?) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        self.extraContext = extraContext
        return AsyncThrowingStream { continuation in
            continuation.yield(.done(
                conversationID: conversationID,
                messageID: 1,
                completionStatus: "complete",
                model: nil,
                sourcesUsed: []
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
