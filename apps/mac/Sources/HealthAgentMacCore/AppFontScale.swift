import Foundation

public struct AppFontScale: Equatable, Sendable {
    public static let defaultsKey = "appFontScaleLevel"
    public static let minLevel = -1
    public static let defaultLevel = 0
    public static let maxLevel = 4

    public let level: Int

    public init(level: Int) {
        self.level = min(Self.maxLevel, max(Self.minLevel, level))
    }

    public var displayPercent: Int {
        switch level {
        case -1: 90
        case 0: 100
        case 1: 112
        case 2: 125
        case 3: 140
        default: 160
        }
    }

    public func increased() -> AppFontScale {
        AppFontScale(level: level + 1)
    }

    public func decreased() -> AppFontScale {
        AppFontScale(level: level - 1)
    }

    public func reset() -> AppFontScale {
        AppFontScale(level: Self.defaultLevel)
    }
}
