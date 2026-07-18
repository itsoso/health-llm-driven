import AppKit
import HealthAgentMacCore
import ServiceManagement
import SwiftUI
import UniformTypeIdentifiers

struct AgentChatView: View {
    @Bindable var viewModel: AgentChatViewModel
    var navigation: AppNavigationState?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @AppStorage(AppFontScale.defaultsKey) private var appFontScaleLevel = AppFontScale.defaultLevel
    @State private var draft = ""
    // Default model = Qwen3.7 Max, persisted across launches (also remembers the
    // user's later choice). "auto" / "default3" / "manual"; when manual, the
    // chosen model id is persistedModelID.
    @AppStorage("agent.model.strategy") private var modelStrategy = "manual"
    @AppStorage("agent.model.id") private var persistedModelID = "qwen3.7-max"
    @State private var editorFocusToken = 0
    @State private var isAttachImporterPresented = false
    @State private var contextBundleName = ""
    @State private var selectedToolActivity: AgentToolActivity?
    @State private var historyPage = 0
    @State private var composerTextHeight: CGFloat = 0

    private static let historyPageSize = 6
    // ChatGPT-style: start at ~1 line, grow with content, then scroll past a cap.
    private static let composerMinHeight: CGFloat = 38
    private static let composerMaxHeight: CGFloat = 260

    private var composerEditorHeight: CGFloat {
        min(max(composerTextHeight, Self.composerMinHeight), Self.composerMaxHeight)
    }

    private let modelOptions = AgentModelCatalog.defaultOptions

    var body: some View {
        VStack(spacing: 12) {
            header

            // ⚠️ 结构性防卡死(第 7 轮根因 · sample 实锤):这里曾用 ViewThatFits(in:.horizontal)。
            // ViewThatFits 会把**两个候选(宽屏双列 / 窄屏单列)各自的完整消息列表**在多个
            // 建议尺寸下反复测量;滚动/重布局时整张列表被重测 → 指数级 sizeThatFits(100% CPU,
            // 热点栈纯 SwiftUICore 无 app 符号、beginTransaction 极少 = 单次不收敛布局 pass)。
            // #132(内容定宽)、#133(单 Text + 断 GeometryReader 环)都没碰它,所以滚动仍卡。
            // 改为 GeometryReader + 阈值的确定性 if/else:每次只构建一个分支,容器宽=窗口宽稳定,
            // 探测消失。阈值 920 ≈ chatColumn 560 + context 340 + spacing/padding。
            GeometryReader { geo in
                // ⚠️ 第 8 轮根治:**整棵聊天子树根部钉死宽度**。此前 chatColumn 是
                // maxWidth:.infinity(弹性),HStack 在它与 340 侧栏之间反复分配探测,
                // 35 层弹性 frame 嵌套放大成单次 ~1s 不收敛布局 pass(sample:6224 次
                // sizeThatFits / beginTransaction 仅 7,叶子=composer NSTextView)。
                // 每修一个叶子触发器换下一个继续爆 —— 唯有根部定宽,全树确定,探测消失。
                Group {
                    if geo.size.width >= 920 {
                        // Wide: 左聊天列(消息滚动、composer 钉底),右上下文面板。
                        HStack(alignment: .top, spacing: 16) {
                            chatColumn
                                .frame(width: max(geo.size.width - 340 - 16, 400), alignment: .topLeading)
                            ScrollView {
                                contextPanel
                            }
                            .frame(width: 340)
                        }
                    } else {
                        // Narrow: WebView transcript 占主区(自带滚动),上下文面板收进顶部的
                        // 定高原生 ScrollView(WebView 不能嵌进另一个 SwiftUI ScrollView,
                        // 否则双层滚动冲突)。composer 钉底。
                        VStack(spacing: 0) {
                            if !viewModel.messages.isEmpty {
                                ScrollView {
                                    contextPanel
                                        .frame(width: max(geo.size.width, 320), alignment: .topLeading)
                                }
                                .frame(maxHeight: 220)
                                Divider()
                            }
                            chatColumn
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                        .frame(width: max(geo.size.width, 320))
                    }
                }
                .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(.horizontal, 24)
        .padding(.top, 12)
        .padding(.bottom, 18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(
            LinearGradient(
                colors: [
                    Color(nsColor: .windowBackgroundColor),
                    Color.accentColor.opacity(0.05),
                    Color(nsColor: .windowBackgroundColor)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()
        )
        .onAppear {
            applyPersistedModelSelection()
            ingestPreparedDraft()
            editorFocusToken += 1
        }
        .task {
            // Pull the durable conversation list from the backend so Mac shows the
            // same history as web/mobile. Failure falls back to the local cache
            // (viewModel sets historyNotice) — never silently empty.
            await viewModel.refreshConversationHistory()
        }
        .onChange(of: viewModel.preparedDraft) { _, _ in
            ingestPreparedDraft()
        }
        .onChange(of: navigation?.newConversationTick) { _, _ in
            // ⌘N: start a fresh conversation and clear the local composer draft
            // (mirrors the header "New Chat" button).
            draft = ""
            viewModel.startNewConversation()
            editorFocusToken += 1
        }
        .sheet(item: $selectedToolActivity) { activity in
            ToolActivityDetailSheet(activity: activity)
        }
    }

    // ChatGPT-style slim top bar: model selector + new-chat on the left, history /
    // status on the right. No big page title and no full-width history card —
    // those used to eat the top third of the view and clip the transcript.
    private var header: some View {
        HStack(alignment: .center, spacing: 10) {
            modelMenuButton
            newChatButton
            if viewModel.isStreaming {
                ProgressView()
                    .controlSize(.small)
                Button {
                    viewModel.cancelStreaming()
                } label: {
                    Image(systemName: "stop.fill")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.primary)
                        .frame(width: 24, height: 24)
                        .background(Color.secondary.opacity(0.18), in: Circle())
                }
                .buttonStyle(.plain)
                .help(appText("Stop generating", appLanguageRaw))
            }
            Spacer()
            statusChip
        }
    }

    private var newChatButton: some View {
        Button {
            draft = ""
            viewModel.startNewConversation()
            editorFocusToken += 1
        } label: {
            Image(systemName: "square.and.pencil")
                .font(.body)
        }
        .buttonStyle(.borderless)
        .help(appText("New Chat", appLanguageRaw))
    }

    /// Apply the persisted model selection to the view model on appear, so a fresh
    /// launch defaults to Qwen3.7 Max (manual) and later switches are remembered.
    private func applyPersistedModelSelection() {
        viewModel.multiModel = (modelStrategy == "default3")
        if modelStrategy == "manual", !persistedModelID.isEmpty {
            let canonicalID = AgentModelCatalog.canonicalID(for: persistedModelID)
            if canonicalID != persistedModelID {
                persistedModelID = canonicalID
            }
            if viewModel.selectedModelID != canonicalID {
                viewModel.selectModel(canonicalID)
            }
        } else if viewModel.selectedModelID != nil {
            viewModel.selectModel(nil)
        }
    }

    private var modelMenuButton: some View {
        Menu {
            // Surface the model the backend actually used on the last run (auto /
            // default mode resolve server-side, so this is the honest answer).
            if let raw = viewModel.lastModel, !raw.isEmpty {
                Text("\(appText("Currently using", appLanguageRaw)): \(resolvedModelTitle(raw))")
            }
            Section(appText("Mode", appLanguageRaw)) {
                Button {
                    modelStrategy = "auto"
                    viewModel.multiModel = false
                    viewModel.selectModel(nil)
                } label: {
                    Label(appText("Auto Select", appLanguageRaw), systemImage: modelStrategy == "auto" ? "checkmark" : "")
                }
                Button {
                    modelStrategy = "default3"
                    viewModel.multiModel = true
                    viewModel.selectModel(nil)
                } label: {
                    Label(appText("Default 3", appLanguageRaw), systemImage: modelStrategy == "default3" ? "checkmark" : "")
                }
            }
            Section(appText("Manual", appLanguageRaw)) {
                ForEach(modelOptions, id: \.id) { option in
                    Button {
                        modelStrategy = "manual"
                        viewModel.multiModel = false
                        persistedModelID = option.id
                        viewModel.selectModel(option.id)
                    } label: {
                        Label(
                            "\(option.title) · \(option.tier)",
                            systemImage: (modelStrategy == "manual" && viewModel.selectedModelID == option.id) ? "checkmark" : ""
                        )
                    }
                }
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "slider.horizontal.3")
                Text(modelMenuLabel)
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.caption2)
            }
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help(selectedModelDescription)
    }

    private var modelMenuLabel: String {
        if modelStrategy == "manual",
           let id = viewModel.selectedModelID,
           let option = modelOptions.first(where: { $0.id == id }) {
            return option.title
        }
        // Auto / default mode: show the actual model used last run when known,
        // prefixed with the mode so it's clear it was auto-resolved.
        let modePrefix = modelStrategy == "default3" ? appText("Default 3", appLanguageRaw) : appText("Auto", appLanguageRaw)
        if let raw = viewModel.lastModel, !raw.isEmpty {
            return "\(modePrefix) · \(resolvedModelTitle(raw))"
        }
        return modelStrategy == "default3" ? appText("Default 3", appLanguageRaw) : appText("Auto Select", appLanguageRaw)
    }

    /// Map a raw model id from the stream (e.g. "commercial/GPT-5.5") to a
    /// friendly catalog title, falling back to the last path component.
    private func resolvedModelTitle(_ raw: String) -> String {
        if let option = modelOptions.first(where: { $0.id == raw || $0.title == raw }) {
            return option.title
        }
        if let slash = raw.lastIndex(of: "/") {
            return String(raw[raw.index(after: slash)...])
        }
        return raw
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 14) {
            // ChatGPT-style input box: text on top, a control bar inside the same
            // rounded box — attach + web on the left, round send/stop on the right.
            VStack(alignment: .leading, spacing: 8) {
                ZStack(alignment: .topLeading) {
                    PromptCommandTextEditor(
                        text: $draft,
                        focusToken: editorFocusToken,
                        measuredHeight: $composerTextHeight,
                        onPasteImage: { handlePastedImage($0) },
                        onPasteFileURLs: { urls in urls.forEach { attach($0) } }
                    ) {
                        sendDraft()
                    }
                    .frame(height: composerEditorHeight)
                    .animation(.easeOut(duration: 0.12), value: composerEditorHeight)

                    if draft.isEmpty {
                        Text(appText("Ask about health data, labs, genes, records, or a specific execution plan.", appLanguageRaw))
                            .foregroundStyle(.tertiary)
                            .padding(.top, 12)
                            .padding(.leading, 8)
                            .allowsHitTesting(false)
                    }
                }

                HStack(spacing: 8) {
                    attachButton
                    webSearchToggle
                    Spacer(minLength: 0)
                    composerSendButton
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            // White input field (ChatGPT-style) instead of the grey fill.
            // `.textBackgroundColor` is the system text-field white and stays
            // correct in dark mode; a slightly stronger border keeps the white
            // box legible against the composer card.
            .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Color.secondary.opacity(0.18), lineWidth: 1)
            }
            .onDrop(of: [UTType.fileURL.identifier], isTargeted: nil, perform: handleFileDrop)

            if !viewModel.attachments.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(viewModel.attachments) { item in
                        AttachmentChip(item: item) {
                            viewModel.removeAttachment(item)
                        }
                    }
                }
            }

            composerStatusLine
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
        .fileImporter(
            isPresented: $isAttachImporterPresented,
            allowedContentTypes: [.data, .folder],
            allowsMultipleSelection: true
        ) { result in
            do {
                for url in try result.get() {
                    attach(url)
                }
            } catch {
                viewModel.errorMessage = "Attach failed: \(userFacingError(error, appLanguageRaw))"
            }
        }
    }

    // ChatGPT-style round button at the input's bottom-right: ↑ to send,
    // ↩ (and ⌘↩) sends; ⇧↩ inserts a newline. Stop lives in the status bar so
    // the composer remains usable while a turn is streaming.
    @ViewBuilder
    private var composerSendButton: some View {
        let canSend = viewModel.canSubmit(draft)
        Button {
            sendDraft()
        } label: {
            Image(systemName: "arrow.up")
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 30, height: 30)
                .background(canSend ? Color.accentColor : Color.secondary.opacity(0.35), in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(!canSend)
        .keyboardShortcut(.return, modifiers: .command)
        .help("Command-Return")
    }

    // Contextual line below the input — only appears on error / retry, so the
    // composer has no permanent bottom action row.
    @ViewBuilder
    private var composerStatusLine: some View {
        if let error = viewModel.errorMessage {
            HStack(spacing: 10) {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
                if viewModel.canRetry && !viewModel.isStreaming {
                    Button {
                        Task { await viewModel.retryLastMessage() }
                    } label: {
                        Label(appText("Retry", appLanguageRaw), systemImage: "arrow.clockwise")
                            .font(.caption)
                    }
                    .buttonStyle(.borderless)
                }
                Spacer()
            }
        } else if viewModel.canRetry && !viewModel.isStreaming {
            HStack {
                Spacer()
                Button {
                    Task { await viewModel.retryLastMessage() }
                } label: {
                    Label(appText("Retry", appLanguageRaw), systemImage: "arrow.clockwise")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
            }
        }
    }

    // Bottom-left input controls (ChatGPT-style). No verbose "New Analysis"
    // headline — the icons speak for themselves.
    private var attachButton: some View {
        Button {
            isAttachImporterPresented = true
        } label: {
            Image(systemName: "paperclip")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 28, height: 28)
                .background(Color.secondary.opacity(0.08), in: Circle())
        }
        .buttonStyle(.plain)
        .help("Attach medical exam PDF/photo, image, genome txt, Apple Health export, or Dedao folder")
    }

    private var webSearchToggle: some View {
        Button {
            viewModel.webSearchEnabled.toggle()
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "network")
                Text(appText("Web Search", appLanguageRaw))
            }
            .font(.caption.weight(.medium))
            .foregroundStyle(viewModel.webSearchEnabled ? Color.accentColor : .secondary)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(
                (viewModel.webSearchEnabled ? Color.accentColor.opacity(0.14) : Color.secondary.opacity(0.08)),
                in: Capsule()
            )
        }
        .buttonStyle(.plain)
        .help(appText("Web Search", appLanguageRaw))
    }

    private var promptSuggestions: some View {
        FlowLayout(spacing: 8) {
            ForEach(promptSuggestionTexts, id: \.self) { suggestion in
                Button {
                    draft = suggestion
                    editorFocusToken += 1
                } label: {
                    Text(suggestion)
                        .lineLimit(1)
                }
                .buttonStyle(.plain)
                .font(.caption)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.secondary.opacity(0.09), in: Capsule())
            }
        }
    }

    private var promptSuggestionTexts: [String] {
        [
            appText("Analyze my latest health records and give today priorities.", appLanguageRaw),
            appText("Create a 30-day plan based on genes, labs, supplements, and exercise.", appLanguageRaw),
            appText("Check this answer for evidence and uncertainty boundaries.", appLanguageRaw)
        ]
    }

    @ViewBuilder
    private var historyPageCount: Int {
        let count = viewModel.conversationHistory.count
        guard count > 0 else { return 0 }
        return (count + Self.historyPageSize - 1) / Self.historyPageSize
    }

    /// Conversations for the current page, clamping the page index so a stale
    /// index (e.g. after deleting the last item on the last page) can't slice
    /// out of range.
    private var historyPageItems: [AgentConversationSnapshot] {
        let all = viewModel.conversationHistory
        guard !all.isEmpty else { return [] }
        let pageCount = historyPageCount
        let page = min(max(historyPage, 0), pageCount - 1)
        let start = page * Self.historyPageSize
        let end = min(start + Self.historyPageSize, all.count)
        return Array(all[start..<end])
    }

