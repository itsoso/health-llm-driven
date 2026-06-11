import SwiftUI
import HealthAgentMacCore

/// 「肝脏趋势」页:消费后端 `GET /chronic/liver`。
/// - available=false → 空态(显示后端给的 reason)。
/// - ALT/GGT 趋势:逐行 summary_lines + verdict 配色(improving 绿 / worsening 红 /
///   stable 灰)。
/// - AST/ALT 比值、FIB-4(有则值+band,无则灰字提示补血常规)、脂肪肝风险(偏高橙)。
/// - advice 列表 + 固定免责:趋势提示,非诊断,结合腹部超声+医生。
/// 文案诚实:加载失败显示错误态而非伪造数据;数据缺失如实显示「数据不足」。
struct LiverTrendView: View {
    let client: LiverHealthClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var report: LiverHealthReport?
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var loaded = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                disclaimer
                content
            }
            .frame(maxWidth: 1100, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(28)
        }
        .background(backgroundGradient.ignoresSafeArea())
        .task {
            guard !loaded else { return }
            loaded = true
            await reload()
        }
    }

    private var backgroundGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(nsColor: .windowBackgroundColor),
                Color.orange.opacity(0.05),
                Color(nsColor: .windowBackgroundColor)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Liver Trend", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Trends in liver enzymes and fibrosis markers from your labs.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if isLoading {
                ProgressView().controlSize(.small)
            }
            Button(appText("Refresh", appLanguageRaw)) {
                Task { await reload() }
            }
            .controlSize(.small)
        }
    }

    private var disclaimer: some View {
        Label(
            appText("Trend hint, not a diagnosis — review with an abdominal ultrasound and your doctor.", appLanguageRaw),
            systemImage: "info.circle"
        )
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    // MARK: - Content routing

    @ViewBuilder
    private var content: some View {
        if let loadError {
            Label(loadError, systemImage: "exclamationmark.triangle.fill")
                .font(.callout)
                .foregroundStyle(.red)
        } else if let report {
            if report.available {
                availableContent(report)
            } else {
                emptyState(report)
            }
        } else if !isLoading {
            Text(appText("No liver data yet.", appLanguageRaw))
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }

    private func emptyState(_ report: LiverHealthReport) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: "cross.case")
                .font(.system(size: 30))
                .foregroundStyle(.secondary)
            Text(appText("Not enough lab data to assess liver trend yet.", appLanguageRaw))
                .font(.headline)
            if let reason = report.reason, !reason.isEmpty {
                Text(reason)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    @ViewBuilder
    private func availableContent(_ report: LiverHealthReport) -> some View {
        trendsSection(report)
        markersSection(report)
        adviceSection(report)
    }

    // MARK: - Trends section

    private func trendsSection(_ report: LiverHealthReport) -> some View {
        SectionPanel(
            title: appText("Enzyme trends", appLanguageRaw),
            systemImage: "waveform.path.ecg"
        ) {
            if report.summaryLines.isEmpty && report.altTrend == nil && report.ggtTrend == nil {
                Text(appText("No trend summary available.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(report.summaryLines.enumerated()), id: \.offset) { _, line in
                    Text(line)
                        .font(.callout)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                if let alt = report.altTrend {
                    TrendChip(label: appText("ALT", appLanguageRaw), trend: alt, appLanguageRaw: appLanguageRaw)
                }
                if let ggt = report.ggtTrend {
                    TrendChip(label: appText("GGT", appLanguageRaw), trend: ggt, appLanguageRaw: appLanguageRaw)
                }
            }
        }
    }

    // MARK: - Markers section

    private func markersSection(_ report: LiverHealthReport) -> some View {
        SectionPanel(
            title: appText("Markers", appLanguageRaw),
            systemImage: "list.bullet.rectangle"
        ) {
            ratioRow(report)
            fib4Row(report)
            fattyLiverRow(report)
        }
    }

    @ViewBuilder
    private func ratioRow(_ report: LiverHealthReport) -> some View {
        if let ratio = report.astAltRatio {
            MarkerRow(
                title: appText("AST/ALT ratio", appLanguageRaw),
                value: formatNumber(ratio),
                detail: nil,
                tint: .primary
            )
        }
    }

    @ViewBuilder
    private func fib4Row(_ report: LiverHealthReport) -> some View {
        if report.hasFib4, let fib4 = report.fib4 {
            MarkerRow(
                title: appText("FIB-4", appLanguageRaw),
                value: formatNumber(fib4),
                detail: report.fib4Band,
                tint: .primary
            )
        } else {
            MarkerRow(
                title: appText("FIB-4", appLanguageRaw),
                value: appText("Needs platelets — add a CBC to assess.", appLanguageRaw),
                detail: nil,
                tint: .secondary
            )
        }
    }

    @ViewBuilder
    private func fattyLiverRow(_ report: LiverHealthReport) -> some View {
        if let risk = report.fattyLiverRisk, !risk.isEmpty {
            MarkerRow(
                title: appText("Fatty liver risk", appLanguageRaw),
                value: risk,
                detail: nil,
                tint: report.fattyLiverRiskElevated ? .orange : .primary
            )
        }
    }

    // MARK: - Advice section

    @ViewBuilder
    private func adviceSection(_ report: LiverHealthReport) -> some View {
        if !report.advice.isEmpty {
            SectionPanel(
                title: appText("Advice", appLanguageRaw),
                systemImage: "lightbulb"
            ) {
                ForEach(Array(report.advice.enumerated()), id: \.offset) { _, line in
                    Label {
                        Text(line)
                            .font(.callout)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } icon: {
                        Image(systemName: "checkmark.circle")
                            .foregroundStyle(.secondary)
                    }
                }
                if let onAskAgent {
                    HStack {
                        Spacer()
                        Button {
                            onAskAgent(askPrompt(report), nil)
                        } label: {
                            Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                        }
                        .buttonStyle(.borderless)
                    }
                }
            }
        }
    }

    // MARK: - Helpers

    private func formatNumber(_ value: Double) -> String {
        String(format: "%.2f", value)
    }

    private func askPrompt(_ report: LiverHealthReport) -> String {
        var parts: [String] = ["请结合我的肝脏趋势数据解读："]
        parts.append(contentsOf: report.summaryLines)
        if report.hasFib4, let fib4 = report.fib4 {
            parts.append("FIB-4=\(formatNumber(fib4))" + (report.fib4Band.map { "（\($0)）" } ?? ""))
        }
        parts.append("这只是趋势提示,不是诊断。请说明我该如何向医生求证,以及是否需要腹部超声。")
        return parts.joined(separator: "\n")
    }

    private func reload() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            report = try await client.fetchReport()
        } catch {
            report = nil
            loadError = appText("Could not load liver trend. Try refresh.", appLanguageRaw)
        }
    }
}

// MARK: - Trend chip

private struct TrendChip: View {
    let label: String
    let trend: LiverTrend
    let appLanguageRaw: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: iconName)
                .foregroundStyle(tint)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 8) {
                    Text(label)
                        .font(.callout.weight(.semibold))
                    Text(verdictLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 2)
                        .background(tint.opacity(0.14), in: Capsule())
                }
                if let detail = changeDetail {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tint.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var tint: Color {
        switch trend.normalizedVerdict {
        case .improving: .green
        case .worsening: .red
        case .stable, .none: .secondary
        }
    }

    private var iconName: String {
        switch trend.normalizedVerdict {
        case .improving: "arrow.down.right.circle.fill"
        case .worsening: "arrow.up.right.circle.fill"
        case .stable, .none: "minus.circle.fill"
        }
    }

    private var verdictLabel: String {
        switch trend.normalizedVerdict {
        case .improving: appText("Improving", appLanguageRaw)
        case .worsening: appText("Worsening", appLanguageRaw)
        case .stable: appText("Stable", appLanguageRaw)
        case .none: appText("Trend", appLanguageRaw)
        }
    }

    private var changeDetail: String? {
        guard let first = trend.firstValue, let last = trend.lastValue else { return nil }
        let firstText = String(format: "%.1f", first)
        let lastText = String(format: "%.1f", last)
        if let pct = trend.pctChange {
            let pctText = String(format: "%+.0f%%", pct)
            return "\(firstText) → \(lastText) (\(pctText), n=\(trend.n))"
        }
        return "\(firstText) → \(lastText) (n=\(trend.n))"
    }
}

// MARK: - Marker row

private struct MarkerRow: View {
    let title: String
    let value: String
    let detail: String?
    let tint: Color

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(title)
                .font(.callout)
                .foregroundStyle(.secondary)
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(value)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(tint)
                    .multilineTextAlignment(.trailing)
                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 6)
    }
}
