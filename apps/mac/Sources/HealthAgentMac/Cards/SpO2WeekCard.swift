import SwiftUI
import HealthAgentMacCore

struct SpO2WeekCard: View {
    let nights: [NocturnalWeekNight]
    let appLanguageRaw: String
    var onAskAgent: ((String, AgentContextItem?) -> Void)? = nil

    var body: some View {
        SectionPanel(
            title: appText("Overnight SpO2 risk · last 7 nights", appLanguageRaw),
            systemImage: "lungs.fill"
        ) {
            HStack(alignment: .top, spacing: 14) {
                Circle()
                    .fill(badgeColor)
                    .frame(width: 12, height: 12)
                    .padding(.top, 4)
                VStack(alignment: .leading, spacing: 6) {
                    Text(headline)
                        .font(.callout.weight(.medium))
                    HStack(spacing: 8) {
                        ForEach(nights) { night in
                            VStack(spacing: 2) {
                                Circle()
                                    .fill(Self.dotColor(for: night))
                                    .frame(width: 8, height: 8)
                                Text(Self.shortLabel(night.date))
                                    .font(.system(size: 9).monospacedDigit())
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                    if let onAskAgent {
                        Button {
                            onAskAgent(promptText, contextItem)
                        } label: {
                            Label(appText("Ask Agent about this", appLanguageRaw), systemImage: "sparkles")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                }
                Spacer(minLength: 0)
            }
        }
    }

    static func shouldShow(nights: [NocturnalWeekNight], loaded: Bool) -> Bool {
        loaded && Self.nightsWithData(nights) >= 1
    }

    static func nightsWithData(_ nights: [NocturnalWeekNight]) -> Int {
        nights.filter { ($0.summary?.samples.isEmpty == false) }.count
    }

    static func nightsWithLongHypoxicEpisode(_ nights: [NocturnalWeekNight]) -> Int {
        nights.filter { ($0.summary?.longHypoxicEpisodeCount ?? 0) > 0 }.count
    }

    private var longEpisodeNightCount: Int { Self.nightsWithLongHypoxicEpisode(nights) }
    private var nightsWithDataCount: Int { Self.nightsWithData(nights) }

    private var badgeColor: Color {
        switch longEpisodeNightCount {
        case 0: return .green
        case 1, 2: return .yellow
        default: return .red
        }
    }

    private var headline: String {
        let count = longEpisodeNightCount
        switch count {
        case 0:
            return appText("Overnight SpO2 looks steady this week.", appLanguageRaw)
        case 1, 2:
            let template = appText("%d night(s) with sustained low-SpO2 segments.", appLanguageRaw)
            return String(format: template, count)
        default:
            let template = appText("%d nights showed sustained low-SpO2 segments — consider follow-up.", appLanguageRaw)
            return String(format: template, count)
        }
    }

    private var promptText: String {
        "近 7 夜中有 \(longEpisodeNightCount) 夜出现持续 ≥5 分钟的 SpO2<90% 段。请结合我已有的鼻炎、用药、睡眠数据评估是否需要进一步检查。"
    }

    private var contextItem: AgentContextItem? {
        guard !nights.isEmpty else { return nil }
        let payload: [String: String] = [
            "long_episode_nights": "\(longEpisodeNightCount)",
            "nights_loaded": "\(nightsWithDataCount)",
            "min_overall": nights.compactMap { $0.summary?.minValue }.min().map { String(format: "%.1f", $0) } ?? "—"
        ]
        let summary = "近 7 夜，长低氧段夜数 \(longEpisodeNightCount)/\(nightsWithDataCount)"
        return AgentContextItem(
            sourceID: "spo2-week-risk",
            sourceKind: "wearable",
            title: "Overnight SpO2 weekly risk",
            summary: summary,
            payload: payload
        )
    }

    static func dotColor(for night: NocturnalWeekNight) -> Color {
        guard let summary = night.summary else { return Color.gray.opacity(0.3) }
        let count = summary.longHypoxicEpisodeCount
        if count == 0 { return .green }
        if count == 1 { return .yellow }
        return .red
    }

    static func shortLabel(_ date: String) -> String {
        let parts = date.split(separator: "-")
        if parts.count == 3 { return "\(parts[1])/\(parts[2])" }
        return date
    }
}