    private var historyPager: some View {
        let pageCount = historyPageCount
        let page = min(max(historyPage, 0), max(pageCount - 1, 0))
        return HStack(spacing: 12) {
            Button {
                if historyPage > 0 { historyPage -= 1 }
            } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(.plain)
            .disabled(page <= 0)

            Text("\(page + 1) / \(pageCount)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)

            Button {
                if historyPage < pageCount - 1 { historyPage += 1 }
            } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(.plain)
            .disabled(page >= pageCount - 1)

            Spacer()
        }
        .font(.caption.weight(.semibold))
        .padding(.top, 4)
    }

    private var selectedModelDescription: String {
        if let selectedModelID = viewModel.selectedModelID,
           let option = modelOptions.first(where: { $0.id == selectedModelID }) {
            return "\(appText("Manual", appLanguageRaw)) · \(option.title)"
        }
        if modelStrategy == "default3" {
            return appText("Use the default 3-model panel.", appLanguageRaw)
        }
        return appText("Let the backend choose the best route.", appLanguageRaw)
    }

    private func runStateText(_ state: AgentRunState) -> String {
        switch state {
        case .idle:
            return "Ready"
        case .preparing:
            return "Preparing"
        case .streaming:
            return "Generating"
        case .completed:
            return "Completed"
        case .partial:
            return "Partial"
        case .failed:
            return "Failed"
        }
    }

    private func runStateIcon(_ state: AgentRunState) -> String {
        switch state {
        case .idle:
            return "circle"
        case .preparing:
            return "hourglass"
        case .streaming:
            return "waveform"
        case .completed:
            return "checkmark.circle.fill"
        case .partial:
            return "exclamationmark.circle"
        case .failed:
            return "xmark.circle"
        }
    }

    private func runStateColor(_ state: AgentRunState) -> Color {
        switch state {
        case .idle:
            return .secondary
        case .preparing, .streaming:
            return .accentColor
        case .completed:
            return .green
        case .partial:
            return .orange
        case .failed:
            return .red
        }
    }

    /// Wide-layout chat column: messages scroll in the upper area and the
    /// composer stays pinned to the bottom edge — the standard ChatBot/ChatAgent
    /// arrangement (newest content above a fixed input).
    private var chatColumn: some View {
        VStack(spacing: 0) {
            // ⚠️ 第 9 轮结构性根治:对话区从 SwiftUI 改为 WKWebView 渲染(ChatGPT 桌面版同款)。
            // 8 轮地鼠证明 SwiftUI 在弹性 frame 嵌套里对流式增长的富文本做宽度协商 → 指数级
            // sizeThatFits。WebView 用浏览器引擎做线性增量布局,整类卡死消失;文本选择浏览器原生免费。
            // proposed action 卡片 + follow-up chips 仍是原生 SwiftUI(放 transcript 下方)。
            if viewModel.messages.isEmpty {
                ScrollView {
                    emptyConversationState
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                transcriptWebView
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                nativeTranscriptFooter
            }
            composer
                .padding(.top, 12)
        }
    }

    /// WKWebView 渲染的滚动对话区(自带滚动 + 自动滚底 + 文本选择)。
    private var transcriptWebView: some View {
        ChatTranscriptWebView(
            messages: viewModel.renderedTranscript(language: appLanguageRaw),
            fontScale: AppFontScale(level: appFontScaleLevel).pointScale,
            onCopy: { id in handleWebCopy(messageID: id) },
            onRouteOpen: { route in handleWebRouteOpen(route) },
            onAIGCConfirm: { confirmationID in
                Task { await viewModel.confirmAIGCMediaDraft(id: confirmationID) }
            }
        )
    }

    /// JS 复制按钮回调:按 messageID 找回原文写 NSPasteboard(原生剪贴板,非 WebView 内复制)。
    private func handleWebCopy(messageID: String) {
        guard let message = viewModel.messages.first(where: { $0.id.uuidString == messageID }) else { return }
        let text = viewModel.displayContent(for: message)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    /// Mac 端没有 mobile 的 tab router。动态卡片 route.open 经 DynamicCardRouting
    /// 解释:/chat?prompt → 预填输入框;已映射页面路由 → 跳侧边栏;其余渲染层
    /// 已不画按钮(死键点了没反应曾是实锤,Rule#1 不假装成功)。
    private func handleWebRouteOpen(_ route: String) {
        switch DynamicCardRouting.resolve(route: route) {
        case .chatPrompt(let prompt):
            draft = prompt
            editorFocusToken += 1
        case .sidebar(let destination):
            navigation?.selection = destination
        case nil:
            return
        }
    }

    /// transcript 下方的原生 SwiftUI:仅对最后一条助手消息渲染 proposed action 卡片 +
    /// follow-up chips(保持原生交互;流式 spinner 也在这里)。
    @ViewBuilder
    private var nativeTranscriptFooter: some View {
        if let last = viewModel.messages.last, last.role == .assistant {
            let actions = viewModel.proposedActions(for: last)
            let showChips = shouldShowFollowUpChips(for: last)
            // The "thinking process" trace now renders INSIDE the streaming assistant
            // bubble (see renderedTranscript / ChatTranscriptHTML.thinkingTraceHTML) so
            // it follows the bubble instead of being stranded above the composer. The
            // footer keeps only post-answer affordances: proposed-action cards + chips.
            if !actions.isEmpty || showChips {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(actions) { action in
                        AgentProposedActionCard(
                            action: action,
                            isStreaming: viewModel.isStreaming,
                            onConfirm: {
                                Task { await viewModel.confirmProposedAction(action) }
                            },
                            onDismiss: {
                                viewModel.dismissProposedAction(action)
                            }
                        )
                    }
                    if showChips {
                        followUpChips(for: last)
                    }
                }
                .frame(maxWidth: 860, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, 8)
            }
        }
    }

    private var emptyConversationState: some View {
        VStack(spacing: 18) {
            VStack(spacing: 10) {
                Image(systemName: "sparkles")
                    .font(.system(size: 32))
                    .foregroundStyle(.tertiary)
                Text(appText("Ask about health data, labs, genes, records, or a specific execution plan.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 420)
            }
            // Starter prompts live here on the blank page (ChatGPT-style), not in
            // the composer — they seed a first question and disappear once chatting.
            promptSuggestions
                .frame(maxWidth: 540)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        .padding(.top, 40)
    }

    private func shouldShowFollowUpChips(for message: AgentChatMessage) -> Bool {
        guard message.role == .assistant else { return false }
        guard !viewModel.isStreaming else { return false }
        guard !message.content.isEmpty else { return false }
        guard let last = viewModel.messages.last(where: { $0.role == .assistant }) else { return false }
        return last.id == message.id
    }

    private func followUpChips(for message: AgentChatMessage) -> some View {
        let prompts: [(label: String, prompt: String, icon: String)] = [
            ("Deeper", "深入这一点，给我更细的机制和细节。", "arrow.down.right.circle"),
            ("Action steps", "把这件事拆成具体可执行的步骤，标注先后。", "checklist"),
            ("Plain words", "用大白话再说一遍，假设我没医学背景。", "text.bubble"),
            ("Find evidence", "给我支撑这个结论的证据来源和等级。", "books.vertical"),
            ("Compare last", "和上次对比有什么变化，重点列差异。", "arrow.left.arrow.right.circle")
        ]
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(prompts, id: \.label) { chip in
                    Button {
                        viewModel.submit(chip.prompt)
                    } label: {
                        Label(appText(chip.label, appLanguageRaw), systemImage: chip.icon)
                            .labelStyle(.titleAndIcon)
                            .font(.caption.weight(.medium))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 7)
                    }
                    .buttonStyle(.plain)
                    .background(Color.accentColor.opacity(0.10), in: Capsule())
                    .foregroundStyle(Color.accentColor)
                    .help(chip.prompt)
                }
            }
            .padding(.top, 4)
        }
    }

    private var contextPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(appText("Context", appLanguageRaw), systemImage: "square.stack.3d.up")
                .font(.headline)
            contextMetric(
                title: appText("Files", appLanguageRaw),
                value: "\(viewModel.attachments.count)",
                detail: appText("Drag files here or use Attach.", appLanguageRaw),
                systemImage: "paperclip"
            )
            contextMetric(
                title: appText("Web", appLanguageRaw),
                value: appText(viewModel.webSearchEnabled ? "On" : "Off", appLanguageRaw),
                detail: appText("Use for current facts and external sources.", appLanguageRaw),
                systemImage: "network"
            )
            contextMetric(
                title: appText("Route", appLanguageRaw),
                value: routeShortText,
                detail: selectedModelDescription,
                systemImage: "point.3.connected.trianglepath.dotted"
            )

            if !viewModel.conversationHistory.isEmpty || viewModel.historyNotice != nil || viewModel.isLoadingHistory {
                Divider()

                HStack {
                    Label(appText("History", appLanguageRaw), systemImage: "clock.arrow.circlepath")
                        .font(.subheadline.bold())
                    if viewModel.isLoadingHistory {
                        ProgressView().controlSize(.small)
                    }
                    Spacer()
                    if !viewModel.conversationHistory.isEmpty {
                        Text("\(viewModel.conversationHistory.count)")
                            .font(.caption.bold())
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.10), in: Capsule())
                    }
                    Button {
                        Task { await viewModel.refreshConversationHistory() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                    .disabled(viewModel.isLoadingHistory)
                    .help(appText("Refresh", appLanguageRaw))
                }

                // Offline / 401 / server-error: the list below is the local cache,
                // not the live backend. Say so instead of pretending it's current.
                if let notice = viewModel.historyNotice {
                    Text(notice)
                        .font(.caption2)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }

                VStack(alignment: .leading, spacing: 8) {
                    ForEach(historyPageItems) { conversation in
                        AgentConversationHistoryRow(
                            conversation: conversation,
                            isSelected: conversation.id == viewModel.currentConversationID,
                            onLoad: {
                                // Fetch the full transcript from the backend so a
                                // conversation started on another device opens here.
                                Task { await viewModel.openConversation(conversation) }
                            },
                            onDelete: {
                                viewModel.deleteConversation(conversation)
                            },
                            onRename: { newTitle in
                                Task { await viewModel.renameConversation(conversation, to: newTitle) }
                            },
                            onShare: {
                                await viewModel.shareConversation(conversation)
                            }
                        )
                    }
                }
                if historyPageCount > 1 {
                    historyPager
                }
            }

            if !viewModel.contextItems.isEmpty {
                Divider()

                HStack {
                    Label(appText("Selected Context", appLanguageRaw), systemImage: "tray.full")
                        .font(.subheadline.bold())
                    Spacer()
                    Button(appText("Clear", appLanguageRaw)) {
                        viewModel.clearContextItems()
                    }
                    .buttonStyle(.plain)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.contextItems) { item in
                        AgentContextItemCard(item: item) {
                            viewModel.removeContextItem(item)
                        }
                    }
                }

                HStack(spacing: 8) {
                    TextField(appText("Bundle name", appLanguageRaw), text: $contextBundleName)
                        .textFieldStyle(.roundedBorder)
                    Button {
                        let bundle = viewModel.saveCurrentContextBundle(named: contextBundleName)
                        contextBundleName = bundle.name
                    } label: {
                        Label(appText("Save Bundle", appLanguageRaw), systemImage: "archivebox")
                    }
                    .buttonStyle(.bordered)
                    .disabled(viewModel.contextItems.isEmpty)
                }
            }

            if !viewModel.savedContextBundles.isEmpty {
                Divider()

                Label(appText("Saved Context Bundles", appLanguageRaw), systemImage: "archivebox.fill")
                    .font(.subheadline.bold())
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.savedContextBundles.prefix(4)) { bundle in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "square.stack.3d.up.fill")
                                .foregroundStyle(.white)
                                .frame(width: 24, height: 24)
                                .background(Color.indigo.opacity(0.85), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(bundle.name)
                                    .font(.caption.weight(.semibold))
                                    .lineLimit(1)
                                Text("\(bundle.itemCount) \(appText("items", appLanguageRaw))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 0)
                            Button {
                                viewModel.applyContextBundle(bundle)
                            } label: {
                                Image(systemName: "plus.circle.fill")
                            }
                            .buttonStyle(.plain)
                            .help(appText("Apply Bundle", appLanguageRaw))
                            Button {
                                viewModel.deleteContextBundle(bundle)
                            } label: {
                                Image(systemName: "trash")
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(.secondary)
                            .help(appText("Delete", appLanguageRaw))
                        }
                        .padding(10)
                        .background(Color.indigo.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                }
            }

            if !viewModel.toolActivities.isEmpty {
                Divider()

                HStack(spacing: 6) {
                    Label(appText("Tool Timeline", appLanguageRaw), systemImage: "wrench.and.screwdriver")
                        .font(.subheadline.bold())
                    Spacer()
                    toolTimelineSummary
                }
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(groupedToolActivities(), id: \.round) { group in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 6) {
                                Image(systemName: "arrow.right.circle.fill")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                                Text(roundLabel(group.round, count: group.activities.count))
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                Spacer()
                                if group.activities.contains(where: { $0.status == .running }) {
                                    ProgressView()
                                        .controlSize(.mini)
                                }
                            }
                            VStack(alignment: .leading, spacing: 5) {
                                ForEach(group.activities) { activity in
                                    Button {
                                        selectedToolActivity = activity
                                    } label: {
                                        HStack(spacing: 8) {
                                            Image(systemName: toolActivityIcon(activity.status))
                                                .foregroundStyle(toolActivityColor(activity.status))
                                                .frame(width: 18)
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(activity.name)
                                                    .font(.caption.weight(.semibold))
                                                    .lineLimit(1)
                                                if let summary = activity.resultText ?? activity.arguments {
                                                    Text(summary)
                                                        .font(.caption2)
                                                        .foregroundStyle(.secondary)
                                                        .lineLimit(1)
                                                }
                                            }
                                            Spacer(minLength: 0)
                                            Text(appText(toolActivityText(activity.status), appLanguageRaw))
                                                .font(.caption2.weight(.bold))
                                                .foregroundStyle(toolActivityColor(activity.status))
                                            Image(systemName: "chevron.right")
                                                .font(.caption2.weight(.bold))
                                                .foregroundStyle(.tertiary)
                                        }
                                        .contentShape(Rectangle())
                                    }
                                    .buttonStyle(.plain)
                                    .padding(.horizontal, 9)
                                    .padding(.vertical, 7)
                                    .background(toolActivityColor(activity.status).opacity(0.10), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                                    .help(appText("View Tool Result", appLanguageRaw))
                                }
                            }
                            .padding(.leading, 12)
                            .overlay(alignment: .leading) {
                                Rectangle()
                                    .fill(Color.secondary.opacity(0.18))
                                    .frame(width: 1.5)
                                    .padding(.leading, 4)
                            }
                        }
                    }
                }
            }

            Divider()

            Label(appText("Evidence", appLanguageRaw), systemImage: "doc.text.magnifyingglass")
                .font(.subheadline.bold())
            if !viewModel.attachments.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(appText("Attachments", appLanguageRaw))
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    ForEach(viewModel.attachments) { item in
                        Label(item.name, systemImage: "paperclip")
                            .font(.caption)
                            .lineLimit(1)
                    }
                }
            }
            if !viewModel.lastSourcesUsed.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(appText("Sources", appLanguageRaw))
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    ForEach(viewModel.lastSourcesUsed, id: \.self) { source in
                        evidenceSourceChip(source)
                    }
                }
            }
            if viewModel.lastSourcesUsed.isEmpty && viewModel.attachments.isEmpty {
                Text(appText("Sources, attachments, and evidence refs will appear here.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private var statusChip: some View {
        Label(appText(runStateText(viewModel.runState), appLanguageRaw), systemImage: runStateIcon(viewModel.runState))
            .font(.caption.bold())
            .foregroundStyle(runStateColor(viewModel.runState))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(runStateColor(viewModel.runState).opacity(0.12), in: Capsule())
    }

    private var routeShortText: String {
        if viewModel.selectedModelID != nil {
            return appText("Manual", appLanguageRaw)
        }
        return modelStrategy == "default3" ? appText("Default 3", appLanguageRaw) : appText("Auto", appLanguageRaw)
    }

    private func contextMetric(title: String, value: String, detail: String, systemImage: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: systemImage)
                .font(.callout)
                .foregroundStyle(.white)
                .frame(width: 28, height: 28)
                .background(Color.accentColor.opacity(0.85), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(title)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(value)
                        .font(.callout.bold())
                }
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func toolActivityText(_ status: AgentToolActivityStatus) -> String {
        switch status {
        case .running: "Running"
        case .succeeded: "Succeeded"
        case .failed: "Failed"
        }
    }

    private struct ToolActivityGroup {
        let round: Int
        let activities: [AgentToolActivity]
    }

    private func groupedToolActivities() -> [ToolActivityGroup] {
        var buckets: [Int: [AgentToolActivity]] = [:]
        var order: [Int] = []
        for (idx, activity) in viewModel.toolActivities.enumerated() {
            let key = activity.round ?? 0
            if buckets[key] == nil {
                buckets[key] = []
                order.append(key)
            }
            buckets[key]?.append(activity)
            _ = idx
        }
        return order.map { ToolActivityGroup(round: $0, activities: buckets[$0] ?? []) }
    }

    private func roundLabel(_ round: Int, count: Int) -> String {
        let stepWord = count == 1
            ? appText("step", appLanguageRaw)
            : appText("steps", appLanguageRaw)
        if round <= 0 {
            return "\(appText("Initial", appLanguageRaw)) · \(count) \(stepWord)"
        }
        return "\(appText("Round", appLanguageRaw)) \(round) · \(count) \(stepWord)"
    }

    private var toolTimelineSummary: some View {
        let total = viewModel.toolActivities.count
        let running = viewModel.toolActivities.filter { $0.status == .running }.count
        let failed = viewModel.toolActivities.filter { $0.status == .failed }.count
        return HStack(spacing: 6) {
            if running > 0 {
                Text("\(running)")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(Color.accentColor)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.accentColor.opacity(0.12), in: Capsule())
            }
            if failed > 0 {
                Text("\(failed)")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.red)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.red.opacity(0.12), in: Capsule())
            }
            Text("\(total)")
                .font(.caption2.weight(.semibold).monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    private func toolActivityIcon(_ status: AgentToolActivityStatus) -> String {
        switch status {
        case .running: "hourglass"
        case .succeeded: "checkmark.circle.fill"
        case .failed: "xmark.circle.fill"
        }
    }

    private func toolActivityColor(_ status: AgentToolActivityStatus) -> Color {
        switch status {
        case .running: .accentColor
        case .succeeded: .green
        case .failed: .red
        }
    }

    private func sendDraft() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard viewModel.canSubmit(text) else { return }
        draft = ""
        viewModel.submit(text)
        editorFocusToken += 1
    }

    private func ingestPreparedDraft() {
        guard let preparedDraft = viewModel.consumePreparedDraft() else {
            return
        }
        draft = preparedDraft
        editorFocusToken += 1
    }

    private func attach(_ url: URL) {
        Task {
            do {
                let item = try await FileIntakeService.inspect(url: url)
                viewModel.addAttachment(item)
            } catch {
                viewModel.errorMessage = "Attach failed: \(userFacingError(error, appLanguageRaw))"
            }
        }
    }

    /// ⌘V 粘贴的图片:转 PNG 落临时文件,复用 attach(url) 走 FileIntakeService → 图片附件
    /// (与 📎/拖拽同一条发送路径,端到端已支持 png/jpg vision)。
    private func handlePastedImage(_ image: NSImage) {
        guard let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else {
            viewModel.errorMessage = appText("Couldn't read the pasted image.", appLanguageRaw)
            return
        }
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("pasted-\(UUID().uuidString).png")
        do {
            try png.write(to: url)
            attach(url)
        } catch {
            viewModel.errorMessage = "Attach failed: \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func handleFileDrop(_ providers: [NSItemProvider]) -> Bool {
        var accepted = false
        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            accepted = true
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                let url: URL?
                if let data = item as? Data {
                    url = URL(dataRepresentation: data, relativeTo: nil)
                } else {
                    url = item as? URL
                }
                if let url {
                    Task { @MainActor in
                        attach(url)
                    }
                }
            }
        }
        return accepted
    }

    @ViewBuilder
    private func evidenceSourceChip(_ rawSource: String) -> some View {
        let level = EvidenceLevel.classify(sourceLabel: rawSource)
        let destination = evidenceDestination(for: rawSource)
        Button {
            if let destination {
                navigation?.selection = destination
            }
        } label: {
            HStack(alignment: .center, spacing: 6) {
                Image(systemName: "link")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(rawSource)
                    .font(.caption)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                if destination != nil {
                    Image(systemName: "chevron.right")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.secondary)
                }
                Label(appText(level.displayLabel, appLanguageRaw), systemImage: level.systemImage)
                    .labelStyle(.titleAndIcon)
                    .font(.caption2.weight(.semibold))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(evidenceChipBackground(for: level), in: Capsule())
                    .foregroundStyle(evidenceChipForeground(for: level))
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(destination == nil)
    }

    /// Maps an evidence source label to the workspace it came from, so tapping a
    /// source jumps there. nil → the chip stays non-interactive (no fake action).
    private func evidenceDestination(for source: String) -> SidebarDestination? {
        let lower = source.lowercased()
        if source.contains("基因") || lower.contains("gene") || lower.contains("genom") {
            return .genetics
        }
        if source.contains("知识") || source.contains("文献") || lower.contains("knowledge") || lower.contains("wiki") {
            return .knowledge
        }
        if source.contains("运动") || lower.contains("workout") {
            return .workouts
        }
        if source.contains("化验") || source.contains("检验") || lower.contains("lab")
            || source.contains("Garmin") || source.contains("健康数据")
            || source.contains("睡眠") || source.contains("血氧") || source.contains("HRV")
            || source.contains("补剂") || source.contains("药物") || source.contains("指标") {
            return .data
        }
        return nil
    }

    private func evidenceChipBackground(for level: EvidenceLevel) -> Color {
        switch level {
        case .high: Color.green.opacity(0.18)
        case .medium: Color.yellow.opacity(0.22)
        case .low: Color.gray.opacity(0.18)
        case .medicalGrade: Color.red.opacity(0.18)
        }
    }

    private func evidenceChipForeground(for level: EvidenceLevel) -> Color {
        switch level {
        case .high: Color.green
        case .medium: Color.orange
        case .low: Color.secondary
        case .medicalGrade: Color.red
        }
    }
}

