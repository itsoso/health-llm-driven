import SwiftUI
import HealthAgentMacCore

struct AgendaView: View {
    let client: AgendaClient
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var today: AgendaToday?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var completingID: String?

    private var language: AppLanguage { AppLanguage(storedValue: appLanguageRaw) }
    private var summary: AgendaSummary? {
        today.map(AgendaSummary.init(today:))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                if let summary {
                    summaryGrid(summary)
                }
                content
            }
            .padding(24)
            .frame(maxWidth: 980, alignment: .leading)
        }
        .task {
            if today == nil {
                await refresh()
            }
        }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Health Agenda", appLanguageRaw))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(appText("Today Agenda", appLanguageRaw))
                    .font(.largeTitle.weight(.bold))
                if let today {
                    Text("\(today.agendaDate) · \(today.count) \(appText("Agenda Items", appLanguageRaw))")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } else {
                    Text(appText("Training gate, follow-ups, protocols, and device quality in one place.", appLanguageRaw))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button {
                Task { await refresh() }
            } label: {
                Label(appText("Refresh", appLanguageRaw), systemImage: isLoading ? "arrow.triangle.2.circlepath" : "arrow.clockwise")
            }
            .disabled(isLoading)
        }
    }

    private func summaryGrid(_ summary: AgendaSummary) -> some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 4), spacing: 12) {
            summaryTile(appText("Agenda Total", appLanguageRaw), summary.total, .blue)
            summaryTile(appText("Actionable", appLanguageRaw), summary.actionable, .green)
            summaryTile(appText("Overdue", appLanguageRaw), summary.overdue, .red)
            summaryTile(appText("Advisory", appLanguageRaw), summary.info, .yellow)
        }
    }

    private func summaryTile(_ label: String, _ value: Int, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(value)")
                .font(.title2.weight(.bold))
                .foregroundStyle(color)
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.secondary.opacity(0.12))
        )
    }

    @ViewBuilder
    private var content: some View {
        if isLoading && today == nil {
            ProgressView(appText("Loading agenda...", appLanguageRaw))
                .frame(maxWidth: .infinity, minHeight: 220)
        } else if let errorMessage {
            ContentUnavailableView(
                appText("Agenda failed to load", appLanguageRaw),
                systemImage: "exclamationmark.triangle",
                description: Text(errorMessage)
            )
            .frame(minHeight: 260)
        } else if (today?.items ?? []).isEmpty {
            ContentUnavailableView(
                appText("No agenda items today", appLanguageRaw),
                systemImage: "checkmark.circle",
                description: Text(appText("No protocol, follow-up, training gate, or device-quality item is due.", appLanguageRaw))
            )
            .frame(minHeight: 260)
        } else {
            VStack(spacing: 10) {
                ForEach(today?.items ?? []) { item in
                    agendaRow(item)
                }
            }
        }
    }

    private func agendaRow(_ item: AgendaItem) -> some View {
        let presentation = AgendaItemPresentation(item: item)
        return HStack(alignment: .top, spacing: 12) {
            Image(systemName: presentation.systemImage)
                .font(.title3)
                .foregroundStyle(color(for: presentation.tone))
                .frame(width: 34, height: 34)
                .background(color(for: presentation.tone).opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Text(item.title)
                        .font(.headline)
                        .lineLimit(2)
                    Text(presentation.statusLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(color(for: presentation.tone))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(color(for: presentation.tone).opacity(0.12), in: Capsule())
                }
                if let detail = item.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                }
                if !presentation.metaLine.isEmpty {
                    Text(presentation.metaLine)
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
            Spacer()
            if presentation.canComplete {
                Button {
                    Task { await complete(item) }
                } label: {
                    if completingID == item.id {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label(appText("Complete", appLanguageRaw), systemImage: "checkmark")
                    }
                }
                .disabled(completingID != nil)
            }
        }
        .padding(14)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.10)))
    }

    private func color(for tone: AgendaTone) -> Color {
        switch tone {
        case .green: .green
        case .yellow: .orange
        case .red: .red
        case .blue: .blue
        case .gray: .secondary
        }
    }

    private func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            today = try await client.fetchToday()
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func complete(_ item: AgendaItem) async {
        completingID = item.id
        defer { completingID = nil }
        do {
            _ = try await client.complete(item.source)
            await refresh()
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }
}
