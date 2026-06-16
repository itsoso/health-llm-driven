import XCTest
@testable import WatchCompanionCore

final class WatchSummaryTests: XCTestCase {
    // fixture 对齐后端 watch_summary.build_watch_summary 输出契约
    private let json = Data("""
    {
      "status": {"light": "green", "readiness_score": 78, "headline": "今日恢复良好,可按计划训练"},
      "top_action": {"title": "2000ml 温水杯", "kind": "hydration", "time_window": "anytime",
                     "source": {"object_type": "health_protocol", "object_id": 12}},
      "agenda": {"total": 4, "pending": 2},
      "quick_actions": [
        {"kind": "water", "label": "喝水", "endpoint": "/water/records/quick", "method": "POST"},
        {"kind": "exercise", "label": "运动", "endpoint": "/daily-health/exercise", "method": "POST"}
      ],
      "push_items": [
        {"tier": "P1", "title": "今日训练:以休息为主", "detail": null, "kind": "training", "source": null}
      ],
      "generated_at": "2026-06-16T01:00:00+00:00"
    }
    """.utf8)

    func testDecodeSummary() throws {
        let s = try WatchSummary.decode(json)
        XCTAssertEqual(s.status.light, .green)
        XCTAssertEqual(s.status.readinessScore, 78)
        XCTAssertEqual(s.topAction?.kind, "hydration")
        XCTAssertEqual(s.topAction?.source?.objectId, 12)
        XCTAssertEqual(s.agenda.pending, 2)
        XCTAssertEqual(s.quickActions.count, 2)
        XCTAssertEqual(s.pushItems.first?.tier, "P1")
        XCTAssertFalse(s.pushItems.first!.isUrgent)
    }

    func testDecodeNullTopAction() throws {
        let data = Data("""
        {"status":{"light":"gray","readiness_score":null,"headline":"今日暂无待办"},
         "top_action":null,"agenda":{"total":0,"pending":0},
         "quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)
        XCTAssertNil(s.topAction)
        XCTAssertNil(s.status.readinessScore)
        XCTAssertTrue(s.pushItems.isEmpty)
    }
}

final class ComplicationStateTests: XCTestCase {
    private func summary(light: ComplicationTone, score: Int?, push: [WatchPushItem]) -> WatchSummary {
        WatchSummary(
            status: WatchStatus(light: light, readinessScore: score, headline: "h"),
            topAction: nil,
            agenda: WatchAgendaCount(total: 0, pending: 0),
            quickActions: [],
            pushItems: push
        )
    }

    private func push(_ tier: String, _ title: String, _ kind: String) -> WatchPushItem {
        WatchPushItem(tier: tier, title: title, detail: nil, kind: kind, source: nil)
    }

    func testGreenReadinessShowsScore() {
        let st = ComplicationState.from(summary(light: .green, score: 78, push: []))
        XCTAssertEqual(st.tone, .green)
        XCTAssertEqual(st.shortText, "恢复 78")
        XCTAssertEqual(st.urgentBadge, 0)
    }

    func testP0PushForcesRedAndBadge() {
        let st = ComplicationState.from(summary(
            light: .green, score: 90,
            push: [push("P0", "复查:胃溃疡", "checkup"), push("P1", "用药", "medication")]
        ))
        XCTAssertEqual(st.tone, .red, "有 P0 推送时表盘强制红,压过训练绿灯")
        XCTAssertEqual(st.urgentBadge, 1)
        XCTAssertEqual(st.fullText, "复查:胃溃疡")
    }

    func testNoScoreFallsBackToToneText() {
        let st = ComplicationState.from(summary(light: .red, score: nil, push: []))
        XCTAssertEqual(st.tone, .red)
        XCTAssertEqual(st.shortText, "宜休息")
    }

    func testLongTitleShortened() {
        let st = ComplicationState.from(summary(
            light: .green, score: nil,
            push: [push("P0", "复查:胃溃疡随访别忘了带病理报告", "checkup")]
        ))
        XCTAssertLessThanOrEqual(st.shortText.count, 10)
        XCTAssertTrue(st.shortText.hasSuffix("…"))
    }
}

final class QuickRecordTests: XCTestCase {
    func testWaterValid() throws {
        let r = try QuickRecord.water(amountML: 500)
        XCTAssertEqual(r.path, "/water/records/quick")
        XCTAssertEqual(r.query["amount"], "500")
    }

    func testWaterOutOfRange() {
        XCTAssertThrowsError(try QuickRecord.water(amountML: 0))
        XCTAssertThrowsError(try QuickRecord.water(amountML: 6000))
    }

    func testExerciseReps() throws {
        let r = try QuickRecord.exercise(type: "俯卧撑", reps: 43)
        XCTAssertEqual(r.body["exercise_type"], "俯卧撑")
        XCTAssertEqual(r.body["reps"], "43")
    }

    func testExerciseDuration() throws {
        let r = try QuickRecord.exercise(type: "跑步", durationMin: 30)
        XCTAssertEqual(r.body["duration_min"], "30.0")
    }

    func testExerciseNeedsRepsOrDuration() {
        XCTAssertThrowsError(try QuickRecord.exercise(type: "深蹲"))
    }

    func testExerciseEmptyType() {
        XCTAssertThrowsError(try QuickRecord.exercise(type: "  ", reps: 10))
    }

    func testDietVoice() throws {
        let r = try QuickRecord.dietVoice(rawText: "午餐吃了鸡胸肉")
        XCTAssertEqual(r.path, "/diet/voice/parse")
        XCTAssertEqual(r.body["raw_text"], "午餐吃了鸡胸肉")
    }

    func testDietVoiceEmpty() {
        XCTAssertThrowsError(try QuickRecord.dietVoice(rawText: "   "))
    }
}
