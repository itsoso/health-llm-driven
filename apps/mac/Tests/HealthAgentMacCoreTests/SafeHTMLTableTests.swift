import XCTest
@testable import HealthAgentMacCore

final class SafeHTMLTableTests: XCTestCase {
    private let simple = "<table><tr><td>7</td></tr></table>"

    func testTableTextNeverBecomesLegacyProposedAction() {
        let command = "{\"name\":\"health_record\",\"parameters\":{\"type\":\"water\",\"amount\":\"200\"}}"
        XCTAssertFalse(AgentStructuredCommandParser.proposedActions(in: command, messageID: UUID()).isEmpty)
        for source in [
            "<table><tr><td>\(command)</td></tr></table>",
            "```html\n<table><tr><td>\(command)</td></tr></table>\n```",
            "```html\n<table><tr><td onclick='x'>\(command)</td></tr></table>\n```",
        ] {
            XCTAssertTrue(AgentStructuredCommandParser.proposedActions(in: source, messageID: UUID()).isEmpty)
            XCTAssertEqual(AgentStructuredCommandParser.displayText(for: source), source)
        }
    }

    @MainActor
    func testHTMLBearingMessageKeepsSeparateBodyProtocolFencesLiteral() {
        let protocolBlocks = [
            "```reva-ui\n{\"type\":\"diet_draft\",\"v\":1,\"actions\":[{\"type\":\"route.open\",\"route\":\"/diet\"}]}\n```",
            "```menu_share\n{\"title\":\"合成菜单\",\"items\":[\"示例\"]}\n```",
            "🍽 ```menu_share\n{\"title\":\"合成菜单\",\"items\":[\"示例\"]}\n```",
        ]
        for block in protocolBlocks {
            for source in [simple + "\n\n" + block, block + "\n\n" + simple] {
                let message = AgentChatMessage(role: .assistant, content: source)
                let model = AgentChatViewModel()
                model.messages = [message]
                let html = model.renderedTranscript()[0].bodyHTML
                XCTAssertTrue(html.contains("<table>"))
                XCTAssertFalse(html.contains("reva-ui-chart"))
                XCTAssertFalse(html.contains("data-reva-ui="))
                XCTAssertTrue(html.contains("合成菜单") || html.contains("&quot;type&quot;:&quot;diet_draft&quot;"))
                XCTAssertEqual(model.displayContent(for: message), source)
                XCTAssertEqual(model.copyableText(messageID: message.id.uuidString), source)
                XCTAssertTrue(AgentStructuredCommandParser.proposedActions(in: source, messageID: message.id).isEmpty)
            }
        }
    }

    @MainActor
    func testHTMLBodyDoesNotDisableIndependentServerIssuedCard() {
        let action = AgentDynamicCardActionDescriptor(
            id: "synthetic-server-card", label: "确认记录", action: "diet_record.create", endpoint: "/diet/records",
            payload: .object(["record": .object(["photo_draft_token": .string("synthetic-token")])]),
            style: "primary", requiresManualConfirm: true, capabilityID: "diet_draft.v1",
            requiredReceipt: true, autonomyTier: "manual_confirm"
        )
        let model = AgentChatViewModel()
        model.messages = [.init(role: .assistant, content: simple, cardType: "diet_draft",
                                cardData: .object(["food_items": .string("合成餐")]), cardActions: [action])]
        let html = model.renderedTranscript()[0].bodyHTML
        XCTAssertTrue(html.contains("<table>"))
        XCTAssertTrue(html.contains("xiaoba-diet-confirm://synthetic-server-card"))
    }

