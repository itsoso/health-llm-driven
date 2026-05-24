import Foundation

public struct DesktopRecordHubPresentation: Equatable, Sendable {
    public let date: String?
    public let todayMetrics: [DesktopDashboardMetric]
    public let sevenDayMetrics: [DesktopDashboardMetric]
    public let recentRows: [DesktopDashboardRow]

    public init(summary: RecentRecordsSummary) {
        self.date = summary.date
        self.todayMetrics = Self.todayMetrics(from: summary)
        self.sevenDayMetrics = Self.sevenDayMetrics(from: summary)
        self.recentRows = (summary.recentRecords ?? []).prefix(6).map {
            DesktopDashboardRow(
                id: "\($0.type)-\($0.id)",
                title: $0.title,
                subtitle: $0.recordDate,
                value: $0.displayValue,
                tone: Self.tone(forRecordType: $0.type),
                systemImage: Self.icon(forRecordType: $0.type),
                progress: nil
            )
        }
    }

    private static func todayMetrics(from summary: RecentRecordsSummary) -> [DesktopDashboardMetric] {
        [
            DesktopDashboardMetric(
                id: "today_diet",
                titleKey: "Today Diet",
                value: "\(formatNumber(summary.diet?.todayCalories ?? 0)) kcal",
                detail: "\(summary.diet?.todayCount ?? 0) records",
                tone: "orange",
                systemImage: "fork.knife"
            ),
            DesktopDashboardMetric(
                id: "today_water",
                titleKey: "Today Water",
                value: "\(formatNumber(Double(summary.water?.todayTotalMl ?? 0))) ml",
                detail: "\(summary.water?.todayCount ?? 0) records",
                tone: "cyan",
                systemImage: "drop.fill"
            ),
            DesktopDashboardMetric(
                id: "today_supplements",
                titleKey: "Today Supplements",
                value: "\(summary.supplements?.todayCount ?? 0)",
                detail: "\(summary.supplements?.activeCount ?? 0) active",
                tone: "teal",
                systemImage: "pills.fill"
            )
        ]
    }

    private static func sevenDayMetrics(from summary: RecentRecordsSummary) -> [DesktopDashboardMetric] {
        let dietCalories = summary.diet?.last7Calories ?? summary.diet?.todayCalories ?? 0
        let dietAverage = summary.diet?.last7AvgCalories ?? dietCalories / 7
        let waterMl = summary.water?.last7TotalMl ?? summary.water?.todayTotalMl ?? 0
        let waterAverage = summary.water?.last7AvgMl ?? Double(waterMl) / 7
        let supplementCount = summary.supplements?.last7Count ?? summary.supplements?.todayCount ?? 0
        let supplementAverage = summary.supplements?.last7AvgPerDay ?? Double(supplementCount) / 7

        return [
            DesktopDashboardMetric(
                id: "seven_diet",
                titleKey: "Diet 7d",
                value: "\(formatNumber(dietCalories)) kcal",
                detail: "Avg \(formatNumber(dietAverage))/day · \(summary.diet?.last7Count ?? summary.diet?.todayCount ?? 0) records",
                tone: "orange",
                systemImage: "chart.bar.fill"
            ),
            DesktopDashboardMetric(
                id: "seven_water",
                titleKey: "Water 7d",
                value: "\(formatNumber(Double(waterMl))) ml",
                detail: "Avg \(formatNumber(waterAverage))/day · \(summary.water?.last7Count ?? summary.water?.todayCount ?? 0) records",
                tone: "cyan",
                systemImage: "drop.degreesign.fill"
            ),
            DesktopDashboardMetric(
                id: "seven_supplements",
                titleKey: "Supplements 7d",
                value: "\(supplementCount)",
                detail: supplementDetail(summary: summary, average: supplementAverage),
                tone: "teal",
                systemImage: "pills.circle.fill"
            ),
            DesktopDashboardMetric(
                id: "latest_vitals",
                titleKey: "Latest Vitals",
                value: latestVitalsValue(summary: summary),
                detail: latestVitalsDetail(summary: summary),
                tone: "green",
                systemImage: "heart.text.square.fill"
            )
        ]
    }

    private static func supplementDetail(summary: RecentRecordsSummary, average: Double) -> String {
        if let adherence = summary.supplements?.adherence7Pct {
            return "Avg \(formatNumber(average))/day · Adherence \(formatNumber(adherence))%"
        }
        return "Avg \(formatNumber(average))/day · \(summary.supplements?.activeCount ?? 0) active"
    }

    private static func latestVitalsValue(summary: RecentRecordsSummary) -> String {
        if let weight = summary.latestWeight?.displayValue {
            return weight
        }
        return summary.latestBloodPressure?.displayValue ?? "—"
    }

    private static func latestVitalsDetail(summary: RecentRecordsSummary) -> String {
        if let bloodPressure = summary.latestBloodPressure?.displayValue {
            return bloodPressure
        }
        return summary.latestWeight?.recordDate ?? summary.latestBloodPressure?.recordDate ?? "No record"
    }

    private static func icon(forRecordType type: String) -> String {
        switch type {
        case "diet": "fork.knife"
        case "water": "drop.fill"
        case "weight": "scalemass.fill"
        case "blood_pressure": "heart.text.square.fill"
        case "supplement", "supplements": "pills.fill"
        case "symptom": "cross.case.fill"
        default: "waveform.path.ecg"
        }
    }

    private static func tone(forRecordType type: String) -> String {
        switch type {
        case "diet": "orange"
        case "water": "cyan"
        case "weight": "green"
        case "blood_pressure": "pink"
        case "supplement", "supplements": "teal"
        case "symptom": "indigo"
        default: "blue"
        }
    }

    private static func formatNumber(_ value: Double) -> String {
        if value.rounded() == value {
            return String(Int(value))
        }
        return String(format: "%.1f", value)
    }
}
