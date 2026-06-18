import Foundation

/// 注销 / 换机时清掉腕上残留的粗粒度健康数据。
///
/// JWT 本身在 Keychain 单独清除(`WatchCredentialStore.deleteToken()`);这里只负责
/// App Group UserDefaults 里的明文摘要 + 表盘缓存——它们不是秘密,但不应跨账号/换机存活。
public enum WatchSessionReset {
    /// 清空 watch summary 缓存与 complication 状态缓存。注销信号到达时调用。
    /// - Parameter store: 仅供测试注入隔离的 UserDefaults;生产默认走 App Group。
    public static func clearCachedHealthData(in store: UserDefaults? = nil) {
        let defaults = store ?? (UserDefaults(suiteName: ComplicationCache.appGroup) ?? .standard)
        WatchSummaryCache(defaults: defaults).clear()
        ComplicationCache.clear(in: defaults)
    }
}
