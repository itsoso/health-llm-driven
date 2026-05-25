import AppKit
import HealthAgentMacCore
import SwiftUI
import UniformTypeIdentifiers

struct AgentChatView: View {
    @Bindable var viewModel: AgentChatViewModel
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var draft = ""
    @State private var modelStrategy = "auto"
    @State private var editorFocusToken = 0
    @State private var isAttachImporterPresented = false
    @State private var contextBundleName = ""
    @State private var selectedToolActivity: AgentToolActivity?

    private let modelOptions = AgentModelCatalog.defaultOptions

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                conversationHistoryStrip
                conversationSection

                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 16) {
                        composer
                            .frame(minWidth: 560, maxWidth: .infinity, alignment: .topLeading)
                        contextPanel
                            .frame(width: 340, alignment: .topLeading)
                    }

                    VStack(alignment: .leading, spacing: 16) {
                        composer
                        contextPanel
                    }
                }

                modelControls
            }
            .padding(24)
        }
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
            ingestPreparedDraft()
            editorFocusToken += 1
        }
        .onChange(of: viewModel.preparedDraft) { _, _ in
            ingestPreparedDraft()
        }
        .sheet(item: $selectedToolActivity) { activity in
            ToolActivityDetailSheet(activity: activity)
        }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text(appText("Analysis", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Turn health context into an answer, plan, or evidence check.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                draft = ""
                viewModel.startNewConversation()
                editorFocusToken += 1
            } label: {
                Label(appText("New Chat", appLanguageRaw), systemImage: "square.and.pencil")
            }
            .buttonStyle(.bordered)
            statusChip
            if viewModel.isStreaming {
                ProgressView()
                    .controlSize(.small)
            }
        }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 14) {
            promptToolbar
            ZStack(alignment: .topLeading) {
                PromptCommandTextEditor(
                    text: $draft,
                    focusToken: editorFocusToken
                ) {
                    Task { await sendDraft() }
                }
                .frame(minHeight: 190, maxHeight: 300)

                if draft.isEmpty {
                    Text(appText("Ask about health data, labs, genes, records, or a specific execution plan.", appLanguageRaw))
                        .foregroundStyle(.tertiary)
                        .padding(.top, 12)
                        .padding(.leading, 8)
                        .allowsHitTesting(false)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
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

            promptSuggestions

            HStack(alignment: .center, spacing: 10) {
                if let error = viewModel.errorMessage {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                        .lineLimit(1)
                }
                Spacer()
                Text("⌘↩")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(Color.secondary.opacity(0.10), in: Capsule())
                if viewModel.canRetry {
                    Button {
                        Task { await viewModel.retryLastMessage() }
                    } label: {
                        Label(appText("Retry", appLanguageRaw), systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                }
                Button {
                    Task { await sendDraft() }
                } label: {
                    Label(appText(viewModel.isStreaming ? "Running" : "Run", appLanguageRaw), systemImage: "play.fill")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!viewModel.canSubmit(draft))
                .keyboardShortcut(.return, modifiers: .command)
                .help("Command-Return")
            }
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
                viewModel.errorMessage = "Attach failed: \(error.localizedDescription)"
            }
        }
    }

    private var promptToolbar: some View {
        HStack(spacing: 12) {
            Label(appText("New Analysis", appLanguageRaw), systemImage: "sparkles")
                .font(.headline)
            Text(appText("Draft, attach, then run.", appLanguageRaw))
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                isAttachImporterPresented = true
            } label: {
                Label(appText("Attach", appLanguageRaw), systemImage: "paperclip")
            }
            .buttonStyle(.bordered)
            .controlSize(.regular)
            .help("Attach image, PDF, genome txt, Apple Health export, or Dedao folder")
            Toggle(isOn: $viewModel.webSearchEnabled) {
                Label(appText("Web Search", appLanguageRaw), systemImage: "network")
            }
            .toggleStyle(.switch)
            .controlSize(.small)
        }
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
                .disabled(viewModel.isStreaming)
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

    private var modelControls: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                Label(appText("Model Routing", appLanguageRaw), systemImage: "slider.horizontal.3")
                    .font(.headline)
                Text(selectedModelDescription)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Picker(appText("Mode", appLanguageRaw), selection: $modelStrategy) {
                    Text(appText("Auto Select", appLanguageRaw)).tag("auto")
                    Text(appText("Default 3", appLanguageRaw)).tag("default3")
                    Text(appText("Manual", appLanguageRaw)).tag("manual")
                }
                .pickerStyle(.segmented)
                .frame(width: 270)
                .onChange(of: modelStrategy) { _, newValue in
                    if newValue == "auto" || newValue == "default3" {
                        viewModel.selectModel(nil)
                    }
                }
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 10)], spacing: 10) {
                ForEach(modelOptions, id: \.id) { option in
                    modelCard(option)
                }
            }
        }
        .padding(16)
        .background(Color.secondary.opacity(0.055), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    @ViewBuilder
    private var conversationHistoryStrip: some View {
        if !viewModel.conversationHistory.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Label(appText("History", appLanguageRaw), systemImage: "clock.arrow.circlepath")
                        .font(.headline)
                    Text(appText("Continue a recent conversation or start fresh.", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("\(viewModel.conversationHistory.count)")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.secondary.opacity(0.10), in: Capsule())
                }

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(viewModel.conversationHistory.prefix(12)) { conversation in
                            AgentConversationHistoryPill(
                                conversation: conversation,
                                isSelected: conversation.id == viewModel.currentConversationID,
                                onLoad: {
                                    viewModel.loadConversation(conversation)
                                    editorFocusToken += 1
                                },
                                onDelete: {
                                    viewModel.deleteConversation(conversation)
                                }
                            )
                            .frame(width: 260)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
            .padding(16)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.secondary.opacity(0.10), lineWidth: 1)
            }
        }
    }

    private func modelCard(_ option: AgentModelOption) -> some View {
        let isSelected = viewModel.selectedModelID == option.id
        return Button {
            modelStrategy = "manual"
            viewModel.selectModel(option.id)
        } label: {
            HStack(spacing: 10) {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(isSelected ? .accentColor : .secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(option.title)
                        .font(.callout)
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                    Text(option.tier)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(option.provider)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 10)
            .background(
                isSelected ? Color.accentColor.opacity(0.18) : Color(nsColor: .controlBackgroundColor).opacity(0.8),
                in: RoundedRectangle(cornerRadius: 10, style: .continuous)
            )
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(isSelected ? Color.accentColor.opacity(0.55) : Color.secondary.opacity(0.08), lineWidth: 1)
            }
        }
        .buttonStyle(.plain)
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

    private var conversationSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(appText("Result", appLanguageRaw), systemImage: "text.bubble")
                    .font(.headline)
                Spacer()
                if let status = viewModel.lastCompletionStatus {
                    Text(status)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if viewModel.messages.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "text.magnifyingglass")
                        .font(.system(size: 34))
                        .foregroundStyle(.secondary)
                    Text(appText("Run an analysis to see the answer stream here.", appLanguageRaw))
                        .font(.headline)
                    Text(appText("Sources, model, and file context stay visible while you iterate.", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 170)
                .background(Color.secondary.opacity(0.055), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            } else {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(viewModel.messages) { message in
                        messageBubble(message)
                    }
                }
            }
        }
    }

    private func messageBubble(_ message: AgentChatMessage) -> some View {
        HStack(alignment: .top) {
            if message.role == .user {
                Spacer(minLength: 90)
            }
            VStack(alignment: .leading, spacing: 6) {
                Label(
                    appText(message.role == .user ? "You" : "Assistant", appLanguageRaw),
                    systemImage: message.role == .user ? "person.crop.circle" : "sparkles"
                )
                .font(.caption.bold())
                .foregroundStyle(.secondary)
                messageContent(message)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if message.role == .assistant {
                    ForEach(viewModel.proposedActions(for: message)) { action in
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
                }
                if message.role == .assistant && viewModel.isStreaming && message.content.isEmpty {
                    ProgressView()
                        .controlSize(.small)
                }
            }
            .padding(14)
            .background(
                message.role == .user ? Color.accentColor.opacity(0.18) : Color(nsColor: .controlBackgroundColor).opacity(0.92),
                in: RoundedRectangle(cornerRadius: 14, style: .continuous)
            )
            .overlay {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(message.role == .user ? Color.accentColor.opacity(0.25) : Color.secondary.opacity(0.08), lineWidth: 1)
            }
            .frame(maxWidth: message.role == .user ? 720 : .infinity, alignment: message.role == .user ? .trailing : .leading)
            if message.role == .assistant {
                Spacer(minLength: 70)
            }
        }
    }

    @ViewBuilder
    private func messageContent(_ message: AgentChatMessage) -> some View {
        if message.role == .assistant {
            MarkdownMessageText(markdown: viewModel.displayContent(for: message))
        } else {
            Text(message.content.isEmpty ? " " : message.content)
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

            if !viewModel.conversationHistory.isEmpty {
                Divider()

                Label(appText("History", appLanguageRaw), systemImage: "clock.arrow.circlepath")
                    .font(.subheadline.bold())
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.conversationHistory.prefix(6)) { conversation in
                        AgentConversationHistoryRow(
                            conversation: conversation,
                            isSelected: conversation.id == viewModel.currentConversationID,
                            onLoad: {
                                viewModel.loadConversation(conversation)
                            },
                            onDelete: {
                                viewModel.deleteConversation(conversation)
                            }
                        )
                    }
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

                Label(appText("Tool Timeline", appLanguageRaw), systemImage: "wrench.and.screwdriver")
                    .font(.subheadline.bold())
                VStack(alignment: .leading, spacing: 7) {
                    ForEach(viewModel.toolActivities) { activity in
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
                        Label(source, systemImage: "link")
                            .font(.caption)
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

    private func sendDraft() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard viewModel.canSubmit(text) else { return }
        draft = ""
        await viewModel.send(text)
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
                viewModel.errorMessage = "Attach failed: \(error.localizedDescription)"
            }
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
    let markdown: String
    @AppStorage(AppFontScale.defaultsKey) private var appFontScaleLevel = AppFontScale.defaultLevel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                blockView(block)
            }
        }
    }

    private var blocks: [MarkdownRenderBlock] {
        let blocks = MarkdownRenderSupport.blocks(from: markdown.isEmpty ? " " : markdown)
        if blocks.isEmpty {
            return [.paragraph(MarkdownRenderSupport.readableFallback(markdown.isEmpty ? " " : markdown))]
        }
        return blocks
    }

    @ViewBuilder
    private func blockView(_ block: MarkdownRenderBlock) -> some View {
        switch block {
        case .heading(let level, let text):
            inlineText(text)
                .font(level <= 2 ? scaledFont(base: 20, weight: .bold) : scaledFont(base: 16, weight: .semibold))
                .foregroundStyle(.primary)
                .padding(.top, level <= 2 ? 4 : 2)
        case .paragraph(let text):
            inlineText(text)
                .font(scaledFont(base: 15))
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
        case .bullet(let text):
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("•")
                    .font(scaledFont(base: 15, weight: .bold))
                    .foregroundStyle(Color.accentColor)
                inlineText(text)
                    .font(scaledFont(base: 15))
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .numbered(let index, let text):
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("\(index).")
                    .font(scaledFont(base: 15, weight: .bold))
                    .foregroundStyle(Color.accentColor)
                    .frame(minWidth: 22, alignment: .trailing)
                inlineText(text)
                    .font(scaledFont(base: 15))
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .tableRow(let columns):
            HStack(alignment: .top, spacing: 0) {
                ForEach(Array(columns.enumerated()), id: \.offset) { _, column in
                    inlineText(column)
                        .font(scaledFont(base: 12))
                        .lineLimit(4)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 7)
                        .background(Color.secondary.opacity(0.06))
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        case .divider:
            Divider()
                .padding(.vertical, 2)
        }
    }

    private func inlineText(_ text: String) -> Text {
        let cleaned = MarkdownRenderSupport.sanitizedForSwiftUI(text)
        if let attributed = try? AttributedString(
            markdown: cleaned,
            options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        ) {
            return Text(attributed)
        }
        return Text(MarkdownRenderSupport.readableFallback(text))
    }

    private var appFontScale: AppFontScale {
        AppFontScale(level: appFontScaleLevel)
    }

    private func scaledFont(base: Double, weight: Font.Weight? = nil) -> Font {
        .system(size: appFontScale.pointSize(base: base), weight: weight)
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

private struct AgentConversationHistoryPill: View {
    let conversation: AgentConversationSnapshot
    let isSelected: Bool
    let onLoad: () -> Void
    let onDelete: () -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Button {
                onLoad()
            } label: {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: isSelected ? "checkmark.circle.fill" : "bubble.left.and.bubble.right")
                        .font(.callout)
                        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                        .frame(width: 22)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(conversation.title)
                            .font(.callout.weight(.semibold))
                            .foregroundStyle(.primary)
                            .lineLimit(2)
                        Text(historySubtitle)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }
            }
            .buttonStyle(.plain)
            .help(appText("Load Chat", appLanguageRaw))

            Button {
                onDelete()
            } label: {
                Image(systemName: "trash")
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help(appText("Delete", appLanguageRaw))
        }
        .padding(12)
        .background(
            isSelected ? Color.accentColor.opacity(0.13) : Color(nsColor: .controlBackgroundColor).opacity(0.86),
            in: RoundedRectangle(cornerRadius: 13, style: .continuous)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(isSelected ? Color.accentColor.opacity(0.35) : Color.secondary.opacity(0.08), lineWidth: 1)
        }
    }

    private var historySubtitle: String {
        let count = conversation.messages.count
        let date = conversation.updatedAt.formatted(date: .numeric, time: .shortened)
        if let conversationID = conversation.conversationID {
            return "#\(conversationID) · \(count) \(appText("messages", appLanguageRaw)) · \(date)"
        }
        return "\(count) \(appText("messages", appLanguageRaw)) · \(date)"
    }
}

