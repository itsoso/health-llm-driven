import AppKit
import HealthAgentMacCore

@MainActor
final class HealthAgentAppDelegate: NSObject, NSApplicationDelegate {
    func applicationWillFinishLaunching(_ notification: Notification) {
        activateExistingInstanceAndTerminateIfNeeded()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        MacAppLifecyclePolicy.terminatesAfterLastWindowClosed
    }

    private func activateExistingInstanceAndTerminateIfNeeded() {
        let currentPID = ProcessInfo.processInfo.processIdentifier
        let runningInstances = NSRunningApplication
            .runningApplications(withBundleIdentifier: MacAppLifecyclePolicy.bundleIdentifier)
        let snapshots = runningInstances.map {
            MacRunningApplicationSnapshot(
                processIdentifier: $0.processIdentifier,
                isTerminated: $0.isTerminated
            )
        }

        let action = MacSingleInstanceLaunchGuard.launchAction(
            currentProcessIdentifier: currentPID,
            runningApplications: snapshots
        )
        guard case .activateExistingAndTerminate(let processIdentifier) = action,
              let existingInstance = runningInstances.first(where: { $0.processIdentifier == processIdentifier }) else {
            return
        }

        existingInstance.activate(options: [.activateAllWindows])
        NSApplication.shared.terminate(nil)
    }
}
