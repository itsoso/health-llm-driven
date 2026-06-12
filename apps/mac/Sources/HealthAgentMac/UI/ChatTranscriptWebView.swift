import AppKit
import HealthAgentMacCore
import SwiftUI
import WebKit

/// WKWebView-backed chat transcript (取代 SwiftUI 的 conversationSection / messageBubble /
/// MarkdownMessageText 渲染路径)。浏览器引擎做布局协商 → 根治 SwiftUI 在弹性 frame 嵌套里
/// 对流式富文本的指数级 sizeThatFits 卡死(8 轮地鼠的结构性终结)。
///
/// 安全配置(AGENTS.md 硬约束):
///  - `WKWebsiteDataStore.nonPersistent()` —— 不落任何数据到磁盘缓存。
///  - 禁文件访问:不用 `loadFileURL` 暴露目录;HTML 以字符串注入(baseURL = nil)。
///  - 禁导航跳转:navigationDelegate 拦截一切非初始加载;外链经 NSWorkspace 打开。
///  - 消息内容在 Core 侧 `ChatTranscriptHTML.escape` 转义后才进 DOM(防 XSS)。
@MainActor
struct ChatTranscriptWebView: NSViewRepresentable {
    let messages: [ChatTranscriptHTML.RenderedMessage]
    let fontScale: Double
    /// 复制回调:JS 端点复制按钮 → messageHandler → 这里拿 messageID 写 NSPasteboard。
    let onCopy: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onCopy: onCopy)
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let prefs = WKPreferences()
        prefs.javaScriptCanOpenWindowsAutomatically = false
        config.preferences = prefs

        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "copy")
        controller.add(context.coordinator, name: "ready")
        config.userContentController = controller

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.setValue(false, forKey: "drawsBackground") // 透明,露出 SwiftUI 背景渐变
        webView.allowsBackForwardNavigationGestures = false

        context.coordinator.webView = webView
        context.coordinator.loadShell()
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
        context.coordinator.onCopy = onCopy
        context.coordinator.apply(messages: messages, fontScale: fontScale)
    }

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var onCopy: (String) -> Void
        weak var webView: WKWebView?

        private var isReady = false
        private var hasLoadedShell = false
        private var pendingMessages: [ChatTranscriptHTML.RenderedMessage] = []
        private var pendingFontScale: Double = 1
        private var lastSyncedIDs: [String] = []
        private var lastSyncedFontScale: Double = -1

        init(onCopy: @escaping (String) -> Void) {
            self.onCopy = onCopy
        }

        func loadShell() {
            guard let webView else { return }
            guard let url = Bundle.main.url(forResource: "chat-transcript", withExtension: "html")
                ?? Bundle.module.url(forResource: "chat-transcript", withExtension: "html") else {
                // 资源缺失:加载一个最小占位(不假装成功 —— 仍渲染但显式标注)。
                webView.loadHTMLString(Self.fallbackShell, baseURL: nil)
                return
            }
            // 以字符串注入(baseURL=nil)而非 loadFileURL → 不向 WebView 暴露文件系统目录。
            if let html = try? String(contentsOf: url, encoding: .utf8) {
                webView.loadHTMLString(html, baseURL: nil)
            } else {
                webView.loadHTMLString(Self.fallbackShell, baseURL: nil)
            }
            hasLoadedShell = true
        }

        /// 增量同步:首帧 / 会话切换全量 setMessages;之后仅最后一条变化时 appendOrUpdateLast。
        func apply(messages: [ChatTranscriptHTML.RenderedMessage], fontScale: Double) {
            pendingMessages = messages
            pendingFontScale = fontScale
            guard isReady, let webView else { return }

            if fontScale != lastSyncedFontScale {
                lastSyncedFontScale = fontScale
                webView.evaluateJavaScript("window.chat.setFontScale(\(fontScale));", completionHandler: nil)
            }

            let ids = messages.map(\.id)
            let isAppendOrUpdateLast =
                !lastSyncedIDs.isEmpty &&
                ids.count >= lastSyncedIDs.count &&
                Array(ids.prefix(lastSyncedIDs.count - 1)) == Array(lastSyncedIDs.prefix(lastSyncedIDs.count - 1)) &&
                ids.count <= lastSyncedIDs.count + 1

            if isAppendOrUpdateLast, let last = messages.last {
                webView.evaluateJavaScript("window.chat.appendOrUpdateLast(\(last.jsonObject));", completionHandler: nil)
            } else {
                let json = ChatTranscriptHTML.messagesJSONArray(messages)
                webView.evaluateJavaScript("window.chat.setMessages(\(json));", completionHandler: nil)
            }
            lastSyncedIDs = ids
        }

        // MARK: WKScriptMessageHandler

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            switch message.name {
            case "ready":
                isReady = true
                lastSyncedIDs = []
                lastSyncedFontScale = -1
                apply(messages: pendingMessages, fontScale: pendingFontScale)
            case "copy":
                if let id = message.body as? String {
                    onCopy(id)
                }
            default:
                break
            }
        }

        // MARK: WKNavigationDelegate (禁导航跳转)
        //
        // ⚠️ 用 async 重载实现(返回 WKNavigationActionPolicy)而非 completionHandler 版本:
        // CI 的 Xcode 工具链常比本地旧,completionHandler 版的 `@escaping` 闭包在不同 SDK 下
        // actor 隔离标注不一致,会触发 "nearly matches optional requirement" 警告(本地 Swift 6.3
        // 实测)。async 重载签名跨版本稳定,且天然在 main actor 上 await。
        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction
        ) async -> WKNavigationActionPolicy {
            // 用户主动点链接:不在 WebView 内导航,仅把 http/https 交给系统浏览器。
            if navigationAction.navigationType == .linkActivated {
                if let url = navigationAction.request.url,
                   let scheme = url.scheme?.lowercased(),
                   scheme == "http" || scheme == "https" {
                    NSWorkspace.shared.open(url)
                }
                return .cancel
            }
            // 我们自己的 shell 注入(loadHTMLString,navigationType == .other)放行;
            // 任何其它来源(iframe / redirect / form 等)一律拦截。
            return navigationAction.navigationType == .other ? .allow : .cancel
        }

        private static let fallbackShell = """
        <!DOCTYPE html><html><body style="font-family:-apple-system;color:#888;padding:16px;">\
        <p>Chat transcript resource missing.</p></body></html>
        """
    }
}
