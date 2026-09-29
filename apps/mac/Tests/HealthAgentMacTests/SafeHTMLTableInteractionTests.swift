import AppKit
import HealthAgentMacCore
import WebKit
import XCTest

@MainActor
final class SafeHTMLTableInteractionTests: XCTestCase {
    func testRealTranscriptShellRendersTableAndDisclosesExactInertSource() async throws {
        let source = """
        ```html
        <table style="background:url(https://invalid.test/never-load)">
        <caption>合成示例：最近一周睡眠</caption>
        <thead><tr><th>日期</th><th>睡眠时长</th><th>备注</th></tr></thead>
        <tbody><tr><td>周一</td><td>7 小时 10 分</td><td></td></tr>
        <tr><td>周二</td><td>7 小时 30 分</td><td>A | B</td></tr>
        <tr><td>周三</td><td>8 小时</td><td>&lt;script&gt;仅作为文本&lt;/script&gt;</td></tr></tbody>
        </table>
        ```
        """
        let model = AgentChatViewModel()
        model.messages = [.init(role: .assistant, content: "以下为合成数据，仅用于显示验收。\n\n" + source)]
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        let webView = WKWebView(frame: CGRect(x: 0, y: 0, width: 820, height: 600), configuration: configuration)
        let window = NSWindow(contentRect: webView.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.orderFront(nil)
        defer { window.close() }
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let shell = try String(contentsOf: root.appendingPathComponent("Sources/HealthAgentMac/Resources/chat-transcript.html"), encoding: .utf8)
        webView.loadHTMLString(shell, baseURL: nil)
        for _ in 0..<200 {
            if (try? await webView.evaluateJavaScript("typeof window.chat === 'object'")) as? Bool == true { break }
            try await Task.sleep(for: .milliseconds(25))
        }
        _ = try await webView.evaluateJavaScript("window.chat.setMessages(\(ChatTranscriptHTML.messagesJSONArray(model.renderedTranscript()))); true")
        let rows = try await webView.evaluateJavaScript("document.querySelectorAll('.body table tr').length")
        XCTAssertEqual(rows as? Int, 4)
        let cells = try await webView.evaluateJavaScript("Array.from(document.querySelectorAll('.body td')).map(x=>x.textContent)")
        XCTAssertEqual(cells as? [String], ["周一", "7 小时 10 分", "", "周二", "7 小时 30 分", "A | B", "周三", "8 小时", "<script>仅作为文本</script>"])
        let dangerous = try await webView.evaluateJavaScript("document.querySelectorAll('.body script,.body iframe,.body img,.body [data-action]').length")
        XCTAssertEqual(dangerous as? Int, 0)
        let overflow = try await webView.evaluateJavaScript("getComputedStyle(document.querySelector('.body table').parentElement).overflowX")
        XCTAssertEqual(overflow as? String, "auto")
        let literal = try await webView.evaluateJavaScript("document.querySelector('.body details pre').textContent")
        XCTAssertEqual(literal as? String, source)
        _ = try await webView.evaluateJavaScript("document.querySelector('.body details').open=true; true")
        if let path = ProcessInfo.processInfo.environment["REVA_HTML_TABLE_SMOKE_PNG"] {
            let snapshot = try await webView.takeSnapshot(configuration: nil)
            let bitmap = try XCTUnwrap(snapshot.tiffRepresentation.flatMap(NSBitmapImageRep.init(data:)))
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: URL(fileURLWithPath: path))
        }
    }
}
