import XCTest
@testable import HealthAgentMacCore

@MainActor private final class BridgeCredentials: ShoppingCredentialSource {
    func cookies() async -> [HTTPCookie] { [] }
    func reset() {}
}

@MainActor final class ShoppingBridgeTests: XCTestCase {
    private func connect(_ pairing: ShoppingBridgePairing, token: String? = nil, origin: String? = nil) async throws -> URLSessionWebSocketTask {
        var request = URLRequest(url: URL(string: "ws://127.0.0.1:\(pairing.port)/shopping-bridge")!)
        request.timeoutInterval = 5
        if let origin { request.setValue(origin, forHTTPHeaderField: "Origin") }
        let socket = URLSession.shared.webSocketTask(with: request)
        socket.resume()
        try await socket.send(.string("{\"v\":1,\"type\":\"hello\",\"token\":\"\(token ?? pairing.token)\"}"))
        return socket
    }
    private func receive(_ socket: URLSessionWebSocketTask) async throws -> [String: Any] {
        let message = try await socket.receive()
        let data: Data
        switch message {
        case .string(let text): data = Data(text.utf8)
        case .data(let bytes): data = bytes
        @unknown default: throw ShoppingBridgeError.invalidFrame
        }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
    func testReplyRendersInViewModelAndAccountChangeClearsIt() async throws {
        let vm = ShoppingChatViewModel(credentials: BridgeCredentials())
        vm.bindOwner("synthetic-owner")
        let pairing = try await vm.startLocalBridge()
        defer { vm.disconnectLocalBridge() }
        let socket = try await connect(pairing)
        defer { socket.cancel(with: .goingAway, reason: nil) }
        _ = try await receive(socket)
        try await socket.send(.string("{\"v\":1,\"type\":\"ready\"}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"ping\"}"))
        _ = try await receive(socket)
        vm.draft = "synthetic cup"
        XCTAssertTrue(vm.canSend)
        XCTAssertFalse(vm.usesOfficialAppForSending)
        let task = Task { await vm.send() }
        let request = try await receive(socket)
        let id = try XCTUnwrap(request["id"] as? String)
        let messageID = try XCTUnwrap(request["messageId"] as? String)
        XCTAssertEqual(vm.transcript.messages.first?.messageId, messageID)
        let payload: [String: Any] = ["v": 1, "type": "chunk", "id": id, "command": [
            "commandType": "show_msg", "commandData": ["msgItem": ["messageId": "synthetic-ai", "sender": "ai", "blocks": [
                ["moduleId": "text", "type": "text", "content": ["text": "synthetic answer"]]
            ]]]
        ]]
        let bytes = try JSONSerialization.data(withJSONObject: payload)
        try await socket.send(.string(String(decoding: bytes, as: UTF8.self)))
        try await socket.send(.string("{\"v\":1,\"type\":\"stream_end\",\"id\":\"\(id)\"}"))
        await task.value
        XCTAssertEqual(vm.transcript.messages.last?.blocks.first?.text, "synthetic answer")
        XCTAssertTrue(vm.notice?.contains("尚未确认") ?? false)
        try await socket.send(.string("{\"v\":1,\"type\":\"error\",\"code\":\"auth_changed\"}"))
        do { _ = try await receive(socket); XCTFail("Identity must disconnect") } catch { }
        XCTAssertTrue(vm.transcript.messages.isEmpty)
        XCTAssertFalse(vm.localBridge.isReady)
    }

    func testPairingRequiresTokenAndExplicitReady() async throws {
        let bridge = ShoppingBridgeTransport()
        let pairing = try await bridge.start()
        defer { bridge.disconnect() }
        XCTAssertEqual(pairing.token.count, 64)
        XCTAssertEqual(pairing.code.count, 6)
        let socket = try await connect(pairing)
        defer { socket.cancel(with: .goingAway, reason: nil) }
        let paired = try await receive(socket)
        XCTAssertEqual(paired["type"] as? String, "paired")
        XCTAssertFalse(bridge.isReady)
        try await socket.send(.string("{\"v\":1,\"type\":\"ready\"}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"ping\"}"))
        _ = try await receive(socket)
        XCTAssertTrue(bridge.isReady)
    }
    func testRNLoopbackOriginIsAcceptedAndForeignBrowserOriginRejected() async throws {
        for allowed in [true, false] {
            let bridge = ShoppingBridgeTransport()
            let pairing = try await bridge.start()
            defer { bridge.disconnect() }
            do {
                let socket = try await connect(pairing, origin: allowed ? "http://127.0.0.1:\(pairing.port)" : "https://example.com")
                defer { socket.cancel(with: .goingAway, reason: nil) }
                _ = try await receive(socket)
                XCTAssertTrue(allowed, "Foreign website must not pair even with a token")
            } catch { XCTAssertFalse(allowed) }
        }
    }

    func testRePairInvalidatesOldCapability() async throws {
        let bridge = ShoppingBridgeTransport()
        let old = try await bridge.start()
        let new = try await bridge.start()
        defer { bridge.disconnect() }
        XCTAssertNotEqual(old.token, new.token)
        let socket = try await connect(new, token: old.token)
        defer { socket.cancel(with: .goingAway, reason: nil) }
        do { _ = try await receive(socket); XCTFail("Old token accepted") } catch { }
        XCTAssertFalse(bridge.isReady)
    }

    func testCancelledFramesAndErrorsCannotCompleteOrInterruptNewRequest() async throws {
        let bridge = ShoppingBridgeTransport()
        let pairing = try await bridge.start()
        defer { bridge.disconnect() }
        let socket = try await connect(pairing)
        defer { socket.cancel(with: .goingAway, reason: nil) }
        _ = try await receive(socket)
        try await socket.send(.string("{\"v\":1,\"type\":\"ready\"}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"ping\"}"))
        _ = try await receive(socket)
        let old = try bridge.chat(content: "old", messageID: "mac-00000000-0000-4000-a000-000000000003")
        let first = try await receive(socket)
        let oldID = try XCTUnwrap(first["id"] as? String)
        bridge.cancelRequest()
        _ = try await receive(socket) // cancellation delivered
        do { for try await _ in old {} ; XCTFail("Cancel cannot succeed") } catch { }
        let stream = try bridge.chat(content: "new", messageID: "mac-00000000-0000-4000-a000-000000000004")
        let request = try await receive(socket)
        let id = try XCTUnwrap(request["id"] as? String)
        try await socket.send(.string("{\"v\":1,\"type\":\"error\",\"code\":\"request_failed\",\"id\":\"\(oldID)\"}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"stream_end\",\"id\":\"\(oldID)\"}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"chunk\",\"id\":\"\(id)\",\"command\":{\"commandType\":\"show_msg\",\"commandData\":{}}}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"stream_end\",\"id\":\"\(id)\"}"))
        var count = 0
        for try await _ in stream { count += 1 }
        XCTAssertEqual(count, 1)
        XCTAssertTrue(bridge.isReady)
    }

    func testWrongTokenCannotPair() async throws {
        let bridge = ShoppingBridgeTransport()
        let pairing = try await bridge.start()
        defer { bridge.disconnect() }
        let socket = try await connect(pairing, token: String(repeating: "0", count: 64))
        defer { socket.cancel(with: .goingAway, reason: nil) }
        do { _ = try await receive(socket); XCTFail("Wrong token accepted") } catch { }
        XCTAssertFalse(bridge.isReady)
    }
    func testChatRequiresCommandAndCompletionReceipt() async throws {
        let bridge = ShoppingBridgeTransport()
        let pairing = try await bridge.start()
        defer { bridge.disconnect() }
        let socket = try await connect(pairing)
        defer { socket.cancel(with: .goingAway, reason: nil) }
        _ = try await receive(socket)
        try await socket.send(.string("{\"v\":1,\"type\":\"ready\"}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"ping\"}"))
        _ = try await receive(socket)
        let stream = try bridge.chat(content: "test cup", messageID: "mac-00000000-0000-4000-a000-000000000001")
        let request = try await receive(socket)
        let id = try XCTUnwrap(request["id"] as? String)
        XCTAssertEqual(request["content"] as? String, "test cup")
        try await socket.send(.string("{\"v\":1,\"type\":\"chunk\",\"id\":\"\(id)\",\"command\":{\"commandType\":\"show_msg\",\"commandData\":{}}}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"stream_end\",\"id\":\"\(id)\"}"))
        var count = 0
        for try await _ in stream { count += 1 }
        XCTAssertEqual(count, 1)
        let empty = try bridge.chat(content: "next", messageID: "mac-00000000-0000-4000-a000-000000000002")
        let next = try await receive(socket)
        let nextID = try XCTUnwrap(next["id"] as? String)
        try await socket.send(.string("{\"v\":1,\"type\":\"stream_end\",\"id\":\"\(nextID)\"}"))
        do { for try await _ in empty {} ; XCTFail("Empty completion accepted") }
        catch { XCTAssertEqual(error as? ShoppingBridgeError, .invalidFrame) }
    }
    func testDisconnectFailsPendingRequest() async throws {
        let bridge = ShoppingBridgeTransport()
        let pairing = try await bridge.start()
        let socket = try await connect(pairing)
        defer { socket.cancel(with: .goingAway, reason: nil); bridge.disconnect() }
        _ = try await receive(socket)
        try await socket.send(.string("{\"v\":1,\"type\":\"ready\"}"))
        try await socket.send(.string("{\"v\":1,\"type\":\"ping\"}"))
        _ = try await receive(socket)
        let stream = try bridge.chat(content: "test", messageID: "mac-00000000-0000-4000-a000-000000000001")
        _ = try await receive(socket)
        socket.cancel(with: .goingAway, reason: nil)
        do { for try await _ in stream {} ; XCTFail("EOF cannot complete") }
        catch { XCTAssertEqual(error as? ShoppingBridgeError, .disconnected) }
        XCTAssertFalse(bridge.isReady)
    }
}
