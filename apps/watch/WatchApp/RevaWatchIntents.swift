import AppIntents
import Foundation

@available(iOS 17.0, watchOS 10.0, macOS 14.0, *)
struct RevaWatchAskIntent: AppIntent {
    static var title: LocalizedStringResource = "问 Reva"
    static var description = IntentDescription("打开 Reva 腕上短答入口")
    static var openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult {
        WatchLaunchRequest.mark(.assistant)
        return .result()
    }
}

@available(iOS 17.0, watchOS 10.0, macOS 14.0, *)
struct RevaWatchRecordIntent: AppIntent {
    static var title: LocalizedStringResource = "快速记录"
    static var description = IntentDescription("打开 Reva 腕上饮食、喝水和运动记录入口")
    static var openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult {
        WatchLaunchRequest.mark(.quickRecord)
        return .result()
    }
}

@available(iOS 17.0, watchOS 10.0, macOS 14.0, *)
struct RevaWatchShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: RevaWatchAskIntent(),
            phrases: [
                "问\(.applicationName)",
                "用\(.applicationName)问一下",
                "打开\(.applicationName)问一下",
            ],
            shortTitle: "问 Reva",
            systemImageName: "mic.circle.fill"
        )
        AppShortcut(
            intent: RevaWatchRecordIntent(),
            phrases: [
                "用\(.applicationName)记录",
                "让\(.applicationName)记一下",
                "打开\(.applicationName)记录",
            ],
            shortTitle: "快速记录",
            systemImageName: "plus.circle.fill"
        )
    }
}
