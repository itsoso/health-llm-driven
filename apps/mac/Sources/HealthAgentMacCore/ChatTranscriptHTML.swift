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
    ///
    /// GenUI(契约 v0 §3.2):先把 ```reva-ui 围栏块**整段抽离**(在 markdown 解析之前——
    /// 否则解析器会把多行 JSON 折成一行 + `---` 误判分割线,JSON 被毁)。抽出的块以
    /// `<div class="reva-ui-chart" data-reva-ui="<base64 原始 JSON>">` 占位符承载,真正的
    /// 解析 + SVG 折线绘制由 WebView 的 JS shell 完成(离线、零外链)。围栏外 markdown 正常渲染。
    public static func renderMessageBody(markdown: String) -> String {
        let src = markdown.isEmpty ? "" : markdown
        let segments = RevaUIBlock.split(from: src)
        // 至少有一个 reva-ui 块 → 分段渲染:普通段各自走 blocks,reva-ui 段换占位 div。
        // 无块时退回原始单段路径(零行为变化)。
        if segments.contains(where: { if case .revaUI = $0 { return true } else { return false } }) {
            var html = ""
            for segment in segments {
                switch segment {
                case .markdown(let text):
                    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty {
                        html += renderMarkdownBlocksHTML(text)
                    }
                case .revaUI(let rawJSON):
                    html += revaUIPlaceholderHTML(rawJSON: rawJSON)
                }
            }
            return html
        }
        return renderMarkdownBlocksHTML(src)
    }

    /// 给一个已抽出的 reva-ui 原始 JSON 字符串生成占位 div。原始 JSON 经 base64 进 data 属性,
    /// 既避开 HTML 属性转义/引号问题,也让 JS 端拿到**未被 markdown 解析器破坏**的原文。
    static func revaUIPlaceholderHTML(rawJSON: String) -> String {
        let b64 = Data(rawJSON.utf8).base64EncodedString()
        return "<div class=\"reva-ui-chart\" data-reva-ui=\"\(b64)\">图表生成中…</div>"
    }

    /// 原 renderMessageBody 主体:markdown → blocks → HTML。供分段渲染与无块路径共用。
    static func renderMarkdownBlocksHTML(_ markdown: String) -> String {
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
        selectedModel: String? = nil,
        answerModel: String? = nil,
        toolModels: [String] = [],
        fallbackReasons: [String] = [],
        elapsedMs: Int?,
        llmRounds: Int?,
        sourcesUsed: [String],
        toolsUsed: [String],
        perf: MessagePerf? = nil
    ) -> String {
        var sections: [String] = []

        // 延迟瀑布图:紧跟在 footer 顶部(耗时行之上),给「秒都花哪了」一眼画像。
        // perf 缺失(老消息 / 老后端)→ 空串 → footer 其余部分行为完全不变。
        if let perf {
            let waterfall = latencyWaterfallHTML(perf)
            if !waterfall.isEmpty {
                sections.append(waterfall)
            }
        }

        // 第一行:耗时 · N 轮 · 回答模型 · 工具模型(各自缺则跳过;整行全缺则不输出)。
        var lineParts: [String] = []
        if let elapsedMs, elapsedMs > 0 {
            let seconds = Double(elapsedMs) / 1000.0
            lineParts.append(escape(String(format: "%.1fs", seconds)))
        }
        if let llmRounds, llmRounds > 1 {
            lineParts.append(escape("\(llmRounds) 轮"))
        }
        let selected = selectedModel?.trimmingCharacters(in: .whitespacesAndNewlines)
        let answer = (answerModel ?? model)?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let selected, !selected.isEmpty, let answer, !answer.isEmpty, selected != answer {
            lineParts.append(escape("选择 \(selected)"))
        }
        if let answer, !answer.isEmpty {
            lineParts.append(escape("回答 \(answer)"))
        } else if let model, !model.trimmingCharacters(in: .whitespaces).isEmpty {
            lineParts.append(escape(model))
        }
        let toolModelNames = toolModels.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        if !toolModelNames.isEmpty {
            lineParts.append(escape("工具 \(toolModelNames.joined(separator: ", "))"))
        }
        if !lineParts.isEmpty {
            sections.append("<div class=\"meta-line\">" + lineParts.joined(separator: " · ") + "</div>")
        }

        let fallbackLabels = fallbackReasons
            .map(fallbackReasonLabel)
            .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        if !fallbackLabels.isEmpty {
            let chips = fallbackLabels.map { "<span class=\"meta-chip\">\(escape($0))</span>" }.joined()
            sections.append("<div class=\"meta-tools\"><span class=\"meta-tools-label\">路由</span>\(chips)</div>")
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

    private static func fallbackReasonLabel(_ reason: String) -> String {
        switch reason {
        case "selected_model_tool_unreliable", "selected_model_tool_stream_failed", "selected_model_tool_chat_failed":
            return "工具调用临时切到可靠模型"
        case "preferred_model_tool_unreliable":
            return "偏好模型工具调用临时切到可靠模型"
        default:
            return reason
        }
    }

    // MARK: - Latency waterfall (每回复级阶段耗时瀑布图)

    /// 渲染一条紧凑的横向色带瀑布图 + 可折叠 `<details>` 明细。段宽按 ms 正比,沿
    /// `total_ms` 时间线求和。默认收起,只显示色带 + 总耗时;展开显示 7 个 pre-LLM 阶段
    /// + 逐轮 {生成/工具/工具名}。数据不足(无 total_ms)→ 返回 ""(不渲染)。
    ///
    /// 全部走 CSS(段是 flex 子元素,`flex-grow` 承载比例);展开用原生 `<details>`,零 JS。
    /// 所有动态文本经 `escape(_:)` 防 XSS(与 footer 其余部分同一防线)。
    static func latencyWaterfallHTML(_ perf: MessagePerf) -> String {
        let bands = perf.bands()
        guard !bands.isEmpty, let total = perf.totalMs, total > 0 else { return "" }

        let totalSeconds = String(format: "%.1fs", Double(total) / 1000.0)

        // 色带:每段 flex-grow = ms(相对总时长的比例)。极小段给个下限,避免 0 宽不可见。
        let segments = bands.map { band -> String in
            let grow = max(band.ms, 1)
            let title = "\(band.label) \(msLabel(band.ms))"
            return "<span class=\"wf-seg wf-\(band.kind.rawValue)\" style=\"flex-grow:\(grow)\" title=\"\(escape(title))\"></span>"
        }.joined()

        // 图例:只列真正出现的色带,和色带一一对应。
        let legend = bands.map { band -> String in
            "<span class=\"wf-legend-item\"><span class=\"wf-dot wf-\(band.kind.rawValue)\"></span>\(escape(band.label)) \(escape(msLabel(band.ms)))</span>"
        }.joined()

        // 展开明细:7 个 pre-LLM 阶段(非零)+ 逐轮生成/工具。
        var detailRows = ""
        if let stages = perf.preLLMStages {
            let stageItems = stages.orderedNonZero
            if !stageItems.isEmpty {
                let rows = stageItems.map { item in
                    "<div class=\"wf-detail-row\"><span>\(escape(item.label))</span><span>\(escape(msLabel(item.ms)))</span></div>"
                }.joined()
                detailRows += "<div class=\"wf-detail-group\"><div class=\"wf-detail-head\">组装阶段</div>\(rows)</div>"
            }
        }
        if !perf.rounds.isEmpty {
            let rows = perf.rounds.enumerated().map { index, round -> String in
                let gen = msLabel(round.llmGenMs ?? 0)
                let tool = msLabel(round.toolExecMs ?? 0)
                let toolNames = round.tools.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
                let toolsSuffix = toolNames.isEmpty ? "" : " · " + toolNames.joined(separator: ", ")
                let label = "第 \(index + 1) 轮"
                let value = "生成 \(gen) · 工具 \(tool)\(toolsSuffix)"
                return "<div class=\"wf-detail-row\"><span>\(escape(label))</span><span>\(escape(value))</span></div>"
            }.joined()
            detailRows += "<div class=\"wf-detail-group\"><div class=\"wf-detail-head\">LLM 轮次</div>\(rows)</div>"
        }

        // 无任何明细可展开时,退化为纯色带(不套 <details>,避免空展开)。
        if detailRows.isEmpty {
            return """
            <div class="latency-waterfall">
              <div class="wf-summary-static"><span class="wf-title">延迟</span><span class="wf-total">\(escape(totalSeconds))</span></div>
              <div class="wf-bar">\(segments)</div>
              <div class="wf-legend">\(legend)</div>
            </div>
            """
        }

        return """
        <details class="latency-waterfall">
          <summary class="wf-summary"><span class="wf-title">延迟</span><span class="wf-total">\(escape(totalSeconds))</span><span class="wf-hint">明细</span></summary>
          <div class="wf-bar">\(segments)</div>
          <div class="wf-legend">\(legend)</div>
          <div class="wf-detail">\(detailRows)</div>
        </details>
        """
    }

    /// 把毫秒格式化为紧凑标签:≥1000ms → "x.xs";否则 "Nms"。
    private static func msLabel(_ ms: Int) -> String {
        if ms >= 1000 {
            return String(format: "%.1fs", Double(ms) / 1000.0)
        }
        return "\(ms)ms"
    }

    // MARK: - Attached images

    /// Renders public image attachments as a small gallery. URLs are treated as
    /// untrusted input: only http/https URLs are emitted, and every attribute is
    /// escaped before entering the HTML fragment.
    public static func imageGalleryHTML(urls: [String]) -> String {
        let items = urls.compactMap { raw -> String? in
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let url = URL(string: trimmed),
                  let scheme = url.scheme?.lowercased(),
                  ["http", "https"].contains(scheme) else {
                return nil
            }
            let escaped = escape(url.absoluteString)
            return """
            <a class="attachment-image-link" href="\(escaped)" target="_blank" rel="noopener noreferrer"><img class="attachment-image" src="\(escaped)" loading="lazy" alt="attached image"></a>
            """
        }
        guard !items.isEmpty else { return "" }
        return "<div class=\"attachment-images\">" + items.joined() + "</div>"
    }

    // MARK: - Dynamic cards

    public static func dynamicCardHTML(
        type: String?,
        data: AgentDynamicCardValue?,
        actions: [AgentDynamicCardActionDescriptor] = []
    ) -> String? {
        guard let type, let data else {
            return nil
        }
        return dynamicCardHTML(type: type, data: data, actions: actions)
    }

    public static func dynamicCardHTML(
        type: String,
        data: AgentDynamicCardValue,
        actions: [AgentDynamicCardActionDescriptor] = []
    ) -> String? {
        let html: String?
        switch type {
        case "medical_exam_import_result":
            html = medicalExamImportCardHTML(data)
        case "system_knowledge_evidence":
            html = systemKnowledgeEvidenceCardHTML(data)
        case "safety":
            html = safetyCardHTML(data)
        case "record_quality":
            html = recordQualityCardHTML(data)
        default:
            html = genericDynamicCardHTML(type: type, data: data)
        }
        guard let html else {
            return nil
        }
        return appendDynamicCardActions(to: html, actions: actions)
    }

    private static func medicalExamImportCardHTML(_ data: AgentDynamicCardValue) -> String? {
        guard case .object = data else {
            return nil
        }
        let source = sourceLabel(data["source"]?.stringValue ?? "")
        let itemsCount = data["items_count"]?.intValue ?? 0
        let abnormalCount = data["abnormal_count"]?.intValue ?? 0
        let conclusionsCount = data["conclusions_count"]?.intValue
        let badge = abnormalCount > 0 ? "\(abnormalCount) 项异常" : "待复核"
        let badgeClass = abnormalCount > 0 ? "risk" : "neutral"
        let detail = [
            data["exam_date"]?.stringValue,
            data["hospital_name"]?.stringValue,
            data["exam_type"]?.stringValue
        ].compactMap { value in
            let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return trimmed.isEmpty ? nil : trimmed
        }.joined(separator: " · ")
        let conclusion = data["conclusion"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let reviewRequired = data["review_required"]?.boolValue ?? true
        let safetyNote = data["safety_note"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
            ?? "OCR/AI 解析结果需要复核后再用于判断。"

        var html = """
        <div class="dynamic-card medical-exam-import-card">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">体检导入结果</div>
              <div class="dynamic-card-title">体检报告已导入</div>
            </div>
            <span class="dynamic-card-badge \(badgeClass)">\(escape(badge))</span>
          </div>
          <div class="dynamic-card-metrics">
            \(metricHTML(label: "来源", value: source, risk: false))
            \(metricHTML(label: "指标", value: "\(itemsCount) 项指标", risk: false))
            \(metricHTML(label: "异常", value: "\(abnormalCount) 项异常", risk: abnormalCount > 0))
        """
        if let conclusionsCount {
            html += metricHTML(label: "结论", value: "\(conclusionsCount) 条", risk: false)
        }
        html += "</div>"
        if !detail.isEmpty {
            html += "<div class=\"dynamic-card-detail\">\(escape(detail))</div>"
        }
        if !conclusion.isEmpty {
            html += "<div class=\"dynamic-card-conclusion\">\(escape(conclusion))</div>"
        }
        if reviewRequired {
            html += "<div class=\"dynamic-card-warning\">\(escape(safetyNote))</div>"
        }
        html += """
          <div class="dynamic-card-next">下一步：复核识别结果后，再让 Reva 基于异常项生成 30 天行动建议。</div>
        </div>
        """
        return html
    }

    private static func systemKnowledgeEvidenceCardHTML(_ data: AgentDynamicCardValue) -> String? {
        let title = data["entity"]?["title"]?.stringValue?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let claimsCount = data["claims"]?.arrayValue?.count ?? 0
        return """
        <div class="dynamic-card evidence-card">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">知识证据卡</div>
              <div class="dynamic-card-title">\(escape((title?.isEmpty == false ? title : nil) ?? "系统知识库"))</div>
            </div>
            <span class="dynamic-card-badge neutral">\(escape("\(claimsCount) 条证据"))</span>
          </div>
          <div class="dynamic-card-next">本回答引用了已审核知识库证据，具体结论仍需结合个人数据边界判断。</div>
        </div>
        """
    }

    private static func safetyCardHTML(_ data: AgentDynamicCardValue) -> String? {
        let title = cardString(data["title"]) ?? "安全提醒"
        let severity = normalizedSafetySeverity(data["severity"]?.stringValue)
        let meta = safetySeverityMeta(severity)
        let summary = cardString(data["summary"])
        let recommendations = safetyRecommendations(from: data["recommendations"])
        let boundary = cardString(data["boundary"]) ?? "这不是诊断；如出现急性不适或持续症状，请及时就医。"
        let needsAttention = (data["requires_medical_attention"]?.boolValue == true) || severity == "critical"
        let detail = [
            cardString(data["rule_id"]).map { "规则 \($0)" },
            cardString(data["category"]).map { "类别 \($0)" }
        ].compactMap { $0 }.joined(separator: " · ")

        var html = """
        <div class="dynamic-card safety-card safety-card-\(meta.toneClass)">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">Safety Guardian</div>
              <div class="dynamic-card-title">\(escape(title))</div>
            </div>
            <span class="dynamic-card-badge \(meta.badgeClass)">\(escape(meta.label))</span>
          </div>
        """
        if let summary {
            html += "<div class=\"safety-card-summary\">\(escape(summary))</div>"
        }
        if !recommendations.isEmpty {
            let items = recommendations
                .map { "<li>\(escape($0))</li>" }
                .joined()
            html += "<ul class=\"safety-card-recommendations\">\(items)</ul>"
        }
        if needsAttention {
            html += "<div class=\"safety-card-attention\">需要关注</div>"
        }
        if !detail.isEmpty {
            html += "<div class=\"dynamic-card-detail\">\(escape(detail))</div>"
        }
        html += "<div class=\"dynamic-card-warning\">\(escape(boundary))</div>"
        html += "</div>"
        return html
    }

    private static func recordQualityCardHTML(_ data: AgentDynamicCardValue) -> String? {
        guard case .object = data else {
            return nil
        }
        let domain = cardText(data["domain"]) ?? "diet"
        let badge = domain == "exercise" ? "运动" : "饮食"
        let badgeClass = domain == "exercise" ? "neutral" : "caution"
        let title = cardText(data["title"]) ?? "已记录"
        let summary = cardText(data["summary"])
        let judgement = cardText(data["primary_judgement"])
        let nextAction = cardText(data["next_action"])
        let boundary = cardText(data["boundary"]) ?? "健康管理建议，不替代医生诊断、处方或治疗。"
        let cautions = cardStringArray(data["personal_cautions"]).prefix(2)

        var html = """
        <div class="dynamic-card record-quality-card">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">记录后建议</div>
              <div class="dynamic-card-title">\(escape(title))</div>
            </div>
            <span class="dynamic-card-badge \(badgeClass)">\(escape(badge))</span>
          </div>
        """
        if let summary {
            html += "<div class=\"dynamic-card-detail\">\(escape(summary))</div>"
        }
        let metrics = recordQualityMetricsHTML(data["metrics"])
        let progress = recordQualityProgressHTML(data["progress"])
        if !metrics.isEmpty || !progress.isEmpty {
            html += "<div class=\"dynamic-card-metrics\">\(metrics)\(progress)</div>"
        }
        if let judgement {
            html += "<div class=\"dynamic-card-conclusion\">\(escape(judgement))</div>"
        }
        for item in cautions {
            html += "<div class=\"dynamic-card-warning\">\(escape(item))</div>"
        }
        if let nextAction {
            html += "<div class=\"dynamic-card-next\">下一步：\(escape(nextAction))</div>"
        }
        html += "<div class=\"dynamic-card-detail\">\(escape(boundary))</div>"
        html += "</div>"
        return html
    }

    private static func recordQualityMetricsHTML(_ value: AgentDynamicCardValue?) -> String {
        guard case .array(let items) = value else {
            return ""
        }
        return items.prefix(5).compactMap { item -> String? in
            let label = cardText(item["label"])
            let value = cardText(item["value"])
            guard let label, let value else {
                return nil
            }
            return metricHTML(label: label, value: value, risk: false)
        }.joined()
    }

    private static func recordQualityProgressHTML(_ value: AgentDynamicCardValue?) -> String {
        guard let proteinTotal = cardNumber(value?["protein_total_g"]),
              let proteinTarget = cardNumber(value?["protein_target_g"]) else {
            return ""
        }
        let remaining = cardNumber(value?["remaining_protein_g"]) ?? max(0, proteinTarget - proteinTotal)
        let valueText = "\(Int(proteinTotal.rounded()))/\(Int(proteinTarget.rounded()))g · 还差\(Int(remaining.rounded()))g"
        return metricHTML(label: "今日蛋白", value: valueText, risk: remaining > 0)
    }

    private static func genericDynamicCardHTML(type: String, data: AgentDynamicCardValue) -> String? {
        let rows = cardSummaryRows(data: data)
            .prefix(4)
            .map { key, value in
                "<div class=\"dynamic-card-summary-row\"><span>\(escape(key))</span><strong>\(escape(value))</strong></div>"
            }
            .joined()
        return """
        <div class="dynamic-card generic-card">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">动态卡片</div>
              <div class="dynamic-card-title">\(escape(type))</div>
            </div>
          </div>
          <div class="dynamic-card-summary">\(rows)</div>
        </div>
        """
    }

    private static func appendDynamicCardActions(
        to html: String,
        actions: [AgentDynamicCardActionDescriptor]
    ) -> String {
        let actionBar = dynamicCardActionsHTML(actions)
        guard !actionBar.isEmpty,
              let closingRange = html.range(of: "</div>", options: .backwards) else {
            return html
        }
        var result = html
        result.replaceSubrange(closingRange, with: "\(actionBar)\n</div>")
        return result
    }

    private static func dynamicCardActionsHTML(_ actions: [AgentDynamicCardActionDescriptor]) -> String {
        let items = actions.compactMap { action -> String? in
            guard action.action == "route.open" else {
                return nil
            }
            let label = action.label.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !label.isEmpty,
                  let route = action.payload?["route"]?.stringValue?
                    .trimmingCharacters(in: .whitespacesAndNewlines),
                  isSafeInternalRoute(route) else {
                return nil
            }
            let styleClass = action.style == "primary" ? "primary" : "secondary"
            return """
            <a class="dynamic-card-action \(styleClass)" href="\(escape(route))">\(escape(label))</a>
            """
        }
        guard !items.isEmpty else {
            return ""
        }
        return "<div class=\"dynamic-card-actions\">\(items.joined())</div>"
    }

    private static func isSafeInternalRoute(_ route: String) -> Bool {
        guard route.hasPrefix("/"),
              !route.hasPrefix("//"),
              route.rangeOfCharacter(from: .controlCharacters) == nil else {
            return false
        }
        return true
    }

    private static func metricHTML(label: String, value: String, risk: Bool) -> String {
        let riskClass = risk ? " risk" : ""
        return """
        <div class="dynamic-card-metric">
          <div class="dynamic-card-metric-label">\(escape(label))</div>
          <div class="dynamic-card-metric-value\(riskClass)">\(escape(value))</div>
        </div>
        """
    }

    private static func sourceLabel(_ source: String) -> String {
        switch source {
        case "pdf":
            return "PDF"
        case "image":
            return "图片 OCR"
        case "text":
            return "文字"
        default:
            return source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "未知" : source
        }
    }

    private static func cardSummaryRows(data: AgentDynamicCardValue) -> [(String, String)] {
        guard case .object(let object) = data else {
            return [("value", scalarSummary(data))]
        }
        return object
            .sorted { $0.key < $1.key }
            .compactMap { key, value in
                let summary = scalarSummary(value)
                return summary.isEmpty ? nil : (key, summary)
        }
    }

    private static func cardText(_ value: AgentDynamicCardValue?) -> String? {
        guard let raw = value?.stringValue else {
            return nil
        }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func cardNumber(_ value: AgentDynamicCardValue?) -> Double? {
        guard let value else {
            return nil
        }
        switch value {
        case .int(let raw):
            return Double(raw)
        case .double(let raw):
            return raw
        case .string(let raw):
            return Double(raw.trimmingCharacters(in: .whitespacesAndNewlines))
        case .null, .bool, .object, .array:
            return nil
        }
    }

    private static func cardStringArray(_ value: AgentDynamicCardValue?) -> [String] {
        let rawItems: [AgentDynamicCardValue]
        if case .array(let values) = value {
            rawItems = values
        } else if let value {
            rawItems = [value]
        } else {
            rawItems = []
        }
        return rawItems.compactMap(cardText)
    }

    private static func cardString(_ value: AgentDynamicCardValue?) -> String? {
        guard case .string(let raw) = value else {
            return nil
        }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func normalizedSafetySeverity(_ raw: String?) -> String {
        let value = raw?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
        return ["critical", "high", "medium", "low", "info"].contains(value) ? value : "info"
    }

    private static func safetySeverityMeta(_ severity: String) -> (label: String, badgeClass: String, toneClass: String) {
        switch severity {
        case "critical":
            return ("紧急风险", "risk", "risk")
        case "high":
            return ("高风险", "risk", "risk")
        case "medium":
            return ("注意", "caution", "caution")
        case "low":
            return ("低风险", "neutral", "info")
        default:
            return ("安全提示", "neutral", "info")
        }
    }

    private static func safetyRecommendations(from value: AgentDynamicCardValue?) -> [String] {
        let rawItems: [AgentDynamicCardValue]
        if case .array(let values) = value {
            rawItems = values
        } else if let value {
            rawItems = [value]
        } else {
            rawItems = []
        }
        let items = rawItems
            .compactMap { item -> String? in
                let text = item.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                return text.isEmpty ? nil : text
            }
        return Array(items.prefix(3))
    }

    private static func scalarSummary(_ value: AgentDynamicCardValue) -> String {
        switch value {
        case .null:
            return ""
        case .string(let raw):
            return raw
        case .int(let raw):
            return String(raw)
        case .double(let raw):
            return String(raw)
        case .bool(let raw):
            return raw ? "true" : "false"
        case .array(let values):
            return "\(values.count) 项"
        case .object(let object):
            return "\(object.count) 字段"
        }
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