private struct AgentConversationHistoryRow: View {
    let conversation: AgentConversationSnapshot
    let isSelected: Bool
    let onLoad: () -> Void
    let onDelete: () -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

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

            Button {
                onDelete()
            } label: {
                Image(systemName: "trash")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help(appText("Delete", appLanguageRaw))
        }
        .padding(10)
        .background(
            isSelected ? Color.accentColor.opacity(0.10) : Color.secondary.opacity(0.07),
            in: RoundedRectangle(cornerRadius: 11, style: .continuous)
        )
    }

    private var historySubtitle: String {
        let count = conversation.messages.count
        let date = conversation.updatedAt.formatted(date: .numeric, time: .shortened)
        if let conversationID = conversation.conversationID {
            return "#\(conversationID) · \(count) \(appText("messages", appLanguageRaw)) · \(date)"
        }
        return "\(count) \(appText("messages", appLanguageRaw)) · \(date)"
    }
}

private struct PromptCommandTextEditor: NSViewRepresentable {
    @Binding var text: String
    let focusToken: Int
    let onCommandReturn: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let textView = CommandReturnTextView()
        textView.delegate = context.coordinator
        textView.onCommandReturn = onCommandReturn
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
        }
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        textView.onCommandReturn = onCommandReturn
        if textView.string != text {
            textView.string = text
        }
        if context.coordinator.focusToken != focusToken {
            context.coordinator.focusToken = focusToken
            DispatchQueue.main.async {
                textView.window?.makeFirstResponder(textView)
            }
        }
        _ = scrollView
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: String
        weak var textView: CommandReturnTextView?
        var focusToken = 0

        init(text: Binding<String>) {
            self._text = text
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            text = textView.string
        }
    }
}

