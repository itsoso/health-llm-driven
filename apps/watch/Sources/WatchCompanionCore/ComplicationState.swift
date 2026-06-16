import Foundation

/// 表盘 complication / Smart Stack 的展示状态(从 WatchSummary 映射)。
/// watchOS WidgetKit 层(W3)读这个渲染;映射逻辑在此可单测。
public struct ComplicationState: Sendable, Equatable {
    public let tone: ComplicationTone
    public let shortText: String      // 表盘小字(≤ ~10 字),如 "恢复 78" / "复查!"
    public let fullText: String       // 较大 complication 一行,如 headline
    public let urgentBadge: Int       // P0 推送条数(>0 时表盘标红点/数字)

    public init(tone: ComplicationTone, shortText: String, fullText: String, urgentBadge: Int) {
        self.tone = tone
        self.shortText = shortText
        self.fullText = fullText
        self.urgentBadge = urgentBadge
    }

    /// 从腕上摘要派生。优先级:有 P0 推送 → 表盘喊「复查!/紧急」并标红;否则显示恢复状态。
    public static func from(_ summary: WatchSummary) -> ComplicationState {
        let urgent = summary.pushItems.filter { $0.isUrgent }
        let urgentCount = urgent.count

        if let first = urgent.first {
            // 有 P0:表盘以紧急项为主,tone 强制 red(无论训练灯)
            return ComplicationState(
                tone: .red,
                shortText: shorten(first.title),
                fullText: first.title,
                urgentBadge: urgentCount
            )
        }

        let short: String
        if let score = summary.status.readinessScore, score > 0 {
            short = "恢复 \(score)"
        } else {
            short = toneShort(summary.status.light)
        }
        return ComplicationState(
            tone: summary.status.light,
            shortText: short,
            fullText: summary.status.headline,
            urgentBadge: 0
        )
    }

    private static func toneShort(_ tone: ComplicationTone) -> String {
        switch tone {
        case .green: return "状态好"
        case .yellow: return "适度"
        case .red: return "宜休息"
        case .gray: return "无数据"
        }
    }

    private static func shorten(_ s: String, max: Int = 10) -> String {
        s.count <= max ? s : String(s.prefix(max - 1)) + "…"
    }
}
