import Foundation

/// Watch App 与 WidgetKit complication 共享最近一次状态。优先用 App Group,本地测试/模拟器不可用时退回 standard。
public enum ComplicationCache {
    public static let appGroup = "group.life.executor.health"
    private static let key = "reva.complication.state"

    private static var defaults: UserDefaults {
        UserDefaults(suiteName: appGroup) ?? .standard
    }

    public static func save(_ state: ComplicationState) {
        let dict: [String: Any] = [
            "tone": state.tone.rawValue,
            "short": state.shortText,
            "full": state.fullText,
            "badge": state.urgentBadge,
        ]
        defaults.set(dict, forKey: key)
    }

    public static func load() -> ComplicationState {
        guard let d = defaults.dictionary(forKey: key),
              let toneRaw = d["tone"] as? String,
              let tone = ComplicationTone(rawValue: toneRaw) else {
            return .init(tone: .gray, shortText: "Reva", fullText: "健康助理", urgentBadge: 0)
        }
        return .init(
            tone: tone,
            shortText: d["short"] as? String ?? "",
            fullText: d["full"] as? String ?? "",
            urgentBadge: d["badge"] as? Int ?? 0
        )
    }
}
