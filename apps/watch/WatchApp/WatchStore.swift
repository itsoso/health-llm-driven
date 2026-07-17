import Foundation
import SwiftUI
#if canImport(WidgetKit)
import WidgetKit
#endif

/// 腕上状态容器:优先用 Watch 本机 token 直连后端;旧 WatchConnectivity relay 兜底。
/// 启动时先展示上次成功摘要缓存,再异步刷新,避免独立打开 Watch 时空白等待。
@MainActor
final class WatchStore: ObservableObject {
    @Published var summary: WatchSummary?
    @Published var loading = false
    @Published var lastError: String?
    @Published var lastRecordOK: Bool?
    @Published var lastRecordMessage: String?
    @Published var pendingDietDraft: VoiceFoodDraft?
    @Published var symptomResult: SymptomEvalResult?   // 最近一次语音记症状的安全裁决(供 QuickRecordView 渲染)
    @Published var symptomSubmitting = false           // 记症状请求在途(禁重复点)
    @Published var completing = false          // 「一键已做」请求在途(禁重复点 + tile 转圈)
    @Published var skipping = false            // 「跳过」请求在途(禁重复点)
    @Published var snoozing = false            // 「稍后」请求在途(禁重复点)

    private let connectivity: WatchConnectivityClient
    private let events: WatchEventClient
    private let summaryCache: WatchSummaryCache

    init(connectivity: WatchConnectivityClient = .shared,
         events: WatchEventClient? = nil,
         summaryCache: WatchSummaryCache = WatchSummaryCache()) {
        self.connectivity = connectivity
        self.events = events ?? WatchEventClient.shared
        self.summaryCache = summaryCache
        self.summary = summaryCache.load()
    }

    var complication: ComplicationState? {
        summary.map(ComplicationState.from)
    }

    func refresh() async {
        loading = true
        lastError = nil
        defer { loading = false }
        do {
            let data = try await connectivity.fetchSummary()
            let decoded = try WatchSummary.decode(data)
            summary = decoded
            summaryCache.save(decoded)
            ComplicationCache.save(ComplicationState.from(decoded))
            events.smartReminderVisible(decoded)
            reloadComplicationTimelines()
        } catch {
            lastError = Self.fetchErrorMessage(for: error)
        }
    }

    /// 把取摘要的失败映射成可读、可行动的提示(fail loud + 指明该去哪修),不再笼统「拉取失败」。
    static func fetchErrorMessage(for error: Error) -> String {
        if let wc = error as? WatchConnectivityClient.WCError {
            switch wc {
            case .unreachable:
                return "iPhone 未连接 —— 请在 iPhone 打开「小巴」后下拉重试"
            case .badResponse:
                return "数据异常,请下拉重试"
            case .relayFailed(let m):
                if m.contains("未登录") { return "请先在 iPhone 上登录「小巴」,再下拉重试" }
                if m.contains("401") { return "登录已过期,请在 iPhone 重新登录" }
                if m.hasPrefix("HTTP") { return "服务器繁忙(\(m)),稍后下拉重试" }
                return m   // 网络等系统错误原文,直说
            case .directFailed(let m):
                return "\(m),稍后下拉重试"
            case .missingWatchToken:
                return "请先在 iPhone 登录小巴并同步 Watch,之后手表可独立刷新"
            }
        }
        return "数据解析失败,请下拉重试"
    }

    /// 打点失败也要 fail loud,但不能把登录/token/网络状态吞成笼统「记录失败」。
    static func recordErrorMessage(for error: WatchConnectivityClient.WCError) -> String {
        switch error {
        case .unreachable:
            return "iPhone 未连接,请打开小巴后重试"
        case .badResponse:
            return "记录返回异常,请在手机端确认"
        case .relayFailed(let message):
            if message.contains("未登录") {
                return "请先在 iPhone 登录小巴并同步 Watch"
            }
            if message.contains("401") {
                return "登录已过期,请在 iPhone 重新登录"
            }
            if message.hasPrefix("HTTP") {
                return "服务器繁忙(\(message)),稍后重试"
            }
            return message
        case .directFailed(let message):
            return "\(message),稍后重试"
        case .missingWatchToken:
            return "请先在 iPhone 登录小巴并同步 Watch"
        }
    }

    /// 打点:校验(WatchCompanionCore)→ 经 iPhone 中继。失败 fail loud,不假装成功。
    func submit(_ build: () throws -> QuickRecordRequest) async {
        lastRecordOK = nil
        lastRecordMessage = nil
        lastError = nil
        do {
            let req = try build()
            let data = try await connectivity.sendQuickRecord(req)
            switch req.resultKind {
            case .draft:
                guard let data else { throw WatchStoreError.missingDraftData }
                pendingDietDraft = try VoiceFoodDraft.decode(data)
                lastRecordMessage = "请确认饮食草稿"
            case .symptom:
                // 安全裁决:必须解出 SymptomEvalResult 才算成功;解不出 fail loud。
                // 不在此点绿灯(lastRecordOK)——安全态由 SymptomEvalResult 计算属性决定,
                // 普通 submit 链路不参与症状的安全渲染(View 走 submitSymptom)。
                guard let data else { throw WatchStoreError.missingDraftData }
                symptomResult = try SymptomEvalResult.decode(data)
                lastRecordMessage = nil
            case .saved:
                if req.path == "/diet/records" {
                    pendingDietDraft = nil
                }
                lastRecordOK = true
                lastRecordMessage = req.successMessage
                await refresh()
            }
        } catch let e as QuickRecordError {
            lastRecordOK = false
            lastError = Self.message(for: e)
        } catch let e as WatchConnectivityClient.WCError {
            lastRecordOK = false
            lastError = Self.recordErrorMessage(for: e)
        } catch is WatchStoreError {
            lastRecordOK = false
            lastError = "解析失败,请在手机端确认"
        } catch {
            lastRecordOK = false
            lastError = "记录失败,请重试"
        }
    }

