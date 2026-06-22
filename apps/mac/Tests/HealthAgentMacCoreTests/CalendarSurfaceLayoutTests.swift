import Foundation
import XCTest
@testable import HealthAgentMacCore

final class CalendarSurfaceLayoutTests: XCTestCase {
    func testWindowRangesForDayWeekMonthAndYear() throws {
        let anchor = try XCTUnwrap(Self.date("2026-06-22T12:30:00Z"))
        let calendar = Self.utcMondayCalendar

        let day = CalendarSurfaceLayout.window(scope: .day, anchor: anchor, calendar: calendar)
        XCTAssertEqual(Self.ymd(day.start), "2026-06-22")
        XCTAssertEqual(Self.ymd(day.end), "2026-06-22")

        let week = CalendarSurfaceLayout.window(scope: .week, anchor: anchor, calendar: calendar)
        XCTAssertEqual(Self.ymd(week.start), "2026-06-22")
        XCTAssertEqual(Self.ymd(week.end), "2026-06-28")

        let month = CalendarSurfaceLayout.window(scope: .month, anchor: anchor, calendar: calendar)
        XCTAssertEqual(Self.ymd(month.start), "2026-06-01")
        XCTAssertEqual(Self.ymd(month.end), "2026-06-30")

        let year = CalendarSurfaceLayout.window(scope: .year, anchor: anchor, calendar: calendar)
        XCTAssertEqual(Self.ymd(year.start), "2026-01-01")
        XCTAssertEqual(Self.ymd(year.end), "2026-12-31")
    }

    func testMonthGridIncludesLeadingAndTrailingDays() throws {
        let anchor = try XCTUnwrap(Self.date("2026-06-22T12:30:00Z"))
        let days = CalendarSurfaceLayout.monthGridDays(containing: anchor, calendar: Self.utcMondayCalendar)

        XCTAssertEqual(days.count, 42)
        XCTAssertEqual(Self.ymd(days.first), "2026-06-01")
        XCTAssertEqual(Self.ymd(days.last), "2026-07-12")
    }

    func testNavigationMovesByScope() throws {
        let anchor = try XCTUnwrap(Self.date("2026-06-22T12:30:00Z"))
        let calendar = Self.utcMondayCalendar

        XCTAssertEqual(Self.ymd(CalendarSurfaceLayout.moved(anchor, scope: .day, offset: -1, calendar: calendar)), "2026-06-21")
        XCTAssertEqual(Self.ymd(CalendarSurfaceLayout.moved(anchor, scope: .week, offset: 1, calendar: calendar)), "2026-06-29")
        XCTAssertEqual(Self.ymd(CalendarSurfaceLayout.moved(anchor, scope: .month, offset: 1, calendar: calendar)), "2026-07-22")
        XCTAssertEqual(Self.ymd(CalendarSurfaceLayout.moved(anchor, scope: .year, offset: -1, calendar: calendar)), "2025-06-22")
    }

    func testBeijingCalendarKeepsChinaDayAcrossSystemTimezoneBoundary() throws {
        let anchor = try XCTUnwrap(Self.date("2026-06-21T20:30:00Z")) // 2026-06-22 04:30 in Beijing.
        let calendar = CalendarSurfaceLayout.beijingCalendar(locale: Locale(identifier: "zh_CN"))

        let day = CalendarSurfaceLayout.window(scope: .day, anchor: anchor, calendar: calendar)

        XCTAssertEqual(Self.ymd(day.start, timeZone: CalendarSurfaceLayout.beijingTimeZone), "2026-06-22")
        XCTAssertEqual(CalendarSurfaceLayout.beijingYMD(day.start), "2026-06-22")
        XCTAssertEqual(calendar.timeZone.identifier, "Asia/Shanghai")
    }

    private static var utcMondayCalendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        calendar.firstWeekday = 2
        return calendar
    }

    private static func date(_ value: String) -> Date? {
        ISO8601DateFormatter().date(from: value)
    }

    private static func ymd(_ date: Date?, timeZone: TimeZone = TimeZone(identifier: "UTC")!) -> String? {
        guard let date else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }
}