    func testCompletedHTMLTableShowsControlledPreviewAndOriginalSource() {
        let source = "```html\n<table><tr><th>A</th><th>B</th></tr><tr><td></td><td>x | y</td></tr></table>\n```"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: source)
        XCTAssertTrue(html.contains("<table>"))
        XCTAssertTrue(html.contains("<td></td>"))
        XCTAssertTrue(html.contains("<td>x | y</td>"))
        XCTAssertTrue(html.contains("<summary>查看 HTML 源码</summary>"))
        XCTAssertTrue(html.contains("<pre>" + ChatTranscriptHTML.escape(source) + "</pre>"))
    }

    func testPresentationAttributesAndWrappersAreDiscardedNotExecuted() throws {
        let source = "<TABLE style=\"background:url(https://invalid.test)\" border='1' cellpadding=2 cellspacing=0 width='100%' height='10' align='left' valign='top' class='confirm'><caption>本周 &nbsp; 睡眠</caption><thead><tr><th>日期</th><th>时长</th></tr></thead><tbody><tr><td><b>**7**</b> 小时</td><td><span class='x'> A <i>B</i> C </span><br/>D</td></tr></tbody><tfoot><tr><td>均值</td><td>7</td></tr></tfoot></TABLE>"
        let table = try XCTUnwrap(SafeHTMLTable.parse(source))
        XCTAssertEqual(table.caption, "本周 \u{00a0} 睡眠")
        XCTAssertEqual(table.rows[1].map(\.text), ["**7** 小时", "A B C\nD"])
        XCTAssertTrue(table.rows[0].allSatisfy(\.header))
        let html = ChatTranscriptHTML.renderMessageBody(markdown: source)
        let preview = String(html.components(separatedBy: "<details>")[0])
        XCTAssertFalse(preview.contains("https://"))
        XCTAssertFalse(preview.contains("class="))
        XCTAssertFalse(preview.contains("<strong>"))
        XCTAssertTrue(preview.contains("**7** 小时"))
        XCTAssertTrue(preview.contains("overflow-x:auto"))
    }

    func testEntitiesDecodeOnceAndRemainEscapedText() throws {
        let source = "<table><tr><td>&amp;lt;img&amp;gt; &unknown; &#0; &#xD800; &#1114112; &lt;script&gt; &#x65F6; &#128512; &quot; &apos;</td></tr></table>"
        let text = try XCTUnwrap(SafeHTMLTable.parse(source)).rows[0][0].text
        XCTAssertEqual(text, "&lt;img&gt; &unknown; &#0; &#xD800; &#1114112; <script> 时 😀 \" '")
        let html = ChatTranscriptHTML.renderMessageBody(markdown: source)
        XCTAssertFalse(html.contains("<script>"))
        XCTAssertFalse(html.contains("<img"))
        XCTAssertTrue(html.contains("&lt;script&gt;"))
        XCTAssertTrue(html.contains("&amp;lt;img&amp;gt;"))
    }

    func testUnsupportedMarkupAndAttributesFailClosedWithReadableSource() {
        let bad = [
            "<table onclick='x()'><tr><td>7</td></tr></table>",
            "<table><tr><td colspan='2'>7</td></tr></table>",
            "<table><tr><td rowspan='2'>7</td></tr></table>",
            "<table><tr><td data-action='confirm'>7</td></tr></table>",
            "<table id='x'><tr><td>7</td></tr></table>",
            "<table><tr><td><img src='https://invalid.test/a'></td></tr></table>",
            "<table><tr><td><script>window.webkit.messageHandlers.copy.postMessage('x')</script></td></tr></table>",
            "<table><tr><td><a href='javascript:alert(1)'>7</a></td></tr></table>",
            "<table><tr><td><iframe></iframe></td></tr></table>",
            "<table><tr><td><object></object></td></tr></table>",
            "<table><tr><td><form></form></td></tr></table>",
            "<table><tr><td><svg></svg></td></tr></table>",
            "<table><tr><td><table><tr><td>7</td></tr></table></td></tr></table>",
            "<table><tr><td>7</tr></table>",
            "<table><tr><td>7</td></tr><tr><td>8</td><td>9</td></tr></table>",
            "<table>lost text<tr><td>7</td></tr></table>",
            "<table><tr><td>7</td></tr></table><script>x()</script>",
            "before<table><tr><td>7</td></tr></table>",
            "<table><tr><td>7</td></tr></table>after",
            "<table><tr><td>x</td></tr></table><!-- comment -->",
            "<!DOCTYPE table><table><tr><td>x</td></tr></table>",
            "<table><tr><td style='a' style='b'>7</td></tr></table>",
            "<table><tr><td/ ></tr></table>",
        ]
        for source in bad {
            XCTAssertNil(SafeHTMLTable.parse(source), source)
            let fenced = "```html\n\(source)\n```"
            let rendered = ChatTranscriptHTML.renderMessageBody(markdown: fenced)
            XCTAssertFalse(rendered.contains("<table>"), source)
            XCTAssertFalse(rendered.contains("<script>"), source)
            XCTAssertFalse(rendered.contains("<img"), source)
            XCTAssertTrue(rendered.contains(ChatTranscriptHTML.escape(fenced)), source)
        }
    }

    func testFencesSupportCaseTildesLongClosingAndPreserveAllMixedProse() {
        for (open, close) in [("```html", "```"), ("~~~HTM", "~~~~"), ("````HTML", "`````"), ("   ```html", "   ```")] {
            let source = "前文\n\n\(open)\n\(simple)\n\(close)\n后文\n\(simple)\n"
            let segments = SafeHTMLTable.segments(from: source)
            XCTAssertEqual(original(segments), source)
            XCTAssertEqual(previewCount(segments), 2)
            let html = ChatTranscriptHTML.renderMessageBody(markdown: source)
            XCTAssertTrue(html.hasPrefix("<p>前文</p>"))
            XCTAssertTrue(html.contains("<p>后文</p>"))
        }
    }

    func testOtherCodeAndIncompleteOrNonStandaloneTablesNeverPreview() {
        for source in [
            "```text\n\(simple)\n```",
            "````md\n```html\n\(simple)\n```\n````",
            "```html\n\(simple)",
            "````html\n\(simple)\n```",
            "~~~html\n\(simple)\n```",
            "```html extra\n\(simple)\n```",
            "前文 \(simple)",
            "    \(simple)",
            "<table><tr><td>unfinished",
            "```html\n前文\n\(simple)\n```",
        ] {
            let segments = SafeHTMLTable.segments(from: source)
            XCTAssertEqual(previewCount(segments), 0, source)
            XCTAssertEqual(original(segments), source)
            XCTAssertFalse(ChatTranscriptHTML.renderMessageBody(markdown: source).contains("<table>"), source)
        }
    }

    @MainActor
    func testDisplayCleanupCannotPromoteCodeOrMutateRejectedHTMLSource() {
        let sources = [
            "    \(simple)",
            "```text\n\(simple)\n```",
            "```html\n<table><tr><td data-action='x'>[claim:literal] **7**</td></tr></table>\n```",
            "```html\n<table><tr><td>[claim:literal]\n```reva-ui\n{\"v\":1}\n</td></tr></table>\n```",
            "````text\n```reva-ui\n{\"v\":1}\n```\n````",
        ]
        for source in sources {
            let message = AgentChatMessage(role: .assistant, content: source)
            let model = AgentChatViewModel()
            model.messages = [message]
            XCTAssertEqual(model.displayContent(for: message), source)
            XCTAssertEqual(model.copyableText(messageID: message.id.uuidString), source)
            let html = model.renderedTranscript()[0].bodyHTML
            XCTAssertFalse(html.contains("reva-ui-chart"))
            if source != sources[3] { XCTAssertFalse(html.contains("<table>")) }
        }
    }

    func testAllResourceLimitsRejectWholeTableWithoutTruncation() {
        for source in [
            "<table>" + String(repeating: "<tr><td>x</td></tr>", count: 101) + "</table>",
            "<table><tr>" + String(repeating: "<td>x</td>", count: 21) + "</tr></table>",
            "<table><tr><td>" + String(repeating: "x", count: 2001) + "</td></tr></table>",
            String(repeating: " ", count: 32_001) + simple,
        ] {
            XCTAssertNil(SafeHTMLTable.parse(source))
            let fenced = "```html\n\(source)\n```"
            XCTAssertEqual(previewCount(SafeHTMLTable.segments(from: fenced)), 0)
            XCTAssertTrue(ChatTranscriptHTML.renderMessageBody(markdown: fenced).contains(ChatTranscriptHTML.escape(fenced)))
        }
        XCTAssertNotNil(SafeHTMLTable.parse("<table>" + String(repeating: "<tr><td>x</td></tr>", count: 100) + "</table>"))
        XCTAssertNotNil(SafeHTMLTable.parse("<table><tr>" + String(repeating: "<td>x</td>", count: 20) + "</tr></table>"))
        XCTAssertNotNil(SafeHTMLTable.parse("<table><tr><td>" + String(repeating: "x", count: 2000) + "</td></tr></table>"))
    }

    func testUnicodeDepthAndWhitespaceBoundaries() throws {
        XCTAssertNil(SafeHTMLTable.parse("<table><tr><td>" + String(repeating: "e\u{301}", count: 1001) + "</td></tr></table>"))
        XCTAssertNil(SafeHTMLTable.parse("<table><tr><td>" + String(repeating: "<b>", count: 33) + "x" + String(repeating: "</b>", count: 33) + "</td></tr></table>"))
        XCTAssertNil(SafeHTMLTable.parse("<table>&nbsp;<tr><td>x</td></tr></table>"))
        XCTAssertNil(SafeHTMLTable.parse("<table>\u{00a0}<tr><td>x</td></tr></table>"))
        let table = try XCTUnwrap(SafeHTMLTable.parse("<table><caption> \n 合成 &nbsp; </caption><tr><td>\n  A <span> B </span> C\n D<br> E\n </td><td>&am<span>p;</span></td></tr></table>"))
        XCTAssertEqual(table.caption, "合成 \u{00a0}")
        XCTAssertEqual(table.rows[0].map(\.text), ["A B C D\nE", "&amp;"])
        let longAttribute = String(repeating: "e\u{301}", count: 16_000)
        XCTAssertNil(SafeHTMLTable.parse("<table style='\(longAttribute)'><tr><td>x</td></tr></table>"))
    }

    @MainActor
    func testRealTranscriptKeepsUserAndStreamingLiteralThenShowsCompletedPreview() {
        let source = "```html\n\(simple)\n```"
        let user = AgentChatMessage(role: .user, content: source)
        let assistant = AgentChatMessage(role: .assistant, content: source)
        let model = AgentChatViewModel()
        model.messages = [user, assistant]
        model.isStreaming = true
        let streaming = model.renderedTranscript()
        XCTAssertFalse(streaming[0].bodyHTML.contains("<table>"))
        XCTAssertFalse(streaming[1].bodyHTML.contains("<table>"))
        model.isStreaming = false
        let done = model.renderedTranscript()
        XCTAssertFalse(done[0].bodyHTML.contains("<table>"))
        XCTAssertTrue(done[1].bodyHTML.contains("<table>"))
        XCTAssertEqual(model.copyableText(messageID: assistant.id.uuidString), source)
        XCTAssertEqual(model.messages[1].content, source)
        XCTAssertEqual(done, model.renderedTranscript())
    }

    private func previewCount(_ segments: [SafeHTMLTable.Segment]) -> Int {
        segments.filter { if case .table = $0 { return true }; return false }.count
    }
    private func original(_ segments: [SafeHTMLTable.Segment]) -> String {
        segments.map { segment in
            switch segment {
            case .markdown(let source), .source(let source), .code(let source), .table(_, let source): return source
            }
        }.joined()
    }
}
