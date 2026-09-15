import AppKit
import HealthAgentMacCore
import Observation

/// Opens the existing consumer KRN page. Only an explicitly submitted shopping
/// question may be forwarded; no account, credentials, or health context.
@MainActor @Observable final class ShoppingAppLauncher {
    static let assistantURL = URL(string: "kwai://krn?bundleId=KwaishopCAIChatPageV2&componentName=KwaishopCAIChatPageV2&entrySrc=HOME_SHORTCUT")!
    static let appStoreURL = URL(string: "https://apps.apple.com/cn/app/id440948110")!

    private(set) var notice: String?
    private(set) var isOpening = false
    private let findApplication: () -> URL?
    private let open: (URL, URL) async -> Bool

    init(
        findApplication: @escaping () -> URL? = {
            NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.jiangjia.gif")
        },
        open: @escaping (URL, URL) async -> Bool = { url, application in
            await withCheckedContinuation { continuation in
                NSWorkspace.shared.open([url], withApplicationAt: application,
                                        configuration: NSWorkspace.OpenConfiguration()) { app, error in
                    continuation.resume(returning: app != nil && error == nil)
                }
            }
        }
    ) {
        self.findApplication = findApplication
        self.open = open
    }

    /// Only meaningful after this RN revision is distributed to the official host.
    func openLocalBridge(_ pairing: ShoppingBridgePairing) async -> Bool {
        guard !isOpening, let application = findApplication(),
              var parts = URLComponents(url: Self.assistantURL, resolvingAgainstBaseURL: false) else {
            notice = "无法打开快手桥接页，请确认已安装支持桥接的快手购物页面。"
            return false
        }
        parts.queryItems = (parts.queryItems ?? []) + [
            .init(name: "desktopBridgePort", value: String(pairing.port)),
            .init(name: "desktopBridgeToken", value: pairing.token),
            .init(name: "desktopBridgeCode", value: pairing.code)
        ]
        guard let url = parts.url else { notice = "无法准备本机配对。"; return false }
        isOpening = true
        defer { isOpening = false }
        let opened = await open(url, application)
        notice = opened ? "请在快手桥接页核对配对码并允许连接。如果仍是普通购物页，需要先分发支持桥接的页面版本。"
            : "未能打开快手桥接页，请检查客户端。"
        return opened
    }

    @discardableResult func openShoppingAssistant(question: String? = nil) async -> Bool {
        guard !isOpening else { return false }
        var url = Self.assistantURL
        if let question {
            let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { notice = "请先输入要发送到快手的问题。"; return false }
            guard text.utf8.count <= 2000,
                  text.unicodeScalars.allSatisfy({ !CharacterSet.controlCharacters.contains($0) || $0 == "\n" || $0 == "\r" || $0 == "\t" }) else {
                notice = "内容过长或包含不支持的字符，请精简后再发送到快手。"
                return false
            }
            do {
                let data = try JSONSerialization.data(withJSONObject: ["inputContent": text])
                guard let ext = String(data: data, encoding: .utf8),
                      var parts = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
                    notice = "无法准备购物问题，请重新输入。"
                    return false
                }
                parts.queryItems = (parts.queryItems ?? []) + [URLQueryItem(name: "sugText", value: text), URLQueryItem(name: "sugExtData", value: ext)]
                // A plus must remain literal even if an intermediate decoder uses form semantics.
                parts.percentEncodedQuery = parts.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
                guard let questionURL = parts.url else { notice = "无法准备购物问题，请重新输入。"; return false }
                url = questionURL
            } catch {
                notice = "无法准备购物问题，请重新输入。"
                return false
            }
        }
        guard let application = findApplication() else {
            notice = "请先从 App Store 安装快手，再打开购物助手。"
            return false
        }
        isOpening = true
        defer { isOpening = false }
        notice = nil
        let opened = await open(url, application)
        notice = opened
            ? (question == nil ? "已请求打开，请在快手窗口继续。是否登录和能否聊天，以快手页面为准。"
               : "已将问题交给快手，请在快手窗口查看提问和回复；未出现时请勿反复提交。")
            : "未能打开快手，请确认官方客户端已安装并可正常启动。"
        return opened
    }
}
