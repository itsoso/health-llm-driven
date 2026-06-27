import Foundation
import XCTest
@testable import HealthAgentMacCore

final class AgentConversationHistoryTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    // MARK: - AgentConversationClient mapping (over the real APIClient + stub)

    func testConversationClientFetchesAndMapsListFromBackend() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(
                request.url?.absoluteString,
                "https://example.test/api/v1/agent/conversations?limit=30&offset=0"
            )
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token")
            let data = """
            {
              "items": [
                {"id": 42, "title": "睡眠分析", "last_message": "我昨晚没睡好",
                 "created_at": "2026-06-10 08:00:00+00:00", "updated_at": "2026-06-12 09:30:00+00:00", "mode": "agent"},
                {"id": 7, "title": null, "last_message": "帮我看看血压",
                 "created_at": "2026-06-01 08:00:00+00:00", "updated_at": "2026-06-01 08:05:00+00:00", "mode": "agent"}
              ],
              "total": 2, "limit": 30, "offset": 0
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = AgentConversationClient(apiClient: stubbedAPIClient())

        let snapshots = try await client.fetchConversations(limit: 30, offset: 0)

        XCTAssertEqual(snapshots.count, 2)
        XCTAssertEqual(snapshots[0].conversationID, 42)
        XCTAssertEqual(snapshots[0].title, "睡眠分析")
        XCTAssertTrue(snapshots[0].messages.isEmpty, "list snapshots carry no messages until opened")
        // Missing title falls back to the last_message preview.
        XCTAssertEqual(snapshots[1].title, "帮我看看血压")
        // Deterministic ids so selection survives a refresh.
        XCTAssertEqual(snapshots[0].id, AgentConversationClient.deterministicID(forConversationID: 42))
    }

    func testConversationClientFetchesDetailAndMapsMessages() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/agent/conversations/42")
            let data = """
            {
              "id": 42, "title": "睡眠分析", "total_messages": 3, "mode": "agent",
              "messages": [
                {"id": 1, "role": "user", "content": "我昨晚没睡好",
                 "image_url": "[\\"/api/v1/upload/files/chat/dinner.jpg\\", \\"https://cdn.example.test/meal.png\\"]",
                 "created_at": "2026-06-12 09:00:00+00:00"},
                {"id": 2, "role": "assistant", "content": "了解,我们看看你的睡眠数据",
                 "meta": {"model": "commercial/Claude-Opus-4.7", "selected_model": "commercial/Claude-Opus-4.7", "answer_model": "commercial/Claude-Opus-4.7", "tool_models": ["qwen3.7-max"], "fallback_reasons": ["selected_model_tool_stream_failed"], "elapsed_ms": 3300, "llm_rounds": 2, "sources_used": ["系统知识库"], "tools_used": ["health_query"], "completion_status": "complete", "cards": [{"type": "system_knowledge_evidence", "data": {"entity": {"title": "MTHFR"}, "claims": []}}]},
                 "created_at": "2026-06-12 09:01:00+00:00"},
                {"id": 3, "role": "system", "content": "internal", "created_at": "2026-06-12 09:02:00+00:00"}
              ]
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = AgentConversationClient(apiClient: stubbedAPIClient())

        let messages = try await client.fetchDetail(conversationID: 42)

        // system row dropped; user + assistant kept in order.
        XCTAssertEqual(messages.count, 2)
        XCTAssertEqual(messages[0].role, .user)
        XCTAssertEqual(messages[0].content, "我昨晚没睡好")
        XCTAssertEqual(messages[0].remoteImageURLs, [
            "https://example.test/api/v1/upload/files/chat/dinner.jpg",
            "https://cdn.example.test/meal.png",
        ])
        XCTAssertEqual(messages[1].role, .assistant)
        XCTAssertEqual(messages[1].model, "commercial/Claude-Opus-4.7")
        XCTAssertEqual(messages[1].selectedModel, "commercial/Claude-Opus-4.7")
        XCTAssertEqual(messages[1].answerModel, "commercial/Claude-Opus-4.7")
        XCTAssertEqual(messages[1].toolModels, ["qwen3.7-max"])
        XCTAssertEqual(messages[1].fallbackReasons, ["selected_model_tool_stream_failed"])
        XCTAssertEqual(messages[1].elapsedMs, 3300)
        XCTAssertEqual(messages[1].llmRounds, 2)
        XCTAssertEqual(messages[1].sourcesUsed, ["系统知识库"])
        XCTAssertEqual(messages[1].toolsUsed, ["health_query"])
        XCTAssertEqual(messages[1].completionStatus, "complete")
        XCTAssertEqual(messages[1].cardType, "system_knowledge_evidence")
        XCTAssertEqual(messages[1].cardData?["entity"]?["title"]?.stringValue, "MTHFR")
    }

    func testConversationClientParsesPythonAndISODates() {
        XCTAssertNotNil(AgentConversationClient.parseDate("2026-06-12 09:30:00+00:00"))
        XCTAssertNotNil(AgentConversationClient.parseDate("2026-06-12T09:30:00Z"))
        XCTAssertNotNil(AgentConversationClient.parseDate("2026-06-12T09:30:00.123Z"))
        XCTAssertNil(AgentConversationClient.parseDate(nil))
        XCTAssertNil(AgentConversationClient.parseDate(""))
    }

    // MARK: - ViewModel history behaviour

    @MainActor
    func testRefreshReplacesLocalCacheWithBackendOnSuccess() async {
        let store = InMemoryConversationStore(seed: [
            AgentConversationSnapshot(conversationID: 99, title: "stale local", messages: [
                .init(role: .user, content: "old")
            ])
        ])
        let remote = FakeRemoteSource()
        remote.list = [AgentConversationSnapshot(
            id: AgentConversationClient.deterministicID(forConversationID: 42),
            conversationID: 42, title: "backend chat", messages: []
        )]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        await model.refreshConversationHistory()

        XCTAssertEqual(model.conversationHistory.count, 1)
        XCTAssertEqual(model.conversationHistory.first?.conversationID, 42)
        XCTAssertNil(model.historyNotice)
        // Backend result is also written to the local cache for offline use.
        XCTAssertEqual(store.saved.last?.first?.conversationID, 42)
    }

    @MainActor
    func testRefreshFallsBackToLocalCacheAndSetsNoticeOnFailure() async {
        let local = AgentConversationSnapshot(conversationID: 99, title: "local only", messages: [
            .init(role: .user, content: "cached")
        ])
        let store = InMemoryConversationStore(seed: [local])
        let remote = FakeRemoteSource()
        remote.listError = APIError.httpStatus(500, nil)
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        await model.refreshConversationHistory()

        // History not wiped; notice surfaced so the user knows it's stale.
        XCTAssertEqual(model.conversationHistory.count, 1)
        XCTAssertEqual(model.conversationHistory.first?.conversationID, 99)
        XCTAssertNotNil(model.historyNotice)
    }

    @MainActor
    func testOpenConversationFetchesDetailFromBackend() async {
        let listSnapshot = AgentConversationSnapshot(
            id: AgentConversationClient.deterministicID(forConversationID: 42),
            conversationID: 42, title: "backend chat", messages: []
        )
        let store = InMemoryConversationStore(seed: [])
        let remote = FakeRemoteSource()
        remote.list = [listSnapshot]
        remote.detailByID[42] = [
            .init(role: .user, content: "我昨晚没睡好"),
            .init(role: .assistant, content: "我们看看数据"),
        ]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)
        await model.refreshConversationHistory()

        await model.openConversation(model.conversationHistory[0])

        XCTAssertEqual(model.messages.count, 2)
        XCTAssertEqual(model.messages.first?.content, "我昨晚没睡好")
        XCTAssertEqual(model.currentConversationID, listSnapshot.id)
    }

    @MainActor
    func testRefreshAutoLoadsLatestRemoteConversationWhenNoLocalCache() async {
        let remoteSnapshot = AgentConversationSnapshot(
            id: AgentConversationClient.deterministicID(forConversationID: 42),
            conversationID: 42,
            title: "手机会话",
            messages: []
        )
        let store = InMemoryConversationStore(seed: [])
        let remote = FakeRemoteSource()
        remote.list = [remoteSnapshot]
        remote.detailByID[42] = [
            .init(role: .user, content: "手机上的问题"),
            .init(role: .assistant, content: "手机上的回答"),
        ]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        await model.refreshConversationHistory()

        XCTAssertEqual(remote.fetchedDetailIDs, [42])
        XCTAssertEqual(model.currentConversationID, remoteSnapshot.id)
        XCTAssertEqual(model.messages.map(\.content), ["手机上的问题", "手机上的回答"])
        XCTAssertNil(model.historyNotice)
    }

    @MainActor
    func testRefreshUpdatesCurrentCachedConversationFromBackendDetail() async {
        let convID = 42
        let id = AgentConversationClient.deterministicID(forConversationID: convID)
        let cached = AgentConversationSnapshot(id: id, conversationID: convID, title: "chat", messages: [
            .init(role: .user, content: "本地旧问题"),
            .init(role: .assistant, content: "本地旧回答"),
        ])
        let store = InMemoryConversationStore(seed: [cached])
        let remote = FakeRemoteSource()
        remote.list = [AgentConversationSnapshot(id: id, conversationID: convID, title: "chat", messages: [])]
        remote.detailByID[convID] = [
            .init(role: .user, content: "手机新增问题"),
            .init(role: .assistant, content: "手机新增回答"),
        ]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        await model.refreshConversationHistory()

        XCTAssertEqual(remote.fetchedDetailIDs, [convID])
        XCTAssertEqual(model.messages.map(\.content), ["手机新增问题", "手机新增回答"])
        XCTAssertEqual(store.saved.last?.first?.messages.map(\.content), ["手机新增问题", "手机新增回答"])
    }

    @MainActor
    func testOpenConversationRefreshesCachedTranscriptFromBackendDetail() async {
        let convID = 42
        let id = AgentConversationClient.deterministicID(forConversationID: convID)
        let cached = AgentConversationSnapshot(id: id, conversationID: convID, title: "chat", messages: [
            .init(role: .user, content: "本地旧问题")
        ])
        let store = InMemoryConversationStore(seed: [])
        let remote = FakeRemoteSource()
        remote.detailByID[convID] = [
            .init(role: .user, content: "手机上的新问题"),
            .init(role: .assistant, content: "手机上的新回答"),
        ]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        await model.openConversation(cached)

        XCTAssertEqual(remote.fetchedDetailIDs, [convID])
        XCTAssertEqual(model.messages.map(\.content), ["手机上的新问题", "手机上的新回答"])
        XCTAssertNil(model.historyNotice)
    }

    @MainActor
    func testRefreshPreservesCachedTranscriptUnderMessagelessBackendList() async {
        let convID = 42
        let id = AgentConversationClient.deterministicID(forConversationID: convID)
        // Decoy first so the target isn't auto-loaded into `messages` by init.
        let decoyID = AgentConversationClient.deterministicID(forConversationID: 1)
        let decoy = AgentConversationSnapshot(id: decoyID, conversationID: 1, title: "other", messages: [
            .init(role: .user, content: "unrelated")
        ])
        let cached = AgentConversationSnapshot(id: id, conversationID: convID, title: "chat", messages: [
            .init(role: .user, content: "cached question"),
            .init(role: .assistant, content: "cached answer"),
        ])
        let store = InMemoryConversationStore(seed: [decoy, cached])
        let remote = FakeRemoteSource()
        // Backend list carries no messages — refresh must NOT wipe cached transcripts.
        remote.list = [
            AgentConversationSnapshot(id: decoyID, conversationID: 1, title: "other", messages: []),
            AgentConversationSnapshot(id: id, conversationID: convID, title: "chat", messages: []),
        ]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        await model.refreshConversationHistory()

        XCTAssertEqual(model.conversationHistory[1].messages.count, 2)
        // Opening still tries to sync detail; if that fails, cached transcript is
        // the visible fallback instead of silently showing an empty chat.
        remote.detailError = APIError.httpStatus(503, nil)
        await model.openConversation(model.conversationHistory[1])
        XCTAssertEqual(model.messages.first?.content, "cached question")
        XCTAssertNotNil(model.historyNotice)
    }

    @MainActor
    func testOpenConversationSurfacesNoticeWhenDetailFailsAndNoCache() async {
        let convID = 42
        let id = AgentConversationClient.deterministicID(forConversationID: convID)
        let store = InMemoryConversationStore(seed: [])
        let remote = FakeRemoteSource()
        // Backend lists it but with no messages, and the detail fetch fails. No
        // local cache exists for it → can't fake success.
        remote.list = [AgentConversationSnapshot(id: id, conversationID: convID, title: "chat", messages: [])]
        remote.detailError = APIError.httpStatus(503, nil)
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)
        await model.refreshConversationHistory()

        await model.openConversation(model.conversationHistory[0])

        XCTAssertTrue(model.messages.isEmpty)
        XCTAssertNotNil(model.historyNotice)
    }

    @MainActor
    func testDeleteCallsBackendThenRemovesLocally() async {
        let id = AgentConversationClient.deterministicID(forConversationID: 42)
        let snapshot = AgentConversationSnapshot(id: id, conversationID: 42, title: "chat", messages: [
            .init(role: .user, content: "hi")
        ])
        let store = InMemoryConversationStore(seed: [snapshot])
        let remote = FakeRemoteSource()
        remote.list = [snapshot]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)
        await model.refreshConversationHistory()

        model.deleteConversation(model.conversationHistory[0])
        // 等 fire-and-forget 的后端删除 Task 完成。单个 Task.yield() 在 CI 繁忙调度下
        // 不保证 detached Task 已跑 → 竞态翻红(本地快机过、CI 挂)。有界轮询直到副作用出现。
        for _ in 0..<200 {
            if !remote.deletedIDs.isEmpty { break }
            await Task.yield()
            try? await Task.sleep(nanoseconds: 1_000_000)  // 1ms
        }

        XCTAssertTrue(model.conversationHistory.isEmpty)
        XCTAssertEqual(remote.deletedIDs, [42])
    }

    // MARK: - Helpers

    private func stubbedAPIClient() -> APIClient {
        APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )
    }
}

