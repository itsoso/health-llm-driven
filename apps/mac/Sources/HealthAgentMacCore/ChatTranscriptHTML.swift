import Foundation

/// Pure, testable HTML generation for the WKWebView-backed chat transcript.
///
/// 架构选择(2026-06-12,第 9 轮 · 结构性根治):助手页对话区从 SwiftUI 改为 WKWebView 渲染。
/// 8 轮地鼠证明 SwiftUI 在弹性 frame 嵌套里对流式增长的富文本做宽度协商 → 指数级 sizeThatFits。
/// 浏览器引擎的布局是线性增量的,根除整类问题。
///
/// 为什么 Swift 侧 blocks→HTML(而非打包 marked.js):
///  1. 复用现成的 `MarkdownRenderSupport.blocks(from:)` 解析器(标题/列表/表格/段落/分割线都有,
///     且已被 SwiftUI 渲染路径验证过)—— 零第三方 JS,不必 pin 版本 / 审 license / 进 bundle / 防网络加载。
///  2. 表格在 HTML 里恢复为真 `<table>` 网格(浏览器 CSS 排版,不再像 SwiftUI 单 Text 那样降级成「·」分隔)。
///  3. JS 端只剩极薄的 append/setMessages/scroll/copy 桥接,攻击面小、易审计。
///
/// 安全(AGENTS.md 硬约束):所有进入 HTML 的消息内容**先经 `escape(_:)` 转义**(防 XSS);
/// inline markdown(**bold** / *italic* / `code`)在转义之后才做受控的标签替换,顺序不可颠倒。
public enum ChatTranscriptHTML {

    // MARK: - HTML escaping (XSS 防线)

    /// 把任意字符串转义为可安全嵌入 HTML 文本节点 / 属性的形式。
    /// 顺序关键:`&` 必须最先替换,否则会把后续插入的实体里的 `&` 二次转义。
    public static func escape(_ raw: String) -> String {
        var out = raw
        out = out.replacingOccurrences(of: "&", with: "&amp;")
        out = out.replacingOccurrences(of: "<", with: "&lt;")
        out = out.replacingOccurrences(of: ">", with: "&gt;")
        out = out.replacingOccurrences(of: "\"", with: "&quot;")
        out = out.replacingOccurrences(of: "'", with: "&#39;")
        return out
    }

    // MARK: - Inline markdown (转义之后才做,受控白名单)

    /// 对**已转义**的文本做受控的 inline markdown → HTML。
    /// 仅识别 `**bold**`、`*italic*`、`` `code` ``;不引入任何属性,不解析链接/图片(避免
    /// 注入 href/src 的攻击面)。裸 URL 不自动链接 —— 保持纯文本,外链交互留给 SwiftUI 层。
    static func inlineMarkdown(_ escaped: String) -> String {
        var s = escaped
        s = replacePaired(s, marker: "`", openTag: "<code>", closeTag: "</code>")
        s = replacePaired(s, marker: "**", openTag: "<strong>", closeTag: "</strong>")
        // bold 处理完后,任何残留 `**` 都是未闭合的字面量 —— 用占位符护住,避免被下面
        // 的单 `*`(italic)pass 当成两个标记切开(否则 `a **b` 会错变成 `a <em></em>b`)。
        let doubleStarPlaceholder = "\u{0001}DBLSTAR\u{0001}"
        s = s.replacingOccurrences(of: "**", with: doubleStarPlaceholder)
        s = replacePaired(s, marker: "*", openTag: "<em>", closeTag: "</em>")
        s = s.replacingOccurrences(of: doubleStarPlaceholder, with: "**")
        return s
    }

