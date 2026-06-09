import SwiftUI
import HealthAgentMacCore

struct BriefingCardView: View {
    let briefing: DailyBriefing
    let appLanguageRaw: String
    var onAskAgent: ((String, AgentContextItem?) -> Void)? = nil
    var onAddContext: ((AgentContextItem) -> Void)? = nil
    var onScheduleReminder: ((BriefingSection) -> Void)? = nil

    @State private var reminderConfirmedFor: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Label(appText("Today's Briefing", appLanguageRaw), systemImage: "sun.max.fill")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.orange)
                Spacer()
                if let date = briefing.date, !date.isEmpty {
                    Text(date)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            if let greeting = briefing.greeting, !greeting.isEmpty {
                Text(greeting)
                    .font(.body)
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            VStack(alignment: .leading, spacing: 12) {
                ForEach(briefing.sections) { section in
                    sectionRow(section)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .appCard()
    }

    private func sectionRow(_ section: BriefingSection) -> some View {
        let kind = section.statusKind
        let color = Self.statusColor(kind)

        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: Self.statusIcon(kind))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(color)
                Text(section.title)
                    .font(.headline.weight(.semibold))
            }
            ForEach(Array(section.items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: 8) {
                    Text("•")
                        .font(.body)
                        .foregroundStyle(color)
                    Text(item)
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            sectionActions(section)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(color.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    @ViewBuilder
    private func sectionActions(_ section: BriefingSection) -> some View {
        if !section.items.isEmpty {
            HStack(spacing: 8) {
                if let onAskAgent {
                    Button {
                        onAskAgent(Self.promptText(for: section), Self.contextItem(for: section))
                    } label: {
                        Label(appText("Ask Agent", appLanguageRaw), systemImage: "sparkles")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.mini)
                }
                Button {
                    onScheduleReminder?(section)
                    confirmReminder(for: section)
                } label: {
                    Label(appText("Remind me", appLanguageRaw), systemImage: "bell.badge")
                        .font(.caption2)
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)
                if let onAddContext {
                    Button {
                        onAddContext(Self.contextItem(for: section))
                    } label: {
                        Label(appText("Add to basket", appLanguageRaw), systemImage: "tray.and.arrow.down")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.mini)
                }
                if reminderConfirmedFor == section.title {
                    Text(appText("Reminder set", appLanguageRaw))
                        .font(.caption2)
                        .foregroundStyle(.green)
                }
            }
            .padding(.top, 2)
        }
    }

    private func confirmReminder(for section: BriefingSection) {
        reminderConfirmedFor = section.title
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            if reminderConfirmedFor == section.title {
                reminderConfirmedFor = nil
            }
        }
    }

    static func statusColor(_ kind: BriefingSection.Status) -> Color {
        switch kind {
        case .good: return .green
        case .warning: return .orange
        case .poor: return .red
        case .info: return .secondary
        }
    }

    static func statusIcon(_ kind: BriefingSection.Status) -> String {
        switch kind {
        case .good: return "checkmark.circle.fill"
        case .warning: return "exclamationmark.triangle.fill"
        case .poor: return "xmark.octagon.fill"
        case .info: return "info.circle.fill"
        }
    }

    static func promptText(for section: BriefingSection) -> String {
        let body = section.items.joined(separator: "\n• ")
        return "\(section.title)\n• \(body)\n\n请基于这个简报段落给出 1–2 个具体的行动建议。"
    }

    static func contextItem(for section: BriefingSection) -> AgentContextItem {
        let summary = section.items.prefix(3).joined(separator: " / ")
        var payload: [String: String] = [
            "status": section.statusKind.rawValue
        ]
        for (idx, item) in section.items.enumerated() where idx < 5 {
            payload["item_\(idx)"] = item
        }
        return AgentContextItem(
            sourceID: "briefing-\(section.title)",
            sourceKind: "briefing",
            title: section.title,
            summary: summary.isEmpty ? section.title : summary,
            payload: payload
        )
    }
}
