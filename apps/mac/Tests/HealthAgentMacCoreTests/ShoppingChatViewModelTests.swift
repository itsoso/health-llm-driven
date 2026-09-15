import Foundation
import XCTest
@testable import HealthAgentMacCore

@MainActor
private final class ShoppingCredentialsFake: ShoppingCredentialSource {
    var values: [HTTPCookie] = []
    var resets = 0
    func cookies() async -> [HTTPCookie] { values }
    func reset() { resets += 1; values = [] }
}

@MainActor
private final class ShoppingServiceFake: ShoppingService {
    var calls = 0
    var lastContent: String?
    var lastMessageID: String?
    var historyResponse = Data(#"{"result":1,"data":{"historyList":[],"pcursor":"no_more"}}"#.utf8)
    var continuation: AsyncThrowingStream<Data, Error>.Continuation?
    var onChat: (() -> Void)?
    var loadResponse = Data(#"{"result":1,"data":{"historyList":[]}}"#.utf8)
    func load(cookies: [HTTPCookie]) async throws -> Data { calls += 1; return loadResponse }
    func questions(cookies: [HTTPCookie]) async throws -> Data { calls += 1; return Data(#"{"result":1,"data":{"questions":[]}}"#.utf8) }
    func history(pcursor: String, cookies: [HTTPCookie]) async throws -> Data { calls += 1; return historyResponse }
    func feedback(messageID: String, sessionID: String?, type: Int, cookies: [HTTPCookie]) async throws -> Data { calls += 1; return Data(#"{"result":1}"#.utf8) }
    func chat(content: String, messageID: String, globalParams: [String: ShoppingJSONValue], cookies: [HTTPCookie]) -> AsyncThrowingStream<Data, Error> {
        calls += 1; lastContent = content; lastMessageID = messageID
        return AsyncThrowingStream { continuation in self.continuation = continuation; onChat?() }
    }
}

final class ShoppingChatViewModelTests: XCTestCase {
    @MainActor func testBridgeDisconnectCannotRestorePreviousNativeAccount() async throws {
        let credentials = ShoppingCredentialsFake()
        let service = ShoppingServiceFake()
        let config = try ShoppingConfiguration(gateway: URL(string: "https://shop.kuaishou.com")!, entrySource: "test")
        let vm = ShoppingChatViewModel(credentials: credentials, configuration: config, service: service)
        vm.bindOwner("owner")
        service.onChat = { service.continuation?.finish() }
        let cookie = HTTPCookie(properties: [.name: "token", .value: "synthetic-native-A", .domain: ".kuaishou.com", .path: "/"])!
        credentials.values = [cookie]
        await vm.refreshCredentials()
        XCTAssertTrue(vm.canUseService)
        _ = try await vm.startLocalBridge()
        vm.localBridge.disconnect()
        XCTAssertFalse(vm.canUseService, "Disconnect must not restore account A")
        credentials.values = [cookie]
        await vm.refreshCredentials()
        XCTAssertFalse(vm.canUseService, "Cookie refresh must not silently change transport")
        vm.draft = "synthetic"
        await vm.send()
        await vm.loadHistory()
        await vm.load()
        XCTAssertEqual(service.calls, 0)
        vm.prepareForLogin()
        credentials.values = [cookie]
        await vm.refreshCredentials()
        XCTAssertTrue(vm.canUseService, "Explicit native login may start a clean session")
        XCTAssertTrue(vm.transcript.messages.isEmpty)
    }

    @MainActor func testBridgePairingCannotSurviveOwnerChange() async throws {
        let vm = ShoppingChatViewModel(credentials: ShoppingCredentialsFake())
        vm.bindOwner("a")
        _ = try await vm.startLocalBridge()
        XCTAssertTrue(vm.localBridge.isActive)
        vm.bindOwner("b")
        XCTAssertFalse(vm.localBridge.isActive)
        XCTAssertNil(vm.localBridge.pairingCode)
        XCTAssertTrue(vm.transcript.messages.isEmpty)
    }

    @MainActor func testBridgeRequiresOwnerAndDemoCannotStartIt() async {
        let vm = ShoppingChatViewModel(credentials: ShoppingCredentialsFake())
        do { _ = try await vm.startLocalBridge(); XCTFail("No owner") } catch { }
        vm.bindOwner("a")
        vm.setDemoMode(true)
        do { _ = try await vm.startLocalBridge(); XCTFail("Demo mode") } catch { }
        XCTAssertFalse(vm.localBridge.isActive)
    }

    @MainActor func testQueuedOfficialQuestionCannotOutliveOwnerDraftOrMode() throws {
        for mutation in 0..<5 {
            let vm = ShoppingChatViewModel(credentials: ShoppingCredentialsFake())
            vm.bindOwner("a")
            vm.draft = "找个通勤杯子"
            let submission = try XCTUnwrap(vm.prepareOfficialQuestion())
            XCTAssertEqual(vm.validateOfficialQuestion(submission), "找个通勤杯子")
            switch mutation {
            case 0: vm.bindOwner(nil)
            case 1: vm.bindOwner("b")
            case 2: vm.clearConversation(); vm.draft = "找个通勤杯子"
            case 3: vm.setDemoMode(true)
            default: vm.draft = "另一个问题"
            }
            XCTAssertNil(vm.validateOfficialQuestion(submission), "Queued external submission must be invalidated")
        }
    }

    @MainActor func testUnconfiguredDraftUsesOfficialAppWithoutDirectServiceSend() async {
        let service = ShoppingServiceFake()
        let vm = ShoppingChatViewModel(credentials: ShoppingCredentialsFake(), service: service)
        vm.bindOwner("owner")
        vm.draft = "找个通勤杯子"
        XCTAssertTrue(vm.usesOfficialAppForSending)
        XCTAssertFalse(vm.canSend)
        await vm.send()
        XCTAssertEqual(service.calls, 0)
        XCTAssertEqual(vm.draft, "找个通勤杯子")
        vm.setDemoMode(true)
        XCTAssertFalse(vm.usesOfficialAppForSending)
    }

    @MainActor func testSentMessageAndHistoryShareIdentityWithoutDuplicatingRepeatedText() async throws {
        let credentials = ShoppingCredentialsFake()
        let service = ShoppingServiceFake()
        let config = try ShoppingConfiguration(gateway: URL(string: "https://shop.kuaishou.com")!, entrySource: "test-entry")
        let vm = ShoppingChatViewModel(credentials: credentials, configuration: config, service: service)
        vm.bindOwner("owner")
        credentials.values = [HTTPCookie(properties: [.name: "token", .value: "fake-a", .domain: ".kuaishou.com", .path: "/"])!]
        await vm.refreshCredentials()
        service.onChat = { service.continuation?.finish() }
        var sentIDs: [String] = []
        for _ in 0..<2 {
            vm.draft = "再找一个杯子"
            await vm.send()
            let sentID = try XCTUnwrap(service.lastMessageID)
            XCTAssertEqual(vm.transcript.messages.last?.messageId, sentID)
            sentIDs.append(sentID)
        }
        XCTAssertNotEqual(sentIDs[0], sentIDs[1], "Separate sends of identical text must remain distinct")
        service.historyResponse = try JSONSerialization.data(withJSONObject: [
            "result": 1, "data": ["pcursor": "no_more", "historyList": sentIDs.map { id in
                ["messageId": id, "sender": "user", "blocks": [["type": "text", "content": ["text": "再找一个杯子"]]]] as [String: Any]
            }]
        ])
        await vm.loadHistory()
        XCTAssertEqual(vm.transcript.messages.map(\.messageId), sentIDs)
        XCTAssertFalse(vm.hasMoreHistory)
    }

    @MainActor func testOtherWindowCannotRestoreOwnerAfterLogout() {
        let vm = ShoppingChatViewModel(credentials: ShoppingCredentialsFake())
        vm.bindOwner("a")
        let otherWindowRequest = vm.ownerGeneration
        vm.bindOwner(nil)
        XCTAssertFalse(vm.resolveOwner("a", generation: otherWindowRequest))
        XCTAssertFalse(vm.ownerIsBound)
        let loginRequest = vm.ownerGeneration
        XCTAssertTrue(vm.resolveOwner("b", generation: loginRequest))
        XCTAssertTrue(vm.ownerIsBound)
        XCTAssertFalse(vm.resolveOwner("a", generation: otherWindowRequest))
    }

    @MainActor func testLogoutInvalidatesPendingIdentityEvenBeforeFirstBinding() {
        let vm = ShoppingChatViewModel(credentials: ShoppingCredentialsFake())
        let otherWindowRequest = vm.ownerGeneration
        vm.bindOwner(nil)
        XCTAssertFalse(vm.resolveOwner("a", generation: otherWindowRequest))
    }

    @MainActor func testCredentialChangeBeforeOperationDoesNotSendOldAccountData() async throws {
        for action in ["send", "feedback", "history"] {
            let credentials = ShoppingCredentialsFake()
            let service = ShoppingServiceFake()
            let config = try ShoppingConfiguration(gateway: URL(string: "https://shop.kuaishou.com")!, entrySource: "test-entry")
            let vm = ShoppingChatViewModel(credentials: credentials, configuration: config, service: service)
            vm.bindOwner("owner")
            credentials.values = [HTTPCookie(properties: [.name: "token", .value: "fake-a", .domain: ".kuaishou.com", .path: "/"])!]
            await vm.refreshCredentials()
            if action == "feedback" {
                service.loadResponse = Data(#"{"result":1,"data":{"historyList":[{"messageId":"a-reply","sessionId":"a-session","sender":"ai","blocks":[{"type":"text","content":{"text":"Account A reply"}}]}]}}"#.utf8)
                await vm.load()
            }
            let message = vm.transcript.messages.first
            vm.draft = "Account A private draft"
            credentials.values = [HTTPCookie(properties: [.name: "token", .value: "fake-b", .domain: ".kuaishou.com", .path: "/"])!]
            let before = service.calls
            service.onChat = { service.continuation?.finish() }
            if action == "send" { await vm.send() }
            else if action == "feedback", let message { await vm.feedback(message: message, positive: true) }
            else { await vm.loadHistory() }
            XCTAssertEqual(service.calls, before, action)
            XCTAssertTrue(vm.transcript.messages.isEmpty, action)
            XCTAssertTrue(vm.draft.isEmpty, action)
            XCTAssertEqual(vm.credentialState, .serviceCandidate)
        }
    }

    @MainActor func testDemoIsExplicitAndNeverUsesNetworkAndClearsOnExit() async throws {
        let credentials = ShoppingCredentialsFake()
        let service = ShoppingServiceFake()
        let vm = ShoppingChatViewModel(credentials: credentials, configuration: nil, service: service)
        vm.bindOwner("health-a")
        vm.setDemoMode(true)
        vm.draft = "找一个旅行杯"
        await vm.send()
        XCTAssertTrue(vm.isDemo)
        XCTAssertFalse(vm.transcript.messages.isEmpty)
        XCTAssertEqual(service.calls, 0)
        vm.setDemoMode(false)
        XCTAssertTrue(vm.transcript.messages.isEmpty)
        XCTAssertTrue(vm.draft.isEmpty)
        XCTAssertFalse(vm.canSend)
    }

    @MainActor func testWebLoginDoesNotEnableShoppingOrLeakHealthInput() async throws {
        let credentials = ShoppingCredentialsFake()
        let service = ShoppingServiceFake()
        let config = try ShoppingConfiguration(gateway: URL(string: "https://shop.kuaishou.com")!, entrySource: "test-entry")
        let vm = ShoppingChatViewModel(credentials: credentials, configuration: config, service: service)
        vm.bindOwner("health-a")
        credentials.values = [HTTPCookie(properties: [.name: "kuaishou.server.webday7_st", .value: "fake", .domain: "www.kuaishou.com", .path: "/"])!]
        await vm.refreshCredentials()
        vm.draft = "购物输入"
        await vm.send()
        XCTAssertFalse(vm.canSend)
        XCTAssertEqual(service.calls, 0)
        XCTAssertEqual(vm.credentialState, .webOnly)
    }

    @MainActor func testLogoutStopsStreamAndRejectsLateFrames() async throws {
        let credentials = ShoppingCredentialsFake()
        let service = ShoppingServiceFake()
        let config = try ShoppingConfiguration(gateway: URL(string: "https://shop.kuaishou.com")!, entrySource: "test-entry")
        let vm = ShoppingChatViewModel(credentials: credentials, configuration: config, service: service)
        vm.bindOwner("health-a")
        credentials.values = [HTTPCookie(properties: [.name: "token", .value: "fake", .domain: ".kuaishou.com", .path: "/"])!]
        await vm.refreshCredentials()
        let started = expectation(description: "chat started")
        service.onChat = { started.fulfill() }
        vm.draft = "只发送这句话"
        let sending = Task { await vm.send() }
        await fulfillment(of: [started], timeout: 2)
        XCTAssertEqual(service.lastContent, "只发送这句话")
        vm.bindOwner(nil)
        service.continuation?.yield(Data(#"{"result":1,"data":{"result":1,"data":{"commandType":"show_msg","commandData":{"msgItem":{"messageId":"old","sender":"ai","blocks":[{"type":"text","content":{"text":"旧账号响应"}}]}}}}}"#.utf8))
        service.continuation?.finish()
        await sending.value
        XCTAssertTrue(vm.transcript.messages.isEmpty)
        XCTAssertFalse(vm.isBusy)
        XCTAssertEqual(vm.credentialState, .notChecked)
        XCTAssertFalse(vm.canSend)
        XCTAssertGreaterThan(credentials.resets, 0)
    }

    @MainActor func testOwnerSwitchAndCredentialReplacementEraseDraftAndHistory() async throws {
        let credentials = ShoppingCredentialsFake()
        let vm = ShoppingChatViewModel(credentials: credentials)
        vm.bindOwner("a")
        vm.setDemoMode(true)
        vm.draft = "私人购物需求"
        await vm.send()
        vm.bindOwner("b")
        XCTAssertTrue(vm.transcript.messages.isEmpty)
        XCTAssertTrue(vm.draft.isEmpty)
        XCTAssertFalse(vm.isDemo)
        vm.bindOwner(nil)
        vm.setDemoMode(true)
        XCTAssertFalse(vm.isDemo, "Logged-out shell must not retain shopping state")
    }
}
