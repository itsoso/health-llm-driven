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
}

private struct StaticAgentStreamService: AgentStreamServicing {
    let stream: AsyncThrowingStream<AgentStreamEvent, Error>

    func stream(message: String, conversationID: Int?, extraContext: String?) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        stream
    }
}
