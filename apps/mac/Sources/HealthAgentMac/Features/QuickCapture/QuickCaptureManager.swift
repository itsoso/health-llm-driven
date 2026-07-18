import AppKit
import SwiftUI
import HealthAgentMacCore

@MainActor
final class QuickCaptureManager {
    private let recordClient: RecordClient
    private var window: NSPanel?
    private var localMonitor: Any?
    private var globalMonitor: Any?

    init(recordClient: RecordClient) {
        self.recordClient = recordClient
    }

    func install() {
        // Cmd+Shift+Space (keyCode 49 = space).
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return event }
            if Self.matchesQuickCaptureShortcut(event) {
                self.toggle()
                return nil
            }
            return event
        }
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return }
            if Self.matchesQuickCaptureShortcut(event) {
                Task { @MainActor in self.toggle() }
            }
        }
    }

    func uninstall() {
        if let localMonitor { NSEvent.removeMonitor(localMonitor) }
        if let globalMonitor { NSEvent.removeMonitor(globalMonitor) }
        localMonitor = nil
        globalMonitor = nil
        window?.close()
        window = nil
    }

    func show() {
        let panel = ensureWindow()
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
    }

    func hide() {
        window?.close()
    }

    private func toggle() {
        if let window, window.isVisible {
            window.close()
        } else {
            show()
        }
    }

    private func ensureWindow() -> NSPanel {
        if let window { return window }
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 200),
            styleMask: [.titled, .closable, .hudWindow, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.title = "Quick Capture"
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.becomesKeyOnlyIfNeeded = false
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.titlebarAppearsTransparent = true
        panel.center()

        let host = NSHostingController(
            rootView: QuickCaptureView(
                client: recordClient,
                onDismiss: { [weak self] in self?.hide() }
            )
        )
        panel.contentViewController = host
        window = panel
        return panel
    }

    private static func matchesQuickCaptureShortcut(_ event: NSEvent) -> Bool {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        guard flags.contains(.command), flags.contains(.shift),
              !flags.contains(.option), !flags.contains(.control) else {
            return false
        }
        return event.keyCode == 49 // space
    }
}

@MainActor
struct QuickCaptureView: View {
    let client: RecordClient
    let onDismiss: () -> Void
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue
    @State private var text: String = ""
    @State private var isSubmitting = false
    @State private var resultMessage: String?
    @State private var resultIsError = false
    @FocusState private var fieldFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "bolt.circle.fill")
                    .foregroundStyle(.cyan)
                Text(appText("Quick Capture", appLanguageRaw))
                    .font(.headline)
                Spacer()
                Text("⌘⇧Space")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
            }

            TextField(
                appText("Symptom, measurement, note...", appLanguageRaw),
                text: $text,
                axis: .vertical
            )
            .textFieldStyle(.roundedBorder)
            .lineLimit(3...6)
            .focused($fieldFocused)
            .onSubmit { submit() }

            if let resultMessage {
                Text(resultMessage)
                    .font(.caption)
                    .foregroundStyle(resultIsError ? Color.red : Color.green)
            }

            HStack {
                Spacer()
                Button(appText("Cancel", appLanguageRaw)) {
                    onDismiss()
                }
                .keyboardShortcut(.cancelAction)

                Button {
                    submit()
                } label: {
                    if isSubmitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text(appText("Save", appLanguageRaw))
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isSubmitting || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(16)
        .frame(width: 520)
        .onAppear { fieldFocused = true }
    }

    private func submit() {
        let payload = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !payload.isEmpty, !isSubmitting else { return }
        isSubmitting = true
        resultMessage = nil
        Task {
            do {
                let result = try await client.quickRecord(text: payload)
                resultMessage = result.displayMessage
                resultIsError = false
                text = ""
                if result.safetyGuidance != nil {
                    isSubmitting = false
                    return
                }
                try? await Task.sleep(nanoseconds: 600_000_000)
                onDismiss()
            } catch {
                resultMessage = error.localizedDescription
                resultIsError = true
            }
            isSubmitting = false
        }
    }
}
