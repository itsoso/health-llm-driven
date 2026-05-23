import Foundation

public struct DesktopDashboardPresentation: Equatable, Sendable {
    public let heroTitle: String
    public let heroSubtitle: String
    public let heroMetrics: [DesktopDashboardMetric]
    public let primaryMetrics: [DesktopDashboardMetric]
    public let wearableMetrics: [DesktopDashboardMetric]
    public let focusChips: [String]
    public let actionRows: [DesktopDashboardRow]
    public let recentRecordRows: [DesktopDashboardRow]
    public let memoryRows: [DesktopDashboardRow]
    public let activeJobRows: [DesktopDashboardRow]

    public init(bootstrap: DesktopBootstrap) {
        let summary = bootstrap.recentRecordsSummary
        self.heroTitle = bootstrap.user.name?.isEmpty == false ? bootstrap.user.name! : "Health Agent"
        self.heroSubtitle = DesktopDashboardPresentation.subtitle(for: bootstrap)
        self.heroMetrics = DesktopDashboardPresentation.heroMetrics(from: summary)
        self.primaryMetrics = DesktopDashboardPresentation.primaryMetrics(from: summary)
        self.wearableMetrics = DesktopDashboardPresentation.wearableMetrics(from: summary.latestGarmin)
        self.focusChips = Array((bootstrap.trajectory.focusDomains ?? []).prefix(5))
        self.actionRows = bootstrap.dailyPlan.actions.prefix(4).map {
            DesktopDashboardRow(
                id: $0.id,
                title: $0.title,
                subtitle: $0.domain,
                value: nil,
                tone: "teal",
                systemImage: "checkmark.circle.fill",
                progress: nil
            )
        }
        self.recentRecordRows = (summary.recentRecords ?? []).prefix(8).map {
            DesktopDashboardRow(
                id: "\($0.type)-\($0.id)",
                title: $0.title,
                subtitle: $0.recordDate,
                value: $0.displayValue,
                tone: DesktopDashboardPresentation.tone(forRecordType: $0.type),
                systemImage: DesktopDashboardPresentation.icon(forRecordType: $0.type),
                progress: nil
            )
        }
        self.memoryRows = bootstrap.recentMemory
            .filter { !DesktopDashboardPresentation.isLowSignalMemory($0.objectValue) }
            .prefix(5)
            .map {
            DesktopDashboardRow(
                id: "memory-\($0.id)",
                title: $0.objectValue,
                subtitle: nil,
                value: nil,
                tone: "indigo",
                systemImage: "brain.head.profile",
                progress: nil
            )
        }
        self.activeJobRows = bootstrap.activeJobs.prefix(4).map {
            DesktopDashboardRow(
                id: "job-\($0.id)",
                title: $0.jobType,
                subtitle: $0.status,
                value: "\($0.progress)%",
                tone: "blue",
                systemImage: "clock.arrow.circlepath",
                progress: Double($0.progress) / 100
            )
        }
    }

    private static func subtitle(for bootstrap: DesktopBootstrap) -> String {
        let date = bootstrap.recentRecordsSummary.date ?? bootstrap.dailyPlan.planDate
        let recordCount = bootstrap.recentRecordsSummary.recentRecords?.count ?? 0
        return "\(date) · \(bootstrap.actionCards.count) cards · \(bootstrap.recentMemory.count) memories · \(recordCount) recent records"
    }

    private static func heroMetrics(from summary: RecentRecordsSummary) -> [DesktopDashboardMetric] {
        let garmin = summary.latestGarmin
        return [
            .init(id: "hero_steps", titleKey: "Steps", value: garmin?.steps.map(String.init) ?? "—", detail: garmin?.recordDate ?? "No wearable data", tone: "blue", systemImage: "figure.walk"),
            .init(id: "hero_sleep", titleKey: "Sleep Score", value: garmin?.sleepScore.map(String.init) ?? "—", detail: garmin?.trainingReadinessScore.map { "Readiness \($0)" } ?? "No wearable data", tone: "purple", systemImage: "moon.zzz.fill"),
            .init(id: "hero_spo2", titleKey: "SpO2", value: garmin?.spo2Avg.map { "\(formatNumber($0))%" } ?? "—", detail: "wearable", tone: "cyan", systemImage: "lungs.fill"),
            .init(id: "hero_weight", titleKey: "Latest Weight", value: summary.latestWeight?.displayValue ?? "—", detail: summary.latestWeight?.recordDate ?? "No record", tone: "green", systemImage: "scalemass.fill")
        ]
    }