/// Accumulating "thinking process" trace: a left-aligned vertical list of the
/// steps 小巴 went through this turn (from the backend `status` SSE stream).
/// Running step = mini spinner + emphasized text; done steps = checkmark +
/// dimmed. Unlike `ThinkingStatusLine` (a single overwriting line) the whole
/// sequence stays visible through content streaming until the turn resets.
///
/// Layout is deliberately a plain header + `VStack`/`ForEach` over stable step
/// ids with a fixed-width leading gutter — NO `ViewThatFits`/`fixedSize` probing
/// (that path caused an exponential `sizeThatFits` layout freeze historically).
private struct ThinkingProcessTrace: View {
    let steps: [ThinkingStep]
    let language: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 6) {
                Image(systemName: "brain")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Text(appText("Thinking process", language))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 6) {
                ForEach(steps) { step in
                    row(for: step)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func row(for step: ThinkingStep) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            // Fixed-width leading gutter keeps rows aligned and gives the layout a
            // deterministic width (no measurement feedback loop).
            leadingGlyph(for: step.state)
                .frame(width: 16, alignment: .center)
            Text(label(for: step))
                .font(.caption)
                .foregroundStyle(step.state == .running ? Color.primary : .secondary)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
        }
    }

    @ViewBuilder
    private func leadingGlyph(for state: ThinkingStepState) -> some View {
        if state == .running {
            ProgressView()
                .controlSize(.mini)
        } else {
            Image(systemName: "checkmark.circle.fill")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
    }

    /// Resolves a step's L10n key (+ optional detail) exactly like
    /// `ThinkingStatusLine.statusText`: `"Working: %@…"` splices the backend's
    /// Chinese tool label verbatim; other keys are a straight `appText` lookup
    /// (server-phrase keys pass through unchanged in zh).
    private func label(for step: ThinkingStep) -> String {
        let template = appText(step.labelKey, language)
        if let detail = step.labelDetail {
            return String(format: template, detail)
        }
        return template
    }
}

/// Pre-first-token "thinking" affordance shown in the empty assistant bubble
/// while 小巴's TTFT (2–14s, longer on a silent tool round) elapses. Purely
/// presentational: a small spinner + a caption that cycles copy after ~6s so a
/// long wait doesn't feel frozen. No stream/parse/network coupling.
private struct ThinkingStatusLine: View {
    let language: String
    /// True once a tool activity has surfaced this turn — only then do we claim
    /// "checking your records", never on a plain analysis turn.
    let isToolTurn: Bool
    /// Real backend stage (`status` SSE event) → L10n key, from the view model.
    /// When non-nil this drives the copy; nil → time-based fallback below.
    let liveStatusKey: String?
    /// Chinese tool label for the `tool` stage; interpolated into `liveStatusKey`
    /// when it is the "Working: %@…" format string.
    let liveStatusDetail: String?

    /// 0 = initial copy, 1 = after ~6s. Kept minimal; a static line is fine too.
    @State private var phase = 0

    var body: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small)
            Text(statusText)
                .font(.caption)
                .foregroundStyle(.secondary)
                .transition(.opacity)
                .id(statusText)
        }
        .task {
            // Cheap one-shot: advance to the "organizing" copy after ~6s if the
            // token hasn't arrived (this view is torn down the moment it does).
            // Harmless when real status events drive the copy — `statusText`
            // ignores `phase` while `liveStatusKey` is non-nil.
            try? await Task.sleep(nanoseconds: 6_000_000_000)
            withAnimation(.easeInOut(duration: 0.25)) { phase = 1 }
        }
    }

    /// Prefer the real backend stage when present; otherwise keep the original
    /// time-based rotation (full back-compat with old backends that never emit
    /// `status`).
    private var statusText: String {
        if let liveStatusKey {
            let template = appText(liveStatusKey, language)
            if let liveStatusDetail {
                return String(format: template, liveStatusDetail)
            }
            return template
        }
        return appText(fallbackKey, language)
    }

    private var fallbackKey: String {
        if isToolTurn { return "Checking your records…" }
        return phase == 0 ? "Reva is thinking…" : "Reva is organizing…"
    }
}

private struct AgentContextItemCard: View {
    let item: AgentContextItem
    let onRemove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: iconName)
                    .foregroundStyle(.white)
                    .frame(width: 24, height: 24)
                    .background(Color.accentColor.opacity(0.82), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.title)
                        .font(.caption.weight(.semibold))
                        .lineLimit(2)
                    Text(item.sourceKind)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
                Button(action: onRemove) {
                    Image(systemName: "xmark.circle.fill")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
            }
            if !item.summary.isEmpty {
                Text(item.summary)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
        }
        .padding(10)
        .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.accentColor.opacity(0.12), lineWidth: 1)
        }
    }

    private var iconName: String {
        switch item.sourceKind {
        case "genomic_finding", "genomic_category":
            "atom"
        case "health_record":
            "waveform.path.ecg"
        case "knowledge_document":
            "books.vertical.fill"
        default:
            "doc.text.magnifyingglass"
        }
    }
}

private struct AttachmentChip: View {
    let item: FileIntakeItem
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: iconName)
            Text(item.name)
                .lineLimit(1)
            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
        .font(.caption)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.secondary.opacity(0.10), in: Capsule())
        .help(item.sha256)
    }

    private var iconName: String {
        switch item.sourceKind {
        case .genomeText: "atom"
        case .dedaoFolder: "folder"
        case .appleHealthExport: "heart.text.square"
        case .medicalFile: "doc.richtext"
        case .image: "photo"
        case .unknown: "doc"
        }
    }
}

private struct FlowLayout<Content: View>: View {
    let spacing: CGFloat
    @ViewBuilder let content: Content

    init(spacing: CGFloat, @ViewBuilder content: () -> Content) {
        self.spacing = spacing
        self.content = content()
    }

