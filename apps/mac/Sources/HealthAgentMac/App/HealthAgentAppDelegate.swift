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

        // First-wins: bring the already-running instance forward, then this
        // duplicate bows out immediately. We call exit(0) rather than
        // NSApplication.terminate(nil): at willFinishLaunching the app isn't fully
        // up, and terminate() posts an ASYNC termination request that can let a
        // window/side-effect flash before it fires. exit(0) guarantees the dupe
        // dies here — before any UI or heavy init — so there is never more than
        // one live process (belt-and-suspenders with LSMultipleInstancesProhibited).
        existingInstance.activate(options: [.activateAllWindows])
        exit(0)
    }
}
