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

func panelStroke(radius: CGFloat) -> some View {
    RoundedRectangle(cornerRadius: radius, style: .continuous)
        .stroke(Color.primary.opacity(0.07), lineWidth: 1)
}

func sectionHeader(title: String, systemImage: String) -> some View {
    HStack(spacing: 8) {
        Image(systemName: systemImage)
            .foregroundStyle(.secondary)
        Text(title)
            .font(.headline.weight(.semibold))
        Spacer()
    }
}

func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
    VStack(alignment: .leading, spacing: 12) {
        content()
    }
    .padding(16)
    .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    .overlay(panelStroke(radius: 18))
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
