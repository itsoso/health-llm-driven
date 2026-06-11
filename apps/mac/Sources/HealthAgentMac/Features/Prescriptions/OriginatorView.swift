import SwiftUI
import UniformTypeIdentifiers
import HealthAgentMacCore

/// 「原研药」页:两块功能。
/// 1. 处方查原研药:选/拖一张处方图 → 上传识别 → 列出每药的处方名 / 通用名 /
///    原研药(品牌+厂家),无收录如实显示「暂无原研数据」。
/// 2. 原研药建议:列出在用、有原研可换的药,每条可「采纳 / 不需要」→ 写状态 →
///    刷新(采纳/忽略后该条消失)。
/// 文案诚实:全页底部固定「仅供参考,以药师/医生为准」;识别/建议失败显示错误态
/// 而非伪造数据。
struct OriginatorView: View {
    let client: OriginatorClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    // 处方识别态
    @State private var recognize: PrescriptionRecognizeResponse?
    @State private var isRecognizing = false
    @State private var recognizeError: String?
    @State private var isTargetedForDrop = false

    // 建议态
    @State private var recommendations: [OriginatorRecommendation] = []
    @State private var isLoadingRecommendations = false
    @State private var recommendationsError: String?
    @State private var pendingStatusIDs: Set<String> = []
    @State private var loaded = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                disclaimer
                recognizeSection
                suggestionsSection
            }
            .frame(maxWidth: 1100, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(28)
        }
        .background(backgroundGradient.ignoresSafeArea())
        .task {
            guard !loaded else { return }
            loaded = true
            await reloadRecommendations()
        }
    }

    private var backgroundGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(nsColor: .windowBackgroundColor),
                Color.blue.opacity(0.05),
                Color(nsColor: .windowBackgroundColor)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(appText("Originator Drugs", appLanguageRaw))
                .font(.largeTitle.bold())
            Text(appText("Look up originator drugs from a prescription, and review switch suggestions.", appLanguageRaw))
                .foregroundStyle(.secondary)
        }
    }

    private var disclaimer: some View {
        Label(
            appText("For reference only — confirm with your pharmacist or doctor.", appLanguageRaw),
            systemImage: "info.circle"
        )
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    // MARK: - Recognize section

    private var recognizeSection: some View {
        SectionPanel(
            title: appText("Prescription → originator", appLanguageRaw),
            systemImage: "doc.text.viewfinder"
        ) {
            dropZone
            if let recognizeError {
                Label(recognizeError, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout)
                    .foregroundStyle(.red)
            }
            recognizeResults
        }
    }

    private var dropZone: some View {
        VStack(spacing: 10) {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 30))
                .foregroundStyle(.secondary)
            Text(appText("Pick a prescription image (JPG / PNG / HEIC / WebP) or drag it here.", appLanguageRaw))
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            HStack(spacing: 10) {
                Button {
                    chooseImage()
                } label: {
                    Label(appText("Choose image", appLanguageRaw), systemImage: "folder")
                }
                .disabled(isRecognizing)
                if isRecognizing {
                    ProgressView().controlSize(.small)
                    Text(appText("Recognizing…", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 150)
        .padding(18)
        .background(dropBackground)
        .onDrop(of: [.fileURL], isTargeted: $isTargetedForDrop) { providers in
            handleDrop(providers)
        }
    }

    private var dropBackground: some View {
        let stroke = isTargetedForDrop ? Color.accentColor : Color.secondary.opacity(0.25)
        return RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(stroke, style: StrokeStyle(lineWidth: 1.5, dash: [6, 4]))
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.secondary.opacity(isTargetedForDrop ? 0.10 : 0.04))
            )
    }

    @ViewBuilder
    private var recognizeResults: some View {
        if let recognize {
            if let note = recognize.note, !note.isEmpty {
                Text(note)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if recognize.items.isEmpty {
                if !isRecognizing {
                    Text(appText("No medications recognized in this image.", appLanguageRaw))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(matchedLine(recognize.matchedOriginators))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                VStack(spacing: 12) {
                    ForEach(recognize.items) { item in
                        PrescriptionItemCard(item: item, appLanguageRaw: appLanguageRaw, onAskAgent: onAskAgent)
                    }
                }
            }
        }
    }

    private func matchedLine(_ count: Int) -> String {
        String(format: appText("Matched %d originator(s).", appLanguageRaw), count)
    }

    // MARK: - Suggestions section

    private var suggestionsSection: some View {
        SectionPanel(
            title: appText("Originator suggestions", appLanguageRaw),
            systemImage: "arrow.triangle.2.circlepath"
        ) {
            HStack {
                Text(appText("Medications you're taking that have an originator option.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                if isLoadingRecommendations {
                    ProgressView().controlSize(.small)
                }
                Button(appText("Refresh", appLanguageRaw)) {
                    Task { await reloadRecommendations() }
                }
                .controlSize(.small)
            }
            suggestionsContent
        }
    }

    @ViewBuilder
    private var suggestionsContent: some View {
        if let recommendationsError {
            Label(recommendationsError, systemImage: "exclamationmark.triangle.fill")
                .font(.callout)
                .foregroundStyle(.red)
        } else if recommendations.isEmpty {
            if !isLoadingRecommendations {
                Text(appText("No switch suggestions right now.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        } else {
            VStack(spacing: 0) {
                ForEach(recommendations) { rec in
                    RecommendationRow(
                        rec: rec,
                        appLanguageRaw: appLanguageRaw,
                        isPending: pendingStatusIDs.contains(rec.id),
                        onAdopt: { Task { await applyStatus(rec, status: .adopted) } },
                        onDismiss: { Task { await applyStatus(rec, status: .dismissed) } }
                    )
                    if rec.id != recommendations.last?.id {
                        Divider()
                    }
                }
            }
        }
    }

    // MARK: - Actions

    private func chooseImage() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.allowedContentTypes = PrescriptionImageMime.allowedExtensions
            .compactMap { UTType(filenameExtension: $0) }
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task { await recognizeImage(at: url) }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        _ = provider.loadObject(ofClass: URL.self) { url, _ in
            guard let url else { return }
            let ext = url.pathExtension.lowercased()
            guard PrescriptionImageMime.allowedExtensions.contains(ext) else { return }
            Task { @MainActor in
                await recognizeImage(at: url)
            }
        }
        return true
    }

    private func recognizeImage(at url: URL) async {
        isRecognizing = true
        recognizeError = nil
        defer { isRecognizing = false }

        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            recognizeError = appText("Could not recognize this prescription. Try another image.", appLanguageRaw)
            return
        }

        do {
            recognize = try await client.recognize(imageData: data, fileName: url.lastPathComponent)
        } catch {
            recognize = nil
            recognizeError = appText("Could not recognize this prescription. Try another image.", appLanguageRaw)
        }
    }

    private func reloadRecommendations() async {
        isLoadingRecommendations = true
        recommendationsError = nil
        defer { isLoadingRecommendations = false }
        do {
            let response = try await client.fetchRecommendations()
            recommendations = response.recommendations
        } catch {
            recommendations = []
            recommendationsError = appText("Could not load suggestions. Try refresh.", appLanguageRaw)
        }
    }

    private func applyStatus(_ rec: OriginatorRecommendation, status: OriginatorRecommendationStatus) async {
        pendingStatusIDs.insert(rec.id)
        defer { pendingStatusIDs.remove(rec.id) }
        do {
            _ = try await client.setStatus(
                genericName: rec.genericName,
                status: status,
                brand: rec.brand,
                manufacturer: rec.manufacturer
            )
            // 采纳/忽略后该条应消失;乐观移除再以一次刷新对齐后端真值。
            recommendations.removeAll { $0.id == rec.id }
        } catch {
            recommendationsError = appText("Could not load suggestions. Try refresh.", appLanguageRaw)
        }
    }
}

// MARK: - Prescription item card

private struct PrescriptionItemCard: View {
    let item: PrescriptionItem
    let appLanguageRaw: String
    var onAskAgent: ((String, AgentContextItem?) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(item.displayName.isEmpty ? appText("Generic name", appLanguageRaw) : item.displayName)
                .font(.headline)

            metaRow

            if item.hasOriginator, let originator = item.originator {
                originatorBlock(originator)
            } else {
                Label(appText("No originator data", appLanguageRaw), systemImage: "questionmark.circle")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            if let onAskAgent {
                HStack {
                    Spacer()
                    Button {
                        onAskAgent(askPrompt, nil)
                    } label: {
                        Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                    }
                    .buttonStyle(.borderless)
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    @ViewBuilder
    private var metaRow: some View {
        let parts = metaParts
        if !parts.isEmpty {
            HStack(spacing: 12) {
                ForEach(parts, id: \.self) { part in
                    Text(part)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var metaParts: [String] {
        var out: [String] = []
        if let generic = item.genericName, !generic.isEmpty {
            out.append("\(appText("Generic name", appLanguageRaw)): \(generic)")
        }
        if let dosage = item.dosage, !dosage.isEmpty {
            out.append("\(appText("Dosage", appLanguageRaw)): \(dosage)")
        }
        if let frequency = item.frequency, !frequency.isEmpty {
            out.append("\(appText("Frequency", appLanguageRaw)): \(frequency)")
        }
        return out
    }

    private func originatorBlock(_ originator: OriginatorDrug) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.seal.fill")
                .foregroundStyle(.green)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(appText("Originator", appLanguageRaw)): \(originator.brand)")
                    .font(.callout.weight(.semibold))
                if !originator.manufacturer.isEmpty {
                    Text(originator.manufacturer)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var askPrompt: String {
        let name = item.displayName.isEmpty ? (item.genericName ?? "") : item.displayName
        if item.hasOriginator, let originator = item.originator {
            return "处方里的「\(name)」对应的原研药是「\(originator.brand)」(\(originator.manufacturer))。请说明原研药与仿制药在我这种情况下的差异和换药注意事项。仅供参考,最终以药师/医生为准。"
        }
        return "处方里的「\(name)」暂无原研药收录数据。请说明这意味着什么,以及我该如何向药师/医生求证。"
    }
}

// MARK: - Recommendation row

private struct RecommendationRow: View {
    let rec: OriginatorRecommendation
    let appLanguageRaw: String
    let isPending: Bool
    let onAdopt: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(currentLine)
                    .font(.callout.weight(.semibold))
                Text("\(appText("Originator", appLanguageRaw)): \(rec.brand)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if !rec.manufacturer.isEmpty {
                    Text(rec.manufacturer)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            actionButtons
        }
        .padding(.vertical, 12)
    }

    private var currentLine: String {
        let name = rec.medName.isEmpty ? rec.genericName : rec.medName
        return String(format: appText("Currently: %@", appLanguageRaw), name)
    }

    @ViewBuilder
    private var actionButtons: some View {
        if isPending {
            ProgressView().controlSize(.small)
        } else {
            HStack(spacing: 8) {
                Button(appText("Not needed", appLanguageRaw)) { onDismiss() }
                    .controlSize(.small)
                Button(appText("Adopt", appLanguageRaw)) { onAdopt() }
                    .controlSize(.small)
                    .buttonStyle(.borderedProminent)
            }
        }
    }
}
