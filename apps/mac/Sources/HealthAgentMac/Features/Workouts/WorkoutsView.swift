import SwiftUI
import HealthAgentMacCore

struct WorkoutsView: View {
    let client: WorkoutClient
    var onAskAgent: ((String, AgentContextItem?) -> Void)?
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var workouts: [WorkoutSummary] = []
    @State private var stats: WorkoutStats?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var loaded = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                if let stats {
                    statsGrid(stats)
                }
                if let errorMessage {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(.red)
                }
                workoutList
            }
            .frame(maxWidth: 1100, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(28)
        }
        .background(
            LinearGradient(
                colors: [
                    Color(nsColor: .windowBackgroundColor),
                    Color.orange.opacity(0.05),
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
                Text(appText("Workouts", appLanguageRaw))
                    .font(.largeTitle.bold())
                Text(appText("Recent training and load.", appLanguageRaw))
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

    private func statsGrid(_ stats: WorkoutStats) -> some View {
        SectionPanel(
            title: appText("Last 30 days", appLanguageRaw),
            systemImage: "chart.bar.fill"
        ) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                statTile(appText("Workouts", appLanguageRaw), "\(stats.totalWorkouts)", "figure.run", .orange)
                statTile(appText("Total minutes", appLanguageRaw), "\(stats.totalDurationMinutes)", "clock.fill", .blue)
                statTile(appText("Calories", appLanguageRaw), "\(stats.totalCalories)", "flame.fill", .red)
                statTile(appText("Distance (km)", appLanguageRaw), formatNumber(stats.totalDistanceKm), "location.fill", .green)
                statTile(appText("Trend", appLanguageRaw), appText(trendKey(stats.recentTrend), appLanguageRaw), trendIcon(stats.recentTrend), .purple)
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
                .minimumScaleFactor(0.6)
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
    private var workoutList: some View {
        SectionPanel(title: appText("Recent Workouts", appLanguageRaw), systemImage: "list.bullet.rectangle") {
            if workouts.isEmpty {
                Text(appText("No workouts loaded yet.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                VStack(spacing: 0) {
                    ForEach(workouts) { workout in
                        WorkoutRow(workout: workout, appLanguageRaw: appLanguageRaw, onAskAgent: onAskAgent)
                        if workout.id != workouts.last?.id {
                            Divider().padding(.leading, 44)
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
        do {
            async let list = client.fetchWorkouts(limit: 50)
            async let summary = client.fetchStats(days: 30)
            workouts = try await list
            stats = try await summary
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func formatNumber(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(0...1)))
    }

    private func trendKey(_ trend: String) -> String {
        switch trend.lowercased() {
        case "improving": return "Improving"
        case "declining": return "Declining"
        default: return "Stable"
        }
    }

    private func trendIcon(_ trend: String) -> String {
        switch trend.lowercased() {
        case "improving": return "arrow.up.right"
        case "declining": return "arrow.down.right"
        default: return "arrow.right"
        }
    }
}

private struct WorkoutRow: View {
    let workout: WorkoutSummary
    let appLanguageRaw: String
    var onAskAgent: ((String, AgentContextItem?) -> Void)?

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: WorkoutPresentation.icon(for: workout.workoutType))
                .font(.headline)
                .foregroundStyle(.orange)
                .frame(width: 30, height: 30)
                .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                Text(workout.workoutName ?? appText(WorkoutPresentation.typeKey(workout.workoutType), appLanguageRaw))
                    .font(.callout.weight(.semibold))
                    .lineLimit(1)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 12)
            if let calories = workout.calories {
                Text("\(calories) kcal")
                    .font(.callout.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.red)
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
        .padding(.vertical, 10)
    }

    private var subtitle: String {
        var parts: [String] = [String(workout.workoutDate.prefix(10))]
        if let seconds = workout.durationSeconds {
            parts.append("\(seconds / 60) \(appText("min", appLanguageRaw))")
        }
        if let meters = workout.distanceMeters, meters > 0 {
            let km = meters / 1000
            parts.append("\(km.formatted(.number.precision(.fractionLength(0...1)))) km")
        }
        if let hr = workout.avgHeartRate {
            parts.append("\(hr) bpm")
        }
        return parts.joined(separator: " · ")
    }

    private var askPrompt: String {
        let name = workout.workoutName ?? appText(WorkoutPresentation.typeKey(workout.workoutType), appLanguageRaw)
        return "请结合我的恢复状态评估这次「\(name)」运动(\(subtitle))的训练负荷是否合适,并给出下一步建议。"
    }
}

enum WorkoutPresentation {
    static func icon(for type: String) -> String {
        switch type.lowercased() {
        case "running": return "figure.run"
        case "cycling": return "figure.outdoor.cycle"
        case "swimming": return "figure.pool.swim"
        case "strength": return "dumbbell.fill"
        case "yoga": return "figure.yoga"
        case "walking": return "figure.walk"
        case "hiking": return "figure.hiking"
        case "hiit": return "bolt.heart.fill"
        case "cardio": return "heart.fill"
        default: return "figure.mixed.cardio"
        }
    }

    static func typeKey(_ type: String) -> String {
        switch type.lowercased() {
        case "running": return "Running"
        case "cycling": return "Cycling"
        case "swimming": return "Swimming"
        case "strength": return "Strength"
        case "yoga": return "Yoga"
        case "walking": return "Walking"
        case "hiking": return "Hiking"
        case "hiit": return "HIIT"
        case "cardio": return "Cardio"
        default: return "Workout"
        }
    }
}
