import Foundation
import XCTest
@testable import HealthAgentMacCore

/// rank1 GenUI-first(Mac 半):`metric_table` reva-ui 块的 Swift 侧契约。
///
/// 架构提醒:实际的 `<table>` 由 chat-transcript.html 的 `buildRevaMetricTableHTML` 在 WebView 里
/// 运行时自绘(离线 JS,暖色调 CSS —— 见该文件 + 附带的合成截图)。Swift 侧的职责只有一个:
/// 把围栏内的原始 JSON **原封不动**切出来、base64 进占位 div、交给 JS 路由。所以这里的
/// 「rows verbatim」断言打在 base64 解码后的载荷上(证明 markdown 解析器没碰它),
/// 「rendered table」的观感由 WebView 截图佐证,不在纯 Swift 单测范围内。
final class RevaUIMetricTableTests: XCTestCase {

    /// 契约样例:type=metric_table + 3 列 + 3 行 + footnote。
    private let tableJSON = """
    {"type":"metric_table","v":1,"title":"三日关键指标","columns":[{"key":"date","label":"日期"},{"key":"rhr","label":"静息心率"},{"key":"hrv","label":"HRV"}],"rows":[{"date":"07-11","rhr":"58","hrv":"41"},{"date":"07-12","rhr":"55","hrv":"46"},{"date":"07-13","rhr":"54","hrv":"49"}],"footnote":"数据来自 Garmin，非诊断。"}
    """

    /// 从 renderMessageBody 输出里取出第一个 reva-ui 占位的 base64 载荷并解码回原文。
    private func decodeRevaUIPayload(_ html: String) throws -> String {
        let marker = "data-reva-ui=\""
        let start = try XCTUnwrap(html.range(of: marker), "占位 div 应带 data-reva-ui 属性")
        let rest = html[start.upperBound...]
        let end = try XCTUnwrap(rest.range(of: "\""), "data-reva-ui 属性应闭合")
        let b64 = String(rest[..<end.lowerBound])
        let data = try XCTUnwrap(Data(base64Encoded: b64), "data-reva-ui 应为合法 base64")
        return try XCTUnwrap(String(data: data, encoding: .utf8), "base64 应解码为 UTF-8")
    }

    // MARK: - metric_table 围栏 → 占位 + 从 markdown 剥离 + rows 逐字保真

    func testMetricTableFenceStripsFromMarkdownAndCarriesRowsVerbatim() throws {
        let md = "先说结论：恢复在改善。\n\n```reva-ui\n\(tableJSON)\n```\n\n下一步：保持睡眠节律。"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)

        // 1) 产出 reva-ui 占位 div(JS 侧据此自绘表格)。
        XCTAssertTrue(html.contains("class=\"reva-ui-chart\""), "应产出 reva-ui 占位: \(html)")
        XCTAssertTrue(html.contains("data-reva-ui=\""))

        // 2) 围栏从 markdown 流里剥离:既无 ```reva-ui 标记残留,也没有把 JSON 当可见文本泄漏
        //    (只以 base64 进属性),更没被 `|` 之类误判成 markdown 表格。
        XCTAssertFalse(html.contains("```reva-ui"), "开围栏标记应被吞掉")
        XCTAssertFalse(html.contains("\"type\":\"metric_table\""), "原始 JSON 不应作为可见文本泄漏")

        // 3) 围栏外的叙事照常渲染。
        XCTAssertTrue(html.contains("先说结论"))
        XCTAssertTrue(html.contains("下一步"))

        // 4) rows 逐字保真:解码 base64 应与原始围栏内容完全一致(markdown 解析器零改动)。
        let decoded = try decodeRevaUIPayload(html)
        XCTAssertEqual(decoded, tableJSON, "载荷必须与原始 JSON 逐字节一致")
        XCTAssertTrue(decoded.contains("\"date\":\"07-11\""))
        XCTAssertTrue(decoded.contains("\"rhr\":\"58\""))
        XCTAssertTrue(decoded.contains("静息心率"))
        XCTAssertTrue(decoded.contains("数据来自 Garmin"))
    }

    // MARK: - 未知 reva-ui type → 优雅忽略(旧端/新块都不炸)

    func testUnknownRevaUITypeIsIgnoredGracefully() throws {
        let unknownJSON = """
        {"type":"totally_unknown_widget_v99","v":1,"payload":{"foo":"bar","n":3}}
        """
        let md = "一段叙事。\n\n```reva-ui\n\(unknownJSON)\n```\n\n收尾一句。"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)

        // Swift 侧类型无关:未知 type 同样切出占位,交给 JS(JS 无匹配渲染器 → 降级代码块)。
        // 不崩、不把 JSON 当 markdown 乱解、围栏外叙事完好。
        XCTAssertTrue(html.contains("class=\"reva-ui-chart\""))
        XCTAssertFalse(html.contains("```reva-ui"))
        XCTAssertTrue(html.contains("一段叙事"))
        XCTAssertTrue(html.contains("收尾一句"))

        // 未知块的原文照样原封不动进载荷(不吞不改)。
        let decoded = try decodeRevaUIPayload(html)
        XCTAssertEqual(decoded, unknownJSON)
    }

    // MARK: - cap 头暗开关:flag=false 时逐字节不变

    func testClientCapsHeaderByteIdenticalWhenTableCapDisabled() {
        // 纯函数 false 分支 == 历史头值(逐字节)。
        XCTAssertEqual(
            AgentStreamClient.clientCapsHeaderValue(tableCapEnabled: false),
            "genui-v1, genui-components-v1"
        )
        // eval gate 已通过，当前构建应声明 table capability。
        XCTAssertTrue(
            RevaUIFeatureFlags.tableCapEnabled,
            "metric_table eval gate 通过后必须声明 capability"
        )
        XCTAssertEqual(
            AgentStreamClient.clientCapsHeaderValue,
            "genui-v1, genui-components-v1, genui-table-v1"
        )
    }

    func testClientCapsHeaderDeclaresTableCapWhenEnabled() {
        // 翻开后追加 genui-table-v1(且既有 cap 一个不丢)。
        XCTAssertEqual(
            AgentStreamClient.clientCapsHeaderValue(tableCapEnabled: true),
            "genui-v1, genui-components-v1, genui-table-v1"
        )
    }
}
