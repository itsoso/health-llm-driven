import Foundation

public struct DesktopDashboardPresentation: Equatable, Sendable {
    public let heroTitle: String
    public let heroSubtitle: String
    public let heroMetrics: [DesktopDashboardMetric]
    public let primaryMetrics: [DesktopDashboardMetric]
    public let sevenDayMetrics: [DesktopDashboardMetric]
    public let thirtyDayMetrics: [DesktopDashboardMetric]
    public let sevenDayTrends: [DesktopDashboardTrend]
    public let thirtyDayTrends: [DesktopDashboardTrend]
    public let wearableMetrics: [DesktopDashboardMetric]
    public let focusChips: [String]
    public let actionRows: [DesktopDashboardRow]
    public let recentRecordRows: [DesktopDashboardRow]
    public let memoryRows: [DesktopDashboardRow]
    public let activeJobRows: [DesktopDashboardRow]
    public let inputInboxEvents: [DesktopInputInboxEvent]
    public let inputInboxSummary: DesktopInputInboxSummary

    public init(bootstrap: DesktopBootstrap) {
        let summary = bootstrap.recentRecordsSummary
        self.heroTitle = bootstrap.user.name?.isEmpty == false ? bootstrap.user.name! : "Health Agent"
        self.heroSubtitle = DesktopDashboardPresentation.subtitle(for: bootstrap)
        self.heroMetrics = DesktopDashboardPresentation.heroMetrics(from: summary)
        self.sevenDayMetrics = DesktopDashboardPresentation.rangeMetrics(from: summary, days: 7)
        self.thirtyDayMetrics = DesktopDashboardPresentation.rangeMetrics(from: summary, days: 30)
        self.sevenDayTrends = DesktopDashboardPresentation.trends(from: summary, days: 7)
        self.thirtyDayTrends = DesktopDashboardPresentation.trends(from: summary, days: 30)
        self.primaryMetrics = self.sevenDayMetrics
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
        self.inputInboxEvents = DesktopDashboardPresentation.inputInboxEvents(from: bootstrap)
        self.inputInboxSummary = DesktopInputInboxSummary(events: self.inputInboxEvents)
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

    private static func rangeMetrics(from summary: RecentRecordsSummary, days: Int) -> [DesktopDashboardMetric] {
        let dietValue: Double = days == 7
            ? (summary.diet?.last7Calories ?? summary.diet?.last30Calories ?? summary.diet?.todayCalories ?? 0)
            : (summary.diet?.last30Calories ?? summary.diet?.last7Calories ?? summary.diet?.todayCalories ?? 0)
        let dietCount: Int = days == 7
            ? (summary.diet?.last7Count ?? summary.diet?.last30Count ?? summary.diet?.todayCount ?? 0)
            : (summary.diet?.last30Count ?? summary.diet?.last7Count ?? summary.diet?.todayCount ?? 0)
        let dietAverage: Double = days == 7
            ? (summary.diet?.last7AvgCalories ?? dietValue / 7)
            : (summary.diet?.last30AvgCalories ?? dietValue / 30)

        let waterValue: Int = days == 7
            ? (summary.water?.last7TotalMl ?? summary.water?.last30TotalMl ?? summary.water?.todayTotalMl ?? 0)
            : (summary.water?.last30TotalMl ?? summary.water?.last7TotalMl ?? summary.water?.todayTotalMl ?? 0)
        let waterCount: Int = days == 7
            ? (summary.water?.last7Count ?? summary.water?.last30Count ?? summary.water?.todayCount ?? 0)
            : (summary.water?.last30Count ?? summary.water?.last7Count ?? summary.water?.todayCount ?? 0)
        let waterAverage: Double = days == 7
            ? (summary.water?.last7AvgMl ?? Double(waterValue) / 7)
            : (summary.water?.last30AvgMl ?? Double(waterValue) / 30)

        let supplementValue: Int = days == 7
            ? (summary.supplements?.last7Count ?? summary.supplements?.todayCount ?? 0)
            : (summary.supplements?.last30Count ?? summary.supplements?.last7Count ?? summary.supplements?.todayCount ?? 0)
        let supplementAverage: Double = days == 7
            ? (summary.supplements?.last7AvgPerDay ?? Double(supplementValue) / 7)
            : (summary.supplements?.last30AvgPerDay ?? Double(supplementValue) / 30)
        let supplementAdherence = days == 7
            ? summary.supplements?.adherence7Pct
            : summary.supplements?.adherence30Pct
        let supplementDetail: String
        if let supplementAdherence {
            supplementDetail = "Avg \(formatNumber(supplementAverage))/day · Adherence \(formatNumber(supplementAdherence))%"
        } else {
            supplementDetail = "Avg \(formatNumber(supplementAverage))/day · \(summary.supplements?.activeCount ?? 0) active"
        }

        let dietMetric = DesktopDashboardMetric(
            id: "diet",
            titleKey: days == 7 ? "Diet 7d" : "Diet 30d",
            value: "\(formatNumber(dietValue)) kcal",
            detail: "Avg \(formatNumber(dietAverage))/day · \(dietCount) records",
            tone: "orange",
            systemImage: "fork.knife"
        )
        let waterMetric = DesktopDashboardMetric(
            id: "water",
            titleKey: days == 7 ? "Water 7d" : "Water 30d",
            value: "\(formatNumber(Double(waterValue))) ml",
            detail: "Avg \(formatNumber(waterAverage))/day · \(waterCount) records",
            tone: "cyan",
            systemImage: "drop.fill"
        )
        let supplementMetric = DesktopDashboardMetric(
            id: "supplements",
            titleKey: days == 7 ? "Supplements 7d" : "Supplements 30d",
            value: String(supplementValue),
            detail: supplementDetail,
            tone: "teal",
            systemImage: "pills.fill"
        )
        let bloodPressureMetric = DesktopDashboardMetric(
            id: "bp",
            titleKey: "Latest BP",
            value: summary.latestBloodPressure?.displayValue ?? "—",
            detail: summary.latestBloodPressure?.category ?? summary.latestBloodPressure?.recordDate ?? "No record",
            tone: "pink",
            systemImage: "heart.text.square.fill"
        )
        return [dietMetric, waterMetric, supplementMetric, bloodPressureMetric]
    }

    private static func trends(from summary: RecentRecordsSummary, days: Int) -> [DesktopDashboardTrend] {
        let dietPoints = (days == 7 ? summary.diet?.daily7 : summary.diet?.daily30) ?? []
        let waterPoints = (days == 7 ? summary.water?.daily7 : summary.water?.daily30) ?? []
        let supplementPoints = (days == 7 ? summary.supplements?.daily7 : summary.supplements?.daily30) ?? []
        return [
            DesktopDashboardTrend(
                id: "diet-trend-\(days)",
                titleKey: "Diet Trend",
                unit: "kcal",
                tone: "orange",
                averageLabel: "Avg \(formatNumber(days == 7 ? (summary.diet?.last7AvgCalories ?? 0) : (summary.diet?.last30AvgCalories ?? 0)))/day",
                points: dietPoints.map { .init(date: $0.date, value: $0.calories) }
            ),
            DesktopDashboardTrend(
                id: "water-trend-\(days)",
                titleKey: "Water Trend",
                unit: "ml",
                tone: "cyan",
                averageLabel: "Avg \(formatNumber(days == 7 ? (summary.water?.last7AvgMl ?? 0) : (summary.water?.last30AvgMl ?? 0)))/day",
                points: waterPoints.map { .init(date: $0.date, value: Double($0.totalMl)) }
            ),
            DesktopDashboardTrend(
                id: "supplement-trend-\(days)",
                titleKey: "Supplement Trend",
                unit: "x",
                tone: "teal",
                averageLabel: "Avg \(formatNumber(days == 7 ? (summary.supplements?.last7AvgPerDay ?? 0) : (summary.supplements?.last30AvgPerDay ?? 0)))/day",
                points: supplementPoints.map { .init(date: $0.date, value: Double($0.count)) }
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

    private static func inputInboxEvents(from bootstrap: DesktopBootstrap) -> [DesktopInputInboxEvent] {
        var events: [DesktopInputInboxEvent] = []
        let summary = bootstrap.recentRecordsSummary

        if let garmin = summary.latestGarmin {
            events.append(
                DesktopInputInboxEvent(
                    id: "device-garmin-\(garmin.id)",
                    source: .device,
                    state: .autoSaved,
                    title: garmin.title ?? "Garmin",
                    subtitle: garmin.recordDate ?? "wearable sync",
                    detail: [
                        garmin.steps.map { "steps \($0)" },
                        garmin.sleepScore.map { "sleep \($0)" },
                        garmin.spo2Avg.map { "SpO2 \(formatNumber($0))%" }
                    ].compactMap { $0 }.joined(separator: " · "),
                    reviewHint: "Synced automatically. Ready for Agent context.",
                    systemImage: "sensor.tag.radiowaves.forward",
                    tone: "blue",
                    contextItem: garminContextItem(garmin),
                    prompt: garminPrompt(garmin)
                )
            )
        }

        for record in (summary.recentRecords ?? []).prefix(4) {
            events.append(
                DesktopInputInboxEvent(
                    id: "record-\(record.id)",
                    source: .manual,
                    state: .autoSaved,
                    title: record.title,
                    subtitle: record.recordDate ?? record.type,
                    detail: record.displayValue,
                    reviewHint: "Already saved. Use it as context or ask for follow-up.",
                    systemImage: icon(forRecordType: record.type),
                    tone: tone(forRecordType: record.type),
                    contextItem: DesktopWorkspaceContextFactory.contextItem(for: record),
                    prompt: DesktopWorkspaceContextFactory.prompt(for: record)
                )
            )
        }

        for job in bootstrap.activeJobs.prefix(4) {
            events.append(
                DesktopInputInboxEvent(
                    id: "job-\(job.id)",
                    source: .imported,
                    state: job.status == "completed" ? .autoSaved : .needsReview,
                    title: job.sourceName ?? job.jobType,
                    subtitle: "#\(job.id) \(job.jobType)",
                    detail: "\(job.status) · \(job.progress)%",
                    reviewHint: job.status == "completed"
                        ? "Import completed. Ready for knowledge or health context."
                        : "Import is still running. Review before relying on it.",
                    systemImage: "tray.and.arrow.down.fill",
                    tone: job.status == "failed" ? "red" : "indigo",
                    contextItem: DesktopWorkspaceContextFactory.contextItem(for: job),
                    prompt: DesktopWorkspaceContextFactory.prompt(for: job)
                )
            )
        }

        return Array(events.prefix(8))
    }

    private static func garminContextItem(_ garmin: GarminMetricSummary) -> AgentContextItem {
        AgentContextItem(
            sourceID: "device_sync:garmin:\(garmin.id)",
            sourceKind: "device_sync",
            title: garmin.title ?? "Garmin",
            summary: [
                garmin.recordDate,
                garmin.steps.map { "steps \($0)" },
                garmin.sleepScore.map { "sleep \($0)" },
                garmin.spo2Avg.map { "SpO2 \(formatNumber($0))%" },
                garmin.restingHeartRate.map { "RHR \($0)" },
                garmin.hrv.map { "HRV \(formatNumber($0))" }
            ].compactMap { $0 }.joined(separator: " · "),
            payload: [
                "id": "\(garmin.id)",
                "source": "garmin",
                "record_date": garmin.recordDate ?? "",
                "steps": garmin.steps.map { "\($0)" } ?? "",
                "sleep_score": garmin.sleepScore.map { "\($0)" } ?? "",
                "spo2_avg": garmin.spo2Avg.map { "\($0)" } ?? "",
                "resting_heart_rate": garmin.restingHeartRate.map { "\($0)" } ?? "",
                "hrv": garmin.hrv.map { "\($0)" } ?? "",
                "training_readiness_score": garmin.trainingReadinessScore.map { "\($0)" } ?? ""
            ]
        )
    }

    private static func garminPrompt(_ garmin: GarminMetricSummary) -> String {
        "请基于这条设备同步数据，结合我最近记录、基因和知识库上下文，判断今天是否需要调整饮食、运动、补剂或恢复计划。设备：Garmin，日期：\(garmin.recordDate ?? "unknown")。"
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

public struct DesktopDashboardTrend: Equatable, Identifiable, Sendable {
    public let id: String
    public let titleKey: String
    public let unit: String
    public let tone: String
    public let averageLabel: String
    public let points: [DesktopDashboardTrendPoint]
}

public struct DesktopDashboardTrendPoint: Equatable, Identifiable, Sendable {
    public let date: String
    public let value: Double

    public var id: String { date }
}

public enum DesktopInputSource: Equatable, Sendable {
    case device
    case voice
    case image
    case manual
    case imported
}

public enum DesktopInputReviewState: Equatable, Sendable {
    case autoSaved
    case needsReview
    case confirmed
}

public struct DesktopInputInboxEvent: Equatable, Identifiable, Sendable {
    public let id: String
    public let source: DesktopInputSource
    public let state: DesktopInputReviewState
    public let title: String
    public let subtitle: String
    public let detail: String
    public let reviewHint: String
    public let systemImage: String
    public let tone: String
    public let contextItem: AgentContextItem
    public let prompt: String
}

public struct DesktopInputInboxSummary: Equatable, Sendable {
    public let totalCount: Int
    public let autoSavedCount: Int
    public let needsReviewCount: Int
    public let confirmedCount: Int

    public init(events: [DesktopInputInboxEvent]) {
        self.totalCount = events.count
        self.autoSavedCount = events.filter { $0.state == .autoSaved }.count
        self.needsReviewCount = events.filter { $0.state == .needsReview }.count
        self.confirmedCount = events.filter { $0.state == .confirmed }.count
    }
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