    private static func primaryMetrics(from summary: RecentRecordsSummary) -> [DesktopDashboardMetric] {
        [
            .init(
                id: "diet",
                titleKey: "Diet 30d",
                value: "\(formatNumber(summary.diet?.last30Calories ?? summary.diet?.todayCalories ?? 0)) kcal",
                detail: "\(summary.diet?.last30Count ?? summary.diet?.todayCount ?? 0) records",
                tone: "orange",
                systemImage: "fork.knife"
            ),
            .init(
                id: "water",
                titleKey: "Water 30d",
                value: "\(formatNumber(Double(summary.water?.last30TotalMl ?? summary.water?.todayTotalMl ?? 0))) ml",
                detail: "\(summary.water?.last30Count ?? summary.water?.todayCount ?? 0) records",
                tone: "cyan",
                systemImage: "drop.fill"
            ),
            .init(
                id: "weight",
                titleKey: "Latest Weight",
                value: summary.latestWeight?.displayValue ?? "—",
                detail: summary.latestWeight?.recordDate ?? "No record",
                tone: "green",
                systemImage: "scalemass.fill"
            ),
            .init(
                id: "bp",
                titleKey: "Latest BP",
                value: summary.latestBloodPressure?.displayValue ?? "—",
                detail: summary.latestBloodPressure?.category ?? summary.latestBloodPressure?.recordDate ?? "No record",
                tone: "pink",
                systemImage: "heart.text.square.fill"
            )
        ]
    }

    private static func wearableMetrics(from garmin: GarminMetricSummary?) -> [DesktopDashboardMetric] {
        [
            .init(id: "steps", titleKey: "Steps", value: garmin?.steps.map(String.init) ?? "—", detail: garmin?.recordDate ?? "No wearable data", tone: "blue", systemImage: "figure.walk"),
            .init(id: "sleep", titleKey: "Sleep Score", value: garmin?.sleepScore.map(String.init) ?? "—", detail: garmin?.trainingReadinessScore.map { "Readiness \($0)" } ?? "No wearable data", tone: "purple", systemImage: "moon.zzz.fill"),
            .init(id: "spo2", titleKey: "SpO2", value: garmin?.spo2Avg.map { "\(formatNumber($0))%" } ?? "—", detail: "wearable", tone: "cyan", systemImage: "lungs.fill"),
            .init(id: "rhr", titleKey: "Resting HR", value: garmin?.restingHeartRate.map(String.init) ?? "—", detail: garmin?.hrv.map { "HRV \(formatNumber($0))" } ?? "wearable", tone: "red", systemImage: "heart.fill")
        ]
    }

    private static func formatNumber(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.numberStyle = .decimal
        formatter.usesGroupingSeparator = true
        formatter.minimumFractionDigits = 0
        formatter.maximumFractionDigits = value.rounded() == value ? 0 : 1
        return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
    }

    private static func icon(forRecordType type: String) -> String {
        switch type {
        case "diet": "fork.knife"
        case "water": "drop.fill"
        case "weight": "scalemass.fill"
        case "blood_pressure": "heart.text.square.fill"
        default: "doc.text"
        }
    }

    private static func tone(forRecordType type: String) -> String {
        switch type {
        case "diet": "orange"
        case "water": "cyan"
        case "weight": "green"
        case "blood_pressure": "pink"
        default: "gray"
        }
    }

    private static func isLowSignalMemory(_ value: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 4 else { return true }
        return trimmed.allSatisfy { $0.isNumber || $0 == "." || $0 == "%" }
    }
}

public struct DesktopDashboardMetric: Equatable, Identifiable, Sendable {
    public let id: String
    public let titleKey: String
    public let value: String
    public let detail: String
    public let tone: String
    public let systemImage: String
}

public struct DesktopDashboardRow: Equatable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let subtitle: String?
    public let value: String?
    public let tone: String
    public let systemImage: String
    public let progress: Double?
}
