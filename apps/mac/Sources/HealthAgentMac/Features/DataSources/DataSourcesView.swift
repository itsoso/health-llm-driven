import SwiftUI
import HealthAgentMacCore

/// 「数据来源」页:把后端按来源聚合的穿戴数据 (Apple Watch / RingConn / Garmin …)
/// 一来源一张卡展示;底部可选「设备一致性对比」。best-effort 取数:summary 失败
/// 显示错误/空态,绝不伪造数据;compare 失败静默隐藏对比区。
struct DataSourcesView: View {
    let client: DeviceSourcesClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var response: DeviceSourcesResponse?
    @State private var comparison: DeviceComparisonResponse?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var loaded = false

    private let windowDays = 30
    private let compareDays = 7

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
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
                Color.teal.opacity(0.05),
                Color(nsColor: .windowBackgroundColor)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Data Sources", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Wearable records grouped by device.", appLanguageRaw))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if isLoading {
                ProgressView().controlSize(.small)
            }
            Button(appText("Refresh", appLanguageRaw)) {
                Task { await reload() }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let errorMessage {
            Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                .font(.callout)
                .foregroundStyle(.red)
        }

        let sources = response?.sources ?? []
        if sources.isEmpty {
            if !isLoading && errorMessage == nil {
                emptyState
            }
        } else {
            ForEach(sources) { source in
                SourceCard(source: source, appLanguageRaw: appLanguageRaw, onAskAgent: onAskAgent)
            }
            comparisonSection
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: "applewatch.slash")
                .font(.system(size: 34))
                .foregroundStyle(.secondary)
            Text(appText("No wearable data yet — sync Apple Health on your iPhone and it will show up here.", appLanguageRaw))
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 160, alignment: .center)
        .multilineTextAlignment(.center)
        .appCard()
    }

    @ViewBuilder
    private var comparisonSection: some View {
        let rows = comparison?.comparisons ?? []
        if !rows.isEmpty {
            SectionPanel(
                title: appText("Device consistency", appLanguageRaw),
                systemImage: "arrow.left.arrow.right"
            ) {
                Text(appText("Metrics reported by two or more sources.", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                VStack(spacing: 0) {
                    ForEach(rows) { row in
                        ComparisonRow(row: row, appLanguageRaw: appLanguageRaw)
                        if row.id != rows.last?.id {
                            Divider()
                        }
                    }
                }
            }
        }
    }

    private func reload() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        // summary 是主路径:失败 → 显示错误态 (绝不伪造)。
        do {
            response = try await client.fetchSourcesSummary(days: windowDays)
        } catch {
            response = nil
            errorMessage = appText("Could not load data sources. Try refresh.", appLanguageRaw)
        }

        // compare 是次要信息:best-effort,失败/为空就隐藏对比区。
        comparison = await client.fetchComparison(days: compareDays)
    }
}

// MARK: - Source card

private struct SourceCard: View {
    let source: DeviceSourceSummary
    let appLanguageRaw: String
    var onAskAgent: ((String, AgentContextItem?) -> Void)?

    var body: some View {
        SectionPanel(title: displayName, systemImage: DeviceSourceDisplay.systemImage(for: source.dataSource)) {
            Text(coverageLine)
                .font(.caption)
                .foregroundStyle(.secondary)

            let tiles = MetricTile.tiles(for: source.metrics, appLanguageRaw: appLanguageRaw)
            if tiles.isEmpty {
                Text(appText("No data", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 12)], spacing: 12) {
                    ForEach(tiles) { tile in
                        metricTile(tile)
                    }
                }
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
    }

    private var displayName: String {
        DeviceSourceDisplay.name(for: source.dataSource)
    }

    private var coverageLine: String {
        let daysFmt = String(format: appText("Last %d days", appLanguageRaw), source.daysCovered)
        guard let latest = source.latestDate, !latest.isEmpty else {
            return daysFmt
        }
        let latestFmt = String(format: appText("Latest %@", appLanguageRaw), String(latest.prefix(10)))
        return "\(daysFmt) · \(latestFmt)"
    }

    private func metricTile(_ tile: MetricTile) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: tile.systemImage)
                .foregroundStyle(toneColor(tile.tone))
            Text(tile.value)
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            Text(tile.title)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .topLeading)
        .background(toneColor(tile.tone).opacity(0.09), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private var askPrompt: String {
        "请解读我「\(displayName)」最近的穿戴数据(\(coverageLine)),并指出与其他设备相比是否有异常或值得关注的趋势。"
    }
}

// MARK: - Metric tiles (UI-layer mapping)

private struct MetricTile: Identifiable {
    let id: String
    let title: String
    let value: String
    let systemImage: String
    let tone: String

    /// 从一组指标里抽出有值的格子。缺值的不出现 (设备不上报 → 不展示)。
    static func tiles(for m: DeviceSourceMetrics, appLanguageRaw: String) -> [MetricTile] {
        var out: [MetricTile] = []

        if let steps = m.steps {
            out.append(MetricTile(
                id: "steps", title: appText("Steps", appLanguageRaw),
                value: steps.formatted(.number), systemImage: "figure.walk", tone: "green"
            ))
        }
        if let rhr = m.restingHeartRate {
            out.append(MetricTile(
                id: "rhr", title: appText("Resting HR", appLanguageRaw),
                value: "\(rhr)", systemImage: "heart.fill", tone: "red"
            ))
        }
        if let hrv = m.hrv {
            out.append(MetricTile(
                id: "hrv", title: appText("HRV", appLanguageRaw),
                value: hrv.formatted(.number.precision(.fractionLength(0...0))), systemImage: "waveform.path.ecg", tone: "purple"
            ))
        }
        if let sleepText = DurationFormat.minutesToHours(m.totalSleepDuration) {
            out.append(MetricTile(
                id: "sleep", title: appText("Sleep", appLanguageRaw),
                value: sleepText, systemImage: "bed.double.fill", tone: "indigo"
            ))
        }
        if let spo2 = m.spo2Avg {
            out.append(MetricTile(
                id: "spo2", title: appText("SpO2", appLanguageRaw),
                value: "\(spo2.formatted(.number.precision(.fractionLength(0...0))))%", systemImage: "lungs.fill", tone: "cyan"
            ))
        }
        if let cal = m.activeCalories {
            out.append(MetricTile(
                id: "cal", title: appText("Active Calories", appLanguageRaw),
                value: cal.formatted(.number), systemImage: "flame.fill", tone: "orange"
            ))
        }
        return out
    }
}

// MARK: - Comparison row

private struct ComparisonRow: View {
    let row: DeviceComparison
    let appLanguageRaw: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(row.label)
                    .font(.callout.weight(.semibold))
                Spacer()
                if let agreement = row.agreement, !agreement.isEmpty {
                    Text(agreement)
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12), in: Capsule())
                        .foregroundStyle(.secondary)
                }
            }
            HStack(spacing: 14) {
                ForEach(sortedSources, id: \.0) { pair in
                    HStack(spacing: 4) {
                        Text(DeviceSourceDisplay.name(for: pair.0))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(formatValue(pair.1))
                            .font(.caption.weight(.semibold).monospacedDigit())
                    }
                }
            }
        }
        .padding(.vertical, 10)
    }

    private var sortedSources: [(String, Double)] {
        row.bySource.sorted { $0.key < $1.key }.map { ($0.key, $0.value) }
    }

    private func formatValue(_ value: Double) -> String {
        let number = value.formatted(.number.precision(.fractionLength(0...1)))
        guard let unit = row.unit, !unit.isEmpty else {
            return number
        }
        return "\(number) \(unit)"
    }
}