// MARK: - Fakes

private final class FakeRemoteSource: AgentConversationRemoteSourcing, @unchecked Sendable {
    var list: [AgentConversationSnapshot] = []
    var listError: Error?
    var detailByID: [Int: [AgentChatMessage]] = [:]
    var detailError: Error?
    var fetchedDetailIDs: [Int] = []
    var deletedIDs: [Int] = []
    var renamed: [(Int, String)] = []

    func fetchConversations(limit: Int, offset: Int) async throws -> [AgentConversationSnapshot] {
        if let listError { throw listError }
        return list
    }

    func fetchDetail(conversationID: Int) async throws -> [AgentChatMessage] {
        fetchedDetailIDs.append(conversationID)
        if let detailError { throw detailError }
        return detailByID[conversationID] ?? []
    }

    func deleteConversation(conversationID: Int) async throws {
        deletedIDs.append(conversationID)
    }

    func renameConversation(conversationID: Int, title: String) async throws {
        renamed.append((conversationID, title))
    }
}

private final class InMemoryConversationStore: AgentConversationStoring, @unchecked Sendable {
    private var current: [AgentConversationSnapshot]
    private(set) var saved: [[AgentConversationSnapshot]] = []

    init(seed: [AgentConversationSnapshot]) {
        self.current = seed
    }

    func loadConversations() -> [AgentConversationSnapshot] {
        current
    }

    func saveConversations(_ conversations: [AgentConversationSnapshot]) {
        current = conversations
        saved.append(conversations)
    }
}
