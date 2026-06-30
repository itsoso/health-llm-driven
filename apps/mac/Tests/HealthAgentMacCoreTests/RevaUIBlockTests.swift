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

    // MARK: - 真实后端 payload 端到端回归(首个真正到达 live WKWebView 的 reva-ui 块)

    /// 后端实际下发的 HRV 趋势消息:intro 行(含括号/中文/分隔点)+ 空行 + ```reva-ui```
    /// 围栏,内含 4 序列(role: raw/device/avg_7d/avg_30d)、null 密集、latest 注解。
    /// 复刻 prod 上首次真正进入 live WebView 的内容,断言占位 div + 非空 base64 被抽出。
    func testRenderMessageBodyExtractsRealBackendHRVPayload() {
        let realJSON = "{\"v\":1,\"component\":\"line_chart\",\"title\":\"HRV 趋势\",\"unit\":\"ms\","
            + "\"x\":[\"01-01\",\"03-15\",\"06-30\"],"
            + "\"series\":[{\"name\":\"Garmin 夜间 HRV\",\"role\":\"raw\",\"points\":[51.0,53.2,null]},"
            + "{\"name\":\"Apple Watch HRV\",\"role\":\"device\",\"points\":[null,null,58.4]},"
            + "{\"name\":\"7日滚动均值\",\"role\":\"avg_7d\",\"points\":[50.1,52.0,57.3]},"
            + "{\"name\":\"30日滚动均值\",\"role\":\"avg_30d\",\"points\":[49.0,51.5,55.0]}],"
            + "\"annotations\":[{\"x\":\"06-30\",\"label\":\"最新 58.4 ms · Apple Watch\",\"kind\":\"latest\"}],"
            + "\"source\":\"garmin\",\"data_note\":\"基于 178 天真实数据 · 每日 · Garmin 169d + Apple Watch 24d\"}"
        let intro = "近半年HRV趋势（数据来自你的设备，基于 178 天真实数据 · 每日 · Garmin 169d + Apple Watch 24d）："
        // 后端真实拼接形态:{intro}\n\n```reva-ui\n{json}\n``` (render_reva_ui_block)
        let md = intro + "\n\n```reva-ui\n" + realJSON + "\n```"

        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        XCTAssertTrue(html.contains("class=\"reva-ui-chart\""), "real backend payload must emit a placeholder div")
        let b64 = extractDataRevaUI(html)
        XCTAssertNotNil(b64, "data-reva-ui must be present")
        XCTAssertFalse(b64!.isEmpty, "data-reva-ui base64 must be non-empty")
        let decoded = Data(base64Encoded: b64!).flatMap { String(data: $0, encoding: .utf8) }
        XCTAssertEqual(decoded, realJSON, "raw JSON must round-trip verbatim through placeholder")
        // 占位里不该有裸 JSON 字段名(应已 base64)。
        XCTAssertFalse(html.contains("line_chart\""))
        // intro 叙事仍正常渲染为普通 markdown,不被吞。
        XCTAssertTrue(html.contains("近半年HRV趋势"))
    }

    // MARK: - displayText → renderMessageBody 端到端(真实数据路径回归)

    /// 线上首个 reva-ui 块渲染成裸文本的根因:`renderedTranscript()` 喂给 `renderMessageBody`
    /// 的不是原始 content,而是 `displayContent → AgentStructuredCommandParser.displayText` 清洗后的
    /// 文本。旧 displayText 的逐行清洗会**删掉闭合 ``` 行**(它在 legacy 围栏剥离的 filter 里),
    /// 于是 split 把围栏判为「未闭合」退回纯文本,占位永不生成。
    /// 这条测试走真实路径(displayText → renderMessageBody),确保闭合围栏被保留、占位被抽出。
    func testDisplayTextThenRenderMessageBodyKeepsRevaUIFence() {
        let intro = "近半年HRV趋势（数据来自你的设备，基于 178 天真实数据 · 每日 · Garmin 169d + Apple Watch 24d）："
        let md = intro + "\n\n```reva-ui\n" + sampleJSON + "\n```"

        // 关键:模拟 renderedTranscript 的真实链路——先过 displayText,再渲染。
        let displayed = AgentStructuredCommandParser.displayText(for: md)
        // 闭合围栏必须仍在(旧实现会把它删掉)。
        XCTAssertTrue(displayed.contains("```reva-ui"), "opening fence preserved")
        let trailingFence = displayed.hasSuffix("```") || displayed.contains("\n```\n") || displayed.contains("\n```")
        XCTAssertTrue(trailingFence, "closing fence must survive displayText cleanup")

        let html = ChatTranscriptHTML.renderMessageBody(markdown: displayed)
        XCTAssertTrue(html.contains("class=\"reva-ui-chart\""),
                      "after displayText the fence must still yield a chart placeholder, not raw text")
        let b64 = extractDataRevaUI(html)
        XCTAssertNotNil(b64)
        let decoded = Data(base64Encoded: b64!).flatMap { String(data: $0, encoding: .utf8) }
        XCTAssertEqual(decoded, sampleJSON, "raw JSON must round-trip verbatim end-to-end")
        // intro 叙事仍在(普通文本段照常清洗渲染)。
        XCTAssertTrue(html.contains("近半年HRV趋势"))
        // 绝不退回成裸文本(出现裸字段名即说明退回了 markdown 文本路径)。
        XCTAssertFalse(html.contains("line_chart\""))
    }

    /// displayText 仍须正常清洗普通段:legacy 裸 ``` / ```json 围栏标记照常剥、空行照常合并。
    func testDisplayTextStillStripsLegacyFencesWithoutRevaUI() {
        let md = "前言\n\n```json\n{\"name\":\"x\"}\n```\n\n结论"
        let displayed = AgentStructuredCommandParser.displayText(for: md)
        // 无 reva-ui 时行为不变:裸 ```json / ``` 标记被剥。
        XCTAssertFalse(displayed.contains("```json"))
        XCTAssertFalse(displayed.contains("```"))
        XCTAssertTrue(displayed.contains("前言"))
        XCTAssertTrue(displayed.contains("结论"))
    }

    // 提取占位 div 的 data-reva-ui 属性值。
    private func extractDataRevaUI(_ html: String) -> String? {
        guard let range = html.range(of: "data-reva-ui=\"") else { return nil }
        let rest = html[range.upperBound...]
        guard let end = rest.firstIndex(of: "\"") else { return nil }
        return String(rest[..<end])
    }
}
