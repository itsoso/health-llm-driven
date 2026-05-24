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

public enum AppFontScaleKeyboardShortcut: Equatable, Sendable {
    case increase
    case decrease
    case reset

    public static func action(
        forKeyEquivalent keyEquivalent: String,
        keyCode: UInt16? = nil,
        command: Bool,
        shift: Bool = false,
        option: Bool = false,
        control: Bool = false
    ) -> AppFontScaleKeyboardShortcut? {
        guard command, !option, !control else { return nil }

        switch keyEquivalent {
        case "+", "=":
            return .increase
        case "-":
            return .decrease
        case "0":
            return .reset
        default:
            break
        }

        switch keyCode {
        case 24, 69:
            return .increase
        case 27, 78:
            return .decrease
        case 29, 82:
            return .reset
        default:
            return nil
        }
    }

    public func apply(to scale: AppFontScale) -> AppFontScale {
        switch self {
        case .increase:
            scale.increased()
        case .decrease:
            scale.decreased()
        case .reset:
            scale.reset()
        }
    }
}