    var body: some View {
        HStack(spacing: spacing) {
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct AgentProposedActionCard: View {
    let action: AgentProposedAction
    let isStreaming: Bool
    let onConfirm: () -> Void
    let onDismiss: () -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: statusIcon)
                    .font(.headline)
                    .foregroundStyle(statusColor)
                    .frame(width: 28, height: 28)
                    .background(statusColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    Text(action.title)
                        .font(.callout.weight(.semibold))
                    Text(action.summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Spacer(minLength: 8)
                Text(appText(statusText, appLanguageRaw))
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(statusColor)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(statusColor.opacity(0.12), in: Capsule())
            }

            HStack(spacing: 8) {
                Button {
                    onConfirm()
                } label: {
                    Label(appText("Confirm Action", appLanguageRaw), systemImage: "checkmark.circle.fill")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(action.status != .pending || isStreaming)

                Button {
                    onDismiss()
                } label: {
                    Label(appText("Ignore", appLanguageRaw), systemImage: "xmark.circle")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(action.status != .pending || isStreaming)

                Spacer()
                Text(appText("Structured command requires confirmation before execution.", appLanguageRaw))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(statusColor.opacity(0.075), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(statusColor.opacity(0.16), lineWidth: 1)
        }
    }

    private var statusText: String {
        switch action.status {
        case .pending: "Needs Confirmation"
        case .confirmed: "Confirmed"
        case .dismissed: "Ignored"
        }
    }

    private var statusIcon: String {
        switch action.status {
        case .pending: "exclamationmark.shield.fill"
        case .confirmed: "checkmark.shield.fill"
        case .dismissed: "xmark.shield.fill"
        }
    }

    private var statusColor: Color {
        switch action.status {
        case .pending: .orange
        case .confirmed: .green
        case .dismissed: .secondary
        }
    }
}

private struct MarkdownMessageText: View {
    @AppStorage(AppFontScale.defaultsKey) private var appFontScaleLevel = AppFontScale.defaultLevel

    // ⚠️ 结构性防卡死(2026-06-11,第 6 轮根因战):整条消息渲染为**单个 Text(AttributedString)**。
    // 之前的「VStack 多块 + 嵌套 HStack(bullet/numbered/表格行)」结构在 macOS 26.4 SwiftUI 下
    // 反复指数级 sizeThatFits 卡死(100% CPU,sample 实锤 5 次;修掉 GeometryReader 反馈环/
    // fixedSize/表格弹性列后爆点仍转移)。单个 Text 无嵌套 stack、无 frame 协商,布局线性,
    // 数学上不可能组合爆炸。代价:表格从网格降级为「 · 」分隔的文本行 —— 不卡死 > 好看。
    private let markdown: String
    private let contentWidth: CGFloat

    init(markdown: String, contentWidth: CGFloat) {
        self.markdown = markdown
        self.contentWidth = contentWidth
    }

    var body: some View {
        // merged 经全局 NSCache:首次 O(n) 解析合并,之后(布局重建/滚动)O(1) 命中。
        Text(Self.mergedAttributed(markdown: markdown, scaleLevel: appFontScaleLevel))
            .lineSpacing(3)
            .frame(width: contentWidth > 0 ? contentWidth : nil, alignment: .leading)
    }

    // ── 解析 + 合并(全部静态缓存,线程安全 NSCache;Swift 6 nonisolated(unsafe) 同
    //    MarkdownRenderSupport.blocksCache 先例)──
    private final class AttrBox { let value: AttributedString; init(_ v: AttributedString) { self.value = v } }
    nonisolated(unsafe) private static let inlineAttrCache: NSCache<NSString, AttrBox> = {
        let c = NSCache<NSString, AttrBox>(); c.countLimit = 2048; return c
    }()
    nonisolated(unsafe) private static let mergedCache: NSCache<NSString, AttrBox> = {
        let c = NSCache<NSString, AttrBox>(); c.countLimit = 128; return c
    }()

    private static func cachedInlineAttributed(_ text: String) -> AttributedString {
        let key = text as NSString
        if let hit = inlineAttrCache.object(forKey: key) { return hit.value }
        let cleaned = MarkdownRenderSupport.sanitizedForSwiftUI(text)
        let attributed = (try? AttributedString(
            markdown: cleaned,
            options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(MarkdownRenderSupport.readableFallback(text))
        inlineAttrCache.setObject(AttrBox(attributed), forKey: key)
        return attributed
    }

    private static func mergedAttributed(markdown: String, scaleLevel: Int) -> AttributedString {
        let key = "\(scaleLevel)|\(markdown)" as NSString
        if let hit = mergedCache.object(forKey: key) { return hit.value }

        let scale = AppFontScale(level: scaleLevel)
        let bodyFont = Font.system(size: scale.pointSize(base: 10.5))
        let src = markdown.isEmpty ? " " : markdown
        let parsed = MarkdownRenderSupport.blocks(from: src)
        let blocks: [MarkdownRenderBlock] = parsed.isEmpty
            ? [.paragraph(MarkdownRenderSupport.readableFallback(src))]
            : parsed

        var out = AttributedString()
        var isFirst = true
        for block in blocks {
            if !isFirst { out += AttributedString("\n") }
            isFirst = false
            switch block {
            case .heading(let level, let text):
                var a = cachedInlineAttributed(text)
                a.font = .system(
                    size: scale.pointSize(base: level <= 2 ? 13 : 11.5),
                    weight: level <= 2 ? .bold : .semibold
                )
                // 标题前空行(非首块时)抬一点呼吸感
                if out.characters.count > 1 { out += AttributedString("\n") }
                out += a
            case .paragraph(let text):
                var a = cachedInlineAttributed(text)
                a.font = bodyFont
                out += a
            case .bullet(let text):
                var dot = AttributedString("•  ")
                dot.font = .system(size: scale.pointSize(base: 10.5), weight: .bold)
                dot.foregroundColor = .accentColor
                var a = cachedInlineAttributed(text)
                a.font = bodyFont
                out += dot + a
            case .numbered(let index, let text):
                var num = AttributedString("\(index). ")
                num.font = .system(size: scale.pointSize(base: 10.5), weight: .bold)
                num.foregroundColor = .accentColor
                var a = cachedInlineAttributed(text)
                a.font = bodyFont
                out += num + a
            case .tableRow(let columns):
                // 表格降级为分隔文本行(单 Text 内不可能做网格;不卡死优先)。
                var row = AttributedString()
                for (i, col) in columns.enumerated() {
                    if i > 0 {
                        var sep = AttributedString("  ·  ")
                        sep.foregroundColor = .secondary
                        row += sep
                    }
                    var c = cachedInlineAttributed(col)
                    c.font = i == 0 ? .system(size: scale.pointSize(base: 10.5), weight: .semibold) : bodyFont
                    row += c
                }
                out += row
            case .divider:
                var d = AttributedString("────────────")
                d.foregroundColor = .secondary
                out += d
            }
        }
        mergedCache.setObject(AttrBox(out), forKey: key)
        return out
    }
}

private struct ToolActivityDetailSheet: View {
    let activity: AgentToolActivity
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .center, spacing: 12) {
                Image(systemName: iconName)
                    .foregroundStyle(color)
                    .frame(width: 28, height: 28)
                    .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    Text(activity.name)
                        .font(.title3.weight(.semibold))
                    HStack(spacing: 8) {
                        Text(statusText)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(color)
                        if let round = activity.round {
                            Text("\(appText("Round", appLanguageRaw)) \(round)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                Spacer()
                Button(appText("Close", appLanguageRaw)) {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)
            }

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    detailBlock(
                        title: appText("Arguments", appLanguageRaw),
                        text: activity.arguments ?? appText("No arguments captured.", appLanguageRaw)
                    )
                    detailBlock(
                        title: appText("Tool Result", appLanguageRaw),
                        text: activity.resultText ?? appText("No tool result yet.", appLanguageRaw)
                    )
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(22)
        .frame(minWidth: 620, minHeight: 440)
    }

    private func detailBlock(title: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            Text(formatted(text))
                .font(.system(.body, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
    }

    private func formatted(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              JSONSerialization.isValidJSONObject(object),
              let pretty = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]),
              let string = String(data: pretty, encoding: .utf8) else {
            return trimmed
        }
        return string
    }

    private var statusText: String {
        switch activity.status {
        case .running: appText("Running", appLanguageRaw)
        case .succeeded: appText("Succeeded", appLanguageRaw)
        case .failed: appText("Failed", appLanguageRaw)
        }
    }

    private var iconName: String {
        switch activity.status {
        case .running: "hourglass"
        case .succeeded: "checkmark.circle.fill"
        case .failed: "xmark.circle.fill"
        }
    }

    private var color: Color {
        switch activity.status {
        case .running: .accentColor
        case .succeeded: .green
        case .failed: .red
        }
    }
}

private struct AgentConversationHistoryRow: View {
    let conversation: AgentConversationSnapshot
    let isSelected: Bool
    let onLoad: () -> Void
    let onDelete: () -> Void
    /// Push the edited title to the parent (which forwards to the backend). Called
    /// only when the drafted title is non-empty and actually changed.
    let onRename: (String) -> Void
    /// Async: create a public share link and hand back the URL (nil on failure).
    let onShare: () async -> URL?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var isRenaming = false
    @State private var draftTitle = ""
    @State private var isSharing = false
    @State private var sharedURL: URL?
    @State private var showShareConfirm = false

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Button {
                onLoad()
            } label: {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: isSelected ? "checkmark.circle.fill" : "message")
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                        .frame(width: 20)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(conversation.title)
                            .font(.caption.weight(.semibold))
                            .lineLimit(2)
                            .foregroundStyle(.primary)
                        Text(historySubtitle)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }
            }
            .buttonStyle(.plain)
            .help(appText("Load Chat", appLanguageRaw))

            HStack(spacing: 10) {
                Button {
                    guard !isSharing else { return }
                    isSharing = true
                    Task {
                        let url = await onShare()
                        isSharing = false
                        guard let url else { return }
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(url.absoluteString, forType: .string)
                        sharedURL = url
                        showShareConfirm = true
                    }
                } label: {
                    if isSharing {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "square.and.arrow.up")
                    }
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .disabled(isSharing)
                .help(appText("Share", appLanguageRaw))

                Button {
                    draftTitle = conversation.title
                    isRenaming = true
                } label: {
                    Image(systemName: "pencil")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help(appText("Rename", appLanguageRaw))

                Button {
                    onDelete()
                } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help(appText("Delete", appLanguageRaw))
            }
        }
        .padding(10)
        .background(
            isSelected ? Color.accentColor.opacity(0.10) : Color.secondary.opacity(0.07),
            in: RoundedRectangle(cornerRadius: 11, style: .continuous)
        )
        .alert(appText("Rename conversation", appLanguageRaw), isPresented: $isRenaming) {
            TextField(appText("New title", appLanguageRaw), text: $draftTitle)
            Button(appText("Cancel", appLanguageRaw), role: .cancel) {}
            Button(appText("Save", appLanguageRaw)) {
                let trimmed = draftTitle.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty, trimmed != conversation.title {
                    onRename(trimmed)
                }
            }
        }
        .alert(
            appText("Share link copied", appLanguageRaw),
            isPresented: $showShareConfirm,
            presenting: sharedURL
        ) { url in
            Button(appText("Open in browser", appLanguageRaw)) {
                NSWorkspace.shared.open(url)
            }
            Button(appText("Cancel", appLanguageRaw), role: .cancel) {}
        } message: { url in
            Text(url.absoluteString)
        }
    }

    private var historySubtitle: String {
        let date = conversation.updatedAt.formatted(date: .numeric, time: .shortened)
        // A backend list snapshot has no messages until it's opened — show only id
        // + date then, so the row never claims a misleading "0 messages".
        let count = conversation.messages.count
        let countSegment = count > 0 ? "\(count) \(appText("messages", appLanguageRaw)) · " : ""
        if let conversationID = conversation.conversationID {
            return "#\(conversationID) · \(countSegment)\(date)"
        }
        return "\(countSegment)\(date)"
    }
}

private struct PromptCommandTextEditor: NSViewRepresentable {
    @Binding var text: String
    let focusToken: Int
    // Reports laid-out content height for auto-growing composers; defaults to a
    // throwaway binding for call sites that use a fixed frame instead.
    var measuredHeight: Binding<CGFloat> = .constant(0)
    let onCommandReturn: () -> Void
    // ⌘V 粘贴图片/文件回调(默认 nil:快速记录等调用点不接附件)。
    var onPasteImage: ((NSImage) -> Void)? = nil
    var onPasteFileURLs: (([URL]) -> Void)? = nil

    init(
        text: Binding<String>,
        focusToken: Int,
        measuredHeight: Binding<CGFloat> = .constant(0),
        onPasteImage: ((NSImage) -> Void)? = nil,
        onPasteFileURLs: (([URL]) -> Void)? = nil,
        onCommandReturn: @escaping () -> Void
    ) {
        self._text = text
        self.focusToken = focusToken
        self.measuredHeight = measuredHeight
        self.onPasteImage = onPasteImage
        self.onPasteFileURLs = onPasteFileURLs
        self.onCommandReturn = onCommandReturn
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text, measuredHeight: measuredHeight)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let textView = CommandReturnTextView()
        textView.delegate = context.coordinator
        textView.onCommandReturn = onCommandReturn
        textView.onPasteImage = onPasteImage
        textView.onPasteFileURLs = onPasteFileURLs
        textView.isRichText = false
        textView.importsGraphics = false
        textView.allowsUndo = true
        textView.font = .preferredFont(forTextStyle: .body)
        textView.textContainerInset = NSSize(width: 0, height: 6)
        textView.drawsBackground = false
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isAutomaticTextReplacementEnabled = false
        textView.string = text

        let scrollView = NSScrollView()
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder
        scrollView.hasVerticalScroller = true
        scrollView.documentView = textView
        context.coordinator.textView = textView
        context.coordinator.focusToken = focusToken

        DispatchQueue.main.async {
            textView.window?.makeFirstResponder(textView)
            context.coordinator.recomputeHeight()
        }
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        textView.onCommandReturn = onCommandReturn
        textView.onPasteImage = onPasteImage
        textView.onPasteFileURLs = onPasteFileURLs
        if textView.string != text {
            textView.string = text
            context.coordinator.recomputeHeight()
        }
        if context.coordinator.focusToken != focusToken {
            context.coordinator.focusToken = focusToken
            DispatchQueue.main.async {
                textView.window?.makeFirstResponder(textView)
            }
        }
        _ = scrollView
    }

    /// Return a DEFINITE size from the proposal instead of letting SwiftUI probe
    /// the NSScrollView/NSTextView intrinsic size. Without this, nested flexible
    /// frames (.frame(minHeight:maxHeight:)) inside an unbounded-height ScrollView
    /// probe this representable's size combinatorially → an exponential sizeThatFits
    /// pass that never completes (the Record-screen freeze; confirmed via CPU sample:
    /// leaf = PlatformViewRepresentableAdaptor.sizeThatFits under _FlexFrameLayout fan-out).
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSScrollView, context: Context) -> CGSize? {
        let w: CGFloat
        if let pw = proposal.width, pw.isFinite { w = pw } else { w = 320 }
        let h: CGFloat
        if let ph = proposal.height, ph.isFinite { h = ph } else { h = 120 }
        return CGSize(width: w, height: h)
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: String
        @Binding var measuredHeight: CGFloat
        weak var textView: CommandReturnTextView?
        var focusToken = 0

        init(text: Binding<String>, measuredHeight: Binding<CGFloat>) {
            self._text = text
            self._measuredHeight = measuredHeight
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            text = textView.string
            recomputeHeight()
        }

        /// Measure the laid-out text height so the composer can grow with content.
        /// Reports the glyph-box height + the text container's vertical insets;
        /// the SwiftUI side clamps it between one line and a max before scrolling.
        func recomputeHeight() {
            guard let textView,
                  let layoutManager = textView.layoutManager,
                  let container = textView.textContainer else { return }
            layoutManager.ensureLayout(for: container)
            let used = layoutManager.usedRect(for: container).height
            let height = used + textView.textContainerInset.height * 2
            if abs(height - measuredHeight) > 0.5 {
                measuredHeight = height
            }
        }
    }
}

final class CommandReturnTextView: NSTextView {
    var onCommandReturn: (() -> Void)?
    var onPasteImage: ((NSImage) -> Void)?
    var onPasteFileURLs: (([URL]) -> Void)?

    private static let imagePasteboardTypes: [NSPasteboard.PasteboardType] = [
        .png,
        .tiff,
        NSPasteboard.PasteboardType("public.jpeg"),
        NSPasteboard.PasteboardType("public.heic"),
        NSPasteboard.PasteboardType("com.apple.icns"),
        NSPasteboard.PasteboardType("com.adobe.pdf"),
    ]

    static func image(from pasteboard: NSPasteboard) -> NSImage? {
        if let images = pasteboard.readObjects(forClasses: [NSImage.self], options: nil) as? [NSImage],
           let image = images.first {
            return image
        }
        for type in imagePasteboardTypes {
            if let data = pasteboard.data(forType: type), let image = NSImage(data: data) {
                return image
            }
        }
        return nil
    }

    static func canPasteAttachment(from pasteboard: NSPasteboard) -> Bool {
        if image(from: pasteboard) != nil { return true }
        return pasteboard.canReadObject(
            forClasses: [NSURL.self],
            options: [.urlReadingFileURLsOnly: true]
        )
    }

    // ⌘V 粘贴:判定交给 PastedContentClassifier(纯函数,单测覆盖)。
    // 首版"有文本就放弃图"挡掉了浏览器拷图(图+URL文本)和 Finder 拷文件(file-url+文件名),
    // 现按内容形态分流:文件→附原文件;位图(伴生 URL 文本也算)→附图;散文→纯文本粘贴。
    override func paste(_ sender: Any?) {
        let pb = NSPasteboard.general
        let fileURLs = (pb.readObjects(
            forClasses: [NSURL.self],
            options: [.urlReadingFileURLsOnly: true]
        ) as? [URL]) ?? []
        // 位图形态因来源而异:截屏=png/tiff;微信/照片=public.jpeg;预览选区=com.adobe.pdf;
        // 微信临时文件还可能是奇怪扩展名的 file-url(走不进 attachable 文件分支)。
        // 只认 png/tiff 会漏掉这些(实测用户"贴不进") → 放宽为"NSImage 能读的都算图"。
        let bitmapImage = Self.image(from: pb)
        let decision = PastedContentClassifier.decide(
            pastedString: pb.string(forType: .string),
            hasBitmapImage: bitmapImage != nil,
            fileURLs: fileURLs
        )
        // 回调未接线或位图读取失败 → 回退 super.paste,绝不吞掉一次粘贴(Rule#1)。
        switch decision {
        case .attachFiles(let urls):
            if let onPasteFileURLs {
                onPasteFileURLs(urls)
                return
            }
        case .attachBitmap:
            if let onPasteImage,
               let image = bitmapImage {
                onPasteImage(image)
                return
            }
        case .pasteText:
            break
        }
        super.paste(sender)
    }

    // 纯图片剪贴板(如 ⌘⇧⌃4 截图,只有位图、无文本)时,基类 isRichText=false 只声明
    // 文本可读类型 → 系统在调用上面的 paste() 前就把 paste: 判为无效:右键"粘贴"置灰、
    // ⌘V 无响应,处理图片的 paste() 覆写永远进不去(实测:之前只有"图+URL文本"的浏览器
    // 拷图能贴,就是因为那时剪贴板有文本让 paste: 有效)。这里补声明图片/文件可读类型 +
    // 显式放行 paste:,让纯图剪贴板下粘贴也生效。
    override var readablePasteboardTypes: [NSPasteboard.PasteboardType] {
        super.readablePasteboardTypes + Self.imagePasteboardTypes + [.fileURL]
    }

    override func validateUserInterfaceItem(_ item: NSValidatedUserInterfaceItem) -> Bool {
        if item.action == #selector(NSTextView.paste(_:)) {
            if Self.canPasteAttachment(from: .general) { return true }
        }
        return super.validateUserInterfaceItem(item)
    }

    override func keyDown(with event: NSEvent) {
        // 回车提交查询;⇧回车换行。输入法组字中(拼音候选)按回车是确认候选,
        // 不能当提交 —— hasMarkedText() 为真时交还给输入法,确认完下一次回车才提交。
        if event.charactersIgnoringModifiers == "\r", !hasMarkedText() {
            let mods = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            if mods.contains(.shift) {
                super.keyDown(with: event)   // ⇧回车 = 换行
                return
            }
            onCommandReturn?()               // 回车 / ⌘回车 = 提交
            return
        }
        super.keyDown(with: event)
    }
}

struct RecordHubView: View {
    let client: RecordClient
    let productClient: SupplementProductLibraryClient
    let labUploadClient: LabUploadClient
    @Bindable var viewModel: TodayViewModel
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var quickText = ""
    @State private var recordType = StructuredRecordDraftType.diet
    @State private var foodName = ""
    @State private var calories = ""
    @State private var protein = ""
    @State private var waterMl = "250"
    @State private var supplementName = ""
    @State private var supplementDose = ""
    @State private var isSupplementLibraryOpen = false
    @State private var supplementProductSearch = ""
    @State private var supplementProductResults: [SupplementProductSummary] = []
    @State private var selectedSupplementProduct: SupplementProductSummary?
    @State private var isSearchingSupplementProducts = false
    @State private var supplementProductMessage: String?
    @State private var frequentSupplements: [FrequentSupplement] = []
    @State private var frequentWater: [FrequentWater] = []
    @State private var weightKg = ""
    @State private var systolic = ""
    @State private var diastolic = ""
    @State private var symptom = ""
    @State private var sneezeCount = ""
    @State private var nasalWashCount = ""
    @State private var exerciseType = ""
    @State private var reps = ""
    @State private var sets = "1"
    @State private var exerciseDuration = ""
    @State private var moodScore = ""
    @State private var moodNote = ""
    @State private var glucoseValue = ""
    @State private var glucoseUnit = "mmol"
    @State private var excretionType = "bowel"
    @State private var stoolType = ""
    @State private var excretionNotes = ""
    @State private var myMedications: [MedicationOption] = []
    @State private var recentRecords: [String] = []
    @State private var resultMessage: String?
    @State private var lastSavedRecord: QuickRecordResult?
    @State private var isSubmitting = false
    @State private var isLabImporterPresented = false
    @State private var isUploadingLab = false
    @State private var labUploadStatus: String?
    @State private var lastLabUploadResult: LabUploadResult?
    @State private var lastLabUploadFileName: String?
    @State private var lastLabUploadSourceHash: String?
    @State private var isParsingVoiceDraft = false
    @State private var isUndoing = false
    @State private var quickFocusToken = 0

    var body: some View {
        // 用 GeometryReader 读一次确定宽度来选布局,替代 ViewThatFits。
        // ViewThatFits 会为测量把整张重表单(含 NSViewRepresentable 编辑器 +
        // 自适应 LazyVGrid)构建两遍,且在 ScrollView 内反复测量 → macOS 上卡死/性能悬崖。
        // 确定性阈值布局只构建一遍,宽度稳定不震荡。
        GeometryReader { geo in
            let wide = geo.size.width >= 1000
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    recordHeader
                    recordSnapshotSection(wide: wide)

                    if wide {
                        HStack(alignment: .top, spacing: 16) {
                            VStack(alignment: .leading, spacing: 16) {
                                quickCaptureCard
                                labUploadCard
                                structuredCaptureCard
                            }
                            .frame(minWidth: 600, maxWidth: .infinity, alignment: .topLeading)

                            VStack(alignment: .leading, spacing: 16) {
                                saveStatusPanel
                                recentRecordsPanel
                            }
                            .frame(width: 360, alignment: .topLeading)
                        }
                    } else {
                        VStack(alignment: .leading, spacing: 16) {
                            quickCaptureCard
                            labUploadCard
                            structuredCaptureCard
                            saveStatusPanel
                            recentRecordsPanel
                        }
                    }
                }
                .padding(24)
            }
            .background(
                LinearGradient(
                    colors: [
                        Color(nsColor: .windowBackgroundColor),
                        Color.green.opacity(0.05),
                        Color(nsColor: .windowBackgroundColor)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .ignoresSafeArea()
            )
            .onAppear {
                quickFocusToken += 1
                if viewModel.bootstrap == nil {
                    Task { await viewModel.refresh() }
                }
            }
            .task { await loadFrequentSuggestions() }
        }
        .fileImporter(
            isPresented: $isLabImporterPresented,
            allowedContentTypes: [.pdf, .image],
            allowsMultipleSelection: false
        ) { result in
            Task { await uploadLabFile(result: result) }
        }
    }

    /// 拉「常吃补剂 / 常喝饮水」建议；best-effort，失败静默成空(不打扰记录主流程)。
    private func loadFrequentSuggestions() async {
        async let supplements = try? client.fetchFrequentSupplements()
        async let water = try? client.fetchFrequentWater()
        async let meds = client.fetchMyMedications()
        frequentSupplements = await supplements ?? []
        frequentWater = await water ?? []
        myMedications = await meds
    }

    private var recordHeader: some View {
        HStack(alignment: .center, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text(appText("Record", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Capture food, water, supplements, vitals, and symptoms without leaving the keyboard.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            recordModeBadge
        }
    }

    private var recordModeBadge: some View {
        Label(appText(isSubmitting ? "Saving..." : "Ready", appLanguageRaw), systemImage: isSubmitting ? "hourglass" : "checkmark.circle")
            .font(.caption.bold())
            .foregroundStyle(isSubmitting ? .orange : .green)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background((isSubmitting ? Color.orange : Color.green).opacity(0.12), in: Capsule())
    }

    @ViewBuilder
    private func recordSnapshotSection(wide: Bool) -> some View {
        if let presentation = recordPresentation {
            recordSnapshotPanel(presentation, wide: wide)
        } else {
            HStack(spacing: 10) {
                ProgressView()
                    .controlSize(.small)
                Text(appText("Loading desktop context...", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
            }
        }
    }

    private var recordPresentation: DesktopRecordHubPresentation? {
        viewModel.bootstrap.map { DesktopRecordHubPresentation(summary: $0.recentRecordsSummary) }
    }

    private func recordSnapshotPanel(_ presentation: DesktopRecordHubPresentation, wide: Bool) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 12) {
                Label(appText("Recent Record Snapshot", appLanguageRaw), systemImage: "calendar.badge.clock")
                    .font(.headline)
                if let date = presentation.date {
                    Text(date)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    Task { await viewModel.refresh() }
                } label: {
                    Label(appText("Refresh", appLanguageRaw), systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.isLoading)
            }

            if wide {
                HStack(alignment: .top, spacing: 12) {
                    recordMetricGroup(
                        title: appText("Today", appLanguageRaw),
                        subtitle: appText("Latest day", appLanguageRaw),
                        metrics: presentation.todayMetrics
                    )
                    recordMetricGroup(
                        title: appText("7 days", appLanguageRaw),
                        subtitle: appText("Average and trend baseline", appLanguageRaw),
                        metrics: presentation.sevenDayMetrics
                    )
                    recentServerRecords(presentation.recentRows)
                        .frame(width: 320)
                }
            } else {
                VStack(alignment: .leading, spacing: 12) {
                    recordMetricGroup(
                        title: appText("Today", appLanguageRaw),
                        subtitle: appText("Latest day", appLanguageRaw),
                        metrics: presentation.todayMetrics
                    )
                    recordMetricGroup(
                        title: appText("7 days", appLanguageRaw),
                        subtitle: appText("Average and trend baseline", appLanguageRaw),
                        metrics: presentation.sevenDayMetrics
                    )
                    recentServerRecords(presentation.recentRows)
                }
            }

            if let error = viewModel.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private func recordMetricGroup(title: String, subtitle: String, metrics: [DesktopDashboardMetric]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(title)
                    .font(.headline.weight(.semibold))
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 8)], spacing: 8) {
                ForEach(metrics) { metric in
                    recordMetricTile(metric)
                }
            }
        }
        .padding(14)
        .background(Color.secondary.opacity(0.055), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func recordMetricTile(_ metric: DesktopDashboardMetric) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: metric.systemImage)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(recordToneColor(metric.tone))
                    .frame(width: 24, height: 24)
                    .background(recordToneColor(metric.tone).opacity(0.12), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                Text(appText(metric.titleKey, appLanguageRaw))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Text(metric.value)
                .font(.title3.weight(.bold))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.78)
            Text(localizedRecordDetail(metric.detail))
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(recordToneColor(metric.tone).opacity(0.07), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(recordToneColor(metric.tone).opacity(0.12), lineWidth: 1)
        }
    }

    private func recentServerRecords(_ rows: [DesktopDashboardRow]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(appText("Recent Health Records", appLanguageRaw), systemImage: "waveform.path.ecg")
                .font(.headline.weight(.semibold))

            if rows.isEmpty {
                recordEmptyState(text: appText("No recent health records loaded.", appLanguageRaw))
                    .frame(maxWidth: .infinity, minHeight: 118)
            } else {
                VStack(spacing: 0) {
                    ForEach(rows) { row in
                        HStack(spacing: 9) {
                            Image(systemName: row.systemImage)
                                .foregroundStyle(recordToneColor(row.tone))
                                .frame(width: 24, height: 24)
                                .background(recordToneColor(row.tone).opacity(0.12), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.title)
                                    .font(.callout.weight(.semibold))
                                    .lineLimit(1)
                                if let subtitle = row.subtitle {
                                    Text(subtitle)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                            }
                            Spacer()
                            if let value = row.value {
                                Text(value)
                                    .font(.caption.weight(.semibold))
                                    .monospacedDigit()
                                    .lineLimit(1)
                            }
                        }
                        .padding(.vertical, 8)
                        if row.id != rows.last?.id {
                            Divider().padding(.leading, 33)
                        }
                    }
                }
            }
        }
        .padding(14)
        .background(Color.secondary.opacity(0.055), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func localizedRecordDetail(_ detail: String) -> String {
        detail
            .replacingOccurrences(of: "records", with: appText("records", appLanguageRaw))
            .replacingOccurrences(of: "No record", with: appText("No record", appLanguageRaw))
            .replacingOccurrences(of: "Avg", with: appText("Avg", appLanguageRaw))
            .replacingOccurrences(of: "/day", with: appText("/day", appLanguageRaw))
            .replacingOccurrences(of: "Adherence", with: appText("Adherence", appLanguageRaw))
            .replacingOccurrences(of: "active", with: appText("active", appLanguageRaw))
    }

    private func recordEmptyState(text: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "tray")
                .font(.system(size: 24))
                .foregroundStyle(.secondary)
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
    }

    private func recordToneColor(_ tone: String) -> Color {
        switch tone {
        case "orange": .orange
        case "cyan": .cyan
        case "green": .green
        case "pink": .pink
        case "purple": .purple
        case "blue": .blue
        case "red": .red
        case "indigo": .indigo
        case "teal": .teal
        default: .secondary
        }
    }

    private var quickCaptureCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(appText("Natural Language", appLanguageRaw), systemImage: "bolt.fill")
                    .font(.headline)
                Text(appText("Best for fast food, water, supplement, or symptom notes.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text("↩ 发送 · ⇧↩ 换行")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(Color.secondary.opacity(0.10), in: Capsule())
            }

            ZStack(alignment: .topLeading) {
                PromptCommandTextEditor(text: $quickText, focusToken: quickFocusToken) {
                    Task { await submit(text: quickText) }
                }
                .frame(minHeight: 118, maxHeight: 180)

                if quickText.isEmpty {
                    Text(appText("Example: dinner had half rice, beef, broccoli; drank 500ml water", appLanguageRaw))
                        .foregroundStyle(.secondary)
                        .padding(.top, 12)
                        .padding(.leading, 8)
                        .allowsHitTesting(false)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
            }

            FlowLayout(spacing: 8) {
                ForEach(quickTemplates, id: \.self) { template in
                    Button {
                        quickText = template
                        quickFocusToken += 1
                    } label: {
                        Text(template)
                            .lineLimit(1)
                    }
                    .buttonStyle(.plain)
                    .font(.caption)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.secondary.opacity(0.09), in: Capsule())
                    .disabled(isSubmitting)
                }
            }

            HStack {
                Button(appText(isSubmitting ? "Saving..." : "Save Natural", appLanguageRaw)) {
                    Task { await submit(text: quickText) }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isSubmitting || quickText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .keyboardShortcut(.return, modifiers: .command)

                Button(appText("Clear", appLanguageRaw)) {
                    quickText = ""
                    quickFocusToken += 1
                }
                .disabled(quickText.isEmpty || isSubmitting)

                Spacer()
                Text(appText("Quick parser will infer record type.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private var labUploadCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 10) {
                Label(appText("Import Medical Exam Report", appLanguageRaw), systemImage: "doc.badge.arrow.up")
                    .font(.headline)
                Text(appText("PDF or image report", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                if isUploadingLab {
                    ProgressView()
                        .controlSize(.small)
                }
            }

            HStack(alignment: .center, spacing: 10) {
                Button {
                    isLabImporterPresented = true
                } label: {
                    Label(appText("Choose Report", appLanguageRaw), systemImage: "tray.and.arrow.up")
                }
                .buttonStyle(.borderedProminent)
                .disabled(isUploadingLab)

                Text(appText("After import, review OCR values before using them for health decisions.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)

                Spacer()
            }

            if let labUploadStatus {
                Label(
                    labUploadStatus,
                    systemImage: lastLabUploadResult == nil ? "info.circle" : "checkmark.circle.fill"
                )
                .font(.callout)
                .foregroundStyle(lastLabUploadResult == nil ? Color.secondary : Color.green)
                .lineLimit(3)
            }

            if let result = lastLabUploadResult {
                let presentation = LabUploadPresentation.make(result: result, fileName: lastLabUploadFileName)
                HStack(alignment: .center, spacing: 12) {
                    Image(systemName: "stethoscope")
                        .font(.title3)
                        .foregroundStyle(.teal)
                        .frame(width: 30, height: 30)
                        .background(Color.teal.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    VStack(alignment: .leading, spacing: 4) {
                        Text(presentation.title)
                            .font(.callout.weight(.semibold))
                            .lineLimit(1)
                        Text(presentation.summary)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                    Spacer()
                    if let onAskAgent {
                        Button {
                            onAskAgent(
                                presentation.agentPrompt,
                                labUploadContextItem(result)
                            )
                        } label: {
                            Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding(12)
                .background(Color.teal.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(Color.teal.opacity(0.16), lineWidth: 1)
                }
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private var quickTemplates: [String] {
        [
            appText("Drank 500ml water", appLanguageRaw),
            appText("Took fish oil after dinner", appLanguageRaw),
            appText("Weight 70.2kg this morning", appLanguageRaw),
            appText("Blood pressure 119/75", appLanguageRaw)
        ]
    }

    private var structuredCaptureCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(appText("Structured Form", appLanguageRaw), systemImage: "text.badge.checkmark")
                    .font(.headline)
                Text(appText("Use when values must be precise.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
            }

            typeSelectorGrid
            structuredFields

            HStack {
                Button(appText("Use Preview", appLanguageRaw)) {
                    quickText = structuredText()
                    quickFocusToken += 1
                }
                .disabled(!structuredDraft.canSubmit)

                Button(appText(isSubmitting ? "Saving..." : "Save Structured", appLanguageRaw)) {
                    Task { await submitStructured() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isSubmitting || !structuredDraft.canSubmit)
                .keyboardShortcut(.return, modifiers: .command)

                Spacer()
                Text(appText("Typed endpoint, audit-friendly.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private var typeSelectorGrid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 118), spacing: 8)], spacing: 8) {
            ForEach(StructuredRecordDraftType.allCases) { type in
                let isSelected = recordType == type
                Button {
                    recordType = type
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: type.systemImage)
                            .foregroundStyle(recordTypeColor(type))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(appText(type.title, appLanguageRaw))
                                .font(.callout.weight(.semibold))
                            Text(recordTypeHint(type))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 9)
                    .background(
                        isSelected ? recordTypeColor(type).opacity(0.18) : Color.secondary.opacity(0.07),
                        in: RoundedRectangle(cornerRadius: 10, style: .continuous)
                    )
                    .overlay {
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .stroke(isSelected ? recordTypeColor(type).opacity(0.55) : Color.secondary.opacity(0.08), lineWidth: 1)
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var saveStatusPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(appText("Current Draft", appLanguageRaw), systemImage: "doc.text.magnifyingglass")
                .font(.headline)

            VStack(alignment: .leading, spacing: 8) {
                Text(appText("Structured Preview", appLanguageRaw))
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                Text(structuredDraft.canSubmit ? structuredText() : appText("Fill structured fields to preview the saved record.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(structuredDraft.canSubmit ? .primary : .secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(12)
            .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

            if let resultMessage {
                Label(resultMessage, systemImage: lastSavedRecord == nil ? "info.circle" : "checkmark.circle.fill")
                    .font(.callout)
                    .foregroundStyle(lastSavedRecord == nil ? Color.secondary : Color.green)
                    .lineLimit(3)
            } else {
                Text(appText("Saved results and undo controls will appear here.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let lastSavedRecord {
                savedRecordCard(lastSavedRecord)
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private var recentRecordsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(appText("Recent Local Records", appLanguageRaw), systemImage: "clock.arrow.circlepath")
                    .font(.headline)
                Spacer()
                Text("\(recentRecords.count)")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
            }

            if recentRecords.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "tray")
                        .font(.system(size: 26))
                        .foregroundStyle(.secondary)
                    Text(appText("Recent saved commands in this Mac session will appear here.", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else {
                ForEach(recentRecords, id: \.self) { record in
                    HStack(spacing: 10) {
                        Image(systemName: "text.badge.checkmark")
                            .foregroundStyle(.green)
                            .frame(width: 24, height: 24)
                            .background(Color.green.opacity(0.12), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                        Text(record)
                            .font(.callout)
                            .lineLimit(2)
                        Spacer()
                        if let onAskAgent {
                            Button {
                                let contextItem = AgentContextItem(
                                    sourceID: "record-\(record.hashValue)",
                                    sourceKind: "record_hub_recent",
                                    title: appText("Recent Local Records", appLanguageRaw),
                                    summary: record
                                )
                                onAskAgent("基于这条刚记录的内容，给我一段简短分析和后续建议：\n\(record)", contextItem)
                            } label: {
                                Image(systemName: "sparkles")
                            }
                            .buttonStyle(.borderless)
                            .foregroundStyle(.tint)
                            .help(appText("Ask Agent with Context", appLanguageRaw))
                        }
                        Button {
                            quickText = record
                            quickFocusToken += 1
                        } label: {
                            Image(systemName: "arrow.uturn.backward")
                        }
                        .buttonStyle(.borderless)
                        .help(appText("Reuse", appLanguageRaw))
                        Button {
                            recentRecords.removeAll { $0 == record }
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                        .foregroundStyle(.secondary)
                        .help(appText("Delete", appLanguageRaw))
                    }
                    .padding(10)
                    .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        }
    }

    private func savedRecordCard(_ record: QuickRecordResult) -> some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: "checkmark.circle.fill")
                .font(.title3)
                .foregroundStyle(.green)
            VStack(alignment: .leading, spacing: 4) {
                Text(record.message)
                    .font(.headline)
                if let recordID = record.recordID {
                    Text("#\(recordID) · \(record.type)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if let undoPath = record.undoPath {
                Button(appText(isUndoing ? "Undoing..." : "Undo", appLanguageRaw)) {
                    Task { await undoSavedRecord(path: undoPath) }
                }
                .disabled(isUndoing)
            }
        }
        .padding(12)
        .background(Color.green.opacity(0.10), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    @ViewBuilder
    private var structuredFields: some View {
        switch recordType {
        case .diet:
            recordTextField(appText("Food name or photo description", appLanguageRaw), text: $foodName)
            Button(appText(isParsingVoiceDraft ? "Parsing Voice Draft..." : "Parse Voice Draft", appLanguageRaw)) {
                Task { await parseVoiceDietDraft() }
            }
            .buttonStyle(.bordered)
            .disabled(isParsingVoiceDraft || foodName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            HStack {
                recordTextField(appText("Calories kcal", appLanguageRaw), text: $calories)
                recordTextField(appText("Protein g", appLanguageRaw), text: $protein)
            }
        case .water:
            frequentWaterChips
            recordTextField(appText("Amount ml", appLanguageRaw), text: $waterMl)
        case .supplement:
            supplementFields
        case .weight:
            recordTextField(appText("Weight kg", appLanguageRaw), text: $weightKg)
        case .bloodPressure:
            HStack {
                recordTextField(appText("Systolic", appLanguageRaw), text: $systolic)
                recordTextField(appText("Diastolic", appLanguageRaw), text: $diastolic)
            }
        case .symptom:
            recordTextField(appText("Symptom, severity, and context", appLanguageRaw), text: $symptom)
        case .sneeze:
            recordTextField(appText("Sneeze count today", appLanguageRaw), text: $sneezeCount)
        case .nasalWash:
            recordTextField(appText("Nasal wash count today", appLanguageRaw), text: $nasalWashCount)
        case .exercise:
            exerciseFields
        case .medication:
            medicationChips
        case .mood:
            VStack(alignment: .leading, spacing: 10) {
                recordTextField(appText("Mood score 1-10", appLanguageRaw), text: $moodScore)
                recordTextField(appText("Note (optional)", appLanguageRaw), text: $moodNote)
            }
        case .bloodGlucose:
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    recordTextField(appText("Glucose value", appLanguageRaw), text: $glucoseValue)
                    Picker("", selection: $glucoseUnit) {
                        Text("mmol/L").tag("mmol")
                        Text("mg/dL").tag("mgdl")
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 150)
                    .labelsHidden()
                }
            }
        case .excretion:
            VStack(alignment: .leading, spacing: 10) {
                Picker("", selection: $excretionType) {
                    Text(appText("Bowel", appLanguageRaw)).tag("bowel")
                    Text(appText("Urine", appLanguageRaw)).tag("urine")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                if excretionType == "bowel" {
                    recordTextField(appText("Bristol type 1-7 (optional)", appLanguageRaw), text: $stoolType)
                }
                recordTextField(appText("Note (optional)", appLanguageRaw), text: $excretionNotes)
            }
        }
    }

    @ViewBuilder
    private var medicationChips: some View {
        if myMedications.isEmpty {
            Text(appText("No active medications. Add them on web first.", appLanguageRaw))
                .font(.caption)
                .foregroundStyle(.secondary)
        } else {
            VStack(alignment: .leading, spacing: 10) {
                frequentChipsRow(
                    label: appText("Tap a medication to log a dose", appLanguageRaw),
                    icon: "cross.case.fill",
                    tint: .red,
                    chips: myMedications.map { FrequentChipModel(id: "\($0.id)", title: $0.name, meta: $0.dosage) }
                ) { index in
                    let med = myMedications[index]
                    Task { await logMedicationDose(med) }
                }

                if !medicationSafetyAlerts.isEmpty {
                    medicationSafetyAlertsPanel
                }
            }
        }
    }

    private var medicationSafetyAlerts: [MedicationSafetyAlert] {
        myMedications
            .flatMap(\.safetyAlerts)
            .sorted { $0.severity.value > $1.severity.value }
    }

    private var medicationSafetyAlertsPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(appText("Medication safety alerts", appLanguageRaw), systemImage: "exclamationmark.triangle.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.orange)
            ForEach(Array(medicationSafetyAlerts.prefix(3).enumerated()), id: \.offset) { _, alert in
                VStack(alignment: .leading, spacing: 3) {
                    Text("\(alert.severity.labelZH) · \(alert.title)")
                        .font(.caption.weight(.semibold))
                    Text(alert.action ?? alert.message)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            Text(appText("Medication safety alerts are risk stratification, not a diagnosis or prescription decision.", appLanguageRaw))
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(10)
        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Color.orange.opacity(0.18), lineWidth: 1)
        }
    }

    private func logMedicationDose(_ med: MedicationOption) async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            let result = try await client.logMedication(medicationID: med.id, name: med.name, dosage: med.dosage)
            _ = handleRecordResult(result, fallbackText: med.name)
            await viewModel.refresh()
        } catch {
            resultMessage = "Save failed: \(userFacingError(error, appLanguageRaw))"
        }
    }

    private var exerciseFields: some View {
        VStack(alignment: .leading, spacing: 10) {
            recordTextField(appText("Exercise type", appLanguageRaw), text: $exerciseType)
            exerciseRepPresets
            HStack {
                recordTextField(appText("Reps", appLanguageRaw), text: $reps)
                recordTextField(appText("Sets", appLanguageRaw), text: $sets)
                recordTextField(appText("Duration min", appLanguageRaw), text: $exerciseDuration)
            }
        }
    }

    // Quick rep presets, mirroring the Web PushupCard (+10/+15/+20/+30/+50).
    // Tapping fills reps; if no exercise type yet, defaults to 俯卧撑.
    private var exerciseRepPresets: some View {
        VStack(alignment: .leading, spacing: 7) {
            Label(appText("Common reps · one tap to fill", appLanguageRaw), systemImage: "bolt.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            HStack(spacing: 8) {
                ForEach([10, 15, 20, 30, 50], id: \.self) { count in
                    Button {
                        reps = "\(count)"
                        if sets.trimmingCharacters(in: .whitespaces).isEmpty { sets = "1" }
                        if exerciseType.trimmingCharacters(in: .whitespaces).isEmpty {
                            exerciseType = "俯卧撑"
                        }
                    } label: {
                        Text("+\(count)")
                            .font(.callout.weight(.semibold))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 7)
                            .background(Color.green.opacity(0.12), in: Capsule())
                            .overlay { Capsule().stroke(Color.green.opacity(0.22), lineWidth: 1) }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func recordTextField(_ placeholder: String, text: Binding<String>) -> some View {
        TextField(placeholder, text: text)
            .textFieldStyle(.plain)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
            }
    }

    private var supplementFields: some View {
        VStack(alignment: .leading, spacing: 10) {
            frequentSupplementChips
            HStack {
                recordTextField(appText("Supplement", appLanguageRaw), text: $supplementName)
                Button {
                    isSupplementLibraryOpen.toggle()
                    if isSupplementLibraryOpen && supplementProductSearch.isEmpty {
                        supplementProductSearch = supplementName
                    }
                } label: {
                    Label(appText("Choose from Supplement Library", appLanguageRaw), systemImage: "books.vertical")
                }
                .buttonStyle(.bordered)
            }

            recordTextField(appText("Dose and timing", appLanguageRaw), text: $supplementDose)

            if let selectedSupplementProduct {
                HStack(spacing: 8) {
                    Label(
                        "\(appText("Linked Product", appLanguageRaw)) #\(selectedSupplementProduct.id)",
                        systemImage: "checkmark.seal.fill"
                    )
                    .foregroundStyle(.green)
                    Text(selectedSupplementProduct.displayName)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer()
                    Button(appText("Clear", appLanguageRaw)) {
                        self.selectedSupplementProduct = nil
                    }
                    .buttonStyle(.borderless)
                }
                .font(.caption)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Color.green.opacity(0.09), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            }

            if isSupplementLibraryOpen {
                supplementLibraryPicker
            }
        }
    }

    private var supplementLibraryPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField(appText("Search brand or product name", appLanguageRaw), text: $supplementProductSearch)
                    .textFieldStyle(.plain)
                    .onSubmit {
                        Task { await searchSupplementProducts() }
                    }
                Button(appText("Search", appLanguageRaw)) {
                    Task { await searchSupplementProducts() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(isSearchingSupplementProducts || supplementProductSearch.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(Color.purple.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

            if isSearchingSupplementProducts {
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text(appText("Searching supplement library...", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else if let supplementProductMessage {
                Text(supplementProductMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if !supplementProductResults.isEmpty {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(supplementProductResults) { product in
                        Button {
                            selectSupplementProduct(product)
                        } label: {
                            supplementProductRow(product)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(12)
        .background(Color.purple.opacity(0.06), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.purple.opacity(0.16), lineWidth: 1)
        }
    }

    private func supplementProductRow(_ product: SupplementProductSummary) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "pills.fill")
                .foregroundStyle(.purple)
                .frame(width: 26, height: 26)
                .background(Color.purple.opacity(0.13), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(product.displayName)
                    .font(.callout.weight(.semibold))
                    .lineLimit(1)
                HStack(spacing: 8) {
                    if let servingSize = product.servingSize, !servingSize.isEmpty {
                        Text(servingSize)
                    }
                    if let category = product.category, !category.isEmpty {
                        Text(appText(category, appLanguageRaw))
                    }
                    if let price = product.priceCny {
                        Text("¥\(Int(price.rounded()))")
                            .foregroundStyle(.green)
                    }
                    if let rating = product.rating {
                        Text("★ \(String(format: "%.1f", rating))")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                if !product.healthTags.isEmpty {
                    Text(product.healthTags.prefix(3).joined(separator: " · "))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            Image(systemName: "plus.circle.fill")
                .foregroundStyle(.purple)
        }
        .padding(10)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func searchSupplementProducts() async {
        let query = supplementProductSearch.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else {
            supplementProductResults = []
            supplementProductMessage = appText("Enter a product keyword first.", appLanguageRaw)
            return
        }
        isSearchingSupplementProducts = true
        supplementProductMessage = nil
        defer { isSearchingSupplementProducts = false }
        do {
            let response = try await productClient.searchProducts(query: query)
            supplementProductResults = response.items
            supplementProductMessage = response.items.isEmpty
                ? appText("No matching products. You can still enter manually.", appLanguageRaw)
                : "\(response.total) \(appText("products found", appLanguageRaw))"
        } catch {
            supplementProductResults = []
            supplementProductMessage = "\(appText("Search failed", appLanguageRaw)): \(userFacingError(error, appLanguageRaw))"
        }
    }

    private struct FrequentChipModel: Identifiable {
        let id: String
        let title: String
        let meta: String?
    }

    @ViewBuilder
    private var frequentWaterChips: some View {
        if !frequentWater.isEmpty {
            frequentChipsRow(
                label: appText("Frequent · one tap to log", appLanguageRaw),
                icon: "drop.fill",
                tint: .cyan,
                chips: frequentWater.map { water in
                    let type = water.drinkType ?? ""
                    let suffix = (type.isEmpty || type == "水") ? "" : " \(type)"
                    return FrequentChipModel(id: water.id, title: "\(water.amountMl)ml\(suffix)", meta: nil)
                }
            ) { index in
                let water = frequentWater[index]
                Task { await recordFrequentWater(water) }
            }
        }
    }

    @ViewBuilder
    private var frequentSupplementChips: some View {
        if !frequentSupplements.isEmpty {
            frequentChipsRow(
                label: appText("Frequent · one tap to check in", appLanguageRaw),
                icon: "pills.fill",
                tint: .purple,
                chips: frequentSupplements.map { FrequentChipModel(id: "\($0.id)", title: $0.name, meta: $0.dosage) }
            ) { index in
                let supplement = frequentSupplements[index]
                Task { await checkinFrequentSupplement(supplement) }
            }
        }
    }

    private func frequentChipsRow(
        label: String,
        icon: String,
        tint: Color,
        chips: [FrequentChipModel],
        onPick: @escaping (Int) -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Label(label, systemImage: icon)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Array(chips.enumerated()), id: \.element.id) { index, chip in
                        Button {
                            onPick(index)
                        } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(chip.title)
                                    .font(.callout.weight(.semibold))
                                    .lineLimit(1)
                                if let meta = chip.meta, !meta.isEmpty {
                                    Text(meta)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(tint.opacity(0.10), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .overlay {
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .stroke(tint.opacity(0.22), lineWidth: 1)
                            }
                        }
                        .buttonStyle(.plain)
                        .disabled(isSubmitting)
                    }
                }
                .padding(.vertical, 1)
            }
        }
    }

    private func recordFrequentWater(_ water: FrequentWater) async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            let result = try await client.recordWater(amountMl: water.amountMl, drinkType: water.drinkType ?? "水")
            if handleRecordResult(result, fallbackText: "\(water.amountMl)ml") {
                await viewModel.refresh()
            }
        } catch {
            resultMessage = "Save failed: \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func checkinFrequentSupplement(_ supplement: FrequentSupplement) async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            let result = try await client.checkinSupplement(supplementID: supplement.supplementID, name: supplement.name)
            _ = handleRecordResult(result, fallbackText: supplement.name)
            await viewModel.refresh()
        } catch {
            resultMessage = "Save failed: \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func selectSupplementProduct(_ product: SupplementProductSummary) {
        selectedSupplementProduct = product
        supplementName = product.displayName
        supplementDose = product.servingSize ?? supplementDose
        supplementProductSearch = ""
        supplementProductResults = []
        supplementProductMessage = nil
        isSupplementLibraryOpen = false
    }

    private func recordTypeHint(_ type: StructuredRecordDraftType) -> String {
        switch type {
        case .diet:
            return appText("food", appLanguageRaw)
        case .water:
            return appText("ml", appLanguageRaw)
        case .supplement:
            return appText("dose", appLanguageRaw)
        case .weight:
            return appText("kg", appLanguageRaw)
        case .bloodPressure:
            return appText("mmHg", appLanguageRaw)
        case .symptom:
            return appText("context", appLanguageRaw)
        case .sneeze:
            return appText("times", appLanguageRaw)
        case .nasalWash:
            return appText("times", appLanguageRaw)
        case .exercise:
            return appText("reps/min", appLanguageRaw)
        case .medication:
            return appText("one tap", appLanguageRaw)
        case .mood:
            return appText("1-10", appLanguageRaw)
        case .bloodGlucose:
            return appText("mmol/L", appLanguageRaw)
        case .excretion:
            return appText("bowel/urine", appLanguageRaw)
        }
    }

    private func recordTypeColor(_ type: StructuredRecordDraftType) -> Color {
        switch type {
        case .diet:
            return .orange
        case .water:
            return .cyan
        case .supplement:
            return .purple
        case .weight:
            return .green
        case .bloodPressure:
            return .pink
        case .symptom:
            return .indigo
        case .sneeze:
            return .mint
        case .nasalWash:
            return .teal
        case .exercise:
            return .green
        case .medication:
            return .red
        case .mood:
            return .yellow
        case .bloodGlucose:
            return .pink
        case .excretion:
            return .brown
        }
    }

    private var structuredDraft: StructuredRecordDraft {
        StructuredRecordDraft(
            type: recordType,
            foodName: foodName,
            calories: calories,
            protein: protein,
            waterMl: waterMl,
            supplementName: supplementName,
            supplementDose: supplementDose,
            weightKg: weightKg,
            systolic: systolic,
            diastolic: diastolic,
            symptom: symptom,
            sneezeCount: sneezeCount,
            nasalWashCount: nasalWashCount,
            exerciseType: exerciseType,
            reps: reps,
            sets: sets,
            exerciseDuration: exerciseDuration,
            moodScore: moodScore,
            moodNote: moodNote,
            glucoseValue: glucoseValue,
            glucoseUnit: glucoseUnit,
            excretionType: excretionType,
            stoolType: stoolType,
            excretionNotes: excretionNotes
        )
    }

    private func structuredText() -> String {
        structuredDraft.previewText
    }

    private func submitStructured() async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            let draft = structuredDraft
            guard draft.canSubmit else { return }
            let result: QuickRecordResult
            switch recordType {
            case .diet:
                let food = foodName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !food.isEmpty else { return }
                result = try await client.recordDiet(
                    foodItems: food,
                    calories: draft.positiveDouble(calories),
                    protein: draft.positiveDouble(protein)
                )
            case .water:
                guard let amount = draft.positiveInt(waterMl) else { return }
                result = try await client.recordWater(amountMl: amount)
            case .supplement:
                let text = [supplementName, supplementDose]
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
                    .joined(separator: " ")
                guard !text.isEmpty else { return }
                result = try await client.quickRecord(text: "补剂\(text)")
            case .weight:
                guard let weight = draft.positiveDouble(weightKg) else { return }
                result = try await client.recordWeight(weightKg: weight)
            case .bloodPressure:
                guard let systolicValue = draft.positiveInt(systolic), let diastolicValue = draft.positiveInt(diastolic) else { return }
                result = try await client.recordBloodPressure(systolic: systolicValue, diastolic: diastolicValue)
            case .symptom:
                let text = symptom.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { return }
                result = try await client.recordSymptom(description: text)
            case .sneeze:
                guard let count = draft.positiveInt(sneezeCount) else { return }
                result = try await client.recordSneeze(count: count)
            case .nasalWash:
                guard let count = draft.positiveInt(nasalWashCount) else { return }
                result = try await client.recordNasalWash(count: count)
            case .exercise:
                let name = exerciseType.trimmingCharacters(in: .whitespacesAndNewlines)
                let repsValue = draft.positiveInt(reps)
                let durationValue = draft.positiveInt(exerciseDuration)
                guard !name.isEmpty, repsValue != nil || durationValue != nil else { return }
                result = try await client.recordExercise(
                    exerciseType: name,
                    reps: repsValue,
                    sets: repsValue != nil ? (draft.positiveInt(sets) ?? 1) : nil,
                    durationMinutes: durationValue
                )
            case .medication:
                return // 用药通过「我的用药」chip 一键打卡，不走表单提交
            case .mood:
                guard let score = draft.moodScoreValue else { return }
                result = try await client.recordMood(score: score, note: moodNote)
            case .bloodGlucose:
                guard let mgDl = draft.glucoseMgDl else { return }
                let unit = glucoseUnit == "mgdl" ? "mg/dL" : "mmol/L"
                result = try await client.recordBloodGlucose(
                    mgDl: mgDl,
                    displayText: "\(glucoseValue.trimmingCharacters(in: .whitespaces)) \(unit)"
                )
            case .excretion:
                result = try await client.recordExcretion(
                    type: excretionType,
                    stoolType: draft.positiveInt(stoolType),
                    notes: excretionNotes
                )
            }
            let didSave = handleRecordResult(result, fallbackText: draft.previewText)
            if didSave {
                clearStructuredFields()
                await viewModel.refresh()
            }
        } catch {
            resultMessage = "Save failed: \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func submit(text rawText: String) async {
        let text = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            let result = try await client.quickRecord(text: text)
            if handleRecordResult(result, fallbackText: text) {
                await viewModel.refresh()
            }
        } catch {
            resultMessage = "Save failed: \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func uploadLabFile(result: Result<[URL], Error>) async {
        do {
            guard let url = try result.get().first else { return }
            await uploadLabFile(url: url)
        } catch {
            labUploadStatus = "\(appText("Lab upload failed", appLanguageRaw)): \(userFacingError(error, appLanguageRaw))"
            lastLabUploadResult = nil
        }
    }

    private func uploadLabFile(url: URL) async {
        let didStartAccessing = url.startAccessingSecurityScopedResource()
        defer {
            if didStartAccessing {
                url.stopAccessingSecurityScopedResource()
            }
        }

        isUploadingLab = true
        labUploadStatus = appText("Uploading lab report...", appLanguageRaw)
        lastLabUploadResult = nil
        defer { isUploadingLab = false }

        do {
            let intakeItem = try await FileIntakeService.inspect(url: url)
            guard intakeItem.sourceKind == .medicalFile,
                  LabReportUploadMime.isSupported(forExtension: url.pathExtension) else {
                labUploadStatus = appText("Please choose a supported lab PDF or image.", appLanguageRaw)
                return
            }

            let result = try await labUploadClient.importReport(fileURL: url)
            lastLabUploadResult = result
            lastLabUploadFileName = intakeItem.name
            lastLabUploadSourceHash = intakeItem.sha256
            labUploadStatus = LabUploadPresentation.make(result: result, fileName: intakeItem.name).statusText
            await viewModel.refresh()
        } catch {
            labUploadStatus = "\(appText("Lab upload failed", appLanguageRaw)): \(userFacingError(error, appLanguageRaw))"
            lastLabUploadResult = nil
        }
    }

    private func labUploadResultSummary(_ result: LabUploadResult) -> String {
        LabUploadPresentation.make(result: result, fileName: lastLabUploadFileName).summary
    }

    private func labUploadContextItem(_ result: LabUploadResult) -> AgentContextItem {
        var payload: [String: String] = [
            "exam_id": "\(result.examID)",
            "message": result.message
        ]
        if let sourceHash = lastLabUploadSourceHash {
            payload["source_hash"] = sourceHash
        }
        if let fileName = lastLabUploadFileName {
            payload["file_name"] = fileName
        }
        if let examDate = result.examDate {
            payload["exam_date"] = examDate
        }
        if let examType = result.examType {
            payload["exam_type"] = examType
        }
        if let hospitalName = result.hospitalName {
            payload["hospital_name"] = hospitalName
        }
        if let itemsCount = result.itemsCount {
            payload["items_count"] = "\(itemsCount)"
        }
        if let abnormalCount = result.abnormalCount {
            payload["abnormal_count"] = "\(abnormalCount)"
        }
        if let conclusionsCount = result.conclusionsCount {
            payload["conclusions_count"] = "\(conclusionsCount)"
        }
        if let conclusion = result.conclusion {
            payload["conclusion"] = conclusion
        }
        let title = LabUploadPresentation.make(result: result, fileName: lastLabUploadFileName).title
        return AgentContextItem(
            sourceID: "medical_exam:\(result.examID)",
            sourceKind: "lab_report_import",
            title: title,
            summary: labUploadResultSummary(result),
            payload: payload
        )
    }

    private func parseVoiceDietDraft() async {
        let text = foodName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            resultMessage = appText("Paste Apple Watch/Siri transcript first.", appLanguageRaw)
            return
        }
        isParsingVoiceDraft = true
        defer { isParsingVoiceDraft = false }
        do {
            let draft = try await client.parseVoiceDietDraft(rawText: text)
            let foodText = draft.foods.map(voiceFoodLabel).filter { !$0.isEmpty }.joined(separator: "、")
            if !foodText.isEmpty {
                foodName = foodText
            }
            if let caloriesValue = sumVoiceFoods(draft.foods, keyPath: \.calories) {
                calories = formatVoiceNumber(caloriesValue)
            }
            if let proteinValue = sumVoiceFoods(draft.foods, keyPath: \.protein) {
                protein = formatVoiceNumber(proteinValue)
            }
            resultMessage = draft.needsConfirmation
                ? (draft.clarifyingQuestion ?? appText("Voice draft filled. Confirm before saving.", appLanguageRaw))
                : appText("Voice draft filled. Confirm before saving.", appLanguageRaw)
        } catch {
            resultMessage = "\(appText("Voice draft parse failed", appLanguageRaw)): \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func handleRecordResult(_ result: QuickRecordResult, fallbackText: String) -> Bool {
        resultMessage = result.displayMessage
        if result.success {
            lastSavedRecord = result.undoPath == nil ? nil : result
            quickText = ""
            recentRecords.removeAll { $0 == fallbackText }
            recentRecords.insert(fallbackText, at: 0)
            recentRecords = Array(recentRecords.prefix(8))
            return true
        }
        return false
    }

    private func undoSavedRecord(path: String) async {
        guard !isUndoing else { return }
        isUndoing = true
        defer { isUndoing = false }
        do {
            try await client.undoSavedRecord(path: path)
            lastSavedRecord = nil
            resultMessage = appText("Record undone.", appLanguageRaw)
            await viewModel.refresh()
        } catch {
            resultMessage = "\(appText("Undo failed", appLanguageRaw)): \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func clearStructuredFields() {
        switch recordType {
        case .diet:
            foodName = ""
            calories = ""
            protein = ""
        case .water:
            waterMl = "250"
        case .supplement:
            supplementName = ""
            supplementDose = ""
            selectedSupplementProduct = nil
            supplementProductSearch = ""
            supplementProductResults = []
            supplementProductMessage = nil
        case .weight:
            weightKg = ""
        case .bloodPressure:
            systolic = ""
            diastolic = ""
        case .symptom:
            symptom = ""
        case .sneeze:
            sneezeCount = ""
        case .nasalWash:
            nasalWashCount = ""
        case .exercise:
            exerciseType = ""
            reps = ""
            sets = "1"
            exerciseDuration = ""
        case .medication:
            break // chip 即时打卡，无字段可清
        case .mood:
            moodScore = ""
            moodNote = ""
        case .bloodGlucose:
            glucoseValue = ""
        case .excretion:
            stoolType = ""
            excretionNotes = ""
        }
    }

    private func voiceFoodLabel(_ food: VoiceFoodDraftItem) -> String {
        let name = food.name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return "" }
        if let quantity = food.quantity, quantity > 0 {
            return "\(name) \(formatVoiceNumber(quantity))\(food.unit ?? "")"
        }
        return name
    }

    private func sumVoiceFoods(_ foods: [VoiceFoodDraftItem], keyPath: KeyPath<VoiceFoodDraftItem, Double?>) -> Double? {
        let values = foods.compactMap { $0[keyPath: keyPath] }
        guard !values.isEmpty else { return nil }
        return values.reduce(0, +)
    }

    private func formatVoiceNumber(_ value: Double) -> String {
        let rounded = (value * 10).rounded() / 10
        if rounded.rounded() == rounded {
            return String(Int(rounded))
        }
        return String(format: "%.1f", rounded)
    }
}

private extension StructuredRecordDraftType {
    var title: String {
        switch self {
        case .diet: "Diet"
        case .water: "Water"
        case .supplement: "Supplement"
        case .weight: "Weight"
        case .bloodPressure: "BP"
        case .symptom: "Symptom"
        case .sneeze: "Sneeze"
        case .nasalWash: "Nasal Wash"
        case .exercise: "Workout"
        case .medication: "Medication"
        case .mood: "Mood"
        case .bloodGlucose: "Blood Glucose"
        case .excretion: "Excretion"
        }
    }

    var systemImage: String {
        switch self {
        case .diet: "fork.knife"
        case .water: "drop"
        case .supplement: "pills"
        case .weight: "scalemass"
        case .bloodPressure: "heart.text.square"
        case .symptom: "cross.case"
        case .sneeze: "wind"
        case .nasalWash: "humidity"
        case .exercise: "figure.run"
        case .medication: "cross.case.fill"
        case .mood: "face.smiling"
        case .bloodGlucose: "drop.fill"
        case .excretion: "toilet"
        }
    }
}

struct ImportCenterView: View {
    let jobClient: DesktopJobClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var isImporterPresented = false
    @State private var intakeItem: FileIntakeItem?
    @State private var statusText: String?
    @State private var isWorking = false
    @State private var rawUploadConfirmed = false
    @State private var isDropTargeted = false
    @State private var recommendedPrompt: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text(appText("Import", appLanguageRaw))
                    .font(.largeTitle.bold())
                Spacer()
                Button(appText("Choose File or Folder", appLanguageRaw)) {
                    isImporterPresented = true
                }
                Button(appText("Create Job", appLanguageRaw)) {
                    Task { await createJob() }
                }
                .disabled(intakeItem == nil || isWorking || !rawUploadConfirmed)
            }

            if let intakeItem {
                VStack(alignment: .leading, spacing: 12) {
                    Table([intakeItem]) {
                        TableColumn("Name", value: \.name)
                        TableColumn("Kind") { item in Text(item.sourceKind.rawValue) }
                        TableColumn("Hash") { item in Text(item.sha256).lineLimit(1) }
                    }
                    .frame(minHeight: 140)

                    HStack(spacing: 10) {
                        Label(appText("Detected Route", appLanguageRaw), systemImage: "point.3.connected.trianglepath.dotted")
                            .font(.caption.bold())
                            .foregroundStyle(.secondary)
                        Text(jobType(for: intakeItem.sourceKind))
                            .font(.caption.weight(.semibold).monospaced())
                            .padding(.horizontal, 9)
                            .padding(.vertical, 5)
                            .background(Color.accentColor.opacity(0.12), in: Capsule())
                        Spacer()
                        Text(appText("Review hash and route before creating a long-running desktop job.", appLanguageRaw))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Toggle(appText("I confirm this raw local file may be registered as a desktop import job.", appLanguageRaw), isOn: $rawUploadConfirmed)
                        .toggleStyle(.checkbox)
                }
            } else {
                ContentUnavailableView(
                    appText("No file selected", appLanguageRaw),
                    systemImage: "tray.and.arrow.down",
                    description: Text(appText("Select a genome txt, medical file, Apple Health export, or Dedao folder.", appLanguageRaw))
                )
            }

            if let statusText {
                Text(statusText)
                    .foregroundStyle(.secondary)
            }

            if let recommendedPrompt, let onAskAgent, let intakeItem {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "wand.and.stars")
                        .foregroundStyle(.tint)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(appText("Recommended next step", appLanguageRaw))
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Text(recommendedPrompt)
                            .font(.callout)
                    }
                    Spacer()
                    Button(appText("Open in Agent", appLanguageRaw)) {
                        let item = AgentContextItem(
                            sourceID: intakeItem.sha256,
                            sourceKind: "import_" + intakeItem.sourceKind.rawValue,
                            title: intakeItem.name,
                            summary: appText("Detected Route", appLanguageRaw) + ": " + jobType(for: intakeItem.sourceKind)
                        )
                        onAskAgent(recommendedPrompt, item)
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding(12)
                .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }

            Spacer()
        }
        .padding(28)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isDropTargeted ? Color.accentColor : .clear, lineWidth: 2)
        )
        .onDrop(of: [UTType.fileURL.identifier], isTargeted: $isDropTargeted, perform: handleImportDrop)
        .fileImporter(
            isPresented: $isImporterPresented,
            allowedContentTypes: [.data, .folder],
            allowsMultipleSelection: false
        ) { result in
            Task { await inspect(result: result) }
        }
    }

    private func inspect(result: Result<[URL], Error>) async {
        do {
            guard let url = try result.get().first else { return }
            isWorking = true
            defer { isWorking = false }
            intakeItem = try await FileIntakeService.inspect(url: url)
            rawUploadConfirmed = false
            statusText = "Ready to create import job."
        } catch {
            statusText = "Inspect failed: \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func createJob() async {
        guard let intakeItem else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            let job = try await jobClient.createJob(.init(
                jobType: jobType(for: intakeItem.sourceKind),
                sourceKind: intakeItem.sourceKind.rawValue,
                sourceName: intakeItem.name,
                sourceHash: intakeItem.sha256,
                requestPayload: [
                    "raw_upload_confirmed": true,
                    "source_url": .string(intakeItem.url.path)
                ]
            ))
            statusText = "Created job #\(job.id) (\(job.status))."
            recommendedPrompt = pipelineRecommendation(for: intakeItem.sourceKind)
        } catch {
            statusText = "Job creation failed: \(userFacingError(error, appLanguageRaw))"
            recommendedPrompt = nil
        }
    }

    private func pipelineRecommendation(for kind: FileSourceKind) -> String {
        switch kind {
        case .genomeText:
            return "新基因数据已入库。等解析完成后，结合最近化验和补剂清单，告诉我哪些 SNP 现在最该关注，以及对应的生活方式/补剂调整。"
        case .medicalFile:
            return "刚导入的化验/医疗文件解析完后，列出偏离参考范围的指标，按风险排序，每条给一段解释和下一步行动。"
        case .appleHealthExport:
            return "Apple Health 数据导入完毕后，给我最近 30 天的活动、睡眠、心率趋势综合摘要，并指出与基线的明显偏差。"
        case .image:
            return "请基于这张图片识别关键信息，先给结论，再说明不确定的地方和需要我补充的信息。"
        case .dedaoFolder:
            return "得到知识库索引完成后，告诉我新增了哪些主题，以及和我当前健康问题最相关的 3 条结论。"
        case .unknown:
            return "导入完成后，请总结这份数据并建议怎么纳入我的日常分析。"
        }
    }

    private func jobType(for kind: FileSourceKind) -> String {
        switch kind {
        case .genomeText: "gene_reanalysis"
        case .dedaoFolder: "dedao_compile"
        case .medicalFile, .appleHealthExport: "medical_import"
        case .image: "medical_import"
        case .unknown: "medical_import"
        }
    }

    private func handleImportDrop(_ providers: [NSItemProvider]) -> Bool {
        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                let url: URL?
                if let data = item as? Data {
                    url = URL(dataRepresentation: data, relativeTo: nil)
                } else {
                    url = item as? URL
                }
                if let url {
                    Task { @MainActor in
                        await inspect(result: .success([url]))
                    }
                }
            }
            return true
        }
        return false
    }
}

struct JobListView: View {
    let client: DesktopJobClient
    let viewModel: TodayViewModel
    let openTrace: (Int) -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var jobs: [DesktopJobSummary] = []
    @State private var selectedJob: DesktopJobSummary?
    @State private var errorMessage: String?
    @State private var jobFilter: JobStatusFilter = .all

    private var jobsForPresentation: [DesktopJobSummary] {
        jobs.isEmpty ? viewModel.activeJobs : jobs
    }

    private var presentation: DesktopTaskCenterPresentation {
        DesktopTaskCenterPresentation(
            jobs: jobsForPresentation,
            actionCards: viewModel.bootstrap?.actionCards ?? []
        )
    }

    private var filteredJobs: [DesktopJobSummary] {
        jobFilter.filter(jobsForPresentation)
    }

    var body: some View {
        ZStack {
            Color(nsColor: .controlBackgroundColor)
                .ignoresSafeArea()

            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(appText("Jobs", appLanguageRaw))
                        .font(.largeTitle.bold())
                    Spacer()
                    Picker(appText("Status", appLanguageRaw), selection: $jobFilter) {
                        ForEach(JobStatusFilter.allCases) { filter in
                            Text(appText(filter.titleKey, appLanguageRaw)).tag(filter)
                        }
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 360)
                    Button(appText("Refresh", appLanguageRaw)) {
                        Task { await refresh() }
                    }
                }

                HSplitView {
                    VStack(alignment: .leading, spacing: 12) {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 10)], spacing: 10) {
                            JobStatCard(title: appText("Total", appLanguageRaw), value: "\(presentation.totalCount)", systemImage: "tray.full.fill", color: .blue)
                            JobStatCard(title: appText("Running", appLanguageRaw), value: "\(presentation.runningJobCount)", systemImage: "clock.arrow.circlepath", color: .teal)
                            JobStatCard(title: appText("Failed", appLanguageRaw), value: "\(presentation.failedJobCount)", systemImage: "exclamationmark.triangle.fill", color: .orange)
                            JobStatCard(title: appText("Action Cards", appLanguageRaw), value: "\(presentation.actionCards.count)", systemImage: "checkmark.seal.fill", color: .purple)
                        }

                        if !presentation.actionCards.isEmpty {
                            TaskActionCardSection(cards: Array(presentation.actionCards.prefix(8)))
                        }

                        if presentation.isEmpty {
                            EmptyJobState()
                                .frame(maxWidth: .infinity, minHeight: 260, alignment: .top)
                        } else if filteredJobs.isEmpty {
                            NoMatchingJobState()
                                .frame(maxWidth: .infinity, minHeight: 120, alignment: .top)
                        } else {
                            Table(filteredJobs) {
                                TableColumn(appText("ID", appLanguageRaw)) { job in Text("#\(job.id)") }
                                TableColumn(appText("Type", appLanguageRaw), value: \.jobType)
                                TableColumn(appText("Status", appLanguageRaw), value: \.status)
                                TableColumn(appText("Progress", appLanguageRaw)) { job in
                                    ProgressView(value: Double(job.progress), total: 100)
                                }
                                TableColumn(appText("Action", appLanguageRaw)) { job in
                                    HStack {
                                        Button(appText("Details", appLanguageRaw)) { Task { await loadDetail(job.id) } }
                                        Button(appText("Retry", appLanguageRaw)) { Task { await retry(job) } }
                                            .disabled(job.status != "failed")
                                    }
                                }
                            }
                        }
                    }
                    .frame(minWidth: 520, maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

                    JobDetailPanel(job: selectedJob, openTrace: openTrace)
                        .frame(minWidth: 260, idealWidth: 320, maxHeight: .infinity, alignment: .topLeading)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

                if let errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
            }
            .padding(28)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .task { await refresh() }
    }

    private func refresh() async {
        await viewModel.refresh()
        do {
            jobs = try await client.listJobs()
            if selectedJob == nil {
                selectedJob = jobsForPresentation.first
            }
            errorMessage = nil
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func loadDetail(_ id: Int) async {
        do {
            selectedJob = try await client.getJob(id: id)
            errorMessage = nil
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func retry(_ job: DesktopJobSummary) async {
        do {
            selectedJob = try await client.retryJob(id: job.id)
            await refresh()
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }
}

private struct TaskActionCardSection: View {
    let cards: [ActionCardSummary]
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(appText("Health Actions", appLanguageRaw), systemImage: "checklist")
                .font(.headline)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 10)], spacing: 10) {
                ForEach(cards) { card in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: "checkmark.seal.fill")
                                .foregroundStyle(.purple)
                                .frame(width: 30, height: 30)
                                .background(Color.purple.opacity(0.14), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                            VStack(alignment: .leading, spacing: 4) {
                                Text(card.title)
                                    .font(.callout.weight(.semibold))
                                    .lineLimit(2)
                                if let content = card.content, !content.isEmpty {
                                    Text(content)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                            }
                            Spacer(minLength: 0)
                        }

                        HStack(spacing: 6) {
                            if let status = card.status {
                                Text(appText(status, appLanguageRaw))
                                    .taskChipStyle(color: .purple)
                            }
                            if let priority = card.priority {
                                Text("P\(priority)")
                                    .taskChipStyle(color: .orange)
                            }
                            if let metricKey = card.metricKey, !metricKey.isEmpty {
                                Text(metricKey)
                                    .taskChipStyle(color: .teal)
                            }
                            if let sourceType = card.sourceType, !sourceType.isEmpty {
                                Text(sourceType)
                                    .taskChipStyle(color: .blue)
                            }
                        }
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                    .background(Color.purple.opacity(0.08), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(Color.purple.opacity(0.16), lineWidth: 1)
                    )
                }
            }
        }
    }
}

private extension Text {
    func taskChipStyle(color: Color) -> some View {
        self
            .font(.caption2.weight(.bold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.12), in: Capsule())
    }
}

private enum JobStatusFilter: String, CaseIterable, Identifiable {
    case all
    case active
    case failed
    case completed

    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .all: "All"
        case .active: "Active"
        case .failed: "Failed"
        case .completed: "Completed"
        }
    }

    func filter(_ jobs: [DesktopJobSummary]) -> [DesktopJobSummary] {
        switch self {
        case .all:
            jobs
        case .active:
            jobs.filter { $0.status == "queued" || $0.status == "running" }
        case .failed:
            jobs.filter { $0.status == "failed" }
        case .completed:
            jobs.filter { $0.status == "completed" }
        }
    }
}

private struct NoMatchingJobState: View {
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .font(.title2)
                .foregroundStyle(.secondary)
                .frame(width: 42, height: 42)
                .background(Color.secondary.opacity(0.10), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("No desktop jobs match this filter.", appLanguageRaw))
                    .font(.headline)
                Text(appText("Health action cards are still shown above for follow-up.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(16)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct EmptyJobState: View {
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.title2)
                    .foregroundStyle(.teal)
                    .frame(width: 42, height: 42)
                    .background(Color.teal.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    Text(appText("No desktop jobs yet", appLanguageRaw))
                        .font(.title3.bold())
                    Text(appText("Create import or reanalysis jobs from Data, Genetics, or Knowledge tabs.", appLanguageRaw))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            HStack(spacing: 8) {
                Label(appText("Data", appLanguageRaw), systemImage: "chart.xyaxis.line")
                Label(appText("Genetics", appLanguageRaw), systemImage: "dna")
                Label(appText("Knowledge", appLanguageRaw), systemImage: "books.vertical")
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(.secondary)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
        )
    }
}

private struct JobStatCard: View {
    let title: String
    let value: String
    let systemImage: String
    let color: Color

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .foregroundStyle(color)
                .frame(width: 30, height: 30)
                .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.title3.weight(.bold).monospacedDigit())
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(color.opacity(0.07), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct JobDetailPanel: View {
    let job: DesktopJobSummary?
    let openTrace: (Int) -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(appText("Job Detail", appLanguageRaw), systemImage: "list.bullet.rectangle")
                .font(.headline)
            if let job {
                let outcome = DesktopJobOutcomePresentation(job: job)
                Text("#\(job.id) \(job.jobType)")
                    .font(.title3.bold())
                JobOutcomeLandingPanel(job: job, outcome: outcome, openTrace: openTrace)
                LabeledContent(appText("Status", appLanguageRaw), value: job.status)
                LabeledContent(appText("Progress", appLanguageRaw), value: "\(job.progress)%")
                if let sourceName = job.sourceName {
                    LabeledContent(appText("Source", appLanguageRaw), value: sourceName)
                }
                if let sourceKind = job.sourceKind {
                    LabeledContent(appText("Kind", appLanguageRaw), value: sourceKind)
                }
                if let errorMessage = job.errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
                if let conversationID = job.resultPayload?["conversation_id"]?.intValue {
                    Button {
                        openTrace(conversationID)
                    } label: {
                        Label("\(appText("Open Trace", appLanguageRaw)) #\(conversationID)", systemImage: "point.3.connected.trianglepath.dotted")
                    }
                }
                if let resultPayload = job.resultPayload, !resultPayload.isEmpty {
                    Text(appText("Result", appLanguageRaw))
                        .font(.caption.bold())
                    Text(formatJSON(resultPayload))
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                }
            } else {
                Text(appText("Select a job to inspect source, result, error, and trace handoff.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(14)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct JobOutcomeLandingPanel: View {
    let job: DesktopJobSummary
    let outcome: DesktopJobOutcomePresentation
    let openTrace: (Int) -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: iconName)
                    .font(.headline)
                    .foregroundStyle(tint)
                    .frame(width: 30, height: 30)
                    .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    Text(appText(outcome.title, appLanguageRaw))
                        .font(.headline)
                    Text(diagnosticText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if !outcome.summaryItems.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 104), spacing: 8)], alignment: .leading, spacing: 8) {
                    ForEach(outcome.summaryItems, id: \.title) { item in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(appText(item.title, appLanguageRaw))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text(item.value)
                                .font(.caption.weight(.semibold).monospacedDigit())
                                .lineLimit(1)
                        }
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    }
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(appText("Next Actions", appLanguageRaw))
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                ForEach(outcome.nextActions, id: \.title) { action in
                    Label(appText(action.title, appLanguageRaw), systemImage: action.systemImage)
                        .font(.caption)
                        .foregroundStyle(.primary)
                }
            }

            if let conversationID = outcome.conversationID {
                Button {
                    openTrace(conversationID)
                } label: {
                    Label("\(appText("Open Trace", appLanguageRaw)) #\(conversationID)", systemImage: "point.3.connected.trianglepath.dotted")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }
        }
        .padding(12)
        .background(tint.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(tint.opacity(0.16), lineWidth: 1)
        )
    }

    private var iconName: String {
        switch outcome.state {
        case .completed: "checkmark.seal.fill"
        case .failed: "exclamationmark.triangle.fill"
        case .pending: "clock.arrow.circlepath"
        case .unknown: "questionmark.diamond"
        }
    }

    private var tint: Color {
        switch outcome.state {
        case .completed: .teal
        case .failed: .orange
        case .pending: .blue
        case .unknown: .secondary
        }
    }

    private var diagnosticText: String {
        switch outcome.state {
        case .completed:
            let source = job.sourceName?.isEmpty == false ? job.sourceName! : job.jobType
            return "\(source) \(appText("results are ready. Review before using them as Agent context.", appLanguageRaw))"
        case .failed:
            return outcome.diagnostic
        case .pending:
            return "\(job.progress)% \(appText("complete. Return here from the menu bar when it finishes.", appLanguageRaw))"
        case .unknown:
            return appText("Inspect the raw result before acting on it.", appLanguageRaw)
        }
    }
}

struct TraceLookupView: View {
    let client: TraceClient
    @Bindable var navigation: AppNavigationState
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var conversationID = ""
    @State private var trace: ConversationTrace?
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text(appText("Trace", appLanguageRaw))
                    .font(.largeTitle.bold())
                Spacer()
                TextField(appText("Conversation ID", appLanguageRaw), text: $conversationID)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 180)
                Button(appText("Load", appLanguageRaw)) {
                    Task { await load() }
                }
            }

            if let trace {
                Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
                    GridRow {
                        Text(appText("Conversation", appLanguageRaw)).foregroundStyle(.secondary)
                        Text(trace.conversation.title ?? "#\(trace.conversation.id)")
                    }
                    GridRow {
                        Text(appText("Model", appLanguageRaw)).foregroundStyle(.secondary)
                        Text(trace.assistantMessage.model ?? "Unknown")
                    }
                    GridRow {
                        Text(appText("Elapsed", appLanguageRaw)).foregroundStyle(.secondary)
                        Text(formatDuration(trace.assistantMessage.elapsedMs))
                    }
                    GridRow {
                        Text(appText("LLM", appLanguageRaw)).foregroundStyle(.secondary)
                        Text("\(formatDuration(trace.assistantMessage.llmMs)) / \(trace.assistantMessage.llmRounds ?? 0) rounds")
                    }
                    GridRow {
                        Text(appText("Finish", appLanguageRaw)).foregroundStyle(.secondary)
                        Text(trace.assistantMessage.finishReason ?? "Unknown")
                    }
                    GridRow {
                        Text(appText("Status", appLanguageRaw)).foregroundStyle(.secondary)
                        Text(trace.assistantMessage.completionStatus ?? "Unknown")
                    }
                }

                HStack(spacing: 10) {
                    JobStatCard(title: appText("Tools", appLanguageRaw), value: "\(trace.toolCalls.count)", systemImage: "wrench.and.screwdriver", color: .teal)
                    JobStatCard(title: appText("Evidence", appLanguageRaw), value: "\(trace.evidenceCards.count)", systemImage: "doc.text.magnifyingglass", color: .indigo)
                    JobStatCard(title: appText("Sources", appLanguageRaw), value: "\(trace.sourcesUsed.count)", systemImage: "link", color: .blue)
                }

                HSplitView {
                    TraceList(title: "Messages", rows: trace.messages.map { "\($0.role): \($0.content)" })
                    TraceList(title: "Tools", rows: trace.toolCalls.map { $0.name ?? "tool" })
                    TraceList(title: "Evidence", rows: trace.evidenceCards.map { $0.title ?? "evidence" } + trace.sourcesUsed)
                }
            } else {
                ContentUnavailableView(appText("No trace loaded", appLanguageRaw), systemImage: "point.3.connected.trianglepath.dotted")
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
            }
        }
        .padding(28)
        .onAppear { consumePendingTraceID() }
        .onChange(of: navigation.traceConversationID) { _, _ in
            consumePendingTraceID()
        }
    }

    private func load() async {
        guard let id = Int(conversationID.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            errorMessage = "Conversation ID must be a number."
            return
        }
        do {
            trace = try await client.fetchTrace(conversationID: id)
            errorMessage = nil
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func consumePendingTraceID() {
        guard let id = navigation.traceConversationID else { return }
        conversationID = "\(id)"
        navigation.traceConversationID = nil
        Task { await load() }
    }
}

struct SettingsView: View {
    let authClient: AuthClient
    let tokenStore: any AuthTokenStoring
    let onLogout: () -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @AppStorage(APIEndpoint.baseURLDefaultsKey) private var apiBaseURL = APIEndpoint.defaultBaseURL.absoluteString
    @AppStorage("preferredVoice") private var preferredVoice = "private_female"
    @AppStorage("allowFileHashing") private var allowFileHashing = true
    @AppStorage(AppPreferences.Keys.safetyAlertsEnabled) private var safetyAlertsEnabled = AppPreferences.defaultSafetyAlertsEnabled
    @AppStorage(AppPreferences.Keys.safetyAlertSound) private var safetyAlertSound = AppPreferences.defaultSafetyAlertSound
    @AppStorage(AppPreferences.Keys.safetyAlertMinSeverity) private var safetyAlertMinSeverity = AppPreferences.defaultMinSeverity
    @AppStorage(AppPreferences.Keys.safetyPollMinutes) private var safetyPollMinutes = AppPreferences.defaultPollMinutes
    @State private var token = ""
    @State private var statusMessage: String?
    @State private var currentUser: AuthUser?
    @State private var loadingUser = false
    @State private var isConfirmingSignOut = false
    @State private var launchAtLogin = false

    var body: some View {
        Form {
            Section(appText("Account", appLanguageRaw)) {
                HStack(spacing: 10) {
                    Image(systemName: "person.crop.circle.fill")
                        .font(.title2)
                        .foregroundStyle(.teal)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(appText("Signed in as", appLanguageRaw))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(currentUserPrimaryLabel)
                            .font(.callout.weight(.semibold))
                        if let secondary = currentUserSecondaryLabel {
                            Text(secondary)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                }
                Button(role: .destructive) {
                    isConfirmingSignOut = true
                } label: {
                    Label(appText("Switch Account", appLanguageRaw), systemImage: "rectangle.portrait.and.arrow.right")
                }
                .confirmationDialog(
                    appText("Sign out of this account?", appLanguageRaw),
                    isPresented: $isConfirmingSignOut,
                    titleVisibility: .visible
                ) {
                    Button(appText("Sign Out", appLanguageRaw), role: .destructive) {
                        Task { await signOut() }
                    }
                    Button(appText("Cancel", appLanguageRaw), role: .cancel) {}
                }
                Text(appText("Sign out and return to the login screen.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section(appText("Language", appLanguageRaw)) {
                Picker(appText("Display language", appLanguageRaw), selection: $appLanguageRaw) {
                    ForEach(AppLanguage.allCases) { language in
                        Text(language.nativeName).tag(language.rawValue)
                    }
                }
                Text(appText("Chinese is the default. Language changes apply immediately in most views.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }

            Section(appText("Auth", appLanguageRaw)) {
                SecureField(appText("Bearer token", appLanguageRaw), text: $token)
                HStack {
                    Button(appText("Save Token", appLanguageRaw)) {
                        Task { await saveToken() }
                    }
                    Button(appText("Clear Token", appLanguageRaw)) {
                        Task { await clearToken() }
                    }
                }
            }

            Section(appText("API", appLanguageRaw)) {
                TextField(appText("Base URL", appLanguageRaw), text: $apiBaseURL)
                Text(appText("Changing the API base URL takes effect after restarting the Mac app.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }

            Section(appText("Voice", appLanguageRaw)) {
                Picker(appText("Output voice", appLanguageRaw), selection: $preferredVoice) {
                    Text(appText("Private Female", appLanguageRaw)).tag("private_female")
                    Text(appText("System Default", appLanguageRaw)).tag("system_default")
                }
            }

            Section(appText("Notifications", appLanguageRaw)) {
                Toggle(appText("Enable safety alerts", appLanguageRaw), isOn: $safetyAlertsEnabled)
                Toggle(appText("Play alert sound", appLanguageRaw), isOn: $safetyAlertSound)
                    .disabled(!safetyAlertsEnabled)
                Picker(appText("Minimum alert level", appLanguageRaw), selection: $safetyAlertMinSeverity) {
                    Text(appText("Medium and above", appLanguageRaw)).tag(2)
                    Text(appText("High and above", appLanguageRaw)).tag(3)
                    Text(appText("Critical only", appLanguageRaw)).tag(4)
                }
                .disabled(!safetyAlertsEnabled)
                Picker(appText("Check frequency", appLanguageRaw), selection: $safetyPollMinutes) {
                    ForEach(AppPreferences.pollMinutesOptions, id: \.self) { minutes in
                        Text("\(minutes) min").tag(minutes)
                    }
                }
                .disabled(!safetyAlertsEnabled)
                Text(appText("Enable/level/sound apply immediately; frequency takes effect after restarting the Mac app.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section(appText("Startup", appLanguageRaw)) {
                Toggle(appText("Launch at login", appLanguageRaw), isOn: $launchAtLogin)
                    .onChange(of: launchAtLogin) { _, newValue in
                        updateLaunchAtLogin(newValue)
                    }
            }

            Section(appText("Privacy and Files", appLanguageRaw)) {
                Toggle(appText("Allow local file hashing before import", appLanguageRaw), isOn: $allowFileHashing)
                Text(appText("Files stay local in this P0 client. Import jobs register source metadata and hashes unless a backend upload flow is added later.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }

            if let statusMessage {
                Text(statusMessage)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .padding(28)
        .task { await loadCurrentUser() }
        .onAppear { syncLaunchAtLoginState() }
    }

    private func syncLaunchAtLoginState() {
        launchAtLogin = SMAppService.mainApp.status == .enabled
    }

    private func updateLaunchAtLogin(_ enabled: Bool) {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
        } catch {
            // Surface the failure instead of silently leaving the toggle wrong:
            // ad-hoc/unsigned local builds can be denied by the system here.
            statusMessage = "\(appText("Launch at login change failed", appLanguageRaw)): \(userFacingError(error, appLanguageRaw))"
            launchAtLogin = SMAppService.mainApp.status == .enabled
        }
    }

    private var currentUserPrimaryLabel: String {
        if let user = currentUser {
            return user.name ?? user.username
        }
        return loadingUser ? appText("Checking login...", appLanguageRaw) : "—"
    }

    private var currentUserSecondaryLabel: String? {
        guard let user = currentUser else { return nil }
        let primary = user.name ?? user.username
        // Surface email (or username when a display name is shown) as a second line,
        // but skip it when it would just duplicate the primary line.
        let secondary = user.email ?? (user.name != nil ? user.username : nil)
        guard let secondary, secondary != primary else { return nil }
        return secondary
    }

    private func loadCurrentUser() async {
        loadingUser = true
        defer { loadingUser = false }
        currentUser = try? await authClient.currentUser()
    }

    private func saveToken() async {
        do {
            try await tokenStore.setToken(token.trimmingCharacters(in: .whitespacesAndNewlines))
            statusMessage = "Token saved."
            token = ""
        } catch {
            statusMessage = "Save failed: \(userFacingError(error, appLanguageRaw))"
        }
    }

    private func clearToken() async {
        await tokenStore.clearToken()
        statusMessage = "Token cleared."
        onLogout()
    }

    private func signOut() async {
        await authClient.logout()
        statusMessage = "Signed out."
        onLogout()
    }
}

private struct TraceList: View {
    let title: String
    let rows: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            List(rows, id: \.self) { row in
                Text(row)
                    .lineLimit(3)
            }
        }
        .frame(minWidth: 180)
    }
}

private func formatDuration(_ milliseconds: Int?) -> String {
    guard let milliseconds else { return "Unknown" }
    if milliseconds >= 1000 {
        return String(format: "%.1fs", Double(milliseconds) / 1000)
    }
    return "\(milliseconds)ms"
}

private func formatJSON(_ object: [String: JSONValue]) -> String {
    object
        .sorted { $0.key < $1.key }
        .map { "\($0.key): \(formatJSONValue($0.value))" }
        .joined(separator: "\n")
}

private func formatJSONValue(_ value: JSONValue) -> String {
    switch value {
    case .string(let string):
        return string
    case .int(let int):
        return "\(int)"
    case .double(let double):
        return "\(double)"
    case .bool(let bool):
        return bool ? "true" : "false"
    case .object(let object):
        return "{\(formatJSON(object))}"
    case .array(let array):
        return "[" + array.map(formatJSONValue).joined(separator: ", ") + "]"
    case .null:
        return "null"
    }
}
