import AppKit
import HealthAgentMacCore
import SwiftUI
import UniformTypeIdentifiers

struct AgentChatView: View {
    @Bindable var viewModel: AgentChatViewModel
    @State private var draft = ""
    @State private var modelStrategy = "auto"
    @State private var editorFocusToken = 0

    private let modelOptions: [(id: String, title: String, tier: String)] = [
        ("commercial/Claude-Opus-4.7", "Claude Opus 4.7", "Top"),
        ("commercial/Gemini-3.1-Pro-Preview", "Gemini 3.1 Pro", "Top"),
        ("commercial/GPT-5.5", "GPT-5.5", "Top"),
        ("commercial/GPT-5.4", "GPT-5.4", "Top"),
        ("commercial/GPT-5.1", "GPT-5.1", "Mid"),
        ("commercial/DeepSeek-R1", "DeepSeek R1", "Mid"),
        ("commercial/DeepSeek-V3.2", "DeepSeek V3.2", "Mid")
    ]

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    composer
                    modelControls

                    Divider()

                    LazyVStack(alignment: .leading, spacing: 12) {
                        if viewModel.messages.isEmpty {
                            Text("Ready for desktop chat, file context, and evidence inspection.")
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 20)
                        }
                        ForEach(viewModel.messages) { message in
                            bubbleText(message)
                                .frame(maxWidth: .infinity, alignment: message.role == .user ? .trailing : .leading)
                                .overlay(alignment: .topLeading) {
                                    if message.role == .assistant && viewModel.isStreaming && message.content.isEmpty {
                                        ProgressView()
                                            .controlSize(.small)
                                    }
                                }
                        }
                    }
                }
                .padding(24)
            }
        }
        .onAppear {
            editorFocusToken += 1
        }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Analysis")
                    .font(.title2.bold())
                if let status = viewModel.lastCompletionStatus {
                    HStack(spacing: 8) {
                        Text(status)
                        if let model = viewModel.lastModel {
                            Text(model)
                        }
                        if !viewModel.lastSourcesUsed.isEmpty {
                            Text(viewModel.lastSourcesUsed.joined(separator: ", "))
                        }
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if viewModel.isStreaming {
                ProgressView()
                    .controlSize(.small)
            }
        }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Title")
                    .font(.headline)
                Spacer()
                Toggle("Web Search", isOn: $viewModel.webSearchEnabled)
                    .toggleStyle(.switch)
                    .controlSize(.small)
            }

            Divider()

            ZStack(alignment: .topLeading) {
                PromptCommandTextEditor(
                    text: $draft,
                    focusToken: editorFocusToken
                ) {
                    Task { await sendDraft() }
                }
                    .frame(minHeight: 128, maxHeight: 220)

                if draft.isEmpty {
                    Text("Ask about health data, labs, genes, records, or a specific execution plan.")
                        .foregroundStyle(.tertiary)
                        .padding(.top, 8)
                        .padding(.leading, 5)
                        .allowsHitTesting(false)
                }
            }

            HStack {
                if let error = viewModel.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .lineLimit(1)
                }
                Spacer()
                Button {
                    Task { await sendDraft() }
                } label: {
                    Label(viewModel.isStreaming ? "Running" : "Run", systemImage: "play.fill")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!viewModel.canSubmit(draft))
                .keyboardShortcut(.return, modifiers: .command)
                .help("Command-Return")
            }
        }
        .padding(16)
        .background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private var modelControls: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Models")
                    .font(.headline)
                Spacer()
                Picker("Mode", selection: $modelStrategy) {
                    Text("Auto Select").tag("auto")
                    Text("Default 3").tag("default3")
                }
                .pickerStyle(.segmented)
                .frame(width: 190)
                .onChange(of: modelStrategy) { _, newValue in
                    if newValue == "auto" {
                        viewModel.selectModel(nil)
                    }
                }
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 148), spacing: 8)], spacing: 8) {
                ForEach(modelOptions, id: \.id) { option in
                    modelCard(option)
                }
            }
        }
    }

    private func modelCard(_ option: (id: String, title: String, tier: String)) -> some View {
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
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 9)
            .background(
                isSelected ? Color.accentColor.opacity(0.12) : Color.secondary.opacity(0.08),
                in: RoundedRectangle(cornerRadius: 8, style: .continuous)
            )
        }
        .buttonStyle(.plain)
    }

    private func bubbleText(_ message: AgentChatMessage) -> some View {
        Text(message.content.isEmpty ? " " : message.content)
            .padding(12)
            .background(.quaternary)
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private func sendDraft() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard viewModel.canSubmit(text) else { return }
        draft = ""
        await viewModel.send(text)
        editorFocusToken += 1
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
    @State private var quickText = ""
    @State private var resultMessage: String?
    @State private var isSubmitting = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Record")
                .font(.largeTitle.bold())

            HStack {
                TextField("Record food, water, supplement, weight, BP, or symptom", text: $quickText)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await submit() } }
                Button(isSubmitting ? "Saving..." : "Save") {
                    Task { await submit() }
                }
                .disabled(isSubmitting || quickText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            if let resultMessage {
                Text(resultMessage)
                    .foregroundStyle(.secondary)
            }

            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 12) {
                GridRow {
                    Label("Diet", systemImage: "fork.knife")
                    Label("Supplement", systemImage: "pills")
                    Label("Water", systemImage: "drop")
                }
                GridRow {
                    Label("Weight", systemImage: "scalemass")
                    Label("Blood Pressure", systemImage: "heart.text.square")
                    Label("Symptom", systemImage: "cross.case")
                }
            }
            .font(.headline)

            Spacer()
        }
        .padding(28)
    }

    private func submit() async {
        let text = quickText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            let result = try await client.quickRecord(text: text)
            resultMessage = result.message
            if result.success {
                quickText = ""
            }
        } catch {
            resultMessage = "Save failed: \(error.localizedDescription)"
        }
    }
}

