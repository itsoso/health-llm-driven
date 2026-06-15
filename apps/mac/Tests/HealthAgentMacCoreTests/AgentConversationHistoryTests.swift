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
                {"id": 1, "role": "user", "content": "我昨晚没睡好", "created_at": "2026-06-12 09:00:00+00:00"},
                {"id": 2, "role": "assistant", "content": "了解,我们看看你的睡眠数据", "created_at": "2026-06-12 09:01:00+00:00"},
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
        XCTAssertEqual(messages[1].role, .assistant)
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
        // Opening it shows the cached transcript immediately, no detail fetch needed.
        await model.openConversation(model.conversationHistory[1])
        XCTAssertEqual(model.messages.first?.content, "cached question")
        XCTAssertNil(model.historyNotice)
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
        // Let the fire-and-forget backend delete Task run.
        await Task.yield()

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
    var deletedIDs: [Int] = []
    var renamed: [(Int, String)] = []

    func fetchConversations(limit: Int, offset: Int) async throws -> [AgentConversationSnapshot] {
        if let listError { throw listError }
        return list
    }

    func fetchDetail(conversationID: Int) async throws -> [AgentChatMessage] {
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
