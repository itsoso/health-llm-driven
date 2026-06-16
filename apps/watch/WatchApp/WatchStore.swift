import Foundation
import SwiftUI

/// 腕上状态容器:经 WatchConnectivity 向 iPhone 取 WatchSummary、发打点请求。
/// iPhone 持 token + 转发后端(watch 不直接联网、不持 token)。
@MainActor
final class WatchStore: ObservableObject {
    @Published var summary: WatchSummary?
    @Published var loading = false
    @Published var lastError: String?
    @Published var lastRecordOK: Bool?

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
            summary = try WatchSummary.decode(data)
        } catch {
            lastError = "拉取失败,下拉重试"
        }
    }

    /// 打点:校验(WatchCompanionCore)→ 经 iPhone 中继。失败 fail loud,不假装成功。
    func submit(_ build: () throws -> QuickRecordRequest) async {
        lastRecordOK = nil
        do {
            let req = try build()
            try await connectivity.sendQuickRecord(req)
            lastRecordOK = true
            await refresh()
        } catch let e as QuickRecordError {
            lastRecordOK = false
            lastError = Self.message(for: e)
        } catch {
            lastRecordOK = false
            lastError = "记录失败,请重试"
        }
    }

    static func message(for e: QuickRecordError) -> String {
        switch e {
        case .outOfRange(let m), .missing(let m): return m
        }
    }
}
