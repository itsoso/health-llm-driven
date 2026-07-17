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
      "due_items": [
        {"title": "到公司后俯卧撑 12 个", "kind": "training", "time_window": "morning",
         "action_id": "agenda-health_protocol-8",
         "source": {"object_type": "health_protocol", "object_id": 8}}
      ],
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
        XCTAssertNil(s.status.freshness)
        XCTAssertEqual(s.topAction?.kind, "hydration")
        XCTAssertEqual(s.topAction?.source?.objectId, 12)
        XCTAssertEqual(s.topAction?.priorityTier, "P2")
        XCTAssertEqual(s.topAction?.leverageScore, 186)
        XCTAssertEqual(s.topAction?.rationaleShort, "低摩擦高频动作, 先保证当天执行")
        XCTAssertEqual(s.topAction?.verificationWindowDays, 7)
        XCTAssertEqual(s.topAction?.safetyStatus, "allowed")
        XCTAssertEqual(s.agenda.pending, 2)
        XCTAssertEqual(s.dueItems.count, 1)
        XCTAssertEqual(s.dueItems.first?.actionId, "agenda-health_protocol-8")
        XCTAssertEqual(s.dueItems.first?.isCompletable, true)
        XCTAssertEqual(s.quickActions.count, 2)
        XCTAssertEqual(s.pushItems.first?.tier, "P1")
        XCTAssertFalse(s.pushItems.first!.isUrgent)
    }

    func testQuickActionPresentationsUseBackendOrderAndSkipUnsupportedKinds() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":null,
         "agenda":{"total":0,"pending":0},
         "quick_actions":[
           {"kind":"water","label":"喝水","endpoint":"/water/records/quick","method":"POST"},
           {"kind":"supplement","label":"补剂","endpoint":"/supplements/records","method":"POST"},
           {"kind":"exercise","label":"运动","endpoint":"/daily-health/exercise","method":"POST"},
           {"kind":"diet_voice","label":"记一餐","endpoint":"/diet/voice/parse","method":"POST"},
           {"kind":"checkin","label":"打卡","endpoint":"/checkin/records/quick","method":"POST"}
         ],
         "push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)

        XCTAssertEqual(
            watchQuickActionPresentations(s.quickActions),
            [
                WatchQuickActionPresentation(kind: .water, label: "喝水"),
                WatchQuickActionPresentation(kind: .exercise, label: "运动"),
                WatchQuickActionPresentation(kind: .dietVoice, label: "语音记一餐"),
                WatchQuickActionPresentation(kind: .symptomVoice, label: "语音记症状"),
            ]
        )
    }

    func testQuickActionPresentationsFallbackToWatchDefaultsWhenBackendIsEmpty() {
        XCTAssertEqual(
            watchQuickActionPresentations([]),
            [
                WatchQuickActionPresentation(kind: .water, label: "喝水"),
                WatchQuickActionPresentation(kind: .exercise, label: "运动"),
                WatchQuickActionPresentation(kind: .dietVoice, label: "语音记一餐"),
                WatchQuickActionPresentation(kind: .symptomVoice, label: "语音记症状"),
            ]
        )
    }

    func testQuickActionPresentationsSkipMismatchedEndpoints() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":null,
         "agenda":{"total":0,"pending":0},
         "quick_actions":[
           {"kind":"water","label":"喝水","endpoint":"/unexpected/water","method":"POST"},
           {"kind":"exercise","label":"运动","endpoint":"/daily-health/exercise","method":"GET"},
           {"kind":"diet_voice","label":"记一餐","endpoint":"/diet/records","method":"POST"}
         ],
         "push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)

        XCTAssertEqual(
            watchQuickActionPresentations(s.quickActions),
            [WatchQuickActionPresentation(kind: .symptomVoice, label: "语音记症状")]
        )
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

    func testRuntimeContextDecodesForTopAction() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "runtime":{"mode":"runtime","generated_by":"rolling_health_runtime_v1","horizon_days":1},
         "top_action":{"title":"晚餐后步行 15 分钟","kind":"movement","time_window":"evening",
                       "action_id":"agenda-health_protocol-8",
                       "source":{"object_type":"health_protocol","object_id":8},
                       "runtime_context":{
                         "current_state_summary":"晚餐后是今天最短的代谢干预窗口。",
                         "replan_reason":"today_smart_rank",
                         "safety_boundary":"这是健康管理行动建议, 不替代医生诊断。",
                         "verification_window":{"metrics":["post_meal_walk_completed","waist_cm"],"window_days":7}
                       }},
         "agenda":{"total":1,"pending":1},"quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)

        XCTAssertEqual(s.runtime?.generatedBy, "rolling_health_runtime_v1")
        XCTAssertEqual(s.runtime?.horizonDays, 1)
        XCTAssertEqual(s.topAction?.runtimeContext?.replanReason, "today_smart_rank")
        XCTAssertEqual(s.topAction?.runtimeContext?.verificationWindow?.metrics, ["post_meal_walk_completed", "waist_cm"])
        XCTAssertEqual(s.topAction?.runtimeContext?.verificationWindow?.windowDays, 7)
    }

    func testTopActionDecisionBasisUsesRuntimeContextForWatchReadableLines() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":{"title":"晚餐后步行 15 分钟","kind":"movement","time_window":"evening",
                       "rationale_short":"餐后是今天最短的代谢干预窗口。",
                       "action_id":"agenda-health_protocol-8",
                       "source":{"object_type":"health_protocol","object_id":8},
                       "runtime_context":{
                         "current_state_summary":"晚餐后血糖管理优先。",
                         "safety_boundary":"这是健康管理建议, 不替代医生诊断。",
                         "verification_window":{"metrics":["post_meal_walk_completed","waist_cm"],"window_days":7}
                       }},
         "agenda":{"total":1,"pending":1},"quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)

        XCTAssertEqual(
            s.topAction?.decisionBasisLines(maxCount: 3),
            [
                "餐后是今天最短的代谢干预窗口。",
                "晚餐后血糖管理优先。",
                "验证: 7天 · 餐后步行 / 腰围",
            ]
        )
    }

    func testDueItemDecisionBasisFallsBackToVerificationWindow() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":null,
         "agenda":{"total":1,"pending":1},
         "due_items":[
           {"title":"睡前补镁","kind":"supplement","time_window":"bedtime",
            "action_id":"agenda-health_protocol-9",
            "source":{"object_type":"health_protocol","object_id":9},
            "runtime_context":{
              "verification_window":{"metrics":["sleep_score"],"window_days":14}
            }}
         ],
         "quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)

        XCTAssertEqual(s.dueItems.first?.decisionBasisLines(maxCount: 2), ["验证: 14天 · 睡眠"])
    }

    func testDecodeNullTopAction() throws {
        let data = Data("""
        {"status":{"light":"gray","readiness_score":null,"headline":"今日暂无待办"},
         "top_action":null,"agenda":{"total":0,"pending":0},
         "due_items":[],
         "quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)
        XCTAssertNil(s.topAction)
        XCTAssertTrue(s.dueItems.isEmpty)
        XCTAssertNil(s.status.readinessScore)
        XCTAssertTrue(s.pushItems.isEmpty)
    }

    func testDueItemsDefaultToEmptyForOldSummaryPayloads() throws {
        let data = Data("""
        {"status":{"light":"gray","readiness_score":null,"headline":"今日暂无待办"},
         "top_action":null,"agenda":{"total":0,"pending":0},
         "quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)
        let s = try WatchSummary.decode(data)
        XCTAssertTrue(s.dueItems.isEmpty)
    }

    func testSummaryCacheRoundTripsLastSuccessfulSummary() throws {
        let suite = "WatchSummaryCacheTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let cache = WatchSummaryCache(defaults: defaults, key: "summary")
        let summary = try WatchSummary.decode(json)

        cache.save(summary)
        let loaded = try XCTUnwrap(cache.load())

        XCTAssertEqual(loaded.status.headline, summary.status.headline)
        XCTAssertEqual(loaded.topAction?.title, summary.topAction?.title)
        XCTAssertEqual(loaded.dueItems.first?.actionId, "agenda-health_protocol-8")
        XCTAssertEqual(loaded.agenda.pending, 2)
    }

    func testSummaryCacheReturnsNilForCorruptData() throws {
        let suite = "WatchSummaryCacheTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let cache = WatchSummaryCache(defaults: defaults, key: "summary")

        defaults.set(Data("not-json".utf8), forKey: "summary")

        XCTAssertNil(cache.load())
    }

    func testDueItemNonProtocolSourceIsNotCompletableEvenWithActionId() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":null,
         "agenda":{"total":1,"pending":1},
         "due_items":[
           {"title":"下午复查胃镜报告","kind":"checkup","time_window":"afternoon",
            "action_id":"agenda-checkup-4",
            "source":{"object_type":"checkup","object_id":4}}
         ],
         "quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)

        let s = try WatchSummary.decode(data)

        XCTAssertEqual(s.dueItems.first?.actionId, "agenda-checkup-4")
        XCTAssertEqual(s.dueItems.first?.isCompletable, false, "非 health_protocol 来源不可腕上完成/稍后/跳过")
    }

    func testSmartReminderDueItemIsCompletable() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":null,
         "agenda":{"total":1,"pending":1},
         "due_items":[
           {"title":"定时饮水提醒","kind":"hydration","time_window":"13:30",
            "action_id":"agenda-smart_reminder-9",
            "source":{"object_type":"smart_reminder","object_id":9}}
         ],
         "quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)

        let s = try WatchSummary.decode(data)

        XCTAssertEqual(s.dueItems.first?.actionId, "agenda-smart_reminder-9")
        XCTAssertEqual(s.dueItems.first?.isCompletable, true)
    }

    func testSmartReminderVisibleEventMetasFromSummary() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":80,"headline":"h"},
         "top_action":null,
         "agenda":{"total":2,"pending":2},
         "due_items":[
           {"title":"定时饮水提醒","kind":"hydration","time_window":"13:30",
            "action_id":"agenda-smart_reminder-9",
            "source":{"object_type":"smart_reminder","object_id":9}},
           {"title":"补剂","kind":"supplement","time_window":"09:00",
            "action_id":"agenda-health_protocol-8",
            "source":{"object_type":"health_protocol","object_id":8}}
         ],
         "quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)

        let s = try WatchSummary.decode(data)
        let metas = watchSmartReminderVisibleEventMetas(s)

        XCTAssertEqual(metas, [[
            "action_id": "agenda-smart_reminder-9",
            "reminder_id": "9",
            "kind": "hydration",
            "surface": "watch_summary",
        ]])
    }

    func testDecodeStatusFreshness() throws {
        let data = Data("""
        {"status":{"light":"green","readiness_score":78,"headline":"h",
          "freshness":{"state":"stale","label":"数据偏旧 2 天","latest_date":"2026-06-15",
                       "age_days":2,"last_sync_at":"2026-06-15T22:00:00+00:00"}},
         "top_action":null,"agenda":{"total":0,"pending":0},
         "quick_actions":[],"push_items":[],"generated_at":"x"}
        """.utf8)

        let s = try WatchSummary.decode(data)

        XCTAssertEqual(s.status.freshness?.state, .stale)
        XCTAssertEqual(s.status.freshness?.label, "数据偏旧 2 天")
        XCTAssertEqual(s.status.freshness?.latestDate, "2026-06-15")
        XCTAssertEqual(s.status.freshness?.ageDays, 2)
        XCTAssertEqual(s.status.freshness?.lastSyncAt, "2026-06-15T22:00:00+00:00")
        XCTAssertFalse(s.status.freshness?.isFresh ?? true)
    }
}