private final class CommandReturnTextView: NSTextView {
    var onCommandReturn: (() -> Void)?

    override func keyDown(with event: NSEvent) {
        if event.modifierFlags.intersection(.deviceIndependentFlagsMask).contains(.command),
           event.charactersIgnoringModifiers == "\r" {
            onCommandReturn?()
            return
        }
        super.keyDown(with: event)
    }
}

struct RecordHubView: View {
    let client: RecordClient
    let productClient: SupplementProductLibraryClient
    @Bindable var viewModel: TodayViewModel
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
    @State private var weightKg = ""
    @State private var systolic = ""
    @State private var diastolic = ""
    @State private var symptom = ""
    @State private var recentRecords: [String] = []
    @State private var resultMessage: String?
    @State private var lastSavedRecord: QuickRecordResult?
    @State private var isSubmitting = false
    @State private var isUndoing = false
    @State private var quickFocusToken = 0

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                recordHeader
                recordSnapshotSection

                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 16) {
                        VStack(alignment: .leading, spacing: 16) {
                            quickCaptureCard
                            structuredCaptureCard
                        }
                        .frame(minWidth: 600, maxWidth: .infinity, alignment: .topLeading)

                        VStack(alignment: .leading, spacing: 16) {
                            saveStatusPanel
                            recentRecordsPanel
                        }
                        .frame(width: 360, alignment: .topLeading)
                    }

                    VStack(alignment: .leading, spacing: 16) {
                        quickCaptureCard
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
    private var recordSnapshotSection: some View {
        if let presentation = recordPresentation {
            recordSnapshotPanel(presentation)
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

    private func recordSnapshotPanel(_ presentation: DesktopRecordHubPresentation) -> some View {
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

            ViewThatFits(in: .horizontal) {
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
                Text("⌘↩")
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
            HStack {
                recordTextField(appText("Calories kcal", appLanguageRaw), text: $calories)
                recordTextField(appText("Protein g", appLanguageRaw), text: $protein)
            }
        case .water:
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
            supplementProductMessage = "\(appText("Search failed", appLanguageRaw)): \(error.localizedDescription)"
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
            symptom: symptom
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
            }
            let didSave = handleRecordResult(result, fallbackText: draft.previewText)
            if didSave {
                clearStructuredFields()
                await viewModel.refresh()
            }
        } catch {
            resultMessage = "Save failed: \(error.localizedDescription)"
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
            resultMessage = "Save failed: \(error.localizedDescription)"
        }
    }

    private func handleRecordResult(_ result: QuickRecordResult, fallbackText: String) -> Bool {
        resultMessage = result.message
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
            resultMessage = "\(appText("Undo failed", appLanguageRaw)): \(error.localizedDescription)"
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
        }
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
        }
    }
}

