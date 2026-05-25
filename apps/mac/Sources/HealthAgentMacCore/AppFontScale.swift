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
        case -1: 100
        case 0: 112
        case 1: 125
        case 2: 140
        case 3: 160
        default: 190
        }
    }

    public var dynamicTypeSizeName: String {
        switch level {
        case Self.minLevel:
            "medium"
        case 0:
            "large"
        case 1:
            "xLarge"
        case 2:
            "xxLarge"
        case 3:
            "xxxLarge"
        default:
            "accessibility1"
        }
    }

    public var pointScale: Double {
        Double(displayPercent) / Double(AppFontScale(level: Self.defaultLevel).displayPercent)
    }

    public func pointSize(base: Double) -> Double {
        base * pointScale
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

    public static func nativeMenuShortcuts(for action: AppFontScaleKeyboardShortcut) -> [AppFontScaleNativeMenuShortcut] {
        switch action {
        case .increase:
            [
                AppFontScaleNativeMenuShortcut(keyEquivalent: "=", command: true, shift: false),
                AppFontScaleNativeMenuShortcut(keyEquivalent: "=", command: true, shift: true)
            ]
        case .decrease:
            [AppFontScaleNativeMenuShortcut(keyEquivalent: "-", command: true, shift: false)]
        case .reset:
            [AppFontScaleNativeMenuShortcut(keyEquivalent: "0", command: true, shift: false)]
        }
    }
}

public struct AppFontScaleNativeMenuShortcut: Equatable, Sendable {
    public let keyEquivalent: String
    public let command: Bool
    public let shift: Bool

    public init(keyEquivalent: String, command: Bool, shift: Bool) {
        self.keyEquivalent = keyEquivalent
        self.command = command
        self.shift = shift
    }
}
