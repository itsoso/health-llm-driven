import Foundation

public struct MacRunningApplicationSnapshot: Equatable, Sendable {
    public let processIdentifier: Int32
    public let isTerminated: Bool

    public init(processIdentifier: Int32, isTerminated: Bool) {
        self.processIdentifier = processIdentifier
        self.isTerminated = isTerminated
    }
}

public enum MacSingleInstanceLaunchAction: Equatable, Sendable {
    case continueLaunching
    case activateExistingAndTerminate(processIdentifier: Int32)
}

public enum MacSingleInstanceLaunchGuard {
    public static func launchAction(
        currentProcessIdentifier: Int32,
        runningApplications: [MacRunningApplicationSnapshot],
        preventsMultipleInstances: Bool = MacAppLifecyclePolicy.preventsMultipleInstances
    ) -> MacSingleInstanceLaunchAction {
        guard preventsMultipleInstances else {
            return .continueLaunching
        }
        guard let existingInstance = runningApplications.first(where: {
            !$0.isTerminated && $0.processIdentifier != currentProcessIdentifier
        }) else {
            return .continueLaunching
        }
        return .activateExistingAndTerminate(processIdentifier: existingInstance.processIdentifier)
    }
}
