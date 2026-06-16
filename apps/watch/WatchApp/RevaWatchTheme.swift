import SwiftUI

/// 复元 Reva — watchOS 设计令牌(镜像 mobile/constants/revaTheme.ts 的 revaColors)。
///
/// 手表用深色面(OLED 省电 + 高级感):focusBg 系列做底,ink 系列做文字,
/// greenBright 做强调,三级临床色 normal/caution/risk。数字一律 mono 对齐 Reva。
/// 只用 watchOS 10+ 可用的 SwiftUI API。
enum RevaWatch {
    // ── 深色面(focus surface)────────────────────────────────────────────
    static let focusBg   = Color(red: 0x0F / 255, green: 0x1C / 255, blue: 0x17 / 255) // #0F1C17 主背景
    static let focusBg2  = Color(red: 0x16 / 255, green: 0x27 / 255, blue: 0x1F / 255) // #16271F 子面
    static let focusLine = Color(red: 0x23 / 255, green: 0x46 / 255, blue: 0x3A / 255) // #23463A 描边

    // ── 文字(深色面)──────────────────────────────────────────────────────
    static let ink1 = Color(red: 0xEA / 255, green: 0xF3 / 255, blue: 0xEE / 255) // #EAF3EE 主文字
    static let ink2 = Color(red: 0x9D / 255, green: 0xB3 / 255, blue: 0xA8 / 255) // #9DB3A8 次文字

    // ── 强调绿 ──────────────────────────────────────────────────────────────
    static let greenBright = Color(red: 0x3A / 255, green: 0xD2 / 255, blue: 0x9F / 255) // #3AD29F 就绪/强调
    static let green500     = Color(red: 0x1F / 255, green: 0x8A / 255, blue: 0x5B / 255) // #1F8A5B

    // ── 三级临床色(深色面上用亮版)────────────────────────────────────────
    static let normal  = Color(red: 0x3A / 255, green: 0xD2 / 255, blue: 0x9F / 255) // #3AD29F 就绪绿
    static let caution = Color(red: 0xE8 / 255, green: 0xB2 / 255, blue: 0x3A / 255) // #E8B23A 注意黄
    static let risk    = Color(red: 0xF2 / 255, green: 0x6D / 255, blue: 0x5B / 255) // #F26D5B 异常红

    // ── 圆角 ──────────────────────────────────────────────────────────────────
    static let radiusTile: CGFloat = 12
    static let radiusRow: CGFloat = 10

    /// ComplicationTone → 深色面对应色。
    static func tone(_ t: ComplicationTone) -> Color {
        switch t {
        case .green: return normal
        case .yellow: return caution
        case .red: return risk
        case .gray: return ink2
        }
    }

    /// mono 数字字体(对齐 Reva 的 IBM Plex Mono → watchOS 用 system monospaced)。
    static func monoNumber(_ size: CGFloat, weight: Font.Weight = .medium) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}
