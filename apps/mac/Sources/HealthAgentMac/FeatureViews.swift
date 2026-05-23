import AppKit
import HealthAgentMacCore
import SwiftUI
import UniformTypeIdentifiers

struct AgentChatView: View {
    @Bindable var viewModel: AgentChatViewModel
    @State private var draft = ""
    @State private var modelStrategy = "auto"
    @State private var editorFocusToken = 0
    @State private var isAttachImporterPresented = false

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

                    HSplitView {
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
                        .frame(minWidth: 420, maxWidth: .infinity, alignment: .topLeading)

                        evidencePanel
                            .frame(minWidth: 220, idealWidth: 260, maxWidth: 320, alignment: .topLeading)
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
                Button {
                    isAttachImporterPresented = true
                } label: {
                    Label("Attach", systemImage: "paperclip")
                }
                .buttonStyle(.borderless)
                .help("Attach image, PDF, genome txt, Apple Health export, or Dedao folder")
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

    private var evidencePanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Evidence", systemImage: "doc.text.magnifyingglass")
                .font(.headline)
            if viewModel.lastSourcesUsed.isEmpty && viewModel.attachments.isEmpty {
                Text("Sources, attachments, and evidence refs will appear here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if !viewModel.attachments.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Attachments")
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
                    Text("Sources")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    ForEach(viewModel.lastSourcesUsed, id: \.self) { source in
                        Label(source, systemImage: "link")
                            .font(.caption)
                    }
                }
            }
            Spacer()
        }
        .padding(12)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func sendDraft() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard viewModel.canSubmit(text) else { return }
        draft = ""
        await viewModel.send(text)
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
        case .genomeText: "helix"
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
    @State private var recordType = StructuredRecordType.diet
    @State private var foodName = ""
    @State private var calories = ""
    @State private var protein = ""
    @State private var waterMl = "250"
    @State private var supplementName = ""
    @State private var supplementDose = ""
    @State private var weightKg = ""
    @State private var systolic = ""
    @State private var diastolic = ""
    @State private var symptom = ""
    @State private var recentRecords: [String] = []
    @State private var resultMessage: String?
    @State private var isSubmitting = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Record")
                    .font(.largeTitle.bold())

                SectionPanel(title: "Quick Record", systemImage: "bolt.fill") {
                    HStack {
                        TextField("Record food, water, supplement, weight, BP, or symptom", text: $quickText)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit { Task { await submit(text: quickText) } }
                        Button(isSubmitting ? "Saving..." : "Save") {
                            Task { await submit(text: quickText) }
                        }
                        .disabled(isSubmitting || quickText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }

                SectionPanel(title: "Structured Form", systemImage: "text.badge.checkmark") {
                    Picker("Type", selection: $recordType) {
                        ForEach(StructuredRecordType.allCases) { type in
                            Label(type.title, systemImage: type.systemImage).tag(type)
                        }
                    }
                    .pickerStyle(.segmented)

                    structuredFields

                    HStack {
                        Button("Preview") {
                            quickText = structuredText()
                        }
                        Button(isSubmitting ? "Saving..." : "Save Structured") {
                            Task { await submit(text: structuredText()) }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isSubmitting || structuredText().isEmpty)
                    }
                }

                if let resultMessage {
                    Text(resultMessage)
                        .foregroundStyle(.secondary)
                }

                SectionPanel(title: "Recent Local Records", systemImage: "clock") {
                    if recentRecords.isEmpty {
                        Text("Recent saved commands in this Mac session will appear here.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(recentRecords, id: \.self) { record in
                            HStack {
                                Text(record)
                                    .lineLimit(1)
                                Spacer()
                                Button("Reuse") { quickText = record }
                                Button("Delete") { recentRecords.removeAll { $0 == record } }
                            }
                        }
                    }
                }
            }
            .padding(28)
        }
    }

    @ViewBuilder
    private var structuredFields: some View {
        switch recordType {
        case .diet:
            TextField("Food name or photo description", text: $foodName)
            HStack {
                TextField("Calories kcal", text: $calories)
                TextField("Protein g", text: $protein)
            }
        case .water:
            TextField("Amount ml", text: $waterMl)
        case .supplement:
            TextField("Supplement", text: $supplementName)
            TextField("Dose and timing", text: $supplementDose)
        case .weight:
            TextField("Weight kg", text: $weightKg)
        case .bloodPressure:
            HStack {
                TextField("Systolic", text: $systolic)
                TextField("Diastolic", text: $diastolic)
            }
        case .symptom:
            TextField("Symptom, severity, and context", text: $symptom)
        }
    }

    private func structuredText() -> String {
        switch recordType {
        case .diet:
            let parts = [foodName, calories.isEmpty ? "" : "\(calories)kcal", protein.isEmpty ? "" : "蛋白质\(protein)g"]
                .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            return parts.isEmpty ? "" : "记录饮食：" + parts.joined(separator: "，")
        case .water:
            return waterMl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "" : "喝水 \(waterMl)ml"
        case .supplement:
            let text = [supplementName, supplementDose].filter { !$0.isEmpty }.joined(separator: " ")
            return text.isEmpty ? "" : "记录补剂：\(text)"
        case .weight:
            return weightKg.isEmpty ? "" : "记录体重 \(weightKg)kg"
        case .bloodPressure:
            return systolic.isEmpty || diastolic.isEmpty ? "" : "记录血压 \(systolic)/\(diastolic) mmHg"
        case .symptom:
            return symptom.isEmpty ? "" : "记录症状：\(symptom)"
        }
    }

    private func submit(text rawText: String) async {
        let text = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            let result = try await client.quickRecord(text: text)
            resultMessage = result.message
            if result.success {
                quickText = ""
                recentRecords.removeAll { $0 == text }
                recentRecords.insert(text, at: 0)
                recentRecords = Array(recentRecords.prefix(8))
            }
        } catch {
            resultMessage = "Save failed: \(error.localizedDescription)"
        }
    }
}