    /// 语音记症状:校验 → 中继 → 解 SymptomEvalResult → 暴露给 QuickRecordView 渲染安全裁决。
    /// 走统一 submit 链路(.symptom 分支),失败 fail loud(lastError);安全态不在此判定,
    /// 由 SymptomEvalResult 计算属性决定。提交前清掉上一条结果,避免失败时残留旧裁决误导。
    func submitSymptom(rawText: String) async {
        guard !symptomSubmitting else { return }
        symptomSubmitting = true
        defer { symptomSubmitting = false }
        symptomResult = nil
        await submit { try QuickRecord.symptomVoice(rawText: rawText) }
    }

    /// 「一键已做」:把到点项标记完成。仅可完成项(有 action_id 且协议/智能提醒可回写域)调用。
    /// 走与 submit 同一 fail-loud 链路;完成确认成功(lastRecordOK==true)后才发 completed 埋点。
    func completeAction(_ action: WatchTopAction) async {
        guard let actionId = action.actionId,
              action.isCompletable,
              !completing,
              !skipping,
              !snoozing else { return }
        completing = true
        defer { completing = false }
        await submit { try QuickRecord.completeAction(actionId: actionId) }
        if lastRecordOK == true {
            events.actionCompleted(action)
        }
    }

    func completeDueItem(_ item: WatchDueItem) async {
        guard let actionId = item.actionId,
              item.isCompletable,
              !completing,
              !skipping,
              !snoozing else { return }
        completing = true
        defer { completing = false }
        await submit { try QuickRecord.completeAction(actionId: actionId) }
        if lastRecordOK == true {
            events.actionCompleted(actionId: actionId, kind: item.kind)
        }
    }

    func skipAction(_ action: WatchTopAction, reason: String = "no_time") async {
        guard let actionId = action.actionId,
              action.isCompletable,
              !completing,
              !skipping,
              !snoozing else { return }
        skipping = true
        defer { skipping = false }
        await submit { try QuickRecord.skipAction(actionId: actionId, reason: reason) }
        if lastRecordOK == true {
            events.actionSkipped(action, reason: reason)
        }
    }

    func skipDueItem(_ item: WatchDueItem, reason: String = "no_time") async {
        guard let actionId = item.actionId,
              item.isCompletable,
              !completing,
              !skipping,
              !snoozing else { return }
        skipping = true
        defer { skipping = false }
        await submit { try QuickRecord.skipAction(actionId: actionId, reason: reason) }
        if lastRecordOK == true {
            events.actionSkipped(actionId: actionId, kind: item.kind, reason: reason)
        }
    }

    func snoozeAction(_ action: WatchTopAction, minutes: Int = 30) async {
        guard let actionId = action.actionId,
              action.isCompletable,
              !completing,
              !skipping,
              !snoozing else { return }
        snoozing = true
        defer { snoozing = false }
        await submit { try QuickRecord.snoozeAction(actionId: actionId, minutes: minutes) }
        if lastRecordOK == true {
            events.actionSnoozed(action, minutes: minutes)
        }
    }

    func snoozeDueItem(_ item: WatchDueItem, minutes: Int = 30) async {
        guard let actionId = item.actionId,
              item.isCompletable,
              !completing,
              !skipping,
              !snoozing else { return }
        snoozing = true
        defer { snoozing = false }
        await submit { try QuickRecord.snoozeAction(actionId: actionId, minutes: minutes) }
        if lastRecordOK == true {
            events.actionSnoozed(actionId: actionId, kind: item.kind, minutes: minutes)
        }
    }

    /// tile 曝光埋点(分母)。由 TodayStatusView.onAppear 调,旁路 fire-and-forget。
    func reportActionShown(_ action: WatchTopAction) {
        events.actionShown(action)
    }

    func confirmDietDraft() async {
        guard let draft = pendingDietDraft else { return }
        await submit { draft.confirmRequest(recordDate: Self.todayString()) }
    }

    func clearDietDraft() {
        pendingDietDraft = nil
        lastRecordOK = nil
        lastRecordMessage = nil
        lastError = nil
    }

    func clearSymptomResult() {
        symptomResult = nil
        lastRecordOK = nil
        lastRecordMessage = nil
        lastError = nil
    }

    static func message(for e: QuickRecordError) -> String {
        switch e {
        case .outOfRange(let m), .missing(let m): return m
        }
    }

    private static func todayString(now: Date = Date()) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: now)
    }

    private func reloadComplicationTimelines() {
        #if canImport(WidgetKit)
        WidgetCenter.shared.reloadTimelines(ofKind: "RevaComplication")
        #endif
    }
}

private enum WatchStoreError: Error {
    case missingDraftData
}
