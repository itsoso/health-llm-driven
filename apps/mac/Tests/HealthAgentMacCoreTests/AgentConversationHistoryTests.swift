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
                 "meta": {"model": "commercial/Claude-Opus-4.7", "selected_model": "commercial/Claude-Opus-4.7", "answer_model": "commercial/Claude-Opus-4.7", "tool_models": ["qwen3.7-max"], "fallback_reasons": ["selected_model_tool_stream_failed"], "elapsed_ms": 3300, "llm_rounds": 2, "sources_used": ["系统知识库"], "tools_used": ["health_query"], "completion_status": "complete", "cards": [{"type": "system_knowledge_evidence", "render": {"atom": "future_evidence", "reason": "experimental_renderer"}, "data": {"entity": {"title": "MTHFR"}, "claims": []}}]},
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
        XCTAssertEqual(messages[1].cardRender?.atom, "future_evidence")
        XCTAssertEqual(messages[1].cardRender?.reason, "experimental_renderer")
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
    func testSearchForwardsTermAndDoesNotClobberOfflineCache() async {
        // 全量缓存有 2 条;搜索只返回 1 条子集 —— 不能覆盖离线全量缓存。
        let store = InMemoryConversationStore(seed: [])
        let remote = FakeRemoteSource()
        let sleepID = AgentConversationClient.deterministicID(forConversationID: 1)
        let trainingID = AgentConversationClient.deterministicID(forConversationID: 2)
        remote.list = [
            AgentConversationSnapshot(id: sleepID, conversationID: 1, title: "睡眠复盘", messages: []),
            AgentConversationSnapshot(id: trainingID, conversationID: 2, title: "训练计划", messages: []),
        ]
        remote.searchResult = [
            AgentConversationSnapshot(id: sleepID, conversationID: 1, title: "睡眠复盘", messages: []),
        ]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        // 全量拉取 → 缓存写入 2 条
        await model.refreshConversationHistory()
        XCTAssertEqual(store.saved.last?.count, 2)

        // 搜索 → 列表变子集, 但缓存不被子集覆盖(仍是 2 条)
        await model.refreshConversationHistory(search: "睡眠")
        XCTAssertEqual(remote.lastSearch, "睡眠")
        XCTAssertEqual(model.conversationHistory.count, 1)
        XCTAssertEqual(model.conversationHistory.first?.conversationID, 1)
        XCTAssertEqual(store.saved.last?.count, 2, "搜索子集不得覆盖离线全量缓存")
    }

    @MainActor
    func testSearchEntryPointTrimsTermAndPreservesOfflineCache() async {
        let store = InMemoryConversationStore(seed: [])
        let remote = FakeRemoteSource()
        let sleepID = AgentConversationClient.deterministicID(forConversationID: 1)
        let trainingID = AgentConversationClient.deterministicID(forConversationID: 2)
        remote.list = [
            AgentConversationSnapshot(id: sleepID, conversationID: 1, title: "睡眠复盘", messages: []),
            AgentConversationSnapshot(id: trainingID, conversationID: 2, title: "训练计划", messages: []),
        ]
        remote.searchResult = [
            AgentConversationSnapshot(id: sleepID, conversationID: 1, title: "睡眠复盘", messages: []),
        ]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        await model.refreshConversationHistory()
        await model.searchConversationHistory("  睡眠  ")

        XCTAssertEqual(remote.lastSearch, "睡眠")
        XCTAssertEqual(model.conversationHistory.map(\.conversationID), [1])
        XCTAssertEqual(store.saved.last?.count, 2, "搜索结果不能覆盖完整离线缓存")
    }

    @MainActor
    func testSearchFailureShowsOnlyMatchingLocalCache() async {
        let store = InMemoryConversationStore(seed: [
            AgentConversationSnapshot(conversationID: 1, title: "睡眠复盘", messages: [
                .init(role: .user, content: "昨晚睡眠不好"),
            ]),
            AgentConversationSnapshot(conversationID: 2, title: "训练计划", messages: [
                .init(role: .user, content: "今天跑步"),
            ]),
        ])
        let remote = FakeRemoteSource()
        remote.listError = APIError.httpStatus(503, nil)
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)

        await model.searchConversationHistory("睡眠")

        XCTAssertEqual(model.conversationHistory.map(\.conversationID), [1])
        XCTAssertNotNil(model.historyNotice)
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

    // MARK: - Rename

    @MainActor
    func testRenamePushesToBackendThenUpdatesLocalTitle() async {
        let id = AgentConversationClient.deterministicID(forConversationID: 42)
        let snapshot = AgentConversationSnapshot(id: id, conversationID: 42, title: "旧标题", messages: [
            .init(role: .user, content: "hi")
        ])
        let store = InMemoryConversationStore(seed: [snapshot])
        let remote = FakeRemoteSource()
        remote.list = [snapshot]
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)
        await model.refreshConversationHistory()

        await model.renameConversation(model.conversationHistory[0], to: "  新标题  ")

        XCTAssertEqual(remote.renamed.map(\.0), [42])
        XCTAssertEqual(remote.renamed.first?.1, "新标题")  // trimmed
        XCTAssertEqual(model.conversationHistory[0].title, "新标题")
        XCTAssertEqual(store.saved.last?.first?.title, "新标题")
        XCTAssertNil(model.historyNotice)
    }

    @MainActor
    func testRenameBackendFailureKeepsOldTitleAndSetsNotice() async {
        let id = AgentConversationClient.deterministicID(forConversationID: 42)
        let snapshot = AgentConversationSnapshot(id: id, conversationID: 42, title: "旧标题", messages: [
            .init(role: .user, content: "hi")
        ])
        let store = InMemoryConversationStore(seed: [snapshot])
        let remote = FakeRemoteSource()
        remote.list = [snapshot]
        remote.renameError = APIError.httpStatus(500, nil)
        let model = AgentChatViewModel(conversationStore: store, remoteSource: remote)
        await model.refreshConversationHistory()

        await model.renameConversation(model.conversationHistory[0], to: "新标题")

        // Backend rejected → local title must NOT fake success.
        XCTAssertEqual(model.conversationHistory[0].title, "旧标题")
        XCTAssertNotNil(model.historyNotice)
    }

    @MainActor
    func testRenameIgnoresBlankTitle() async {
        let id = AgentConversationClient.deterministicID(forConversationID: 42)
        let snapshot = AgentConversationSnapshot(id: id, conversationID: 42, title: "旧标题", messages: [])
        let remote = FakeRemoteSource()
        remote.list = [snapshot]
        let model = AgentChatViewModel(conversationStore: InMemoryConversationStore(seed: [snapshot]), remoteSource: remote)
        await model.refreshConversationHistory()

        await model.renameConversation(model.conversationHistory[0], to: "   ")

        XCTAssertTrue(remote.renamed.isEmpty)
        XCTAssertEqual(model.conversationHistory[0].title, "旧标题")
    }

    // MARK: - Share

    @MainActor
    func testShareReturnsURLAndHitsBackend() async {
        let id = AgentConversationClient.deterministicID(forConversationID: 42)
        let snapshot = AgentConversationSnapshot(id: id, conversationID: 42, title: "chat", messages: [])
        let remote = FakeRemoteSource()
        remote.list = [snapshot]
        remote.shareURL = URL(string: "https://health.executor.life/shared/abc")!
        let model = AgentChatViewModel(conversationStore: InMemoryConversationStore(seed: [snapshot]), remoteSource: remote)
        await model.refreshConversationHistory()

        let url = await model.shareConversation(model.conversationHistory[0])

        XCTAssertEqual(url?.absoluteString, "https://health.executor.life/shared/abc")
        XCTAssertEqual(remote.sharedIDs, [42])
        XCTAssertNil(model.historyNotice)
    }

    @MainActor
    func testShareFailureReturnsNilAndSetsNotice() async {
        let id = AgentConversationClient.deterministicID(forConversationID: 42)
        let snapshot = AgentConversationSnapshot(id: id, conversationID: 42, title: "chat", messages: [])
        let remote = FakeRemoteSource()
        remote.list = [snapshot]
        remote.shareError = APIError.httpStatus(500, nil)
        let model = AgentChatViewModel(conversationStore: InMemoryConversationStore(seed: [snapshot]), remoteSource: remote)
        await model.refreshConversationHistory()

        let url = await model.shareConversation(model.conversationHistory[0])

        XCTAssertNil(url)
        XCTAssertNotNil(model.historyNotice)
    }

    @MainActor
    func testShareWithoutBackendIDReturnsNil() async {
        // A conversation that only exists locally (no durable backend id) can't be shared.
        let snapshot = AgentConversationSnapshot(conversationID: nil, title: "local only", messages: [])
        let remote = FakeRemoteSource()
        let model = AgentChatViewModel(conversationStore: nil, remoteSource: remote)

        let url = await model.shareConversation(snapshot)

        XCTAssertNil(url)
        XCTAssertTrue(remote.sharedIDs.isEmpty)
        XCTAssertNotNil(model.historyNotice)
    }

    // MARK: - Client share mapping

    func testConversationClientCreatesShareLink() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/shared/create")
            let body = request.bodyDataForTesting ?? Data()
            let json = (try? JSONSerialization.jsonObject(with: body)) as? [String: Any]
            XCTAssertEqual(json?["conversation_id"] as? Int, 42)
            XCTAssertEqual(json?["source_type"] as? String, "agent")
            let data = """
            {"share_token": "tok9", "share_url": "https://health.executor.life/shared/tok9", "expires_at": null}
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = AgentConversationClient(apiClient: stubbedAPIClient())

        let url = try await client.shareConversation(conversationID: 42)

        XCTAssertEqual(url.absoluteString, "https://health.executor.life/shared/tok9")
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
    var renameError: Error?
    var sharedIDs: [Int] = []
    var shareURL = URL(string: "https://health.executor.life/shared/tok-123")!
    var shareError: Error?
    /// Records the last search term the VM forwarded (nil = unfiltered fetch).
    var lastSearch: String?
    /// When set, fetches with a non-empty search return this instead of `list`.
    var searchResult: [AgentConversationSnapshot]?

    func fetchConversations(limit: Int, offset: Int, search: String?) async throws -> [AgentConversationSnapshot] {
        lastSearch = search
        if let listError { throw listError }
        let term = search?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !term.isEmpty, let searchResult { return searchResult }
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
        if let renameError { throw renameError }
        renamed.append((conversationID, title))
    }

    func shareConversation(conversationID: Int) async throws -> URL {
        sharedIDs.append(conversationID)
        if let shareError { throw shareError }
        return shareURL
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

// MARK: - 证据面板回灌(2026-07-03 bug:打开历史对话后右侧证据面板空占位)

extension AgentConversationHistoryTests {
    @MainActor
    func testLoadConversationRehydratesSourcesUsedFromLastAssistant() {
        let model = AgentChatViewModel(conversationStore: nil, remoteSource: nil)
        let snapshot = AgentConversationSnapshot(conversationID: 7, title: "红参分析", messages: [
            .init(role: .user, content: "分析红参"),
            .init(
                role: .assistant,
                content: "分析结果……",
                model: "qwen3.7-max",
                sourcesUsed: ["Garmin 数据 (14 天)", "化验报告 (23 次)", "系统知识库"],
                completionStatus: "complete"
            ),
        ])

        model.loadConversation(snapshot)

        // 气泡按 per-message meta 渲染"引用 N 项数据",证据面板必须同源非空
        XCTAssertEqual(model.lastSourcesUsed.count, 3)
        XCTAssertTrue(model.lastSourcesUsed.contains("系统知识库"))
        XCTAssertEqual(model.lastModel, "qwen3.7-max")
        XCTAssertEqual(model.lastCompletionStatus, "complete")
    }

    @MainActor
    func testLoadConversationWithoutAssistantClearsPanel() {
        let model = AgentChatViewModel(conversationStore: nil, remoteSource: nil)
        model.lastSourcesUsed = ["残留"]
        model.loadConversation(AgentConversationSnapshot(conversationID: 8, title: "空", messages: [
            .init(role: .user, content: "刚开头"),
        ]))
        XCTAssertTrue(model.lastSourcesUsed.isEmpty)
        XCTAssertNil(model.lastModel)
    }
}
