import Foundation

public enum MacAppLifecyclePolicy {
    public static let bundleIdentifier = "life.executor.health.mac"
    public static let multipleInstancePlistKey = "LSMultipleInstancesProhibited"
    public static let preventsMultipleInstances = true
    public static let terminatesAfterLastWindowClosed = true
}
