import SwiftUI
import HealthAgentMacCore

// ── Warm "Claude Design" palette (single source of truth) ───────────────────
// Same tokens the web frontend uses. Each color is defined with an explicit
// light + dark pair via `Color(warmLight:dark:)` so the whole app reads warm in
// both modes (dark = warm near-black, not the system cool gray). Used by
// `toneColor`, the app-card chrome, and the Today dashboard hero.
enum WarmPalette {
    // Surfaces
    static let paper   = Color(warmLight: 0xF7F5EF, dark: 0x1C1A15)
    static let rail    = Color(warmLight: 0xF0EDE4, dark: 0x211E19)
    static let card    = Color(warmLight: 0xFCFBF7, dark: 0x26221A)
    static let card2   = Color(warmLight: 0xF5F2E9, dark: 0x2C2820)
    // Hairlines
    static let hair    = Color(warmLight: 0xE5E1D5, dark: 0x3A352B)
    static let hair2   = Color(warmLight: 0xD8D3C4, dark: 0x47412F)
    // Ink
    static let ink     = Color(warmLight: 0x29261F, dark: 0xF0EBE0)
    static let ink2    = Color(warmLight: 0x6B665A, dark: 0xB8B2A2)
    static let ink3    = Color(warmLight: 0x948F80, dark: 0x8A8574)
    // Accents
    static let clay     = Color(warmLight: 0xC96442, dark: 0xD9784F)
    static let claySoft = Color(warmLight: 0xF3E4DC, dark: 0x40281E)
    static let clayInk  = Color(warmLight: 0xA24F31, dark: 0xE29273)
    static let amber     = Color(warmLight: 0xB8791F, dark: 0xD9A04A)
    static let amberSoft = Color(warmLight: 0xF5EBD6, dark: 0x3A2E17)
    static let sage      = Color(warmLight: 0x5F7A55, dark: 0x8FA982)
    static let sageSoft  = Color(warmLight: 0xE7EDE0, dark: 0x232B1E)
}

extension Color {
    /// Build a warm color with an explicit light/dark hex pair. Drives the whole
    /// app off `NSAppearance` so dark mode is warm, not the cool system gray.
    init(warmLight lightHex: UInt, dark darkHex: UInt) {
        self = Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return NSColor(hex: isDark ? darkHex : lightHex)
        })
    }
}

extension NSColor {
    fileprivate convenience init(hex: UInt) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >> 8) & 0xFF) / 255.0
        let b = Double(hex & 0xFF) / 255.0
        self.init(srgbRed: r, green: g, blue: b, alpha: 1)
    }
}

// Semantic tones referenced from data by string. Remapped onto the warm palette:
// the old teal/blue/pink chrome now reads as sage/clay/amber, cool grays gone.
func toneColor(_ tone: String) -> Color {
    switch tone {
    case "orange": WarmPalette.amber
    case "cyan": WarmPalette.sage
    case "green": WarmPalette.sage
    case "pink": WarmPalette.clay
    case "purple": WarmPalette.clayInk
    case "blue": WarmPalette.clay
    case "red": Color(warmLight: 0xC0453B, dark: 0xE07A6E)
    case "indigo": WarmPalette.clayInk
    case "teal": WarmPalette.sage
    default: WarmPalette.ink3
    }
}

// Single source of truth for the page-level card look so every panel on the
// Today / Data surfaces reads as one design language. Warm card fill + warm
// hairline stroke replace the old opaque-neutral / primary.07 treatment.
enum AppCardStyle {
    static let cornerRadius: CGFloat = 16
    static let padding: CGFloat = 18
    static let strokeOpacity: Double = 0.07
    static let cardFill = WarmPalette.card
    static let strokeColor = WarmPalette.hair
}

// These free helpers build SwiftUI views, whose initializers (Spacer, etc.) are
// MainActor-isolated under the CI runner's stricter Swift concurrency checking.
// Marking the functions @MainActor matches their only callers (SwiftUI view
// bodies) and avoids "main actor-isolated initializer in nonisolated context".
@MainActor
func panelStroke(radius: CGFloat = AppCardStyle.cornerRadius) -> some View {
    RoundedRectangle(cornerRadius: radius, style: .continuous)
        .stroke(AppCardStyle.strokeColor, lineWidth: 1)
}

extension View {
    /// Standard page card: warm card fill, unified radius + warm hairline stroke.
    @MainActor
    func appCard(padding: CGFloat = AppCardStyle.padding) -> some View {
        self
            .padding(padding)
            .background(AppCardStyle.cardFill, in: RoundedRectangle(cornerRadius: AppCardStyle.cornerRadius, style: .continuous))
            .overlay(panelStroke())
    }
}

@MainActor
func sectionHeader(title: String, systemImage: String) -> some View {
    HStack(spacing: 8) {
        Image(systemName: systemImage)
            .foregroundStyle(WarmPalette.clay)
        Text(title)
            .font(.headline.weight(.semibold))
            .foregroundStyle(WarmPalette.ink)
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
        .background(WarmPalette.card2, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
