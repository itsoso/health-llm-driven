import Foundation

/// Watch App 与 WidgetKit complication 共享最近一次状态。优先用 App Group,本地测试/模拟器不可用时退回 standard。
public enum ComplicationCache {
    public static let appGroup = "group.life.executor.health"
    private static let key = "reva.complication.state"

    static var sharedDefaults: UserDefaults {
        UserDefaults(suiteName: appGroup) ?? .standard
    }

    public static func save(_ state: ComplicationState, in store: UserDefaults? = nil) {
        let dict: [String: Any] = [
            "tone": state.tone.rawValue,
            "short": state.shortText,
            "full": state.fullText,
            "badge": state.urgentBadge,
        ]
        (store ?? sharedDefaults).set(dict, forKey: key)
    }

    public static func load(in store: UserDefaults? = nil) -> ComplicationState {
        guard let d = (store ?? sharedDefaults).dictionary(forKey: key),
              let toneRaw = d["tone"] as? String,
              let tone = ComplicationTone(rawValue: toneRaw) else {
            return .init(tone: .gray, shortText: "阿衡", fullText: "阿衡", urgentBadge: 0)
        }
        return .init(
            tone: tone,
            shortText: d["short"] as? String ?? "",
            fullText: d["full"] as? String ?? "",
            urgentBadge: d["badge"] as? Int ?? 0
        )
    }

    /// 注销/换机时清掉残留表盘状态(App Group 明文,不应跨账号存活)。
    public static func clear(in store: UserDefaults? = nil) {
        (store ?? sharedDefaults).removeObject(forKey: key)
    }
}