    /// 把成对出现的 marker 替换为标签;落单(未闭合)的 marker 原样保留,不破坏文本。
    /// `a **b** c` → parts = ["a ", "b", " c"];奇数下标段是「被包裹」内容。
    private static func replacePaired(_ input: String, marker: String, openTag: String, closeTag: String) -> String {
        let parts = input.components(separatedBy: marker)
        guard parts.count >= 3 else { return input }
        // 完整的对数 = (段数 - 1) / 2 向下取整;能配对的最后一个开标记下标。
        let lastPairedOpenIndex = ((parts.count - 1) / 2) * 2 - 1
        var result = parts[0]
        for i in 1..<parts.count {
            if i % 2 == 1 && i <= lastPairedOpenIndex {
                result += openTag + parts[i] + closeTag
            } else if i % 2 == 1 {
                // 落单的开标记:marker 原样还原
                result += marker + parts[i]
            } else {
                result += parts[i]
            }
        }
        return result
    }

    // MARK: - Blocks → HTML body

    /// 把单条消息的 markdown 内容渲染为 HTML 片段(气泡内层)。
    /// 复用 `MarkdownRenderSupport.blocks(from:)`,再逐块转义 + inline markdown + 包标签。
    public static func renderMessageBody(markdown: String) -> String {
        let src = markdown.isEmpty ? "" : markdown
        let blocks = MarkdownRenderSupport.blocks(from: src)
        if blocks.isEmpty {
            return "<p>\(inlineMarkdown(escape(MarkdownRenderSupport.readableFallback(src))))</p>"
        }

        var html = ""
        var pendingBullets: [String] = []
        var pendingNumbered: [String] = []
        var pendingTableRows: [[String]] = []

        func flushBullets() {
            guard !pendingBullets.isEmpty else { return }
            html += "<ul>" + pendingBullets.map { "<li>\($0)</li>" }.joined() + "</ul>"
            pendingBullets = []
        }
        func flushNumbered() {
            guard !pendingNumbered.isEmpty else { return }
            html += "<ol>" + pendingNumbered.map { "<li>\($0)</li>" }.joined() + "</ol>"
            pendingNumbered = []
        }
        func flushTable() {
            guard !pendingTableRows.isEmpty else { return }
            var t = "<table>"
            for (idx, row) in pendingTableRows.enumerated() {
                let tag = idx == 0 ? "th" : "td"
                t += "<tr>" + row.map { "<\(tag)>\($0)</\(tag)>" }.joined() + "</tr>"
            }
            t += "</table>"
            html += t
            pendingTableRows = []
        }
        func flushAll() {
            flushBullets()
            flushNumbered()
            flushTable()
        }

        for block in blocks {
            switch block {
            case .heading(let level, let text):
                flushAll()
                let clampedLevel = min(max(level, 1), 4)
                let inner = inlineMarkdown(escape(text))
                html += "<h\(clampedLevel)>\(inner)</h\(clampedLevel)>"
            case .paragraph(let text):
                flushAll()
                html += "<p>\(inlineMarkdown(escape(text)))</p>"
            case .bullet(let text):
                flushNumbered()
                flushTable()
                pendingBullets.append(inlineMarkdown(escape(text)))
            case .numbered(_, let text):
                flushBullets()
                flushTable()
                pendingNumbered.append(inlineMarkdown(escape(text)))
            case .tableRow(let columns):
                flushBullets()
                flushNumbered()
                pendingTableRows.append(columns.map { inlineMarkdown(escape($0)) })
            case .divider:
                flushAll()
                html += "<hr/>"
            }
        }
        flushAll()
        return html
    }

    // MARK: - Meta footer (模型 · 轮数 · 耗时 / 数据源 / Skill)

