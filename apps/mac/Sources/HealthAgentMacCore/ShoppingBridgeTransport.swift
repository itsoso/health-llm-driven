import Foundation
import Network
import Observation
import Security

/// An ephemeral pairing capability, never an account credential. Do not log URLs containing it.
public struct ShoppingBridgePairing: Sendable {
    fileprivate let generation: UUID
    public let port: UInt16
    public let token: String
    public let code: String
}

public enum ShoppingBridgeError: Error, LocalizedError, Equatable {
    case unavailable, disconnected, invalidFrame, timeout, requestFailed, authChanged
    public var errorDescription: String? {
        switch self {
        case .unavailable: "本机连接尚未就绪，请先在快手桥接页确认连接。"
        case .disconnected: "与快手的本机连接已断开；未确认回复完成，请重新连接。"
        case .invalidFrame: "快手桥接数据无效或超出限制，连接已停止。"
        case .timeout: "等待快手连接或回复超时，请重新连接。"
        case .authChanged: "快手账号已变化，本机购物内容已清除，请重新配对。"
        case .requestFailed: "快手未完成请求；请在快手检查账号和网络后重新连接。"
        }
    }
}

/// Loopback only, one explicit pairing, one outstanding shopping request. Nothing is persisted.
@MainActor @Observable public final class ShoppingBridgeTransport {
    public private(set) var isReady = false
    public private(set) var isActive = false
    public private(set) var pairingCode: String?
    public private(set) var notice: String?
    public var onAccountChanged: (@MainActor () -> Void)?
    private var listener: NWListener?
    private var peer: NWConnection?
    private var epoch = UUID()
    private var secret: String?
    private var authenticated = false
    private var startContinuation: CheckedContinuation<ShoppingBridgePairing, Error>?
    private var pairing: ShoppingBridgePairing?
    private var connectionDeadline: Task<Void, Never>?
    private var heartbeat: Task<Void, Never>?
    private var requestDeadline: Task<Void, Never>?
    private var lastSeen = ContinuousClock.now
    private var requestID: String?
    private var continuation: AsyncThrowingStream<Data, Error>.Continuation?
    private var responseBytes = 0
    private static let maxFrame = 256 * 1024

    public init() {}

