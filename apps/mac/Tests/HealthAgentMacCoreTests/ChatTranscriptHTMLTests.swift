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

    // MARK: - meta footer (模型 · 轮数 · 耗时 / 数据源 / Skill)

    func testMetaFooterRendersModelRoundsElapsed() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "commercial/Claude-Opus-4.7",
            selectedModel: "commercial/Claude-Opus-4.7",
            answerModel: "commercial/Claude-Opus-4.7",
            toolModels: ["qwen3.7-max"],
            fallbackReasons: ["selected_model_tool_stream_failed"],
            elapsedMs: 3500,
            llmRounds: 3,
            sourcesUsed: [],
            toolsUsed: []
        )
        XCTAssertTrue(html.contains("meta-footer"))
        XCTAssertTrue(html.contains("3.5s"))
        XCTAssertTrue(html.contains("3 轮"))
        XCTAssertTrue(html.contains("回答 commercial/Claude-Opus-4.7"))
        XCTAssertTrue(html.contains("工具 qwen3.7-max"))
        XCTAssertTrue(html.contains("工具调用临时切到可靠模型"))
    }

    func testMetaFooterOmitsSingleRound() {
        // llm_rounds == 1 没有展示意义 → 不输出「N 轮」
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "m", elapsedMs: 1200, llmRounds: 1, sourcesUsed: [], toolsUsed: []
        )
        XCTAssertTrue(html.contains("1.2s"))
        XCTAssertFalse(html.contains("轮"))
    }

    func testMetaFooterRendersSourcesAsCollapsibleDetails() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil, elapsedMs: nil, llmRounds: nil,
            sourcesUsed: ["系统知识库", "Garmin 数据"], toolsUsed: []
        )
        XCTAssertTrue(html.contains("<details"))
        XCTAssertTrue(html.contains("引用 2 项数据"))
        XCTAssertTrue(html.contains("<li>系统知识库</li>"))
        XCTAssertTrue(html.contains("<li>Garmin 数据</li>"))
    }

    func testMetaFooterRendersToolChips() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil, elapsedMs: nil, llmRounds: nil,
            sourcesUsed: [], toolsUsed: ["health_query", "health_record"]
        )
        XCTAssertTrue(html.contains("调用 Skill"))
        XCTAssertTrue(html.contains("meta-chip"))
        XCTAssertTrue(html.contains(">health_query<"))
        XCTAssertTrue(html.contains(">health_record<"))
    }

    func testMetaFooterEmptyWhenNoMeta() {
        // 所有字段为空 → 不输出任何 footer(空字符串,JS 端不渲染)
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil, elapsedMs: nil, llmRounds: nil, sourcesUsed: [], toolsUsed: []
        )
        XCTAssertEqual(html, "")
    }

    func testImageGalleryRendersOnlySafeHTTPImages() {
        let html = ChatTranscriptHTML.imageGalleryHTML(urls: [
            "https://example.test/api/v1/upload/files/chat/dinner.jpg",
            "javascript:alert(1)",
            "file:///tmp/private.png",
            "ftp://example.test/private.png",
        ])

        XCTAssertTrue(html.contains("attachment-images"))
        XCTAssertTrue(html.contains("<img"))
        XCTAssertTrue(html.contains("src=\"https://example.test/api/v1/upload/files/chat/dinner.jpg\""))
        XCTAssertFalse(html.contains("javascript:"))
        XCTAssertFalse(html.contains("file:///"))
        XCTAssertFalse(html.contains("ftp://"))
    }

    func testMetaFooterOmitsEmptySourcesAndToolsBlocks() {
        // 有模型行,但 sources/tools 空 → 只出 meta-line,不出 details / meta-tools
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "m", elapsedMs: 1000, llmRounds: nil, sourcesUsed: [], toolsUsed: []
        )
        XCTAssertTrue(html.contains("meta-line"))
        XCTAssertFalse(html.contains("<details"))
        XCTAssertFalse(html.contains("meta-tools"))
    }

    func testMetaFooterEscapesXSSInModelSourcesTools() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "<img src=x onerror=alert(1)>",
            elapsedMs: 100,
            llmRounds: nil,
            sourcesUsed: ["<script>evil</script>"],
            toolsUsed: ["</span><b>x"]
        )
        // 任何注入内容都被转义,无真标签生成
        XCTAssertFalse(html.contains("<img"))
        XCTAssertFalse(html.contains("<script>evil"))
        XCTAssertTrue(html.contains("&lt;img"))
        XCTAssertTrue(html.contains("&lt;script&gt;evil"))
        XCTAssertTrue(html.contains("&lt;/span&gt;&lt;b&gt;x"))
    }

    func testRenderedMessageJSONIncludesFooterField() {
        let footer = ChatTranscriptHTML.metaFooterHTML(
            model: "m", elapsedMs: 2000, llmRounds: nil, sourcesUsed: ["kb"], toolsUsed: []
        )
        let msg = ChatTranscriptHTML.RenderedMessage(
            id: "x", role: "assistant", bodyHTML: "<p>hi</p>",
            isStreaming: false, showCopy: true, footerHTML: footer
        )
        let json = msg.jsonObject
        XCTAssertTrue(json.contains("\"footer\":"))
        // footer HTML 经 jsString 编码注入(< 被编码为 <)
        XCTAssertTrue(json.contains("\\u003cdetails") || json.contains("\\u003cdiv"))
        // 整条信封仍是合法 JSON
        let parsed = try? JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any]
        XCTAssertNotNil(parsed ?? nil)
        XCTAssertNotNil((parsed ?? [:])["footer"])
    }

    func testRenderedMessageFooterDefaultsEmpty() {
        let msg = ChatTranscriptHTML.RenderedMessage(
            id: "x", role: "user", bodyHTML: "<p>hi</p>", isStreaming: false, showCopy: false
        )
        XCTAssertEqual(msg.footerHTML, "")
        XCTAssertTrue(msg.jsonObject.contains("\"footer\":\"\""))
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
