import SwiftUI
import HealthAgentMacCore

struct GoalsView: View {
    let client: GoalClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var goals: [Goal] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var loaded = false

    private var overview: GoalOverview { GoalOverview(goals: goals) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                if !goals.isEmpty {
                    statsGrid(overview)
                }
                if let errorMessage {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(.red)
                }
                goalList
            }
            .frame(maxWidth: 1100, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(28)
        }
        .background(
            LinearGradient(
                colors: [
                    Color(nsColor: .windowBackgroundColor),
                    Color.indigo.opacity(0.05),
                    Color(nsColor: .windowBackgroundColor)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()
        )
        .task {
            guard !loaded else { return }
            loaded = true
            await reload()
        }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Goals", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Health goals and progress.", appLanguageRaw))
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

    private func statsGrid(_ overview: GoalOverview) -> some View {
        SectionPanel(title: appText("Overview", appLanguageRaw), systemImage: "chart.pie.fill") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 12)], spacing: 12) {
                statTile(appText("Active", appLanguageRaw), "\(overview.active)", "bolt.fill", .indigo)
                statTile(appText("Completed", appLanguageRaw), "\(overview.completed)", "checkmark.seal.fill", .green)
                statTile(appText("Total", appLanguageRaw), "\(overview.total)", "list.bullet", .secondary)
                statTile(appText("Completion rate", appLanguageRaw), "\(Int(overview.completionRate * 100))%", "percent", .teal)
            }
        }
    }

    private func statTile(_ title: String, _ value: String, _ icon: String, _ tone: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: icon)
                .foregroundStyle(tone)
            Text(value)
                .font(.system(size: 26, weight: .bold, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading)
        .background(tone.opacity(0.09), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    @ViewBuilder
    private var goalList: some View {
        SectionPanel(title: appText("Your Goals", appLanguageRaw), systemImage: "target") {
            if goals.isEmpty {
                Text(appText("No goals loaded yet.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                VStack(spacing: 12) {
                    ForEach(goals) { goal in
                        GoalCard(goal: goal, appLanguageRaw: appLanguageRaw, onAskAgent: onAskAgent)
                    }
                }
            }
        }
    }

    private func reload() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            goals = try await client.fetchGoals()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct GoalCard: View {
    let goal: Goal
    let appLanguageRaw: String
    var onAskAgent: ((String, AgentContextItem?) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: GoalPresentation.icon(for: goal.goalType))
                    .foregroundStyle(.indigo)
                Text(goal.title ?? appText("Goal", appLanguageRaw))
                    .font(.callout.weight(.semibold))
                    .lineLimit(1)
                Spacer(minLength: 8)
                Text(appText(GoalPresentation.statusKey(goal.status), appLanguageRaw))
                    .font(.caption2.weight(.bold))
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(GoalPresentation.statusColor(goal.status).opacity(0.14), in: Capsule())
                    .foregroundStyle(GoalPresentation.statusColor(goal.status))
            }
            if let description = goal.description, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            if let fraction = goal.progressFraction {
                ProgressView(value: fraction)
                    .tint(.indigo)
            }
            HStack {
                Text(progressLabel)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                Spacer()
                if let endDate = goal.endDate {
                    Label(String(endDate.prefix(10)), systemImage: "calendar")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let onAskAgent {
                    Button {
                        onAskAgent(askPrompt, nil)
                    } label: {
                        Image(systemName: "sparkles")
                    }
                    .buttonStyle(.borderless)
                    .help(appText("Ask Agent", appLanguageRaw))
                }
            }
        }
        .padding(14)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var progressLabel: String {
        if let current = goal.currentValue, let target = goal.targetValue {
            let unit = goal.targetUnit ?? ""
            return "\(formatNumber(current)) / \(formatNumber(target)) \(unit)"
        }
        return appText(GoalPresentation.periodKey(goal.goalPeriod), appLanguageRaw)
    }

    private var askPrompt: String {
        let title = goal.title ?? appText("Goal", appLanguageRaw)
        return "请评估我的健康目标「\(title)」当前进度,结合我的真实数据给出能推进它的具体行动和复查指标。"
    }

    private func formatNumber(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(0...1)))
    }
}

enum GoalPresentation {
    static func icon(for goalType: String) -> String {
        switch goalType.lowercased() {
        case "weight": return "scalemass.fill"
        case "exercise", "fitness": return "figure.run"
        case "diet", "nutrition": return "fork.knife"
        case "sleep": return "bed.double.fill"
        case "mental": return "brain.head.profile"
        case "medical": return "cross.case.fill"
        case "habit": return "repeat"
        default: return "target"
        }
    }

    static func statusKey(_ status: String) -> String {
        switch status.lowercased() {
        case "active": return "Active"
        case "completed": return "Completed"
        case "paused": return "Paused"
        case "abandoned": return "Abandoned"
        default: return status
        }
    }

    static func statusColor(_ status: String) -> Color {
        switch status.lowercased() {
        case "active": return .indigo
        case "completed": return .green
        case "paused": return .orange
        case "abandoned": return .secondary
        default: return .secondary
        }
    }

    static func periodKey(_ period: String) -> String {
        switch period.lowercased() {
        case "daily": return "Daily"
        case "weekly": return "Weekly"
        case "monthly": return "Monthly"
        default: return period
        }
    }
}
