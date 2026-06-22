import Foundation

public enum CalendarSurfaceScope: String, CaseIterable, Identifiable, Sendable {
    case day
    case week
    case month
    case year

    public var id: String { rawValue }
}

public enum CalendarSurfaceLayout {
    public struct Window: Equatable, Sendable {
        public let scope: CalendarSurfaceScope
        public let anchor: Date
        public let start: Date
        public let end: Date

        public init(scope: CalendarSurfaceScope, anchor: Date, start: Date, end: Date) {
            self.scope = scope
            self.anchor = anchor
            self.start = start
            self.end = end
        }
    }

    public static func window(
        scope: CalendarSurfaceScope,
        anchor: Date,
        calendar: Calendar = .current
    ) -> Window {
        let day = calendar.startOfDay(for: anchor)
        let interval: DateInterval
        switch scope {
        case .day:
            interval = DateInterval(start: day, duration: 24 * 60 * 60)
        case .week:
            interval = calendar.dateInterval(of: .weekOfYear, for: day) ?? DateInterval(start: day, duration: 7 * 24 * 60 * 60)
        case .month:
            interval = calendar.dateInterval(of: .month, for: day) ?? DateInterval(start: day, duration: 30 * 24 * 60 * 60)
        case .year:
            interval = calendar.dateInterval(of: .year, for: day) ?? DateInterval(start: day, duration: 365 * 24 * 60 * 60)
        }
        return Window(
            scope: scope,
            anchor: day,
            start: calendar.startOfDay(for: interval.start),
            end: inclusiveEndDate(for: interval, calendar: calendar)
        )
    }

    public static func moved(
        _ anchor: Date,
        scope: CalendarSurfaceScope,
        offset: Int,
        calendar: Calendar = .current
    ) -> Date {
        let component: Calendar.Component
        switch scope {
        case .day:
            component = .day
        case .week:
            component = .weekOfYear
        case .month:
            component = .month
        case .year:
            component = .year
        }
        return calendar.date(byAdding: component, value: offset, to: anchor) ?? anchor
    }

    public static func days(in window: Window, calendar: Calendar = .current) -> [Date] {
        days(from: window.start, through: window.end, calendar: calendar)
    }

    public static func monthGridDays(containing anchor: Date, calendar: Calendar = .current) -> [Date] {
        let monthWindow = window(scope: .month, anchor: anchor, calendar: calendar)
        let leadingWeek = calendar.dateInterval(of: .weekOfYear, for: monthWindow.start)
        let start = leadingWeek?.start ?? monthWindow.start
        let monthDays = days(from: start, through: monthWindow.end, calendar: calendar)
        let minimumCells = max(35, Int(ceil(Double(monthDays.count) / 7.0)) * 7)
        let targetCells = max(42, minimumCells)
        var result = monthDays
        while result.count < targetCells, let last = result.last,
              let next = calendar.date(byAdding: .day, value: 1, to: last) {
            result.append(calendar.startOfDay(for: next))
        }
        return result
    }

    public static func sameDay(_ lhs: Date, _ rhs: Date, calendar: Calendar = .current) -> Bool {
        calendar.isDate(lhs, inSameDayAs: rhs)
    }

    private static func days(from start: Date, through end: Date, calendar: Calendar) -> [Date] {
        var result: [Date] = []
        var current = calendar.startOfDay(for: start)
        let endDay = calendar.startOfDay(for: end)
        while current <= endDay {
            result.append(current)
            guard let next = calendar.date(byAdding: .day, value: 1, to: current) else { break }
            current = calendar.startOfDay(for: next)
        }
        return result
    }

    private static func inclusiveEndDate(for interval: DateInterval, calendar: Calendar) -> Date {
        let exclusiveEnd = interval.end
        let previousMoment = exclusiveEnd.addingTimeInterval(-1)
        return calendar.startOfDay(for: previousMoment)
    }
}
