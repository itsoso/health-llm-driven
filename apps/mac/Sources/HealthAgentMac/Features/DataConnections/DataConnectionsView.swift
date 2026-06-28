import SwiftUI
import HealthAgentMacCore

struct DataConnectionsView: View {
    let client: DataConnectionsClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var response: DataConnectionsResponse?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var loaded = false

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
                Color.blue.opacity(0.045),
                Color(nsColor: .windowBackgroundColor)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Data Connections", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("External data connections, consent scopes, sync health, and degraded behavior.", appLanguageRaw))
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

        let connections = response?.connections ?? []
        if connections.isEmpty {
            if !isLoading && errorMessage == nil {
                emptyState
            }
        } else {
            summaryCard(connections)
            LazyVStack(spacing: 14) {
                ForEach(connections) { connection in
                    ConnectionCard(connection: connection, appLanguageRaw: appLanguageRaw, onAskAgent: onAskAgent)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(alignment: .center, spacing: 10) {
            Image(systemName: "shield.slash")
                .font(.system(size: 34))
                .foregroundStyle(.secondary)
            Text(appText("No external data connections yet.", appLanguageRaw))
                .font(.headline)
            Text(appText("Connect Apple Health, wearable, FHIR, or report sources from mobile/web; Mac will show their sync and authorization health here.", appLanguageRaw))
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, minHeight: 190, alignment: .center)
        .appCard()
    }

    private func summaryCard(_ connections: [DataConnection]) -> some View {
        let healthy = connections.filter { $0.health.status == "healthy" }.count
        let attention = connections.filter { $0.health.needsReconnect || $0.health.severity == "blocked" }.count
        let cached = connections.filter { $0.health.canUseCachedData }.count

        return HStack(spacing: 12) {
            SummaryPill(title: appText("Connections", appLanguageRaw), value: "\(connections.count)", systemImage: "link", tone: "blue")
            SummaryPill(title: appText("Available", appLanguageRaw), value: "\(healthy)", systemImage: "checkmark.seal.fill", tone: "green")
            SummaryPill(title: appText("Needs Action", appLanguageRaw), value: "\(attention)", systemImage: "exclamationmark.triangle.fill", tone: attention > 0 ? "orange" : "secondary")
            SummaryPill(title: appText("Readable Cache", appLanguageRaw), value: "\(cached)", systemImage: "lock.doc", tone: "teal")
        }
        .appCard()
    }

    private func reload() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            response = try await client.fetchMyConnections()
        } catch {
            response = nil
            errorMessage = appText("Could not load data connections. Try refresh.", appLanguageRaw)
        }
    }
}

private struct SummaryPill: View {
    let title: String
    let value: String
    let systemImage: String
    let tone: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .foregroundStyle(toneColor(tone))
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(value)
                    .font(.title3.bold().monospacedDigit())
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
        .background(toneColor(tone).opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct ConnectionCard: View {
    let connection: DataConnection
    let appLanguageRaw: String
    var onAskAgent: ((String, AgentContextItem?) -> Void)?

    private var display: DataConnectionHealthDisplay {
        DataConnectionHealthDisplay.display(for: connection)
    }

    private var health: DataConnectionHealth {
        connection.health
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: providerSymbol)
                    .font(.title2)
                    .foregroundStyle(statusColor)
                    .frame(width: 32)
                VStack(alignment: .leading, spacing: 4) {
                    Text(connection.displayName)
                        .font(.title3.bold())
                    Text(providerLine)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                statusBadge
            }

            Text(display.detail)
                .font(.callout)
                .foregroundStyle(.secondary)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 12)], spacing: 12) {
                DetailTile(title: appText("Connection Action", appLanguageRaw), value: display.actionLabel, systemImage: "hand.tap", tone: display.tint)
                DetailTile(title: appText("Cache", appLanguageRaw), value: display.cachedDataLabel, systemImage: "lock.doc", tone: health.canUseCachedData ? "teal" : "red")
                DetailTile(title: appText("Connection Last Sync", appLanguageRaw), value: shortDate(connection.lastSyncAt ?? health.lastSuccessAt), systemImage: "clock.arrow.circlepath", tone: "blue")
                DetailTile(title: appText("Token", appLanguageRaw), value: health.tokenStatus ?? connection.tokenStatus, systemImage: "key", tone: display.tint)
            }

            if !connection.scopes.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text(appText("Consent Scopes", appLanguageRaw))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    FlowLayout(items: connection.scopes) { scope in
                        Text(scope)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.secondary.opacity(0.10), in: Capsule())
                    }
                }
            }

            footer
        }
        .appCard()
    }

    private var providerLine: String {
        "\(connection.providerType) · \(connection.provider)"
    }

    private var providerSymbol: String {
        switch connection.provider.lowercased() {
        case "apple_health", "apple-health", "healthkit": "heart.text.square.fill"
        case "garmin": "figure.run"
        case "fhir", "hospital": "cross.case.fill"
        default: "link.circle.fill"
        }
    }

    private var statusColor: Color {
        switch display.tint {
        case "ok": .green
        case "warning": .orange
        case "blocked": .red
        default: .secondary
        }
    }

    private var statusBadge: some View {
        Text(display.statusLabel)
            .font(.caption.weight(.bold))
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(statusColor.opacity(0.14), in: Capsule())
            .foregroundStyle(statusColor)
    }

    @ViewBuilder
    private var footer: some View {
        HStack(alignment: .center, spacing: 10) {
            Label(appText("Read-only. Reva never shows tokens here.", appLanguageRaw), systemImage: "lock.shield")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            if let onAskAgent {
                Button {
                    onAskAgent(askPrompt, nil)
                } label: {
                    Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                }
                .buttonStyle(.borderless)
            }
        }
    }

    private var askPrompt: String {
        let scopes = connection.scopes.joined(separator: ", ")
        return "请解释我的 \(connection.displayName) 数据连接状态：状态=\(display.statusLabel)，缓存=\(display.cachedDataLabel)，授权范围=\(scopes)。说明它对未来7天健康运行时编排有什么影响。"
    }

    private func shortDate(_ raw: String?) -> String {
        guard let raw, !raw.isEmpty else {
            return "—"
        }
        return String(raw.prefix(16)).replacingOccurrences(of: "T", with: " ")
    }
}

private struct DetailTile: View {
    let title: String
    let value: String
    let systemImage: String
    let tone: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: systemImage)
                .foregroundStyle(tileColor)
            Text(value.isEmpty ? "—" : value)
                .font(.callout.weight(.semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 86, alignment: .topLeading)
        .background(tileColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private var tileColor: Color {
        switch tone {
        case "ok", "green": .green
        case "warning", "orange": .orange
        case "blocked", "red": .red
        case "teal": .teal
        case "blue": .blue
        default: .secondary
        }
    }
}

private struct FlowLayout<Content: View>: View {
    let items: [String]
    @ViewBuilder let content: (String) -> Content

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 92), spacing: 8)], alignment: .leading, spacing: 8) {
            ForEach(items, id: \.self) { item in
                content(item)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}