    public func start() async throws -> ShoppingBridgePairing {
        disconnect()
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
            throw ShoppingBridgeError.unavailable
        }
        let token = bytes.map { String(format: "%02x", $0) }.joined()
        let code = String(format: "%06d", Int.random(in: 0...999999))
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
        let websocket = NWProtocolWebSocket.Options(.version13)
        websocket.autoReplyPing = true
        websocket.maximumMessageSize = Self.maxFrame
        // RN iOS supplies a loopback Origin; browsers on unrelated pages must be rejected.
        websocket.setClientRequestHandler(.main) { _, headers in
            let origins = headers.filter { $0.name.lowercased() == "origin" }.map(\.value)
            let host = headers.first { $0.name.lowercased() == "host" }?.value ?? ""
            let localHost = host.hasPrefix("127.0.0.1:") && UInt16(host.dropFirst(10)) != nil
            let allowed = origins.isEmpty || (origins.count == 1 && localHost && origins[0] == "http://" + host)
            return .init(status: allowed ? .accept : .reject, subprotocol: nil)
        }
        parameters.defaultProtocolStack.applicationProtocols.insert(websocket, at: 0)
        let server = try NWListener(using: parameters)
        listener = server
        secret = token
        pairingCode = code
        isActive = true
        notice = "请在支持桥接的快手页面核对配对码并允许连接。"
        let stamp = epoch
        server.newConnectionHandler = { [weak self] connection in
            Task { @MainActor in self?.accept(connection, epoch: stamp) }
        }
        server.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                guard let self, self.epoch == stamp else { return }
                switch state {
                case .ready:
                    guard let port = self.listener?.port else { self.fail(.unavailable); return }
                    let result = ShoppingBridgePairing(generation: stamp, port: port.rawValue, token: token, code: code)
                    self.pairing = result
                    self.startContinuation?.resume(returning: result)
                    self.startContinuation = nil
                case .failed: self.fail(.unavailable)
                default: break
                }
            }
        }
        connectionDeadline = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(120)) } catch { return }
            guard let self, self.epoch == stamp, !self.isReady else { return }
            self.fail(.timeout)
        }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                startContinuation = continuation
                server.start(queue: .main)
            }
        } onCancel: {
            Task { @MainActor [weak self] in
                guard self?.epoch == stamp else { return }
                self?.disconnect()
            }
        }
    }

    public func isCurrent(_ pairing: ShoppingBridgePairing) -> Bool { isActive && pairing.generation == epoch }

    public func disconnect() { close(error: .disconnected, message: nil) }

    private func fail(_ error: ShoppingBridgeError) { close(error: error, message: error.localizedDescription) }

    private func close(error: ShoppingBridgeError, message: String?) {
        epoch = UUID()
        isReady = false; isActive = false; pairingCode = nil
        secret = nil; pairing = nil; authenticated = false
        connectionDeadline?.cancel(); connectionDeadline = nil
        heartbeat?.cancel(); heartbeat = nil
        requestDeadline?.cancel(); requestDeadline = nil
        let pending = continuation; continuation = nil; requestID = nil
        pending?.finish(throwing: error)
        startContinuation?.resume(throwing: error); startContinuation = nil
        peer?.cancel(); peer = nil
        listener?.stateUpdateHandler = nil; listener?.newConnectionHandler = nil
        listener?.cancel(); listener = nil
        notice = message
    }

    private func accept(_ connection: NWConnection, epoch stamp: UUID) {
        guard epoch == stamp, peer == nil, !authenticated else { connection.cancel(); return }
        peer = connection
        connection.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                guard let self, self.epoch == stamp, self.peer === connection else { return }
                switch state {
                case .failed, .cancelled: self.fail(.disconnected)
                default: break
                }
            }
        }
        connection.start(queue: .main)
        receive(connection, epoch: stamp)
        Task { [weak self] in
            do { try await Task.sleep(for: .seconds(5)) } catch { return }
            guard let self, self.epoch == stamp, !self.authenticated else { return }
            self.fail(.timeout)
        }
    }

    private func receive(_ connection: NWConnection, epoch stamp: UUID) {
        connection.receiveMessage { [weak self] data, context, complete, error in
            let opcode = (context?.protocolMetadata(definition: NWProtocolWebSocket.definition) as? NWProtocolWebSocket.Metadata)?.opcode
            Task { @MainActor in
                guard let self, self.epoch == stamp, self.peer === connection else { return }
                if let failure = Self.incomingFrameError(data: data, opcode: opcode, complete: complete,
                                                         transportFailed: error != nil) {
                    self.fail(failure); return
                }
                if opcode == .ping || opcode == .pong { self.receive(connection, epoch: stamp); return }
                guard let data else { self.fail(.invalidFrame); return }
                self.handle(data)
                if self.epoch == stamp { self.receive(connection, epoch: stamp) }
            }
        }
    }

    /// Classifies Network.framework callbacks before parsing application data.
    static func incomingFrameError(data: Data?, opcode: NWProtocolWebSocket.Opcode?, complete: Bool,
                                   transportFailed: Bool) -> ShoppingBridgeError? {
        if transportFailed || opcode == .close { return .disconnected }
        // Depending on OS callback ordering, a peer shutdown can arrive as an
        // empty transport EOF before the WebSocket close/error callback. There
        // is no application frame to validate; never report it as malformed data.
        if opcode == nil, data?.isEmpty != false { return .disconnected }
        if opcode == .ping || opcode == .pong { return nil }
        guard complete, opcode == .text, let data, data.count <= maxFrame else { return .invalidFrame }
        return nil
    }

    private func handle(_ data: Data) {
        guard let frame = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let version = frame["v"] as? NSNumber, CFGetTypeID(version) != CFBooleanGetTypeID(), version == 1,
              let type = frame["type"] as? String else { fail(.invalidFrame); return }
        if !authenticated {
            guard type == "hello", let supplied = frame["token"] as? String, supplied == secret else {
                fail(.invalidFrame); return
            }
            secret = nil; pairing = nil; authenticated = true
            lastSeen = .now
            send(["v": 1, "type": "paired"])
            let stamp = epoch
            heartbeat = Task { [weak self] in
                while !Task.isCancelled {
                    do { try await Task.sleep(for: .seconds(5)) } catch { return }
                    guard let self, self.epoch == stamp else { return }
                    if self.lastSeen.duration(to: .now) > .seconds(20) { self.fail(.timeout); return }
                }
            }
            return
        }
        lastSeen = .now
        if type == "ping" { send(["v": 1, "type": "pong"]); return }
        if type == "ready", !isReady {
            isReady = true; pairingCode = nil; connectionDeadline?.cancel(); connectionDeadline = nil
            notice = "本机快手已连接，新问题的回复将在此显示。"
            return
        }
        if type == "error" {
            if frame["code"] as? String == "auth_changed" {
                fail(.authChanged)
                onAccountChanged?()
            } else {
                if let id = frame["id"] as? String, id != requestID { return }
                fail(.requestFailed)
            }
            return
        }
        guard isReady, let id = frame["id"] as? String else { fail(.invalidFrame); return }
        // Delayed callbacks for a cancelled request can never enter a new request.
        guard id == requestID else { return }
        if type == "chunk", let command = frame["command"] as? [String: Any],
           command["commandType"] is String,
           let bytes = try? JSONSerialization.data(withJSONObject: command) {
            responseBytes += bytes.count
            guard responseBytes <= 32 * 1024 * 1024 else { fail(.invalidFrame); return }
            if case .dropped = continuation?.yield(bytes) { fail(.invalidFrame) }
        } else if type == "stream_end", responseBytes > 0 {
            requestID = nil; requestDeadline?.cancel(); requestDeadline = nil
            let pending = continuation; continuation = nil; pending?.finish()
        } else { fail(.invalidFrame) }
    }

    public func chat(content: String, messageID: String) throws -> AsyncThrowingStream<Data, Error> {
        guard isReady, requestID == nil else { throw ShoppingBridgeError.unavailable }
        guard !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              content.utf8.count <= 16 * 1024, messageID.hasPrefix("mac-"),
              messageID.count == 40, UUID(uuidString: String(messageID.dropFirst(4))) != nil else { throw ShoppingBridgeError.invalidFrame }
        let id = UUID().uuidString
        requestID = id; responseBytes = 0
        let pair = AsyncThrowingStream<Data, Error>.makeStream(bufferingPolicy: .bufferingOldest(256))
        continuation = pair.continuation
        pair.continuation.onTermination = { [weak self] _ in
            Task { @MainActor in if self?.requestID == id { self?.cancelRequest() } }
        }
        send(["v": 1, "type": "request", "id": id, "op": "chat", "content": content, "messageId": messageID])
        requestDeadline = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(150)) } catch { return }
            guard let self, self.requestID == id else { return }
            self.fail(.timeout)
        }
        return pair.stream
    }

    public func cancelRequest() {
        guard let id = requestID else { return }
        requestID = nil; requestDeadline?.cancel(); requestDeadline = nil
        let pending = continuation; continuation = nil
        send(["v": 1, "type": "cancel", "id": id])
        pending?.finish(throwing: CancellationError())
    }

    private func send(_ object: [String: Any]) {
        guard let peer, let bytes = try? JSONSerialization.data(withJSONObject: object) else { fail(.invalidFrame); return }
        let stamp = epoch
        let context = NWConnection.ContentContext(identifier: "shopping", metadata: [NWProtocolWebSocket.Metadata(opcode: .text)])
        peer.send(content: bytes, contentContext: context, isComplete: true, completion: .contentProcessed { [weak self] error in
            guard error != nil else { return }
            Task { @MainActor in if self?.epoch == stamp { self?.fail(.disconnected) } }
        })
    }
}
