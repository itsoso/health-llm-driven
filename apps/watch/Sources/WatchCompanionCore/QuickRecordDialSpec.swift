import Foundation

public struct QuickRecordDialSpec: Equatable, Sendable {
    public let defaultValue: Double
    public let lowerBound: Double
    public let upperBound: Double
    public let step: Double

    public init(defaultValue: Double, lowerBound: Double, upperBound: Double, step: Double) {
        precondition(lowerBound <= upperBound)
        precondition(step > 0)
        self.defaultValue = defaultValue
        self.lowerBound = lowerBound
        self.upperBound = upperBound
        self.step = step
    }

    public func snapped(_ rawValue: Double? = nil) -> Double {
        let value = rawValue ?? defaultValue
        let bounded = min(max(value, lowerBound), upperBound)
        let units = ((bounded - lowerBound) / step).rounded()
        let snapped = lowerBound + units * step
        return min(max(snapped, lowerBound), upperBound)
    }

    public func intValue(_ rawValue: Double? = nil) -> Int {
        Int(snapped(rawValue).rounded())
    }
}

public enum QuickRecordDials {
    public static let waterML = QuickRecordDialSpec(
        defaultValue: 250, lowerBound: 100, upperBound: 1000, step: 50
    )
    public static let pushupReps = QuickRecordDialSpec(
        defaultValue: 20, lowerBound: 5, upperBound: 60, step: 1
    )
    public static let runDurationMin = QuickRecordDialSpec(
        defaultValue: 30, lowerBound: 5, upperBound: 90, step: 5
    )
}
