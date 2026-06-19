import Foundation
import XCTest
@testable import HealthAgentMacCore

final class DayTimelineLayoutTests: XCTestCase {
    // MARK: - Decoding (real backend shapes)

    func testDecodesScheduleTodayPayload() throws {
        let json = """
        {
          "scheduled": [
            {"id": 1, "domain": "medication", "time": "08:00", "title": "二甲双胍"},
            {"id": 2, "domain": "movement", "time": "18:30", "title": "跑步",
             "prescription": {"duration_min": 40, "intensity": "Zone 2"}}
          ],
          "rejected": [],
          "deferred": [],
          "disclaimer": "仅供参考"
        }
        """
        let schedule = try JSONDecoder().decode(TodaySchedule.self, from: Data(json.utf8))
        XCTAssertEqual(schedule.scheduled.count, 2)
        XCTAssertEqual(schedule.scheduled[0].id, "1")
        XCTAssertEqual(schedule.scheduled[0].domain, "medication")
        XCTAssertEqual(schedule.scheduled[1].prescription?.durationMin, 40)
        XCTAssertEqual(schedule.disclaimer, "仅供参考")
    }

    func testDecodesScheduleWithStringID() throws {
        let json = """
        { "scheduled": [{"id": "abc", "domain": "diet", "time": "12:00", "title": "午餐"}] }
        """
        let schedule = try JSONDecoder().decode(TodaySchedule.self, from: Data(json.utf8))
        XCTAssertEqual(schedule.scheduled.first?.id, "abc")
    }

    func testDecodesCalendarEvents() throws {
        let json = """
        [
          {"id": 10, "title": "Standup", "start": "2026-06-19T09:00:00+08:00",
           "end": "2026-06-19T09:30:00+08:00", "all_day": false, "location": "Zoom", "source_id": 3},
          {"id": 11, "title": "Holiday", "start": "2026-06-19T00:00:00+08:00",
           "end": "2026-06-20T00:00:00+08:00", "all_day": true}
        ]
        """
        let events = try JSONDecoder().decode([CalendarEvent].self, from: Data(json.utf8))
        XCTAssertEqual(events.count, 2)
        XCTAssertEqual(events[0].title, "Standup")
        XCTAssertFalse(events[0].allDay)
        XCTAssertTrue(events[1].allDay)
    }

    // MARK: - Minute math

    func testHHMMParsing() {
        XCTAssertEqual(DayTimelineLayout.minutes(fromHHMM: "08:30"), 510)
        XCTAssertEqual(DayTimelineLayout.minutes(fromHHMM: "00:00"), 0)
        XCTAssertNil(DayTimelineLayout.minutes(fromHHMM: "25:00"))
        XCTAssertNil(DayTimelineLayout.minutes(fromHHMM: "abc"))
    }

    func testClampDayMinute() {
        XCTAssertEqual(DayTimelineLayout.clampDayMinute(-5), 0)
        XCTAssertEqual(DayTimelineLayout.clampDayMinute(2000), 1440)
        XCTAssertEqual(DayTimelineLayout.clampDayMinute(600), 600)
    }

    // MARK: - Lane assignment

    func testNonOverlappingBlocksShareSingleLane() {
        let blocks = [
            DayTimelineLayout.Block(key: "a", startMin: 0, endMin: 60),
            DayTimelineLayout.Block(key: "b", startMin: 120, endMin: 180)
        ]
        let placements = DayTimelineLayout.assignLanes(blocks)
        XCTAssertTrue(placements.allSatisfy { $0.lanes == 1 && $0.lane == 0 })
    }

    func testOverlappingBlocksSplitIntoLanes() {
        let blocks = [
            DayTimelineLayout.Block(key: "a", startMin: 0, endMin: 120),
            DayTimelineLayout.Block(key: "b", startMin: 30, endMin: 90)
        ]
        let placements = DayTimelineLayout.assignLanes(blocks)
        XCTAssertTrue(placements.allSatisfy { $0.lanes == 2 })
        let lanes = Set(placements.map(\.lane))
        XCTAssertEqual(lanes, [0, 1])
    }

    // MARK: - Merge

    func testMergeCombinesScheduleAndCalendar() {
        let schedule = TodaySchedule(scheduled: [
            ScheduleItem(id: "1", domain: "medication", time: "08:00", title: "Pill"),
            ScheduleItem(id: "2", domain: "movement", time: "18:00", title: "Run",
                         prescription: SchedulePrescription(durationMin: 30))
        ])
        let events = [
            CalendarEvent(id: "10", title: "Meeting", start: "2026-06-19T09:00:00+08:00",
                          end: "2026-06-19T10:00:00+08:00"),
            CalendarEvent(id: "11", title: "Holiday", start: nil, end: nil, allDay: true)
        ]
        let merged = DayTimelineLayout.merge(
            schedule: schedule, events: events, includeSchedule: true,
            language: .en, calendar: utcCalendar
        )
        // 2 schedule + 1 timed event = 3 grid entries; 1 all-day.
        XCTAssertEqual(merged.entries.count, 3)
        XCTAssertEqual(merged.allDay.count, 1)
        // Point domain medication with no duration is a marker.
        let med = merged.entries.first { $0.key == "hs:1" }
        XCTAssertEqual(med?.isPoint, true)
        let run = merged.entries.first { $0.key == "hs:2" }
        XCTAssertEqual(run?.isPoint, false)
    }

    func testMergeExcludesScheduleWhenFlagFalse() {
        let schedule = TodaySchedule(scheduled: [
            ScheduleItem(id: "1", domain: "medication", time: "08:00", title: "Pill")
        ])
        let merged = DayTimelineLayout.merge(
            schedule: schedule, events: [], includeSchedule: false, language: .en
        )
        XCTAssertTrue(merged.entries.isEmpty)
    }

    func testCalendarEventWithoutEndGetsDefaultDuration() {
        let events = [
            CalendarEvent(id: "10", title: "Quick", start: "2026-06-19T09:00:00+00:00", end: nil)
        ]
        let merged = DayTimelineLayout.merge(
            schedule: nil, events: events, includeSchedule: true,
            language: .en, calendar: utcCalendar
        )
        let entry = merged.entries.first
        XCTAssertNotNil(entry)
        XCTAssertEqual((entry?.endMin ?? 0) - (entry?.startMin ?? 0), DayTimelineLayout.defaultBlockMinutes)
    }

    private var utcCalendar: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }
}
