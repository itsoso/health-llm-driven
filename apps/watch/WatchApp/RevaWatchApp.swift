import SwiftUI

/// Reva 健康助理 watchOS App 入口(W3,真机验证)。
/// 逻辑全在 WatchCompanionCore(已 swift test);本层只做 SwiftUI 声明 + WC 取数。
///
/// 三屏(TabView 分页):今日状态 / 打点 / 关键推送。不做腕上长对话/影像/常驻监听。
@main
struct RevaWatchApp: App {
    @StateObject private var store = WatchStore()

    var body: some Scene {
        WindowGroup {
            TabView {
                TodayStatusView(store: store)
                QuickRecordView(store: store)
                PushListView(store: store)
            }
            .tabViewStyle(.verticalPage)
            .task { await store.refresh() }
        }
    }
}
