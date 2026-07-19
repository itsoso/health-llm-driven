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
    /// 动态卡片动作回调:JS 拦截安全内部 route.open → 上层解释 route。
    let onRouteOpen: (String) -> Void
    /// AIGC 确认卡只传 opaque confirmation ID, never prompt/source data.
    let onAIGCConfirm: (String) -> Void
    /// 饮食卡只传服务端已签发的 action ID，完整记录仍绑定在服务端草稿上。
    let onDietDraftConfirm: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(
            onCopy: onCopy,
            onRouteOpen: onRouteOpen,
            onAIGCConfirm: onAIGCConfirm,
            onDietDraftConfirm: onDietDraftConfirm
        )
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let prefs = WKPreferences()
        prefs.javaScriptCanOpenWindowsAutomatically = false
        config.preferences = prefs

        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "copy")
        controller.add(context.coordinator, name: "routeOpen")
        controller.add(context.coordinator, name: "aigcConfirm")
        controller.add(context.coordinator, name: "dietDraftConfirm")
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
        context.coordinator.onRouteOpen = onRouteOpen
        context.coordinator.onAIGCConfirm = onAIGCConfirm
        context.coordinator.onDietDraftConfirm = onDietDraftConfirm
        context.coordinator.apply(messages: messages, fontScale: fontScale)
    }

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var onCopy: (String) -> Void
        var onRouteOpen: (String) -> Void
        var onAIGCConfirm: (String) -> Void
        var onDietDraftConfirm: (String) -> Void
        weak var webView: WKWebView?

        private var isReady = false
        private var hasLoadedShell = false
        private var pendingMessages: [ChatTranscriptHTML.RenderedMessage] = []
        private var pendingFontScale: Double = 1
        private var lastSyncedIDs: [String] = []
        private var lastSyncedFontScale: Double = -1
        // 已同步进 DOM 的整组消息;用于「内容未变就别重推」的闸(见 apply)。
        private var lastSyncedMessages: [ChatTranscriptHTML.RenderedMessage] = []

        init(
            onCopy: @escaping (String) -> Void,
            onRouteOpen: @escaping (String) -> Void,
            onAIGCConfirm: @escaping (String) -> Void,
            onDietDraftConfirm: @escaping (String) -> Void
        ) {
            self.onCopy = onCopy
            self.onRouteOpen = onRouteOpen
            self.onAIGCConfirm = onAIGCConfirm
            self.onDietDraftConfirm = onDietDraftConfirm
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

            // 内容未变就别重推:打字只改 composer 的 draft → 父 body 重算 → updateNSView 被白调,
            // 没这道闸的话每次按键都会 evaluateJavaScript 重发最后一条(含富文本)→ 输入框卡顿。
            // RenderedMessage 是 Equatable,流式时最后一条内容会变 → 不命中 → 正常增量推。
            if messages == lastSyncedMessages {
                return
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
            lastSyncedMessages = messages
        }

        // MARK: WKScriptMessageHandler

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            switch message.name {
            case "ready":
                isReady = true
                lastSyncedIDs = []
                lastSyncedFontScale = -1
                lastSyncedMessages = []
                apply(messages: pendingMessages, fontScale: pendingFontScale)
            case "copy":
                if let id = message.body as? String {
                    onCopy(id)
                }
            case "routeOpen":
                if let route = message.body as? String {
                    onRouteOpen(route)
                }
            case "aigcConfirm":
                if let confirmationID = message.body as? String {
                    onAIGCConfirm(confirmationID)
                }
            case "dietDraftConfirm":
                if let actionID = message.body as? String {
                    onDietDraftConfirm(actionID)
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

// MARK: - Latency waterfall preview fixtures
//
// The Mac app points at the production backend, which isn't yet redeployed with
// the perf contract — so there's no live perf to eyeball. These fixtures drive the
// real WebView render path (`metaFooterHTML` → HTML/CSS in chat-transcript.html)
// so the waterfall can be inspected in the SwiftUI canvas offline.

/// A short assistant reply carrying a representative `perf` (fast path, no tools):
/// total 4.2s dominated by KB retrieval (1.4s) + system prompt (0.9s), then a
/// 0.7s first-token wait and 0.9s generation. Proves gray/amber/green bands.
private func previewFastPathMessage() -> ChatTranscriptHTML.RenderedMessage {
    let perf = MessagePerf(
        totalMs: 4200, preLLMMs: 2600,
        preLLMStages: .init(
            convMs: 40, openerMs: 20, systemPromptMs: 900,
            kbMs: 1400, inspectMs: 120, historyMs: 80, visionMs: 40
        ),
        llmTTFTMs: 3300, llmFullMs: 1500,
        rounds: [.init(llmGenMs: 1500, toolExecMs: 0, tools: [])],
        orchestratorToolMs: nil
    )
    let footer = ChatTranscriptHTML.metaFooterHTML(
        model: "gpt-5.5", answerModel: "gpt-5.5",
        elapsedMs: 4200, llmRounds: 1,
        sourcesUsed: ["Garmin", "系统知识库"], toolsUsed: [],
        perf: perf
    )
    return ChatTranscriptHTML.RenderedMessage(
        id: "preview-fast",
        role: "assistant",
        bodyHTML: "<p>你的 HRV 最近 7 天中位数 62ms，处于个人基线正常带；今天恢复度偏好中等强度训练。</p>",
        isStreaming: false, showCopy: true, footerHTML: footer
    )
}

/// A reply that went through the orchestrator subtree: a 38s "silent" specialist
/// fan-out dwarfs everything else (total 45s). Proves the red orchestrator band
/// plus a blue tool-exec band and a per-round tool name in the expanded detail.
private func previewOrchestratorMessage() -> ChatTranscriptHTML.RenderedMessage {
    let perf = MessagePerf(
        totalMs: 45000, preLLMMs: 2000,
        preLLMStages: .init(systemPromptMs: 700, kbMs: 800, inspectMs: 500),
        llmTTFTMs: 6000, llmFullMs: 1000,
        rounds: [.init(llmGenMs: 1000, toolExecMs: 3000, tools: ["twin_lookup", "safety_scan"])],
        orchestratorToolMs: 38000
    )
    let footer = ChatTranscriptHTML.metaFooterHTML(
        model: "claude-opus-4.7", answerModel: "claude-opus-4.7",
        toolModels: ["gpt-5.5"], elapsedMs: 45000, llmRounds: 1,
        sourcesUsed: ["Garmin", "化验", "基因"], toolsUsed: ["health_query"],
        perf: perf
    )
    return ChatTranscriptHTML.RenderedMessage(
        id: "preview-orch",
        role: "assistant",
        bodyHTML: "<p>综合恢复、代谢与安全专家的分析：本周训练负荷偏高（ACWR 1.4），建议插入一天低强度恢复日。</p>",
        isStreaming: false, showCopy: true, footerHTML: footer
    )
}

#Preview("延迟瀑布图 · 快路径 + 编排子树") {
    ChatTranscriptWebView(
        messages: [
            ChatTranscriptHTML.RenderedMessage(
                id: "preview-user",
                role: "user",
                bodyHTML: "<p class=\"streaming-text\">我今天恢复得怎么样？</p>",
                isStreaming: false, showCopy: false
            ),
            previewFastPathMessage(),
            previewOrchestratorMessage()
        ],
        fontScale: 1.0,
        onCopy: { _ in },
        onRouteOpen: { _ in },
        onAIGCConfirm: { _ in },
        onDietDraftConfirm: { _ in }
    )
    .frame(width: 560, height: 520)
}
