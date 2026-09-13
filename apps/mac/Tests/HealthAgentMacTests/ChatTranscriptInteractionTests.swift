import AppKit
import HealthAgentMacCore
import SwiftUI
import WebKit
import XCTest
@testable import HealthAgentMac

@MainActor
final class ChatTranscriptInteractionTests: XCTestCase {
    func testEditorCanCancelAndResendChangedTextButRejectsEmptyTextAndPendingAttachments() async throws {
        var sent: String?
        var cancelled = false
        let editor = UserPromptEditor(text: "原始问题", hasPendingAttachments: false,
                                      onCancel: { cancelled = true }, onSend: { sent = $0 })
        let host = NSHostingView(rootView: editor)
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 620, height: 540),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        window.makeKeyAndOrderFront(nil)
        defer { window.close() }
        try await Task.sleep(for: .milliseconds(100))
        let input = try XCTUnwrap(descendants(host).compactMap { $0 as? NSTextView }.first)
        XCTAssertEqual(input.string, "原始问题")
        pressShortcut(in: window, cancel: true)
        XCTAssertTrue(cancelled)
        XCTAssertNil(sent)

        input.string = " \n "
        input.didChangeText()
        try await Task.sleep(for: .milliseconds(50))
        pressShortcut(in: window)
        XCTAssertNil(sent)
        input.string = "修改后的问题\n保留换行"
        input.didChangeText()
        try await Task.sleep(for: .milliseconds(50))
        pressShortcut(in: window)
        XCTAssertEqual(sent, "修改后的问题\n保留换行")

        sent = nil
        host.rootView = UserPromptEditor(text: "有待发送附件", hasPendingAttachments: true,
                                         onCancel: {}, onSend: { sent = $0 })
        try await Task.sleep(for: .milliseconds(50))
        pressShortcut(in: window)
        XCTAssertNil(sent)
    }

    private func descendants(_ view: NSView) -> [NSView] {
        [view] + view.subviews.flatMap { descendants($0) }
    }

    private func pressShortcut(in window: NSWindow, cancel: Bool = false) {
        let character = cancel ? "\u{1b}" : "\r"
        let event = NSEvent.keyEvent(with: .keyDown, location: .zero,
                                    modifierFlags: cancel ? [] : .command, timestamp: 0,
                                    windowNumber: window.windowNumber, context: nil,
                                    characters: character, charactersIgnoringModifiers: character,
                                    isARepeat: false, keyCode: cancel ? 53 : 36)!
        _ = window.performKeyEquivalent(with: event)
    }

    func testUserCopyAndEditButtonsReachNativeHandlersWithoutChangingText() async throws {
        let model = AgentChatViewModel()
        let prompt = AgentChatMessage(role: .user, content: "请根据本周的记录给我建议。\n保留换行、<原文> 和 emoji 😀。")
        model.messages = [prompt, .init(role: .assistant, content: "请补充希望查看的时间范围。")]
        let pasteboard = NSPasteboard.withUniqueName()
        defer { pasteboard.releaseGlobally() }
        var editedID: String?
        let coordinator = ChatTranscriptWebView.Coordinator(
            onCopy: { id in
                pasteboard.clearContents()
                pasteboard.setString(model.copyableText(messageID: id) ?? "", forType: .string)
            },
            onEdit: { editedID = $0 },
            onRouteOpen: { _ in }, onAIGCConfirm: { _ in },
            onDietDraftConfirm: { _ in }, onMedicationBatchAction: { _ in }
        )
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        for name in ["ready", "copy", "edit"] {
            configuration.userContentController.add(coordinator, name: name)
        }
        let webView = WKWebView(frame: CGRect(x: 0, y: 0, width: 820, height: 540), configuration: configuration)
        let window = NSWindow(contentRect: webView.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.orderFront(nil)
        defer {
            window.close()
            configuration.userContentController.removeAllScriptMessageHandlers()
        }
        coordinator.webView = webView
        coordinator.apply(messages: model.renderedTranscript(), fontScale: 1)
        coordinator.loadShell()
        for _ in 0..<200 {
            let count = try? await webView.evaluateJavaScript("document.querySelectorAll('.user-actions button').length")
            if count as? Int == 2 { break }
            try await Task.sleep(for: .milliseconds(25))
        }
        let buttons = try await webView.evaluateJavaScript("document.querySelectorAll('.user-actions button').length")
        XCTAssertEqual(buttons as? Int, 2)
        let assistantEditButtons = try await webView.evaluateJavaScript("document.querySelectorAll('.assistant .edit-btn').length")
        XCTAssertEqual(assistantEditButtons as? Int, 0)

        _ = try await webView.evaluateJavaScript("document.querySelector('.user-actions .copy-btn').click()")
        for _ in 0..<100 where pasteboard.string(forType: .string) == nil {
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertEqual(pasteboard.string(forType: .string), prompt.content)
        _ = try await webView.evaluateJavaScript("document.querySelector('.user-actions .edit-btn').click()")
        for _ in 0..<100 where editedID == nil { try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(editedID, prompt.id.uuidString)
        XCTAssertEqual(model.messages.first?.content, prompt.content)

        editedID = nil
        _ = try await webView.evaluateJavaScript("window.webkit.messageHandlers.edit.postMessage('unknown-id'); true")
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertNil(editedID)

        if let output = ProcessInfo.processInfo.environment["REVA_TRANSCRIPT_SMOKE_PNG"] {
            let snapshot = try await webView.takeSnapshot(configuration: nil)
            let bitmap = try XCTUnwrap(snapshot.tiffRepresentation.flatMap(NSBitmapImageRep.init(data:)))
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: URL(fileURLWithPath: output))
        }
    }
}
