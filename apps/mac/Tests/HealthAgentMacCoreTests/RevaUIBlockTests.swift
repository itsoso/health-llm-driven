import Foundation
import XCTest
@testable import HealthAgentMacCore

/// GenUI 契约 v0(P2 Mac):```reva-ui 围栏抽取 + 占位 HTML + renderMessageBody 集成。
final class RevaUIBlockTests: XCTestCase {

    private let sampleJSON = """
    {"v":1,"component":"line_chart","title":"最近半年 HRV 趋势","unit":"ms",\
    "x":["1月","2月","3月"],"series":[{"name":"日均HRV","points":[63,59,61]}],\
    "source":"garmin","data_note":"基于 90 天真实数据"}
    """

    // MARK: - split

    func testSplitExtractsClosedRevaUIBlock() {
        let md = "前面的叙事。\n\n```reva-ui\n\(sampleJSON)\n```\n\n后面的话。"
        let segments = RevaUIBlock.split(from: md)
        // 期望: markdown(前) / revaUI / markdown(后)
        let revaSegments = segments.compactMap { seg -> String? in
            if case .revaUI(let json) = seg { return json } else { return nil }
        }
        XCTAssertEqual(revaSegments.count, 1)
        XCTAssertEqual(revaSegments[0], sampleJSON)
        // 前后叙事各保留一段
        let mdSegments = segments.compactMap { seg -> String? in
            if case .markdown(let t) = seg { return t } else { return nil }
        }
        XCTAssertTrue(mdSegments.contains { $0.contains("前面的叙事") })
        XCTAssertTrue(mdSegments.contains { $0.contains("后面的话") })
    }

    func testSplitNoBlockReturnsSingleMarkdown() {
        let md = "纯文本回答,没有任何图表。\n第二行。"
        let segments = RevaUIBlock.split(from: md)
        XCTAssertEqual(segments.count, 1)
        if case .markdown(let t) = segments[0] {
            XCTAssertEqual(t, md)
        } else {
            XCTFail("expected single markdown segment")
        }
    }

    func testSplitUnclosedFenceTreatedAsMarkdown() {
        // 流式 partial:open 围栏到了但 close 还没到 → 绝不当 revaUI 抽出。
        let md = "开始\n\n```reva-ui\n{\"v\":1,\"component\":\"line_chart\""
        let segments = RevaUIBlock.split(from: md)
        XCTAssertFalse(segments.contains { if case .revaUI = $0 { return true } else { return false } })
        // 原文逐字保留(不丢)
        let joined = segments.compactMap { seg -> String? in
            if case .markdown(let t) = seg { return t } else { return nil }
        }.joined(separator: "\n")
        XCTAssertTrue(joined.contains("```reva-ui"))
        XCTAssertTrue(joined.contains("line_chart"))
    }

    func testSplitIgnoresOtherFenceLanguages() {
        let md = "```json\n{\"a\":1}\n```"
        let segments = RevaUIBlock.split(from: md)
        XCTAssertFalse(segments.contains { if case .revaUI = $0 { return true } else { return false } })
    }

    func testSplitTwoRevaUIBlocks() {
        let md = "```reva-ui\nA\n```\n中间\n```reva-ui\nB\n```"
        let segments = RevaUIBlock.split(from: md)
        let reva = segments.compactMap { seg -> String? in
            if case .revaUI(let json) = seg { return json } else { return nil }
        }
        XCTAssertEqual(reva, ["A", "B"])
    }

    // MARK: - placeholder + renderMessageBody integration

    func testRenderMessageBodyEmitsRevaUIPlaceholderWithBase64() {
        let md = "看趋势:\n\n```reva-ui\n\(sampleJSON)\n```"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        XCTAssertTrue(html.contains("class=\"reva-ui-chart\""))
        XCTAssertTrue(html.contains("data-reva-ui=\""))
        // 占位里不该出现裸 JSON(应已 base64)
        XCTAssertFalse(html.contains("line_chart\""))
        // base64 解回应等于原 JSON
        let b64 = extractDataRevaUI(html)
        XCTAssertNotNil(b64)
        let decoded = Data(base64Encoded: b64!).flatMap { String(data: $0, encoding: .utf8) }
        XCTAssertEqual(decoded, sampleJSON)
        // 叙事正常渲染
        XCTAssertTrue(html.contains("看趋势"))
    }

    func testRenderMessageBodyBase64HasNoHTMLSpecialChars() {
        // base64 字母表无 <>&"' → 进 HTML 属性安全。
        let md = "```reva-ui\n\(sampleJSON)\n```"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        let b64 = extractDataRevaUI(html)!
        for ch in ["<", ">", "&", "\"", "'"] {
            XCTAssertFalse(b64.contains(ch), "base64 should not contain \(ch)")
        }
    }

    func testRenderMessageBodyPreservesEnrichedFieldsVerbatim() {
        // 富契约(role / kind:"latest" / disclaimer)的 JSON 必须原样进 base64,
        // 由 WebView JS 端解析渲染——Swift 占位层不得吞/改任何加性字段。
        let richJSON = """
        {"v":1,"component":"line_chart","title":"半年 HRV","unit":"ms",\
        "y_hint":{"min":30,"max":90},"x":["2026-06-29","2026-06-30"],\
        "series":[{"name":"每日","role":"raw","points":[61,null]},\
        {"name":"7日均","role":"avg_7d","points":[60,62]},\
        {"name":"Apple Watch","role":"device","points":[null,59]}],\
        "annotations":[{"x":"2026-06-30","kind":"latest","label":"2026-06-30"}],\
        "source":"garmin","data_note":"基于 178 天真实数据","disclaimer":"仅供参考,非医疗诊断"}
        """
        let md = "趋势如下:\n\n```reva-ui\n\(richJSON)\n```"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        XCTAssertTrue(html.contains("class=\"reva-ui-chart\""))
        let b64 = extractDataRevaUI(html)
        XCTAssertNotNil(b64)
        let decoded = Data(base64Encoded: b64!).flatMap { String(data: $0, encoding: .utf8) }
        XCTAssertEqual(decoded, richJSON, "enriched JSON must round-trip verbatim through the placeholder")
        // 关键加性字段都在解码结果里(防 Swift 侧意外 schema 收窄)。
        XCTAssertTrue(decoded!.contains("\"role\":\"avg_7d\""))
        XCTAssertTrue(decoded!.contains("\"kind\":\"latest\""))
        XCTAssertTrue(decoded!.contains("\"disclaimer\""))
    }

    func testRenderMessageBodyNoBlockUnchangedBehavior() {
        // 无 reva-ui 块时与旧路径一致(段落渲染)。
        let md = "# 标题\n\n正文。"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        XCTAssertTrue(html.contains("<h1>标题</h1>"))
        XCTAssertTrue(html.contains("<p>正文。</p>"))
        XCTAssertFalse(html.contains("reva-ui-chart"))
    }

    // 提取占位 div 的 data-reva-ui 属性值。
    private func extractDataRevaUI(_ html: String) -> String? {
        guard let range = html.range(of: "data-reva-ui=\"") else { return nil }
        let rest = html[range.upperBound...]
        guard let end = rest.firstIndex(of: "\"") else { return nil }
        return String(rest[..<end])
    }
}
