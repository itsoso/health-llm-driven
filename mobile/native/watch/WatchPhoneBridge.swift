import Foundation
#if canImport(WatchConnectivity)
import WatchConnectivity
#endif

/// iPhone 侧 WatchConnectivity 中继(W3)。watch 不持 token、不直接联网;iPhone 收 WC 消息 →
/// 用 App Group 里的 token 调后端 → 回执给手腕。token 与 Siri extension 共用(同 App Group / key)。
///
/// 注册:App 启动时调 `WatchPhoneBridge.shared.activate()`(AppDelegate / Expo module 里接一行)。
/// 消息协议见 watch 侧 WatchConnectivityClient.swift。
@objc final class WatchPhoneBridge: NSObject {
    @objc static let shared = WatchPhoneBridge()

    private let appGroup = "group.life.executor.health"
    private let tokenKey = "siri_auth_token"          // 与 withIntentsExtension 的 SharedKeychain 一致
    private let apiBase = "https://health.executor.life/api/v1"
    private let allowedQuickRecordRoutes: [String: Set<String>] = [
        "/water/records/quick": ["POST"],
        "/daily-health/exercise": ["POST"],
        "/diet/voice/parse": ["POST"],
        "/diet/records": ["POST"],
    ]

    @objc func activate() {
        #if canImport(WatchConnectivity)
        guard WCSession.isSupported() else { return }
        let s = WCSession.default
        s.delegate = self
        s.activate()
        #endif
    }

    private func token() -> String? {
        UserDefaults(suiteName: appGroup)?.string(forKey: tokenKey)
    }

    /// 把 watch 的请求转成后端调用。reply 必形如 {ok:Bool, data?:base64, error?:String}。
    fileprivate func handle(_ message: [String: Any], reply: @escaping ([String: Any]) -> Void) {
        guard let token = token() else {
            reply(["ok": false, "error": "未登录(iPhone 无 token)"]); return
        }
        let op = message["op"] as? String
        switch op {
        case "summary":
            request(path: "/watch/summary", method: "GET", query: [:], body: [:], token: token) { data, err in
                if let data = data {
                    reply(["ok": true, "data": data.base64EncodedString()])
                } else {
                    reply(["ok": false, "error": err ?? "请求失败"])
                }
            }
        case "quick_record":
            let path = message["path"] as? String ?? ""
            let method = (message["method"] as? String ?? "POST").uppercased()
            let query = message["query"] as? [String: String] ?? [:]
            let body = message["body"] as? [String: String] ?? [:]
            guard allowedQuickRecordRoutes[path]?.contains(method) == true else {
                reply(["ok": false, "error": "不允许的腕上操作"]); return
            }
            request(path: path, method: method, query: query, body: body, token: token) { data, err in
                if let data = data {
                    var payload: [String: Any] = ["ok": true]
                    if !data.isEmpty {
                        payload["data"] = data.base64EncodedString()
                    }
                    reply(payload)
                } else {
                    reply(["ok": false, "error": err ?? "请求失败"])
                }
            }
        default:
            reply(["ok": false, "error": "未知 op"])
        }
    }

    private func request(
        path: String, method: String, query: [String: String], body: [String: String],
        token: String, completion: @escaping (Data?, String?) -> Void
    ) {
        var comps = URLComponents(string: apiBase + path)
        if !query.isEmpty {
            comps?.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = comps?.url else { completion(nil, "URL 构造失败"); return }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if !body.isEmpty {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        URLSession.shared.dataTask(with: req) { data, resp, error in
            if let error = error { completion(nil, error.localizedDescription); return }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard (200..<300).contains(code) else { completion(nil, "HTTP \(code)"); return }
            completion(data ?? Data(), nil)
        }.resume()
    }
}

#if canImport(WatchConnectivity)
extension WatchPhoneBridge: WCSessionDelegate {
    func session(_ s: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {}
    func sessionDidBecomeInactive(_ s: WCSession) {}
    func sessionDidDeactivate(_ s: WCSession) { s.activate() }

    func session(_ s: WCSession, didReceiveMessage message: [String: Any],
                 replyHandler: @escaping ([String: Any]) -> Void) {
        handle(message, reply: replyHandler)
    }
}
#endif
