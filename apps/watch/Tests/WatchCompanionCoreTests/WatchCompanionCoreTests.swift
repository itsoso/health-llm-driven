import XCTest
@testable import WatchCompanionCore

final class WatchSummaryTests: XCTestCase {
    // fixture 对齐后端 watch_summary.build_watch_summary 输出契约
    private let json = Data("""
    {
      "status": {"light": "green", "readiness_score": 78, "headline": "今日恢复良好,可按计划训练"},
      "top_action": {"title": "2000ml 温水杯", "kind": "hydration", "time_window": "anytime",
                     "priority_tier": "P2", "leverage_score": 186,
                     "rationale_short": "低摩擦高频动作, 先保证当天执行",
                     "verification_window_days": 7, "safety_status": "allowed",
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
        XCTAssertEqual(s.topAction?.priorityTier, "P2")
        XCTAssertEqual(s.topAction?.leverageScore, 186)
        XCTAssertEqual(s.topAction?.rationaleShort, "低摩擦高频动作, 先保证当天执行")
        XCTAssertEqual(s.topAction?.verificationWindowDays, 7)
        XCTAssertEqual(s.topAction?.safetyStatus, "allowed")
        XCTAssertEqual(s.agenda.pending, 2)
        XCTAssertEqual(s.quickActions.count, 2)
        XCTAssertEqual(s.pushItems.first?.tier, "P1")
        XCTAssertFalse(s.pushItems.first!.isUrgent)
    }

    func testTopActionWithoutActionIdIsNotCompletable() throws {
        // 既有 fixture 不带 action_id → 可选字段缺省 nil,不破解码,且不可完成(只读)。
        let s = try WatchSummary.decode(json)
        XCTAssertNil(s.topAction?.actionId)
        XCTAssertEqual(s.topAction?.isCompletable, false)
    }

    func testCompletableTopActionDecodesActionId() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":{"title":"二甲双胍 0.5g","kind":"medication","time_window":"morning",
                       "action_id":"agenda-health_protocol-7",
                       "source":{"object_type":"health_protocol","object_id":7}},
         "agenda":{"total":1,"pending":1},"quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)
        XCTAssertEqual(s.topAction?.actionId, "agenda-health_protocol-7")
        XCTAssertEqual(s.topAction?.kind, "medication")
        XCTAssertEqual(s.topAction?.isCompletable, true)
    }

    func testNonProtocolKindNotCompletableEvenWithActionId() throws {
        // 训练/复查等非 health_protocol 域:即便后端给了 action_id 也只读(对齐回写边界)。
        let data = Data("""
        {"status":{"light":"red","readiness_score":40,"headline":"h"},
         "top_action":{"title":"今日休息","kind":"training","time_window":"anytime",
                       "action_id":"agenda-training_decision-3",
                       "source":{"object_type":"training_decision","object_id":3}},
         "agenda":{"total":1,"pending":1},"quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)
        XCTAssertEqual(s.topAction?.actionId, "agenda-training_decision-3")
        XCTAssertEqual(s.topAction?.isCompletable, false, "非 health_protocol 域不可腕上完成")
    }

    func testTrainingProtocolActionIsCompletable() throws {
        // Watch-first Workday Scheduler:训练/活动类 health_protocol 可作为微运动一键完成。
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":{"title":"到公司后俯卧撑 12 个","kind":"training","time_window":"morning",
                       "action_id":"agenda-health_protocol-8",
                       "source":{"object_type":"health_protocol","object_id":8}},
         "agenda":{"total":1,"pending":1},"quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)
        XCTAssertEqual(s.topAction?.actionId, "agenda-health_protocol-8")
        XCTAssertEqual(s.topAction?.kind, "training")
        XCTAssertEqual(s.topAction?.isCompletable, true)
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

    private func summaryWithAction(light: ComplicationTone, action: String, pending: Int,
                                   push: [WatchPushItem] = []) -> WatchSummary {
        WatchSummary(
            status: WatchStatus(light: light, readinessScore: 70, headline: "h"),
            topAction: WatchTopAction(title: action, kind: "hydration", timeWindow: "morning", source: nil),
            agenda: WatchAgendaCount(total: pending, pending: pending),
            quickActions: [],
            pushItems: push
        )
    }

    func testTopActionShownAsTimelineSpine() {
        // R18 ★1:无 P0 时表盘显示「下一项该做什么」+ readiness 灯 + 待办数
        let st = ComplicationState.from(summaryWithAction(light: .yellow, action: "喝水 250ml", pending: 3))
        XCTAssertEqual(st.tone, .yellow, "tone 用 readiness 灯,不是强制色")
        XCTAssertEqual(st.shortText, "喝水 250ml")
        XCTAssertEqual(st.fullText, "喝水 250ml · 待办 3")
        XCTAssertEqual(st.urgentBadge, 0)
    }

    func testSinglePendingActionOmitsCount() {
        let st = ComplicationState.from(summaryWithAction(light: .green, action: "晨起拉伸", pending: 1))
        XCTAssertEqual(st.fullText, "晨起拉伸", "只剩 1 项时不缀「待办 N」")
    }

    func testP0OverridesTopAction() {
        // P0 紧急仍压过「下一项」(安全优先)
        let st = ComplicationState.from(summaryWithAction(
            light: .green, action: "喝水", pending: 2,
            push: [push("P0", "复查:胃溃疡", "checkup")]))
        XCTAssertEqual(st.tone, .red)
        XCTAssertEqual(st.fullText, "复查:胃溃疡")
    }

    func testComplicationCacheRoundTrip() {
        let state = ComplicationState(tone: .yellow, shortText: "适度", fullText: "下午低强度活动", urgentBadge: 0)
        ComplicationCache.save(state)

        XCTAssertEqual(ComplicationCache.load(), state)
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
        XCTAssertEqual(r.resultKind, .draft)
    }

    func testDietVoiceEmpty() {
        XCTAssertThrowsError(try QuickRecord.dietVoice(rawText: "   "))
    }

    func testCompleteActionBuildsPath() throws {
        let r = try QuickRecord.completeAction(actionId: "agenda-health_protocol-12")
        XCTAssertEqual(r.path, "/watch/actions/agenda-health_protocol-12/complete")
        XCTAssertEqual(r.method, "POST")
        XCTAssertTrue(r.query.isEmpty)
        XCTAssertTrue(r.body.isEmpty, "完成端点空 body")
        XCTAssertEqual(r.resultKind, .saved)
    }

    func testCompleteActionEmptyIdThrows() {
        XCTAssertThrowsError(try QuickRecord.completeAction(actionId: "   ")) { err in
            XCTAssertEqual(err as? QuickRecordError, .missing("action_id"))
        }
    }

    func testVoiceFoodDraftBuildsConfirmRequest() throws {
        let data = Data("""
        {
          "raw_text": "午餐吃了鸡胸肉 150g 和米饭一碗",
          "meal_type": "lunch",
          "meal_type_label": "午餐",
          "foods": [
            {"name":"鸡胸肉","amount":"150g","calories":248,"protein":46.5,"carbs":0,"fat":5.4},
            {"name":"米饭","amount":"1碗","calories":232,"protein":4.2,"carbs":51.8,"fat":0.5}
          ],
          "confidence": 0.82,
          "needs_confirmation": true,
          "clarifying_question": "米饭大约多少克?",
          "risk_tags": ["portion_uncertain"],
          "parser_version": "rules-v1"
        }
        """.utf8)

        let draft = try VoiceFoodDraft.decode(data)
        let req = draft.confirmRequest(recordDate: "2026-06-16")

        XCTAssertEqual(req.path, "/diet/records")
        XCTAssertEqual(req.resultKind, .saved)
        XCTAssertEqual(req.body["record_date"], "2026-06-16")
        XCTAssertEqual(req.body["meal_type"], "lunch")
        XCTAssertEqual(req.body["food_items"], "鸡胸肉 150g, 米饭 1碗")
        XCTAssertEqual(req.body["calories"], "480")
        XCTAssertEqual(req.body["protein"], "50.7")
        XCTAssertEqual(req.body["carbs"], "51.8")
        XCTAssertEqual(req.body["fat"], "5.9")
        XCTAssertEqual(req.body["ai_recognized"], "true")
        XCTAssertEqual(draft.summaryLine, "午餐: 鸡胸肉 150g, 米饭 1碗")
    }
}