private enum StructuredRecordType: String, CaseIterable, Identifiable {
    case diet
    case water
    case supplement
    case weight
    case bloodPressure
    case symptom

    var id: String { rawValue }

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
    @State private var isImporterPresented = false
    @State private var intakeItem: FileIntakeItem?
    @State private var statusText: String?
    @State private var isWorking = false
    @State private var rawUploadConfirmed = false
    @State private var isDropTargeted = false

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

                    Toggle("I confirm this raw local file may be registered as a desktop import job.", isOn: $rawUploadConfirmed)
                        .toggleStyle(.checkbox)
                }
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
    let openTrace: (Int) -> Void
    @State private var jobs: [DesktopJobSummary] = []
    @State private var selectedJob: DesktopJobSummary?
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

            HSplitView {
                Table(jobs) {
                    TableColumn("ID") { job in Text("#\(job.id)") }
                    TableColumn("Type", value: \.jobType)
                    TableColumn("Status", value: \.status)
                    TableColumn("Progress") { job in
                        ProgressView(value: Double(job.progress), total: 100)
                    }
                    TableColumn("Action") { job in
                        HStack {
                            Button("Details") { Task { await loadDetail(job.id) } }
                            Button("Retry") { Task { await retry(job) } }
                                .disabled(job.status != "failed")
                        }
                    }
                }

                JobDetailPanel(job: selectedJob, openTrace: openTrace)
                    .frame(minWidth: 260, idealWidth: 320)
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
            if selectedJob == nil {
                selectedJob = jobs.first
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

private struct JobDetailPanel: View {
    let job: DesktopJobSummary?
    let openTrace: (Int) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Job Detail", systemImage: "list.bullet.rectangle")
                .font(.headline)
            if let job {
                Text("#\(job.id) \(job.jobType)")
                    .font(.title3.bold())
                LabeledContent("Status", value: job.status)
                LabeledContent("Progress", value: "\(job.progress)%")
                if let sourceName = job.sourceName {
                    LabeledContent("Source", value: sourceName)
                }
                if let sourceKind = job.sourceKind {
                    LabeledContent("Kind", value: sourceKind)
                }
                if let errorMessage = job.errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
                if let conversationID = job.resultPayload?["conversation_id"]?.intValue {
                    Button {
                        openTrace(conversationID)
                    } label: {
                        Label("Open Trace #\(conversationID)", systemImage: "point.3.connected.trianglepath.dotted")
                    }
                }
                if let resultPayload = job.resultPayload, !resultPayload.isEmpty {
                    Text("Result")
                        .font(.caption.bold())
                    Text(formatJSON(resultPayload))
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                }
            } else {
                Text("Select a job to inspect source, result, error, and trace handoff.")
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(14)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

struct TraceLookupView: View {
    let client: TraceClient
    @Bindable var navigation: AppNavigationState
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
                        Text("Elapsed").foregroundStyle(.secondary)
                        Text(formatDuration(trace.assistantMessage.elapsedMs))
                    }
                    GridRow {
                        Text("LLM").foregroundStyle(.secondary)
                        Text("\(formatDuration(trace.assistantMessage.llmMs)) / \(trace.assistantMessage.llmRounds ?? 0) rounds")
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
    let tokenStore: KeychainTokenStore
    let onLogout: () -> Void
    @AppStorage(APIEndpoint.baseURLDefaultsKey) private var apiBaseURL = APIEndpoint.defaultBaseURL.absoluteString
    @AppStorage("preferredVoice") private var preferredVoice = "private_female"
    @AppStorage("allowFileHashing") private var allowFileHashing = true
    @State private var token = ""
    @State private var statusMessage: String?

    var body: some View {
        Form {
            Section("Auth") {
                SecureField("Bearer token", text: $token)
                HStack {
                    Button("Save Token") {
                        Task { await saveToken() }
                    }
                    Button("Clear Token") {
                        Task { await clearToken() }
                    }
                    Button("Sign Out") {
                        Task { await signOut() }
                    }
                }
            }

            Section("API") {
                TextField("Base URL", text: $apiBaseURL)
                Text("Changing the API base URL takes effect after restarting the Mac app.")
                    .foregroundStyle(.secondary)
            }

            Section("Voice") {
                Picker("Output voice", selection: $preferredVoice) {
                    Text("私享女声").tag("private_female")
                    Text("系统默认").tag("system_default")
                }
            }

            Section("Privacy and Files") {
                Toggle("Allow local file hashing before import", isOn: $allowFileHashing)
                Text("Files stay local in this P0 client. Import jobs register source metadata and hashes unless a backend upload flow is added later.")
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
