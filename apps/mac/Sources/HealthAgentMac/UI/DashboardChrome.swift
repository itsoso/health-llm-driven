import SwiftUI
import HealthAgentMacCore

func toneColor(_ tone: String) -> Color {
    switch tone {
    case "orange": .orange
    case "cyan": .cyan
    case "green": .green
    case "pink": .pink
    case "purple": .purple
    case "blue": .blue
    case "red": .red
    case "indigo": .indigo
    case "teal": .teal
    default: .secondary
    }
}

// Single source of truth for the page-level card look so every panel on the
// Today / Data surfaces reads as one design language (was: radii 10/16/18/22,
// fills .background vs .regularMaterial, strokes primary.07 vs secondary.10).
enum AppCardStyle {
    static let cornerRadius: CGFloat = 16
    static let padding: CGFloat = 18
    static let strokeOpacity: Double = 0.07
}

// These free helpers build SwiftUI views, whose initializers (Spacer, etc.) are
// MainActor-isolated under the CI runner's stricter Swift concurrency checking.
// Marking the functions @MainActor matches their only callers (SwiftUI view
// bodies) and avoids "main actor-isolated initializer in nonisolated context".
@MainActor
func panelStroke(radius: CGFloat = AppCardStyle.cornerRadius) -> some View {
    RoundedRectangle(cornerRadius: radius, style: .continuous)
        .stroke(Color.primary.opacity(AppCardStyle.strokeOpacity), lineWidth: 1)
}

extension View {
    /// Standard page card: opaque background, unified radius + hairline stroke.
    @MainActor
    func appCard(padding: CGFloat = AppCardStyle.padding) -> some View {
        self
            .padding(padding)
            .background(.background, in: RoundedRectangle(cornerRadius: AppCardStyle.cornerRadius, style: .continuous))
            .overlay(panelStroke())
    }
}

@MainActor
func sectionHeader(title: String, systemImage: String) -> some View {
    HStack(spacing: 8) {
        Image(systemName: systemImage)
            .foregroundStyle(.secondary)
        Text(title)
            .font(.headline.weight(.semibold))
        Spacer()
    }
}

@MainActor
func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
    VStack(alignment: .leading, spacing: 12) {
        content()
    }
    .appCard()
}

struct VitalRow: View {
    let metric: DesktopDashboardMetric
    let title: String
    let detail: String
    var showsDisclosure = false

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: metric.systemImage)
                .font(.callout.weight(.semibold))
                .foregroundStyle(toneColor(metric.tone))
                .frame(width: 30, height: 30)
                .background(toneColor(metric.tone).opacity(0.11), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.callout.weight(.semibold))
                    .lineLimit(1)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            Text(metric.value)
                .font(.title3.weight(.bold).monospacedDigit())
                .lineLimit(1)
            if showsDisclosure {
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(10)
        .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