struct ImportCenterView: View {
    let jobClient: DesktopJobClient
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var isImporterPresented = false
    @State private var intakeItem: FileIntakeItem?
    @State private var statusText: String?
    @State private var isWorking = false
    @State private var rawUploadConfirmed = false
    @State private var isDropTargeted = false

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
            statusText = "Inspect failed: \(error.localizedDescription)"
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
        } catch {
            statusText = "Job creation failed: \(error.localizedDescription)"
        }
    }

    private func jobType(for kind: FileSourceKind) -> String {
        switch kind {
        case .genomeText: "gene_reanalysis"
        case .dedaoFolder: "dedao_compile"
        case .medicalFile, .appleHealthExport: "medical_import"
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
            errorMessage = error.localizedDescription
        }
    }

    private func loadDetail(_ id: Int) async {
        do {
            selectedJob = try await client.getJob(id: id)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func retry(_ job: DesktopJobSummary) async {
        do {
            selectedJob = try await client.retryJob(id: job.id)
            await refresh()
        } catch {
            errorMessage = error.localizedDescription
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
            errorMessage = error.localizedDescription
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
    @State private var token = ""
    @State private var statusMessage: String?

    var body: some View {
        Form {
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
                    Button(appText("Sign Out", appLanguageRaw)) {
                        Task { await signOut() }
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
    }

    private func saveToken() async {
        do {
            try await tokenStore.setToken(token.trimmingCharacters(in: .whitespacesAndNewlines))
            statusMessage = "Token saved."
            token = ""
        } catch {
            statusMessage = "Save failed: \(error.localizedDescription)"
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
