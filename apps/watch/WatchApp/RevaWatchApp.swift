import SwiftUI

private enum RevaWatchTab: Hashable {
    case today
    case assistant
    case quickRecord
    case push
}

/// Reva 健康助理 watchOS App 入口(W3,真机验证)。
/// 逻辑全在 WatchCompanionCore(已 swift test);本层只做 SwiftUI 声明 + WC 取数。
///
/// 四屏(TabView 分页):今日状态 / 问 Reva / 打点 / 关键推送。不做腕上长对话/影像/常驻监听。
/// 记症状(王牌⑤)语音入口并入「打点」屏,与「记一餐」并列,安全裁决就地渲染。
@main
struct RevaWatchApp: App {
    @StateObject private var store = WatchStore()
    @State private var selectedTab: RevaWatchTab = .today

    var body: some Scene {
        WindowGroup {
            TabView(selection: $selectedTab) {
                TodayStatusView(store: store)
                    .tag(RevaWatchTab.today)
                RevaVoiceAssistantView(store: store)
                    .tag(RevaWatchTab.assistant)
                QuickRecordView(store: store)
                    .tag(RevaWatchTab.quickRecord)
                PushListView(store: store)
                    .tag(RevaWatchTab.push)
            }
            .tabViewStyle(.verticalPage)
            .onAppear { applyLaunchRequestIfNeeded() }
            .onReceive(NotificationCenter.default.publisher(for: WatchLaunchRequest.notificationName)) { _ in
                applyLaunchRequestIfNeeded()
            }
            .onOpenURL { url in
                guard let surface = WatchLaunchRequest.surface(from: url) else { return }
                applyLaunchSurface(surface)
            }
            .task { await store.refresh() }
        }
    }

    private func applyLaunchRequestIfNeeded() {
        guard let surface = WatchLaunchRequest.consume() else { return }
        applyLaunchSurface(surface)
    }

    private func applyLaunchSurface(_ surface: WatchLaunchSurface) {
        switch surface {
        case .assistant:
            selectedTab = .assistant
        case .quickRecord:
            selectedTab = .quickRecord
        }
    }
}
