import SwiftUI
import HealthAgentMacCore

struct PriorityActionHeroView: View {
    let actions: [DesktopDashboardRow]
    let appLanguageRaw: String
    var onStart: ((DesktopDashboardRow) -> Void)? = nil
    var onWhy: ((DesktopDashboardRow) -> Void)? = nil

    @State private var actionIndex: Int = 0

    var body: some View {
        let count = actions.count
        let safeIndex = count > 0 ? min(actionIndex, count - 1) : 0
        let current = count > 0 ? actions[safeIndex] : nil
        let tone = current.map { toneColor($0.tone) } ?? .secondary

        return VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Label(appText("Now do this", appLanguageRaw), systemImage: "bolt.heart.fill")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(tone)
                Spacer()
                if count > 1 {
                    Text("\(safeIndex + 1) / \(count)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            if let row = current {
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: row.systemImage)
                        .font(.title.weight(.semibold))
                        .foregroundStyle(tone)
                        .frame(width: 40)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(row.title)
                            .font(.title2.weight(.semibold))
                            .lineLimit(2)
                        if let subtitle = row.subtitle, !subtitle.isEmpty {
                            Text(subtitle)
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .lineLimit(3)
                        }
                        if let value = row.value, !value.isEmpty {
                            Text(value)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(tone)
                        }
                    }
                    Spacer(minLength: 0)
                }

                HStack(spacing: 10) {
                    Button {
                        onStart?(row)
                    } label: {
                        Label(appText("Start", appLanguageRaw), systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(tone)

                    if count > 1 {
                        Button {
                            actionIndex = (safeIndex + 1) % count
                        } label: {
                            Label(appText("Switch", appLanguageRaw), systemImage: "arrow.triangle.2.circlepath")
                        }
                        .buttonStyle(.bordered)
                    }

                    Button {
                        onWhy?(row)
                    } label: {
                        Label(appText("Why this?", appLanguageRaw), systemImage: "questionmark.circle")
                    }
                    .buttonStyle(.bordered)

                    Spacer()
                }
            } else {
                Text(appText("Nothing on deck. Take a breath.", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 12)
            }
        }
        .padding(20)
        .background {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(tone.opacity(0.08))
                .overlay {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .strokeBorder(tone.opacity(0.25), lineWidth: 1)
                }
        }
    }
}
