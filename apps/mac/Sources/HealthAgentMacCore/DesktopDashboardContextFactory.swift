import Foundation

public enum DesktopDashboardContextFactory {
    public static func contextItem(for metric: DesktopDashboardMetric, section: String) -> AgentContextItem {
        AgentContextItem(
            sourceID: "dashboard_metric:\(section):\(metric.id)",
            sourceKind: "dashboard_metric",
            title: metric.titleKey,
            summary: "\(metric.value) · \(metric.detail)",
            payload: [
                "section": section,
                "id": metric.id,
                "title": metric.titleKey,
                "value": metric.value,
                "detail": metric.detail,
                "tone": metric.tone
            ]
        )
    }

    public static func contextItem(for trend: DesktopDashboardTrend, section: String, rangeDays: Int) -> AgentContextItem {
        AgentContextItem(
            sourceID: "dashboard_trend:\(section):\(trend.id)",
            sourceKind: "dashboard_trend",
            title: trend.titleKey,
            summary: "\(rangeDays)d · \(trend.averageLabel)",
            payload: [
                "section": section,
                "id": trend.id,
                "title": trend.titleKey,
                "range_days": "\(rangeDays)",
                "unit": trend.unit,
                "average": trend.averageLabel,
                "points": pointSeriesText(for: trend)
            ]
        )
    }

    public static func contextItem(for row: DesktopDashboardRow, section: String) -> AgentContextItem {
        AgentContextItem(
            sourceID: "dashboard_row:\(section):\(row.id)",
            sourceKind: "dashboard_row",
            title: row.title,
            summary: [row.subtitle, row.value].compactMap { $0 }.joined(separator: " · "),
            payload: [
                "section": section,
                "id": row.id,
                "title": row.title,
                "subtitle": row.subtitle ?? "",
                "value": row.value ?? "",
                "progress": row.progress.map { "\($0)" } ?? "",
                "tone": row.tone
            ]
        )
    }

    public static func prompt(for metric: DesktopDashboardMetric, section: String) -> String {
        "请基于今日看板里的这个指标做分析，并结合我最近记录、趋势、基因风险、补剂和知识库证据，判断是否需要调整今天的行动。区域：\(section)，指标：\(metric.titleKey)，数值：\(metric.value)，详情：\(metric.detail)。请列出不确定性边界，不要当作诊断。"
    }

    public static func prompt(for trend: DesktopDashboardTrend, section: String, rangeDays: Int) -> String {
        "请基于今日看板里的\(rangeDays)天趋势做分析，并结合我最近记录、基因风险、补剂和知识库证据，判断是否需要调整饮食、饮水、补剂、运动或复查计划。区域：\(section)，趋势：\(trend.titleKey)，均值：\(trend.averageLabel)，点位：\(pointSeriesText(for: trend))。请列出不确定性边界，不要当作诊断。"
    }

    public static func prompt(for row: DesktopDashboardRow, section: String) -> String {
        "请基于今日看板里的这条事项判断下一步怎么做，并结合我最近健康记录、趋势、基因风险和知识库证据。区域：\(section)，事项：\(row.title)，状态：\(row.subtitle ?? "unknown")，值：\(row.value ?? "none")。请给出可执行建议和不确定性边界。"
    }

    private static func pointSeriesText(for trend: DesktopDashboardTrend) -> String {
        trend.points
            .map { "\($0.date)=\(format($0.value)) \(trend.unit)" }
            .joined(separator: "; ")
    }

    private static func format(_ value: Double) -> String {
        if value.rounded() == value {
            return String(Int(value))
        }
        return String(format: "%.1f", value)
    }
}