struct ImportCenterView: View {
    let jobClient: DesktopJobClient
    @State private var isImporterPresented = false
    @State private var intakeItem: FileIntakeItem?
    @State private var statusText: String?
    @State private var isWorking = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("Import")
                    .font(.largeTitle.bold())
                Spacer()
                Button("Choose File or Folder") {
                    isImporterPresented = true
                }
                Button("Create Job") {
                    Task { await createJob() }
                }
                .disabled(intakeItem == nil || isWorking)
            }

            if let intakeItem {
                Table([intakeItem]) {
                    TableColumn("Name", value: \.name)
                    TableColumn("Kind") { item in Text(item.sourceKind.rawValue) }
                    TableColumn("Hash") { item in Text(item.sha256).lineLimit(1) }
                }
                .frame(minHeight: 140)
            } else {
                ContentUnavailableView(
                    "No file selected",
                    systemImage: "tray.and.arrow.down",
                    description: Text("Select a genome txt, medical file, Apple Health export, or Dedao folder.")
                )
            }

            if let statusText {
                Text(statusText)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(28)
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
                sourceHash: intakeItem.sha256
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
}

struct JobListView: View {
    let client: DesktopJobClient
    @State private var jobs: [DesktopJobSummary] = []
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("Jobs")
                    .font(.largeTitle.bold())
                Spacer()
                Button("Refresh") {
                    Task { await refresh() }
                }
            }

            Table(jobs) {
                TableColumn("ID") { job in Text("#\(job.id)") }
                TableColumn("Type", value: \.jobType)
                TableColumn("Status", value: \.status)
                TableColumn("Progress") { job in
                    ProgressView(value: Double(job.progress), total: 100)
                }
                TableColumn("Action") { job in
                    Button("Retry") {
                        Task { await retry(job) }
                    }
                    .disabled(job.status != "failed")
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
            }
        }
        .padding(28)
        .task { await refresh() }
    }

    private func refresh() async {
        do {
            jobs = try await client.listJobs()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func retry(_ job: DesktopJobSummary) async {
        do {
            _ = try await client.retryJob(id: job.id)
            await refresh()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct TraceLookupView: View {
    let client: TraceClient
    @State private var conversationID = ""
    @State private var trace: ConversationTrace?
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("Trace")
                    .font(.largeTitle.bold())
                Spacer()
                TextField("Conversation ID", text: $conversationID)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 180)
                Button("Load") {
                    Task { await load() }
                }
            }

            if let trace {
                Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
                    GridRow {
                        Text("Conversation").foregroundStyle(.secondary)
                        Text(trace.conversation.title ?? "#\(trace.conversation.id)")
                    }
                    GridRow {
                        Text("Model").foregroundStyle(.secondary)
                        Text(trace.assistantMessage.model ?? "Unknown")
                    }
                    GridRow {
                        Text("Finish").foregroundStyle(.secondary)
                        Text(trace.assistantMessage.finishReason ?? "Unknown")
                    }
                    GridRow {
                        Text("Status").foregroundStyle(.secondary)
                        Text(trace.assistantMessage.completionStatus ?? "Unknown")
                    }
                }

                HSplitView {
                    TraceList(title: "Messages", rows: trace.messages.map { "\($0.role): \($0.content)" })
                    TraceList(title: "Tools", rows: trace.toolCalls.map { $0.name ?? "tool" })
                    TraceList(title: "Evidence", rows: trace.evidenceCards.map { $0.title ?? "evidence" } + trace.sourcesUsed)
                }
            } else {
                ContentUnavailableView("No trace loaded", systemImage: "point.3.connected.trianglepath.dotted")
            }

            if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
            }
        }
        .padding(28)
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
