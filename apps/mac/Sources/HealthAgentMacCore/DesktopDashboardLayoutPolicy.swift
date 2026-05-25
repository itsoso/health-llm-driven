import Foundation

public struct DesktopDashboardLayoutMetrics: Equatable, Sendable {
    public let horizontalPadding: Double
    public let columnSpacing: Double
    public let rightRailWidth: Double
    public let contentMaxWidth: Double

    public var mainColumnWidth: Double {
        max(0, contentMaxWidth - rightRailWidth - columnSpacing)
    }
}

public enum DesktopDashboardLayoutPolicy {
    public static func metrics(forAvailableWidth availableWidth: Double) -> DesktopDashboardLayoutMetrics {
        let isWide = availableWidth >= 1_500
        let horizontalPadding = isWide ? 24.0 : 20.0
        let columnSpacing = isWide ? 20.0 : 16.0
        let rightRailWidth = isWide ? 360.0 : 320.0
        let readableWidth = max(0, availableWidth - (horizontalPadding * 2))
        let contentMaxWidth = min(readableWidth, isWide ? 1_660.0 : readableWidth)

        return DesktopDashboardLayoutMetrics(
            horizontalPadding: horizontalPadding,
            columnSpacing: columnSpacing,
            rightRailWidth: rightRailWidth,
            contentMaxWidth: contentMaxWidth
        )
    }
}
