import Foundation
import Security
#if canImport(WatchConnectivity)
import WatchConnectivity
#endif

/// iPhone 侧 WatchConnectivity bridge(W3)。职责:
/// 1) 把登录 token 通过 applicationContext 同步到 Watch Keychain,让 Watch 可独立联网展示;
/// 2) 保留旧 relay 路径作为 token 未同步/直连失败时的兜底。token 与 Siri extension 共用。
///
/// 注册:App 启动时调 `WatchPhoneBridge.shared.activate()`(AppDelegate / Expo module 里接一行)。
/// 消息协议见 watch 侧 WatchConnectivityClient.swift。
@objc final class WatchPhoneBridge: NSObject {
    @objc static let shared = WatchPhoneBridge()

    private let appGroup = "group.life.executor.health"
    private let tokenKey = "siri_auth_token"          // 与 withIntentsExtension 的 SharedKeychain 一致
    private let apiBase = "https://health.executor.life/api/v1"
    private let watchTokenKey = "watch_auth_token"
    private let watchTokenDeletedKey = "watch_auth_token_deleted"
    private let watchAPIBaseKey = "watch_api_base"
    private let tokenChangedNotification = Notification.Name("RevaSharedAuthTokenChanged")
    private let allowedQuickRecordRoutes: [String: Set<String>] = [
        "/water/records/quick": ["POST"],
        "/daily-health/exercise": ["POST"],
        "/diet/voice/parse": ["POST"],
        "/diet/records": ["POST"],
        "/client-events": ["POST"],              // watch action 埋点中继(shown/completed/snoozed/skipped)
        "/watch/symptoms": ["POST"],             // 王牌⑤ 腕上语音记症状 → SafetyGuardian 裁决
    ]
    // 动态放行:/watch/actions/{action_id}/{complete|skip|snooze} 的 POST。前缀+后缀不够——
    // 中段必须是「单层合法 action_id」,否则 `/watch/actions/../../admin/x/complete`
    // 也同时满足 prefix+suffix(URLComponents 不折叠 ..)。见下 isWatchActionMutation。
    private let watchActionPrefix = "/watch/actions/"
    private let watchActionSuffixes = ["/complete", "/skip", "/snooze"]
    // 与后端 _ACTION_ID_RE 同形: agenda-{object_type}-{object_id}。NSString 锚定(^…$),
    // 中段不含 `/`,故天然单层;`.` 仅出现在 \d 之外即拒,`..` 无从构造。
    private let actionIDPattern = "^agenda-[a-z_]+-[0-9]+$"

    /// /watch/actions/{action_id}/{complete|skip} 的 POST 才放行,且 {action_id} 须是合法单层 id。
    private func isWatchActionMutation(path: String, method: String) -> Bool {
        guard method == "POST" else { return false }
        // 纵深防御:任何 .. 直接拒(即便正则已挡,留显式断言便于 review)。
        guard !path.contains("..") else { return false }
        guard path.hasPrefix(watchActionPrefix),
              let suffix = watchActionSuffixes.first(where: { path.hasSuffix($0) }) else { return false }
        let mid = String(path.dropFirst(watchActionPrefix.count).dropLast(suffix.count))
        // mid 必须就是一个 action_id:不含 `/`(单层)且匹配后端同形正则。
        guard !mid.contains("/") else { return false }
        return mid.range(of: actionIDPattern, options: .regularExpression) != nil
    }

    /// 是否放行该 (path, method)。先查精确白名单,再查受限动态规则。其余一律拒。
    private func isRouteAllowed(path: String, method: String) -> Bool {
        if allowedQuickRecordRoutes[path]?.contains(method) == true { return true }
        if isWatchActionMutation(path: path, method: method) { return true }
        return false
    }

    @objc func activate() {
        #if canImport(WatchConnectivity)
        guard WCSession.isSupported() else { return }
        NotificationCenter.default.removeObserver(self, name: tokenChangedNotification, object: nil)
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(syncCredentialsToWatch),
            name: tokenChangedNotification,
            object: nil
        )
        let s = WCSession.default
        s.delegate = self
        s.activate()
        syncCredentialsToWatch()
        #endif
    }

    private func token() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "life.executor.health.shared",
            kSecAttrAccount as String: tokenKey,
            kSecAttrAccessGroup as String: appGroup,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// One-way credential seed. Watch 持 token 后可直接 GET /watch/summary,不再要求 iPhone App 前台接力。
    @objc func syncCredentialsToWatch() {
        #if canImport(WatchConnectivity)
        guard WCSession.isSupported() else { return }
        let s = WCSession.default
        guard s.activationState == .activated || s.activationState == .inactive else { return }
        var context: [String: Any] = [watchAPIBaseKey: apiBase]
        if let token = token(), !token.isEmpty {
            context[watchTokenKey] = token
            context[watchTokenDeletedKey] = false
        } else {
            context[watchTokenDeletedKey] = true
        }
        try? s.updateApplicationContext(context)
        #endif
    }

    /// 把 watch 的请求转成后端调用。reply 必形如 {ok:Bool, data?:base64, error?:String}。
    fileprivate func handle(_ message: [String: Any], reply: @escaping ([String: Any]) -> Void) {
        syncCredentialsToWatch()
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
            guard isRouteAllowed(path: path, method: method) else {
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
        case "event":
            // watch action 埋点中继。body 形如 {event_name, meta:{action_id,kind,priority_tier}}。
            // 走固定 /client-events,白名单仍校验(防 op 绕过)。失败不阻塞 UI(fire-and-forget)。
            let path = "/client-events"
            guard isRouteAllowed(path: path, method: "POST") else {
                reply(["ok": false, "error": "不允许的腕上操作"]); return
            }
            guard let eventName = message["event_name"] as? String, !eventName.isEmpty else {
                reply(["ok": false, "error": "缺少 event_name"]); return
            }
            let meta = message["meta"] as? [String: String] ?? [:]
            var envelope: [String: Any] = ["event_name": eventName]
            if !meta.isEmpty { envelope["meta"] = meta }
            requestJSON(path: path, method: "POST", jsonBody: envelope, token: token) { _, err in
                if err == nil {
                    reply(["ok": true])
                } else {
                    reply(["ok": false, "error": err ?? "请求失败"])
                }
            }
        default:
            reply(["ok": false, "error": "未知 op"])
        }
    }

    /// 发带任意 JSON object body 的请求(埋点 envelope 含嵌套 meta,无法走 [String:String] 通道)。
    private func requestJSON(
        path: String, method: String, jsonBody: [String: Any],
        token: String, completion: @escaping (Data?, String?) -> Void
    ) {
        guard let url = URL(string: apiBase + path) else { completion(nil, "URL 构造失败"); return }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: jsonBody)
        URLSession.shared.dataTask(with: req) { data, resp, error in
            if let error = error { completion(nil, error.localizedDescription); return }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard (200..<300).contains(code) else { completion(nil, "HTTP \(code)"); return }
            completion(data ?? Data(), nil)
        }.resume()
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
    func session(_ s: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        syncCredentialsToWatch()
    }
    func sessionDidBecomeInactive(_ s: WCSession) {}
    func sessionDidDeactivate(_ s: WCSession) { s.activate() }

    func sessionReachabilityDidChange(_ session: WCSession) {
        syncCredentialsToWatch()
    }

    func session(_ s: WCSession, didReceiveMessage message: [String: Any],
                 replyHandler: @escaping ([String: Any]) -> Void) {
        handle(message, reply: replyHandler)
    }
}
#endif
