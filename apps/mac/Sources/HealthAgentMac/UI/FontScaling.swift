import SwiftUI
import AppKit
import HealthAgentMacCore

extension View {
    func appFontScale(_ scale: AppFontScale) -> some View {
        modifier(AppFontScaleViewModifier(scale: scale))
    }

    func fontScaleKeyboardShortcuts(level: Binding<Int>) -> some View {
        background(FontScaleKeyboardShortcutBridge(level: level).frame(width: 0, height: 0))
    }
}

struct FontScaleKeyboardShortcutBridge: NSViewRepresentable {
    @Binding var level: Int

    func makeCoordinator() -> Coordinator {
        Coordinator(level: $level)
    }

    func makeNSView(context: Context) -> NSView {
        context.coordinator.install()
        return NSView(frame: .zero)
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        context.coordinator.level = $level
    }

    static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
        coordinator.uninstall()
    }

    final class Coordinator {
        var level: Binding<Int>
        private var monitor: Any?

        init(level: Binding<Int>) {
            self.level = level
        }

        func install() {
            guard monitor == nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                guard let self,
                      let key = event.charactersIgnoringModifiers?.lowercased(),
                      let action = AppFontScaleKeyboardShortcut.action(
                        forKeyEquivalent: key,
                        keyCode: event.keyCode,
                        command: event.modifierFlags.contains(.command),
                        shift: event.modifierFlags.contains(.shift),
                        option: event.modifierFlags.contains(.option),
                        control: event.modifierFlags.contains(.control)
                      ) else {
                    return event
                }

                level.wrappedValue = action.apply(to: AppFontScale(level: level.wrappedValue)).level
                return nil
            }
        }

        func uninstall() {
            if let monitor {
                NSEvent.removeMonitor(monitor)
            }
            monitor = nil
        }
    }
}

struct AppFontScaleViewModifier: ViewModifier {
    let scale: AppFontScale

    func body(content: Content) -> some View {
        content
            .dynamicTypeSize(dynamicTypeSize)
    }

    private var dynamicTypeSize: DynamicTypeSize {
        switch scale.dynamicTypeSizeName {
        case "medium":
            .medium
        case "large":
            .large
        case "xLarge":
            .xLarge
        case "xxLarge":
            .xxLarge
        case "xxxLarge":
            .xxxLarge
        case "accessibility1":
            .accessibility1
        default:
            .large
        }
    }
}
