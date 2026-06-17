import Foundation
#if canImport(WatchConnectivity)
import WatchConnectivity
#endif

/// 腕上数据客户端。优先使用 Watch 本机 token 直连后端,不要求 iPhone App 前台接力;
/// WatchConnectivity 只负责 token/applicationContext 同步和旧 relay 兜底。
///
/// 消息协议(与 iPhone 侧 watch-bridge 约定):
///   - {"op":"summary"} → 回 {"ok":true,"data":<watch/summary JSON bytes(base64)>}
///   - {"op":"quick_record","path":..,"method":..,"query":..,"body":..} → 回 {"ok":bool,"data"?:base64,"error"?:String}
final class WatchConnectivityClient: NSObject {
    static let shared = WatchConnectivityClient()

    enum WCError: Error { case unreachable, badResponse, relayFailed(String), directFailed(String), missingWatchToken }

    private let direct: WatchDirectAPIClient
    private let credentials: WatchCredentialStore

    #if canImport(WatchConnectivity)
    private var session: WCSession? {
        WCSession.isSupported() ? WCSession.default : nil
    }
    #endif

    init(direct: WatchDirectAPIClient = .shared, credentials: WatchCredentialStore = .shared) {
        self.direct = direct
        self.credentials = credentials
        super.init()
        activate()
    }

    func activate() {
        #if canImport(WatchConnectivity)
        guard let s = session else { return }
        s.delegate = self
        s.activate()
        credentials.applyApplicationContext(s.receivedApplicationContext)
        #endif
    }

    /// 取今日摘要:返回 watch/summary 的原始 JSON data(交给 WatchSummary.decode)。
    func fetchSummary() async throws -> Data {
        var directError: Error?
        do {
            return try await direct.fetchSummary()
        } catch {
            directError = error
        }

        do {
            return try await fetchSummaryViaRelay()
        } catch {
            throw Self.preferredError(directError: directError, relayError: error)
        }
    }

    private func fetchSummaryViaRelay() async throws -> Data {
        let reply = try await send(["op": "summary"])
        // 中继失败时带回 iPhone 侧的真实原因(未登录 / HTTP 401 / 网络…),别吞成笼统 badResponse。
        guard let ok = reply["ok"] as? Bool, ok else {
            throw WCError.relayFailed((reply["error"] as? String) ?? "中继失败")
        }
        guard let b64 = reply["data"] as? String, let data = Data(base64Encoded: b64) else {
            throw WCError.badResponse
        }
        return data
    }

    /// 发打点请求(已由 QuickRecord 校验)。iPhone 中继到后端;草稿解析类请求会回原始 JSON data。
    func sendQuickRecord(_ req: QuickRecordRequest) async throws -> Data? {
        var directError: Error?
        do {
            return try await direct.sendQuickRecord(req)
        } catch {
            directError = error
        }

        do {
            return try await sendQuickRecordViaRelay(req)
        } catch {
            throw Self.preferredError(directError: directError, relayError: error)
        }
    }

    private func sendQuickRecordViaRelay(_ req: QuickRecordRequest) async throws -> Data? {
        let reply = try await send([
            "op": "quick_record",
            "path": req.path, "method": req.method,
            "query": req.query, "body": req.body,
        ])
        guard let ok = reply["ok"] as? Bool, ok else {
            throw WCError.relayFailed((reply["error"] as? String) ?? "中继失败")
        }
        if let b64 = reply["data"] as? String {
            guard let data = Data(base64Encoded: b64) else { throw WCError.badResponse }
            return data
        }
        return nil
    }

    /// 发埋点事件(经 iPhone 中继到 /client-events)。fire-and-forget:失败抛出由调用方决定是否吞。
    func sendEvent(name: String, meta: [String: String]) async throws {
        do {
            try await direct.sendEvent(name: name, meta: meta)
            return
        } catch {
            // 埋点不影响业务,但仍保留 relay 兜底。
        }
        let reply = try await send(["op": "event", "event_name": name, "meta": meta])
        guard let ok = reply["ok"] as? Bool, ok else {
            throw WCError.relayFailed((reply["error"] as? String) ?? "埋点中继失败")
        }
    }

    private static func preferredError(directError: Error?, relayError: Error) -> Error {
        if let relay = relayError as? WCError {
            switch relay {
            case .unreachable:
                return mappedDirectError(directError) ?? relay
            case .badResponse, .relayFailed, .directFailed, .missingWatchToken:
                return relay
            }
        }
        return mappedDirectError(directError) ?? relayError
    }

    private static func mappedDirectError(_ error: Error?) -> Error? {
        guard let direct = error as? WatchDirectAPIClient.DirectError else { return nil }
        switch direct {
        case .missingToken:
            return WCError.missingWatchToken
        case .httpStatus(let code):
            if code == 401 {
                return WCError.relayFailed("登录已过期,请在 iPhone 重新登录并同步 Watch")
            }
            return WCError.directFailed("服务器返回 HTTP \(code)")
        case .badResponse:
            return WCError.directFailed("服务器响应异常")
        case .requestBuildFailed:
            return WCError.directFailed("请求构造失败")
        }
    }

    private func send(_ message: [String: Any]) async throws -> [String: Any] {
        #if canImport(WatchConnectivity)
        guard let s = session, s.isReachable else { throw WCError.unreachable }
        return try await withCheckedThrowingContinuation { cont in
            s.sendMessage(message, replyHandler: { cont.resume(returning: $0) },
                          errorHandler: { cont.resume(throwing: $0) })
        }
        #else
        throw WCError.unreachable
        #endif
    }
}

#if canImport(WatchConnectivity)
extension WatchConnectivityClient: WCSessionDelegate {
    func session(_ s: WCSession, activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {
        credentials.applyApplicationContext(s.receivedApplicationContext)
    }

    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        credentials.applyApplicationContext(applicationContext)
    }

    #if os(iOS)
    func sessionDidBecomeInactive(_ s: WCSession) {}
    func sessionDidDeactivate(_ s: WCSession) {}
    #endif
}
#endif