    /// 给一条助手消息生成 footer HTML 片段(模型/轮数/耗时一行 + 可折叠数据源 + Skill chips)。
    /// 所有动态文本走 `escape(_:)` 防 XSS。任一块缺数据则该块整体省略;全空返回 ""。
    /// 视觉调性对齐 mobile ChatBubble:低调灰、小字号、数据源用 `<details>` 折叠。
    public static func metaFooterHTML(
        model: String?,
        elapsedMs: Int?,
        llmRounds: Int?,
        sourcesUsed: [String],
        toolsUsed: [String]
    ) -> String {
        var sections: [String] = []

        // 第一行:耗时 · N 轮 · 模型(各自缺则跳过;整行全缺则不输出)。
        var lineParts: [String] = []
        if let elapsedMs, elapsedMs > 0 {
            let seconds = Double(elapsedMs) / 1000.0
            lineParts.append(escape(String(format: "%.1fs", seconds)))
        }
        if let llmRounds, llmRounds > 1 {
            lineParts.append(escape("\(llmRounds) 轮"))
        }
        if let model, !model.trimmingCharacters(in: .whitespaces).isEmpty {
            lineParts.append(escape(model))
        }
        if !lineParts.isEmpty {
            sections.append("<div class=\"meta-line\">" + lineParts.joined(separator: " · ") + "</div>")
        }

        // 数据源:可折叠 <details>(默认收起),summary 显示「引用 N 项数据」。
        let sources = sourcesUsed.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        if !sources.isEmpty {
            let items = sources.map { "<li>\(escape($0))</li>" }.joined()
            sections.append(
                "<details class=\"meta-sources\"><summary>引用 \(sources.count) 项数据</summary><ul>\(items)</ul></details>"
            )
        }

        // Skills:chip 样式,横排。
        let tools = toolsUsed.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        if !tools.isEmpty {
            let chips = tools.map { "<span class=\"meta-chip\">\(escape($0))</span>" }.joined()
            sections.append(
                "<div class=\"meta-tools\"><span class=\"meta-tools-label\">调用 Skill</span>\(chips)</div>"
            )
        }

        guard !sections.isEmpty else { return "" }
        return "<div class=\"meta-footer\">" + sections.joined() + "</div>"
    }

    // MARK: - Message envelope JSON (Swift → JS bridge)

    /// 一条消息喂给 JS 端的数据。`bodyHTML` 已是安全转义后的 HTML 片段。
    public struct RenderedMessage: Equatable, Sendable {
        public let id: String
        public let role: String            // "user" | "assistant"
        public let bodyHTML: String
        public let isStreaming: Bool       // 流式中(plain 文本、无复制按钮)
        public let showCopy: Bool
        /// meta footer 片段(模型/数据源/Skill);流式中或无 meta 时为空 → JS 不渲染 footer。
        public let footerHTML: String

        public init(
            id: String,
            role: String,
            bodyHTML: String,
            isStreaming: Bool,
            showCopy: Bool,
            footerHTML: String = ""
        ) {
            self.id = id
            self.role = role
            self.bodyHTML = bodyHTML
            self.isStreaming = isStreaming
            self.showCopy = showCopy
            self.footerHTML = footerHTML
        }

        /// 序列化为 JS 对象字面量字符串(不依赖 Foundation JSONEncoder 的键序,字段固定)。
        public var jsonObject: String {
            "{\"id\":\(Self.jsString(id)),\"role\":\(Self.jsString(role)),\"html\":\(Self.jsString(bodyHTML)),\"streaming\":\(isStreaming ? "true" : "false"),\"copy\":\(showCopy ? "true" : "false"),\"footer\":\(Self.jsString(footerHTML))}"
        }

        /// JSON 字符串字面量编码(含引号)。用于安全注入 evaluateJavaScript 的字符串实参。
        static func jsString(_ raw: String) -> String {
            var out = "\""
            for scalar in raw.unicodeScalars {
                switch scalar {
                case "\"": out += "\\\""
                case "\\": out += "\\\\"
                case "\n": out += "\\n"
                case "\r": out += "\\r"
                case "\t": out += "\\t"
                case "\u{2028}": out += "\\u2028" // JS line separator — breaks string literals
                case "\u{2029}": out += "\\u2029" // JS paragraph separator
                default:
                    if scalar.value < 0x20 {
                        out += String(format: "\\u%04x", scalar.value)
                    } else if scalar == "<" {
                        // 防止注入的 </script> 在某些上下文提前闭合(深度防御)
                        out += "\\u003c"
                    } else {
                        out.unicodeScalars.append(scalar)
                    }
                }
            }
            out += "\""
            return out
        }
    }

    /// 把整组消息序列化为 JS 数组字面量(setMessages 用)。
    public static func messagesJSONArray(_ messages: [RenderedMessage]) -> String {
        "[" + messages.map(\.jsonObject).joined(separator: ",") + "]"
    }
}
