import Foundation
import SwiftUI
#if canImport(WidgetKit)
import WidgetKit
#endif

/// 腕上状态容器:经 WatchConnectivity 向 iPhone 取 WatchSummary、发打点请求。
/// iPhone 持 token + 转发后端(watch 不直接联网、不持 token)。
@MainActor
final class WatchStore: ObservableObject {
    @Published var summary: WatchSummary?
    @Published var loading = false
    @Published var lastError: String?
    @Published var lastRecordOK: Bool?
    @Published var lastRecordMessage: String?
    @Published var pendingDietDraft: VoiceFoodDraft?
    @Published var completing = false          // 「一键已做」请求在途(禁重复点 + tile 转圈)

    private let connectivity: WatchConnectivityClient
    private let events: WatchEventClient

    init(connectivity: WatchConnectivityClient = .shared,
         events: WatchEventClient = .shared) {
        self.connectivity = connectivity
        self.events = events
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
            ComplicationCache.save(ComplicationState.from(decoded))
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
                return "iPhone 未连接 —— 请在 iPhone 打开「健康助理」后下拉重试"
            case .badResponse:
                return "数据异常,请下拉重试"
            case .relayFailed(let m):
                if m.contains("未登录") { return "请先在 iPhone 上登录「健康助理」,再下拉重试" }
                if m.contains("401") { return "登录已过期,请在 iPhone 重新登录" }
                if m.hasPrefix("HTTP") { return "服务器繁忙(\(m)),稍后下拉重试" }
                return m   // 网络等系统错误原文,直说
            }
        }
        return "数据解析失败,请下拉重试"
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
        } catch is WatchStoreError {
            lastRecordOK = false
            lastError = "解析失败,请在手机端确认"
        } catch {
            lastRecordOK = false
            lastError = "记录失败,请重试"
        }
    }

    /// 「一键已做」:把到点项标记完成。仅可完成项(有 action_id 且 health_protocol 域)调用。
    /// 走与 submit 同一 fail-loud 链路;完成确认成功(lastRecordOK==true)后才发 completed 埋点。
    func completeAction(_ action: WatchTopAction) async {
        guard let actionId = action.actionId, action.isCompletable, !completing else { return }
        completing = true
        defer { completing = false }
        await submit { try QuickRecord.completeAction(actionId: actionId) }
        if lastRecordOK == true {
            events.actionCompleted(action)
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
