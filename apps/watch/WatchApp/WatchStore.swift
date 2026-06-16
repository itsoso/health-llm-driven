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

    private let connectivity: WatchConnectivityClient

    init(connectivity: WatchConnectivityClient = .shared) {
        self.connectivity = connectivity
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
            lastError = "拉取失败,下拉重试"
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
