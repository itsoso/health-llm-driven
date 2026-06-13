import SwiftUI
import HealthAgentMacCore

/// 「健康进阶」页:把四个已上线后端能力(H1)合到一页四个 section。
/// ① 多药梳理(减药候选,⚠️ 绝不命令停药) ② 社会连接自评 ③ 时滞因果 ④ 数据自检。
/// 每个 section 各自加载、各自错误态,互不阻塞 —— 一个挂了不影响其它三个。
/// 文案诚实:加载失败显示错误态而非伪造数据;数据缺失如实显示「暂无」。
struct HealthExtrasView: View {
    let client: HealthExtrasClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                DeprescribingSection(client: client, onAskAgent: onAskAgent)
                ConnectionSection(client: client)
                CausalLinksSection(client: client, onAskAgent: onAskAgent)
                IntegritySection(client: client)
            }
            .frame(maxWidth: 1100, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(28)
        }
        .background(backgroundGradient.ignoresSafeArea())
    }

    private var backgroundGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(nsColor: .windowBackgroundColor),
                Color.teal.opacity(0.05),
                Color(nsColor: .windowBackgroundColor)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(appText("Health Extras", appLanguageRaw))
                .font(.largeTitle.bold())
            Text(appText("Deprescribing review, social connection, causal links, and data self-check.", appLanguageRaw))
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - ① Deprescribing section

private struct DeprescribingSection: View {
    let client: HealthExtrasClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var review: DeprescribingReview?
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var loaded = false

    var body: some View {
        SectionPanel(
            title: appText("Deprescribing Review", appLanguageRaw),
            systemImage: "pills.circle"
        ) {
            content
        }
        .task {
            guard !loaded else { return }
            loaded = true
            await reload()
        }
    }

    @ViewBuilder
    private var content: some View {
        if let loadError {
            ErrorLine(message: loadError)
        } else if let review {
            summaryRow(review)
            if review.flags.isEmpty {
                Text(appText("No deprescribing candidates flagged.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(review.flags) { flag in
                    FlagCard(flag: flag, appLanguageRaw: appLanguageRaw)
                }
            }
            disclaimerLine(review)
            askButton(review)
        } else if isLoading {
            ProgressView().controlSize(.small)
        }
    }

    private func summaryRow(_ review: DeprescribingReview) -> some View {
        HStack(spacing: 10) {
            CountBadge(
                value: "\(review.activeCount)",
                label: appText("Active meds", appLanguageRaw),
                tint: .teal
            )
            if review.isPolypharmacy {
                Label(appText("Polypharmacy (≥5)", appLanguageRaw), systemImage: "exclamationmark.triangle.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.orange)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 4)
                    .background(Color.orange.opacity(0.14), in: Capsule())
            }
            Spacer()
        }
    }

    @ViewBuilder
    private func disclaimerLine(_ review: DeprescribingReview) -> some View {
        if !review.disclaimer.isEmpty {
            Label(review.disclaimer, systemImage: "info.circle")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func askButton(_ review: DeprescribingReview) -> some View {
        if let onAskAgent, !review.flags.isEmpty {
            HStack {
                Spacer()
                Button {
                    onAskAgent(askPrompt(review), nil)
                } label: {
                    Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                }
                .buttonStyle(.borderless)
            }
        }
    }

    private func askPrompt(_ review: DeprescribingReview) -> String {
        var parts: [String] = ["请结合我的多药梳理结果,告诉我哪些点值得带去和医生/药师讨论(不要直接让我停药):"]
        for flag in review.flags {
            parts.append("• \(flag.detail) —— \(flag.suggestion)")
        }
        parts.append("以上为减药候选提示,非建议停药;请说明我该如何向医生求证。")
        return parts.joined(separator: "\n")
    }

    private func reload() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            review = try await client.fetchDeprescribingReview()
        } catch {
            review = nil
            loadError = appText("Could not load deprescribing review. Try again.", appLanguageRaw)
        }
    }
}

// MARK: - ④ Integrity section

private struct IntegritySection: View {
    let client: HealthExtrasClient
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var report: IntegrityReport?
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var loaded = false

    var body: some View {
        SectionPanel(
            title: appText("Data Self-Check", appLanguageRaw),
            systemImage: "checkmark.shield"
        ) {
            content
        }
        .task {
            guard !loaded else { return }
            loaded = true
            await reload()
        }
    }

    @ViewBuilder
    private var content: some View {
        if let loadError {
            ErrorLine(message: loadError)
        } else if let report {
            if report.healthy {
                Label(appText("All data checks passed.", appLanguageRaw), systemImage: "checkmark.seal.fill")
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(.green)
            } else {
                Text(integritySummary(report))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                ForEach(report.issues) { issue in
                    IssueRow(issue: issue, appLanguageRaw: appLanguageRaw)
                }
            }
        } else if isLoading {
            ProgressView().controlSize(.small)
        }
    }

    private func integritySummary(_ report: IntegrityReport) -> String {
        let template = appText("%d data issue(s) found.", appLanguageRaw)
        return String(format: template, report.issueCount)
    }

    private func reload() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            report = try await client.fetchIntegrityReport()
        } catch {
            report = nil
            loadError = appText("Could not load data self-check. Try again.", appLanguageRaw)
        }
    }
}

// MARK: - Shared small views

/// 计数徽章(在用药数等)。
struct CountBadge: View {
    let value: String
    let label: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.title2.weight(.bold))
                .foregroundStyle(tint)
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(tint.opacity(0.10), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

/// 统一错误行。
struct ErrorLine: View {
    let message: String

    var body: some View {
        Label(message, systemImage: "exclamationmark.triangle.fill")
            .font(.callout)
            .foregroundStyle(.red)
    }
}

/// 一条减药候选卡(detail + suggestion)。
private struct FlagCard: View {
    let flag: DeprescribingFlag
    let appLanguageRaw: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: iconName)
                    .foregroundStyle(.orange)
                Text(flag.detail)
                    .font(.callout.weight(.semibold))
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if !flag.suggestion.isEmpty {
                Text(flag.suggestion)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var iconName: String {
        switch flag.code {
        case "polypharmacy": "square.stack.3d.up"
        case "duplicate_class": "doc.on.doc"
        case "long_term_candidate": "clock.badge.exclamationmark"
        case "expired_still_active": "calendar.badge.exclamationmark"
        default: "flag"
        }
    }
}

/// 一条数据完整性问题行。severity:error 红 / warning 橙 / info 灰。
private struct IssueRow: View {
    let issue: IntegrityIssue
    let appLanguageRaw: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: iconName)
                .foregroundStyle(tint)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 8) {
                    Text(issue.detail)
                        .font(.callout.weight(.semibold))
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if issue.count > 1 {
                        Text("×\(issue.count)")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }
                }
                if !issue.fixHint.isEmpty {
                    Text(issue.fixHint)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tint.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var tint: Color {
        switch issue.normalizedSeverity {
        case .error: .red
        case .warning: .orange
        case .info: .secondary
        }
    }

    private var iconName: String {
        switch issue.normalizedSeverity {
        case .error: "xmark.octagon.fill"
        case .warning: "exclamationmark.triangle.fill"
        case .info: "info.circle"
        }
    }
}
