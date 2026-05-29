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
        guard MacAppLifecyclePolicy.preventsMultipleInstances else {
            return
        }
        let currentPID = ProcessInfo.processInfo.processIdentifier
        let runningInstances = NSRunningApplication
            .runningApplications(withBundleIdentifier: MacAppLifecyclePolicy.bundleIdentifier)
            .filter { !$0.isTerminated && $0.processIdentifier != currentPID }

        guard let existingInstance = runningInstances.first else {
            return
        }

        existingInstance.activate(options: [.activateAllWindows])
        NSApplication.shared.terminate(nil)
    }
}