final class ComplicationStateTests: XCTestCase {
    private func summary(light: ComplicationTone, score: Int?, push: [WatchPushItem]) -> WatchSummary {
        WatchSummary(
            status: WatchStatus(light: light, readinessScore: score, headline: "h"),
            topAction: nil,
            dueItems: [],
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

    func testStaleFreshnessSuppressesReadinessFallback() {
        let s = WatchSummary(
            status: WatchStatus(
                light: .green,
                readinessScore: 78,
                headline: "h",
                freshness: WatchFreshness(
                    state: .stale,
                    label: "数据偏旧 2 天",
                    latestDate: "2026-06-15",
                    ageDays: 2,
                    lastSyncAt: nil
                )
            ),
            topAction: nil,
            dueItems: [],
            agenda: WatchAgendaCount(total: 0, pending: 0),
            quickActions: [],
            pushItems: []
        )

        let st = ComplicationState.from(s)

        XCTAssertEqual(st.tone, .gray)
        XCTAssertEqual(st.shortText, "待同步")
        XCTAssertEqual(st.fullText, "数据偏旧 2 天")
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
            dueItems: [],
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
    func testDialSpecSnapsAndClampsValues() {
        XCTAssertEqual(QuickRecordDials.waterML.snapped(276), 300)
        XCTAssertEqual(QuickRecordDials.waterML.snapped(20), 100)
        XCTAssertEqual(QuickRecordDials.waterML.snapped(1200), 1000)
        XCTAssertEqual(QuickRecordDials.runDurationMin.snapped(33), 35)
    }

    func testDialDefaultsBuildValidQuickRecordRequests() throws {
        let waterML = QuickRecordDials.waterML.intValue()
        let reps = QuickRecordDials.pushupReps.intValue()
        let duration = QuickRecordDials.runDurationMin.snapped()

        XCTAssertEqual(try QuickRecord.water(amountML: waterML).query["amount"], "250")
        XCTAssertEqual(try QuickRecord.exercise(type: "俯卧撑", reps: reps).body["reps"], "20")
        XCTAssertEqual(try QuickRecord.exercise(type: "跑步", durationMin: duration).body["duration_min"], "30.0")
    }

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
        XCTAssertEqual(r.body["source"], "apple_watch")
        XCTAssertEqual(r.body["device_type"], "watch")
        XCTAssertEqual(r.resultKind, .draft)
    }

    func testDietVoiceEmpty() {
        XCTAssertThrowsError(try QuickRecord.dietVoice(rawText: "   "))
    }

    func testSymptomVoiceBuildsSafetyRequest() throws {
        let r = try QuickRecord.symptomVoice(rawText: "胸口闷,有点喘")
        XCTAssertEqual(r.path, "/watch/symptoms")
        XCTAssertEqual(r.method, "POST")
        XCTAssertTrue(r.query.isEmpty)
        XCTAssertEqual(r.body["text"], "胸口闷,有点喘")
        XCTAssertEqual(r.resultKind, .symptom)
        XCTAssertEqual(r.successMessage, "症状已记录")
    }

    func testSymptomVoiceEmptyThrows() {
        XCTAssertThrowsError(try QuickRecord.symptomVoice(rawText: "   ")) { err in
            XCTAssertEqual(err as? QuickRecordError, .missing("语音内容"))
        }
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

    func testSkipActionBuildsPathAndReason() throws {
        let r = try QuickRecord.skipAction(actionId: "agenda-health_protocol-12", reason: "too_tired")
        XCTAssertEqual(r.path, "/watch/actions/agenda-health_protocol-12/skip")
        XCTAssertEqual(r.method, "POST")
        XCTAssertTrue(r.query.isEmpty)
        XCTAssertEqual(r.body["reason"], "too_tired")
        XCTAssertEqual(r.successMessage, "已跳过")
    }

    func testSnoozeActionBuildsPathAndMinutes() throws {
        let r = try QuickRecord.snoozeAction(actionId: "agenda-health_protocol-12", minutes: 45)
        XCTAssertEqual(r.path, "/watch/actions/agenda-health_protocol-12/snooze")
        XCTAssertEqual(r.method, "POST")
        XCTAssertTrue(r.query.isEmpty)
        XCTAssertEqual(r.body["minutes"], "45")
        XCTAssertEqual(r.successMessage, "已稍后")
    }

    func testSkipActionEmptyIdThrows() {
        XCTAssertThrowsError(try QuickRecord.skipAction(actionId: "   ", reason: "no_time")) { err in
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
        XCTAssertEqual(req.body["ai_recognized"], "1")
        XCTAssertEqual(req.body["ai_confidence"], "0.82")
        XCTAssertTrue(req.body["notes"]?.contains("parser: rules-v1") ?? false)
        XCTAssertTrue(req.body["notes"]?.contains("confidence: 0.82") ?? false)
        XCTAssertEqual(draft.summaryLine, "午餐: 鸡胸肉 150g, 米饭 1碗")
    }
}

final class SymptomEvalResultTests: XCTestCase {
    func testDecodeCriticalAlertUsesCriticalBannerAndStrongHaptic() throws {
        let data = Data("""
        {
          "symptom_id": 42,
          "alerts": [
            {
              "severity": {"value": 4, "label": "urgent", "label_zh": "紧急"},
              "title": "胸痛伴呼吸困难需要尽快处理",
              "action": "立即联系急救或前往急诊",
              "data_citation": "用户腕上语音记录"
            }
          ],
          "message": "已记录症状并完成安全评估"
        }
        """.utf8)

        let result = try SymptomEvalResult.decode(data)

        XCTAssertEqual(result.symptomId, 42)
        XCTAssertEqual(result.alerts.count, 1)
        XCTAssertEqual(result.alerts.first?.severity.value, 4)
        XCTAssertEqual(result.alerts.first?.severity.labelZh, "紧急")
        XCTAssertEqual(result.displayBanner.tone, .critical)
        XCTAssertEqual(result.displayBanner.title, "胸痛伴呼吸困难需要尽快处理")
        XCTAssertEqual(result.displayBanner.action, "立即联系急救或前往急诊")
        XCTAssertEqual(result.hapticKind, .strong)
        XCTAssertFalse(result.isReassuringSafe)
        XCTAssertFalse(result.evaluationFailed)
    }

    func testDecodeEvaluationFailureWithoutAlertStillUsesCautionBanner() throws {
        let data = Data("""
        {
          "symptom_id": 43,
          "alerts": [],
          "evaluation_failed": true,
          "message": "症状已记录,但安全评估暂不可用"
        }
        """.utf8)

        let result = try SymptomEvalResult.decode(data)

        XCTAssertEqual(result.symptomId, 43)
        XCTAssertTrue(result.alerts.isEmpty)
        XCTAssertEqual(result.displayBanner.tone, .caution)
        XCTAssertEqual(result.displayBanner.title, "安全评估未完成")
        XCTAssertEqual(result.displayBanner.action, "症状已记录,但安全评估暂不可用")
        XCTAssertEqual(result.hapticKind, .notify)
        XCTAssertFalse(result.isReassuringSafe)
        XCTAssertTrue(result.evaluationFailed)
    }

    // MARK: - 后端真实契约的 critical fixture(QA 实测 shape:label=="critical")

    /// 对齐 backend Severity.label:CRITICAL→"critical"/"紧急"。alerts 非空且无 evaluation_failed
    /// → 三态①(取 alerts[0] 渲染)。critical 必 isCritical + 强震 + 绝不 reassuring。
    func testCriticalWithRealBackendLabel() throws {
        let data = Data("""
        {
          "symptom_id": 1,
          "alerts": [
            {
              "severity": {"value": 4, "label": "critical", "label_zh": "紧急"},
              "title": "可疑急性心脏事件",
              "action": "立即停止活动,拨打 120 或前往最近急诊。",
              "data_citation": {}
            }
          ],
          "message": "已记录症状,并触发安全提醒,请查看。"
        }
        """.utf8)
        let r = try SymptomEvalResult.decode(data)
        XCTAssertEqual(r.symptomId, 1)
        // severity 嵌套对象逐字段解析
        XCTAssertEqual(r.topAlert?.severity.value, 4)
        XCTAssertEqual(r.topAlert?.severity.label, "critical")
        XCTAssertEqual(r.topAlert?.severity.labelZh, "紧急")
        XCTAssertEqual(r.topAlert?.title, "可疑急性心脏事件")
        XCTAssertEqual(r.topAlert?.action, "立即停止活动,拨打 120 或前往最近急诊。")
        XCTAssertTrue(r.isCritical)
        XCTAssertEqual(r.hapticKind, .strong)
        XCTAssertFalse(r.isReassuringSafe, "critical 绝不 reassuring")
        XCTAssertFalse(r.evaluationFailed)
        XCTAssertEqual(r.displayBanner.tone, .critical)
    }

    /// 三态②:alerts:[] 且无 evaluation_failed → 真·无告警 = 安全。唯一可点绿灯分支。
    func testGenuineNoAlertIsReassuringSafe() throws {
        let data = Data("""
        {"symptom_id": 7, "alerts": [], "message": "已记录症状,未触发安全规则。"}
        """.utf8)
        let r = try SymptomEvalResult.decode(data)
        XCTAssertTrue(r.alerts.isEmpty)
        XCTAssertFalse(r.evaluationFailed, "成功分支后端不带 evaluation_failed 键 → 默认 false")
        XCTAssertTrue(r.isReassuringSafe)
        XCTAssertEqual(r.displayBanner.tone, .safe)
        XCTAssertEqual(r.hapticKind, .click)
        XCTAssertFalse(r.isCritical)
    }

    /// 三态③ 实际形态:后端 evaluation_failed 时注入一条 HIGH advisory → alerts 非空 + flag true。
    /// 关键:**有 alert 但评估未完成 → 绝不 reassoring,banner 用 caution(橙)不退成普通 high。**
    func testEvaluationFailedWithInjectedHighAdvisoryNeverReassuring() throws {
        let data = Data("""
        {
          "symptom_id": 9,
          "alerts": [
            {
              "severity": {"value": 3, "label": "high", "label_zh": "警告"},
              "title": "安全评估未完成",
              "action": "本次未能完成自动安全筛查,请勿据此判断为安全;如有不适请及时就医,情况紧急请拨打 120。",
              "data_citation": {"reason": "rule_engine_partial_or_total_failure"}
            }
          ],
          "evaluation_failed": true,
          "message": "症状已记录,但本次自动安全评估未能完成。"
        }
        """.utf8)
        let r = try SymptomEvalResult.decode(data)
        XCTAssertEqual(r.alerts.count, 1)
        XCTAssertTrue(r.evaluationFailed)
        XCTAssertFalse(r.isReassuringSafe, "评估未完成即便有/无 alert 都绝不 reassuring")
        XCTAssertFalse(r.isCritical)
        XCTAssertEqual(r.displayBanner.tone, .caution, "评估未完成的 HIGH advisory 用 caution(橙),不退成普通 high")
        XCTAssertEqual(r.displayBanner.title, "安全评估未完成")
        XCTAssertEqual(r.hapticKind, .notify)
    }

    /// 对抗用例:evaluation_failed==true 即使恰好 alerts 为空,也绝不 reassuring(UI 不漏报最后一闸)。
    func testEvaluationFailedEmptyAlertsStillNotReassuring() throws {
        let data = Data("""
        {"symptom_id": 11, "alerts": [], "evaluation_failed": true}
        """.utf8)
        let r = try SymptomEvalResult.decode(data)
        XCTAssertTrue(r.alerts.isEmpty)
        XCTAssertFalse(r.isReassuringSafe)
        XCTAssertNotEqual(r.displayBanner.tone, .safe, "evaluation_failed 绝不渲成 safe(绿)")
    }

    /// 普通(非急症)告警:alerts 非空、评估完成 → high 档,not reassuring,不强震。
    func testNonCriticalAlertIsHighNotReassuring() throws {
        let data = Data("""
        {
          "symptom_id": 5,
          "alerts": [
            {"severity": {"value": 3, "label": "high", "label_zh": "警告"},
             "title": "症状值得关注", "action": "若持续或加重请就医", "data_citation": {}}
          ],
          "message": "已记录症状,并触发安全提醒,请查看。"
        }
        """.utf8)
        let r = try SymptomEvalResult.decode(data)
        XCTAssertFalse(r.isCritical)
        XCTAssertFalse(r.isReassuringSafe)
        XCTAssertEqual(r.displayBanner.tone, .high)
        XCTAssertEqual(r.hapticKind, .notify)
    }
}

final class WatchBackendRequestTests: XCTestCase {
    func testSummaryRequestUsesBearerTokenAndApiV1Path() throws {
        let req = try WatchBackendRequest.summary(apiBase: "https://example.test/api/v1", token: "tok")

        XCTAssertEqual(req.url?.absoluteString, "https://example.test/api/v1/watch/summary")
        XCTAssertEqual(req.httpMethod, "GET")
        XCTAssertEqual(req.value(forHTTPHeaderField: "Authorization"), "Bearer tok")
    }

    func testQuickRecordRejectsPathTraversal() throws {
        let req = QuickRecordRequest(
            path: "/watch/actions/../../admin/x/complete",
            method: "POST",
            query: [:],
            body: [:]
        )

        XCTAssertThrowsError(try WatchBackendRequest.quickRecord(req, apiBase: "https://example.test/api/v1", token: "tok")) { err in
            XCTAssertEqual(err as? WatchBackendRequest.Error, .routeNotAllowed)
        }
    }

    func testQuickRecordAllowsWatchActionMutation() throws {
        let quick = try QuickRecord.snoozeAction(actionId: "agenda-health_protocol-12", minutes: 45)

        let req = try WatchBackendRequest.quickRecord(quick, apiBase: "https://example.test/api/v1", token: "tok")

        XCTAssertEqual(req.url?.absoluteString, "https://example.test/api/v1/watch/actions/agenda-health_protocol-12/snooze")
        XCTAssertEqual(req.httpMethod, "POST")
        XCTAssertEqual(req.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(req.value(forHTTPHeaderField: "Authorization"), "Bearer tok")
        let body = try XCTUnwrap(req.httpBody)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: String])
        XCTAssertEqual(json["minutes"], "45")
    }

    func testEventRequestBuildsClientEventEnvelope() throws {
        let req = try WatchBackendRequest.event(
            name: "watch_action_shown",
            meta: ["action_id": "agenda-health_protocol-12"],
            apiBase: "https://example.test/api/v1",
            token: "tok"
        )

        XCTAssertEqual(req.url?.absoluteString, "https://example.test/api/v1/client-events")
        XCTAssertEqual(req.httpMethod, "POST")
        let body = try XCTUnwrap(req.httpBody)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(json["event_name"] as? String, "watch_action_shown")
        XCTAssertEqual((json["meta"] as? [String: String])?["action_id"], "agenda-health_protocol-12")
    }
}

final class WatchSessionResetTests: XCTestCase {
    private let summaryJSON = Data("""
    {"status":{"light":"green","readiness_score":80,"headline":"h"},
     "top_action":null,"agenda":{"total":1,"pending":1},
     "due_items":[],"quick_actions":[],"push_items":[],"generated_at":"x"}
    """.utf8)

    func testLogoutResetClearsSummaryAndComplicationCaches() throws {
        let suite = "WatchSessionResetTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        // 模拟注销前腕上已缓存粗粒度健康数据
        WatchSummaryCache(defaults: defaults).save(try WatchSummary.decode(summaryJSON))
        ComplicationCache.save(
            ComplicationState(tone: .yellow, shortText: "适度", fullText: "下午低强度活动", urgentBadge: 0),
            in: defaults
        )
        XCTAssertNotNil(WatchSummaryCache(defaults: defaults).load())
        XCTAssertEqual(ComplicationCache.load(in: defaults).tone, .yellow)

        // 注销信号到达后两处缓存都被清空(只剩默认占位)
        WatchSessionReset.clearCachedHealthData(in: defaults)

        XCTAssertNil(WatchSummaryCache(defaults: defaults).load(), "summary 缓存应被清空")
        let complication = ComplicationCache.load(in: defaults)
        XCTAssertEqual(complication.tone, .gray, "complication 应回到默认占位")
        XCTAssertEqual(complication.shortText, "小巴")
        XCTAssertEqual(complication.fullText, "小巴")
    }
}

final class SymptomBuilderTests: XCTestCase {
    func testSymptomBuildsPathMethodBody() throws {
        let r = try QuickRecord.symptom(text: "胸口闷,左手发麻")
        XCTAssertEqual(r.path, "/watch/symptoms")
        XCTAssertEqual(r.method, "POST")
        XCTAssertTrue(r.query.isEmpty)
        XCTAssertEqual(r.body["text"], "胸口闷,左手发麻")
        XCTAssertEqual(r.resultKind, .symptom)
    }

    func testSymptomTrimsWhitespace() throws {
        let r = try QuickRecord.symptom(text: "  头很晕  ")
        XCTAssertEqual(r.body["text"], "头很晕", "前后空白被裁剪,不发脏文本")
    }

    func testSymptomEmptyThrows() {
        XCTAssertThrowsError(try QuickRecord.symptom(text: "")) { err in
            XCTAssertEqual(err as? QuickRecordError, .missing("语音内容"))
        }
    }

    func testSymptomWhitespaceOnlyThrows() {
        // 纯空白(含换行)→ fail-loud,绝不静默发空 → 后端会 400,但腕上先拦。
        XCTAssertThrowsError(try QuickRecord.symptom(text: "  \n\t ")) { err in
            XCTAssertEqual(err as? QuickRecordError, .missing("语音内容"))
        }
    }

    func testSymptomVoiceAliasMatchesSymptom() throws {
        let a = try QuickRecord.symptom(text: "恶心想吐")
        let b = try QuickRecord.symptomVoice(rawText: "恶心想吐")
        XCTAssertEqual(a, b, "symptom(text:) 与 symptomVoice(rawText:) 同构")
    }
}
