import Foundation
import XCTest
@testable import HealthAgentMacCore

final class ChatTranscriptHTMLTests: XCTestCase {

    // MARK: - escape (XSS 防线核心断言)

    func testEscapeNeutralizesScriptInjection() {
        let raw = "<script>alert('xss')</script>"
        let escaped = ChatTranscriptHTML.escape(raw)
        // 没有任何可执行的尖括号标签残留
        XCTAssertFalse(escaped.contains("<script"))
        XCTAssertFalse(escaped.contains("</script>"))
        XCTAssertFalse(escaped.contains("<"))
        XCTAssertFalse(escaped.contains(">"))
        XCTAssertEqual(escaped, "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;")
    }

    func testEscapeHandlesAmpersandFirst() {
        // & 必须最先转义,否则后插入的实体里的 & 会被二次转义成 &amp;amp;
        XCTAssertEqual(ChatTranscriptHTML.escape("a & b"), "a &amp; b")
        XCTAssertEqual(ChatTranscriptHTML.escape("<a> & </a>"), "&lt;a&gt; &amp; &lt;/a&gt;")
    }

    func testEscapeQuotesForAttributeSafety() {
        XCTAssertEqual(ChatTranscriptHTML.escape("\"hi\" 'there'"), "&quot;hi&quot; &#39;there&#39;")
    }

    func testEscapeLeavesPlainTextUnchanged() {
        XCTAssertEqual(ChatTranscriptHTML.escape("正常的中文文本 123"), "正常的中文文本 123")
    }

    func testEscapeIsIdempotentlySafeOnEmpty() {
        XCTAssertEqual(ChatTranscriptHTML.escape(""), "")
    }

    // MARK: - inline markdown after escape (受控白名单)

    func testInlineMarkdownBoldItalicCode() {
        let escaped = ChatTranscriptHTML.escape("**bold** *it* `c`")
        let html = ChatTranscriptHTML.inlineMarkdown(escaped)
        XCTAssertTrue(html.contains("<strong>bold</strong>"))
        XCTAssertTrue(html.contains("<em>it</em>"))
        XCTAssertTrue(html.contains("<code>c</code>"))
    }

    func testInlineMarkdownLeavesUnclosedMarkerLiteral() {
        let html = ChatTranscriptHTML.inlineMarkdown(ChatTranscriptHTML.escape("a **b"))
        XCTAssertEqual(html, "a **b")
    }

    func testInlineMarkdownDoesNotResurrectEscapedTags() {
        // 用户写的 <b> 已被 escape 成 &lt;b&gt;,inline markdown 不能把它变回真标签
        let escaped = ChatTranscriptHTML.escape("<b>not bold</b> **real**")
        let html = ChatTranscriptHTML.inlineMarkdown(escaped)
        XCTAssertFalse(html.contains("<b>"))
        XCTAssertTrue(html.contains("&lt;b&gt;"))
        XCTAssertTrue(html.contains("<strong>real</strong>"))
    }

    // MARK: - renderMessageBody (整条消息 → 安全 HTML)

    func testRenderMessageBodyEscapesInjectionInParagraph() {
        let html = ChatTranscriptHTML.renderMessageBody(markdown: "Hello <img src=x onerror=alert(1)>")
        // 安全属性:尖括号被转义,注入不会成为真 DOM 元素/属性(文本里出现 "onerror"
        // 字样是无害的,因为它是被转义的纯文本,不是 HTML 属性)。
        XCTAssertFalse(html.contains("<img"))
        XCTAssertTrue(html.contains("&lt;img"))
        XCTAssertTrue(html.contains("&gt;"))
    }

    func testRenderMessageBodyProducesTableGrid() {
        let md = "| A | B |\n| 1 | 2 |"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        XCTAssertTrue(html.contains("<table>"))
        XCTAssertTrue(html.contains("<th>A</th>"))
        XCTAssertTrue(html.contains("<td>1</td>"))
    }

    func testRenderMessageBodyBulletList() {
        let html = ChatTranscriptHTML.renderMessageBody(markdown: "- one\n- two")
        XCTAssertTrue(html.contains("<ul>"))
        XCTAssertEqual(html.components(separatedBy: "<li>").count - 1, 2)
    }

    func testRenderMessageBodyHeading() {
        let html = ChatTranscriptHTML.renderMessageBody(markdown: "## Title")
        XCTAssertTrue(html.contains("<h2>Title</h2>"))
    }

    // MARK: - JS string injection safety

    func testRenderedMessageJSStringEscapesQuotesAndScriptClose() {
        let msg = ChatTranscriptHTML.RenderedMessage(
            id: "id-1",
            role: "assistant",
            bodyHTML: "<p>he said \"hi\" </script></p>\nline2",
            isStreaming: false,
            showCopy: true
        )
        let json = msg.jsonObject
        // 不能存在裸 " 破坏 JS 字符串(除字段分隔符外都应被转义)
        XCTAssertTrue(json.contains("\\\""))
        // </script> 的 < 被编码,避免提前闭合脚本块
        XCTAssertFalse(json.contains("</script>"))
        XCTAssertTrue(json.contains("\\u003c/script"))
        // 换行被编码,不破坏字符串字面量
        XCTAssertFalse(json.contains("\n"))
        XCTAssertTrue(json.contains("\\n"))
    }

    func testMessagesJSONArrayWellFormed() {
        let a = ChatTranscriptHTML.RenderedMessage(id: "a", role: "user", bodyHTML: "<p>hi</p>", isStreaming: false, showCopy: false)
        let b = ChatTranscriptHTML.RenderedMessage(id: "b", role: "assistant", bodyHTML: "<p>yo</p>", isStreaming: false, showCopy: true)
        let arr = ChatTranscriptHTML.messagesJSONArray([a, b])
        XCTAssertTrue(arr.hasPrefix("["))
        XCTAssertTrue(arr.hasSuffix("]"))
        let data = arr.data(using: .utf8)!
        let parsed = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        XCTAssertEqual((parsed ?? [])?.count, 2)
    }
}
