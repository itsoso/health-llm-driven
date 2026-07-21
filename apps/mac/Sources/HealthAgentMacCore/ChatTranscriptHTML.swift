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

    public static func messageTimeLabels(for date: Date?) -> (short: String, full: String)? {
        guard let date else { return nil }
        let short = DateFormatter()
        short.locale = Locale(identifier: "zh_CN")
        short.timeZone = .current
        short.dateFormat = "HH:mm"

        let full = DateFormatter()
        full.locale = Locale(identifier: "zh_CN")
        full.timeZone = .current
        full.dateFormat = "yyyy年M月d日 HH:mm"

        return (short.string(from: date), full.string(from: date))
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
        // 无块时退回原始单段路径(零行为变化,除防御性剥离 menu_share 残片外)。
        //
        // menu_share:fenced ```menu_share 块已被 `RevaUIBlock.split` 整段剥离(不产段);
        // 这里再对每个普通 markdown 段做 `stripInlineMenuShareRemnants` 收尾,兜住未被围栏
        // 包裹的 inline / 裸文本残片(founder 实测的畸形形态)。菜单的规范表示是 done 事件
        // 里的结构化 dynamic card,prose 里绝不留原始 JSON。
        let hasRevaUI = segments.contains(where: { if case .revaUI = $0 { return true } else { return false } })
        // fenced ```menu_share 被 split 剥离后,segments 里只剩普通 markdown 段;此时若还走
        // 原始 src 的单段路径,被剥离的 JSON 会重新出现。凡是「有 reva-ui 占位」或「split
        // 把 markdown 段拼回来后与 src 不一致(= 剥离掉了 menu_share fence)」都走分段路径。
        let markdownJoined = segments.compactMap { segment -> String? in
            if case .markdown(let text) = segment { return text } else { return nil }
        }.joined(separator: "\n")
        let normalizedSrc = src.replacingOccurrences(of: "\r\n", with: "\n")
        let strippedByFence = !hasRevaUI && markdownJoined != normalizedSrc

        if hasRevaUI || strippedByFence {
            var html = ""
            for segment in segments {
                switch segment {
                case .markdown(let text):
                    let cleaned = RevaUIBlock.stripInlineMenuShareRemnants(text)
                    let trimmed = cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty {
                        html += renderMarkdownBlocksHTML(cleaned)
                    }
                case .revaUI(let rawJSON):
                    html += revaUIPlaceholderHTML(rawJSON: rawJSON)
                }
            }
            return html
        }
        return renderMarkdownBlocksHTML(RevaUIBlock.stripInlineMenuShareRemnants(src))
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
        // 有序列表跨"被子 bullet 打断"仍连续编号:LLM 常把每个顶级条目都写成 "1.",
        // 且插在条目间的子 bullet 会把 <ol> 冲断成一串单条列表 → 浏览器每个都从 1 显示。
        // 用跨 flush 的运行计数 + <ol start=N> 让编号延续;只在真正的列表分界
        // (标题/段落/分割线)重置回 1。
        var numberedNext = 1        // 下一个有序 <li> 该显示的序号
        var numberedRunStart = 1    // 当前 pending run 的 <ol start> 起始值

        func flushBullets() {
            guard !pendingBullets.isEmpty else { return }
            html += "<ul>" + pendingBullets.map { "<li>\($0)</li>" }.joined() + "</ul>"
            pendingBullets = []
        }
        func flushNumbered() {
            guard !pendingNumbered.isEmpty else { return }
            let startAttr = numberedRunStart > 1 ? " start=\"\(numberedRunStart)\"" : ""
            html += "<ol\(startAttr)>" + pendingNumbered.map { "<li>\($0)</li>" }.joined() + "</ol>"
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
                numberedNext = 1
                let clampedLevel = min(max(level, 1), 4)
                let inner = inlineMarkdown(escape(text))
                html += "<h\(clampedLevel)>\(inner)</h\(clampedLevel)>"
            case .paragraph(let text):
                flushAll()
                numberedNext = 1
                html += "<p>\(inlineMarkdown(escape(text)))</p>"
            case .bullet(let text):
                flushNumbered()
                flushTable()
                pendingBullets.append(inlineMarkdown(escape(text)))
            case .numbered(_, let text):
                flushBullets()
                flushTable()
                // 忽略源里的 index(LLM 常全写 "1"),用运行计数;pending 为空=新一段的起点
                if pendingNumbered.isEmpty { numberedRunStart = numberedNext }
                pendingNumbered.append(inlineMarkdown(escape(text)))
                numberedNext += 1
            case .tableRow(let columns):
                flushBullets()
                flushNumbered()
                pendingTableRows.append(columns.map { inlineMarkdown(escape($0)) })
            case .divider:
                flushAll()
                numberedNext = 1
                html += "<hr/>"
            }
        }
        flushAll()
        return html
    }

    // MARK: - 思考过程 trace (safe progress summaries)

    /// Renders the reviewable "思考过程" trace from the backend's safe progress
    /// summaries (`thinking_steps`). Two modes, ONE component so live and finished
    /// never look like two different UIs:
    ///  - `live: true`  → a `<details open>` (steps visible) whose LAST step is the
    ///    running one (pulsing dot) and earlier steps are done (a small linear
    ///    check). Shown inside the streaming bubble while the answer composes.
    ///  - `live: false` → a `<details>` collapsed by default; the header "思考过程"
    ///    expands to review the finished turn's steps (all done). Survives reload
    ///    because it reads the persisted `message.thinking_steps`.
    ///
    /// Icon: a plain disclosure chevron (▸/▾) on the header — NO brain/emoji glyph
    /// (founder constraint). Step glyphs are a minimal dot / linear check, never 🧠.
    /// Layout is deterministic: a fixed-width leading gutter (CSS `.tp-gutter`), no
    /// measurement feedback loop. Every dynamic string is `escape(_:)`-ed (XSS).
    /// Empty `steps` → "" (nothing rendered).
    public static func thinkingTraceHTML(steps: [String], language: String, live: Bool, open: Bool? = nil) -> String {
        let cleaned = steps
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        guard !cleaned.isEmpty else { return "" }

        let header = escape(L10n.text("Thinking process", language: AppLanguage(storedValue: language)))
        let isOpen = open ?? live
        let openAttr = isOpen ? " open" : ""

        // In live mode the last step is "running"; every earlier step (and every
        // step of a finished turn) is "done".
        let lastIndex = cleaned.count - 1
        let rows = cleaned.enumerated().map { index, step -> String in
            let running = live && index == lastIndex
            let stateClass = running ? "tp-running" : "tp-done"
            let glyph = running
                ? "<span class=\"tp-gutter tp-spinner\" aria-hidden=\"true\"></span>"
                : "<span class=\"tp-gutter tp-check\" aria-hidden=\"true\"></span>"
            return "<li class=\"tp-step \(stateClass)\">\(glyph)<span class=\"tp-label\">\(escape(step))</span></li>"
        }.joined()

        return """
        <details class="thinking-trace\(live ? " thinking-trace-live" : "")"\(openAttr)>
          <summary class="tp-summary">\(header)</summary>
          <ul class="tp-steps">\(rows)</ul>
        </details>
        """
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
        perf: MessagePerf? = nil,
        llmUsage: LLMUsageProfile? = nil
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
        if let llmUsage {
            let usageHTML = tokenUsageHTML(llmUsage)
            if !usageHTML.isEmpty {
                sections.append(usageHTML)
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

    private static func tokenUsageHTML(_ usage: LLMUsageProfile) -> String {
        let prompt = usage.promptTokens ?? 0
        let completion = usage.completionTokens ?? 0
        let failed = usage.failedCalls ?? usage.items.filter { $0.success == false }.count
        guard prompt > 0 || completion > 0 || failed > 0 else { return "" }

        var summaryParts: [String] = []
        if let planCost = costDisplayLabel(
            cny: usage.tokenplanCostCny,
            usd: nil,
            estimated: usage.tokenplanCostEstimated
        ) {
            summaryParts.append(planCost)
        } else if usage.providers.contains(where: { $0.lowercased() == "tokenplan" })
            || usage.items.contains(where: { ($0.provider ?? "").lowercased() == "tokenplan" }) {
            summaryParts.append("套餐折算 暂无法估算")
        }
        summaryParts.append("Token 输入 \(tokenCountLabel(prompt)) · 输出 \(tokenCountLabel(completion))")
        if let calls = usage.calls, calls > 1 {
            summaryParts.append("\(calls)次")
        }
        if failed > 0 {
            summaryParts.append("失败 \(failed)次")
        }
        if let runID = cleanMetaValue(usage.runID ?? usage.items.compactMap(\.runID).first), !runID.isEmpty {
            summaryParts.append("run \(String(runID.prefix(18)))")
        }
        let summary = summaryParts.joined(separator: " · ")

        var detailRows: [String] = []
        if let planCost = costDisplayLabel(
            cny: usage.tokenplanCostCny,
            usd: nil,
            estimated: usage.tokenplanCostEstimated
        ) {
            detailRows.append("<li>套餐折算 \(escape(planCost))</li>")
        }
        if let paygCost = costDisplayLabel(
            cny: usage.tokenplanPaygValueCny ?? usage.costCny,
            usd: usage.costUsd,
            estimated: usage.costEstimated
        ) {
            detailRows.append("<li>按量价对照 \(escape(paygCost))</li>")
        }
        detailRows.append(contentsOf: usage.items.enumerated().map { index, item -> String in
            let model = item.model?.trimmingCharacters(in: .whitespacesAndNewlines)
            let provider = item.provider?.trimmingCharacters(in: .whitespacesAndNewlines)
            let name = (!(model ?? "").isEmpty ? model : provider) ?? "调用 \(index + 1)"
            var value = "输入 \(tokenCountLabel(item.promptTokens ?? 0)) · 输出 \(tokenCountLabel(item.completionTokens ?? 0))"
            if let latency = item.latencyMs, latency > 0 {
                value += " · " + msLabel(latency)
            }
            if item.success == false {
                value += " · 失败"
                if let reason = failureReasonLabel(item) {
                    value += " · \(reason)"
                }
            }
            if let recovery = cleanMetaValue(item.recoveryAction), !recovery.isEmpty {
                value += " · \(recovery)"
            }
            if let recoveryModel = cleanMetaValue(item.recoveryModel), !recoveryModel.isEmpty {
                value += " · 备用 \(recoveryModel)"
            }
            return "<li>\(escape(name))：\(escape(value))</li>"
        })
        let rows = detailRows.joined()

        if rows.isEmpty {
            return "<div class=\"meta-line\">\(escape(summary))</div>"
        }
        return "<details class=\"meta-sources meta-token\"><summary>\(escape(summary))</summary><ul>\(rows)</ul></details>"
    }

    private static func failureReasonLabel(_ item: LLMUsageCall) -> String? {
        let parts = [item.errorCode, item.errorType]
            .compactMap { cleanMetaValue($0) }
            .filter { !$0.isEmpty }
        if !parts.isEmpty {
            return parts.joined(separator: " / ")
        }
        if let message = cleanMetaValue(item.errorMessage), !message.isEmpty {
            return message.count > 80 ? String(message.prefix(80)) + "..." : message
        }
        return nil
    }

    private static func cleanMetaValue(_ value: String?) -> String? {
        value?
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func tokenCountLabel(_ value: Int) -> String {
        if value >= 1000 {
            let formatted = String(format: "%.1fk", Double(value) / 1000.0)
            return formatted.replacingOccurrences(of: ".0k", with: "k")
        }
        return "\(max(0, value))"
    }

    private static func costLabel(_ value: Double) -> String {
        if value < 0.01 {
            return "<$0.01"
        }
        return String(format: "$%.2f", value)
    }

    private static func cnyCostLabel(_ value: Double) -> String {
        if value < 0.01 {
            return "¥0.01以内"
        }
        return String(format: "¥%.2f", value)
    }

    private static func costDisplayLabel(cny: Double?, usd: Double?, estimated: Bool?) -> String? {
        let prefix = estimated == false ? "" : "约"
        if let cny, cny > 0 {
            return prefix + cnyCostLabel(cny)
        }
        if let usd, usd > 0 {
            return prefix + costLabel(usd)
        }
        return nil
    }

    private static func fallbackReasonLabel(_ reason: String) -> String {
        switch reason {
        case "selected_model_tool_unreliable", "selected_model_tool_stream_failed", "selected_model_tool_chat_failed":
            return "工具调用临时切到可靠模型"
        case "preferred_model_tool_unreliable":
            return "偏好模型工具调用临时切到可靠模型"
        case "fast_route_simple_turn":
            return "简单查询·自动用快模型"
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
        render: AgentDynamicCardRenderDescriptor? = nil,
        data: AgentDynamicCardValue?,
        actions: [AgentDynamicCardActionDescriptor] = []
    ) -> String? {
        guard let type, let data else {
            return nil
        }
        return dynamicCardHTML(type: type, render: render, data: data, actions: actions)
    }

    public static func dynamicCardHTML(
        type: String,
        render: AgentDynamicCardRenderDescriptor? = nil,
        data: AgentDynamicCardValue,
        actions: [AgentDynamicCardActionDescriptor] = []
    ) -> String? {
        let rendererType = dynamicCardRendererType(type: type, render: render)
        let html: String?
        switch rendererType {
        case "cards_group":
            html = dynamicCardGroupHTML(data)
        case "medical_exam_import_result":
            html = medicalExamImportCardHTML(data)
        case "system_knowledge_evidence":
            html = systemKnowledgeEvidenceCardHTML(data)
        case "safety":
            html = safetyCardHTML(data)
        case "record_quality":
            html = recordQualityCardHTML(data)
        case "aigc_media_job":
            html = aigcMediaJobCardHTML(data)
        case "aigc_media_confirmation":
            html = aigcMediaConfirmationCardHTML(data)
        case "diet_draft":
            html = dietDraftCardHTML(data)
        case "medication_draft":
            html = medicationDraftCardHTML(data)
        case "menu_share":
            html = menuShareCardHTML(data)
        default:
            html = genericDynamicCardHTML(type: rendererType, data: data)
        }
        guard let html else {
            return nil
        }
        let visibleActions: [AgentDynamicCardActionDescriptor]
        if rendererType == "medication_draft",
           data["action_pending"]?.boolValue == true || cardText(data["decision_status"]) != nil {
            visibleActions = []
        } else {
            visibleActions = actions
        }
        return appendDynamicCardActions(
            to: html,
            actions: visibleActions,
            cardType: rendererType
        )
    }

    private static func dynamicCardGroupHTML(_ data: AgentDynamicCardValue) -> String? {
        guard case .object(let value) = data,
              case .array(let rawCards)? = value["cards"] else {
            return nil
        }
        let cards = rawCards.compactMap(AgentDynamicCardDescriptor.fromGroupValue)
        let items = cards.compactMap { card in
            dynamicCardHTML(
                type: card.type,
                render: card.render,
                data: card.data,
                actions: card.actions
            )
        }
        guard !items.isEmpty else { return nil }
        return "<div class=\"dynamic-card-group\">\(items.joined())</div>"
    }

    private static func dynamicCardRendererType(
        type: String,
        render: AgentDynamicCardRenderDescriptor?
    ) -> String {
        let cardType = cleanCardIdentifier(type) ?? "unknown"
        guard let atom = cleanCardIdentifier(render?.atom) else {
            return cardType
        }
        if dedicatedDynamicCardRenderers.contains(atom) || cardType == "agent_atom" {
            return atom
        }
        return cardType
    }

    private static let dedicatedDynamicCardRenderers: Set<String> = [
        "medical_exam_import_result",
        "system_knowledge_evidence",
        "safety",
        "record_quality",
        "aigc_media_job",
        "aigc_media_confirmation",
        "diet_draft",
        "medication_draft",
        "menu_share"
    ]

    private static func dietDraftCardHTML(_ data: AgentDynamicCardValue) -> String? {
        guard case .object = data else { return nil }
        let mealType = data["meal_type"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "meal"
        let mealLabel: String
        switch mealType {
        case "breakfast": mealLabel = "早餐"
        case "lunch": mealLabel = "午餐"
        case "dinner": mealLabel = "晚餐"
        case "snack": mealLabel = "加餐"
        default: mealLabel = "餐食"
        }
        let recorded = data["recorded"]?.boolValue == true
        let foodItems = cardText(data["food_items"]) ?? "识别到的餐食"
        let confidence = cardNumber(data["confidence"]) ?? cardNumber(data["ai_confidence"])
        let calories = data["calories"]?.stringValue
        let protein = data["protein"]?.stringValue
        let photoURL = privateDietPhotoURL(data["photo_url"]?.stringValue)
        let boundary = cardText(data["boundary"])
            ?? "营养为图像估算；确认后才写入今日饮食记录。"
        let receiptMessage = cardText(data["receipt_message"])
        let statusLabel = recorded ? "已记录" : "待确认"
        let statusClass = recorded ? "neutral" : "caution"

        var html = """
        <div class="dynamic-card diet-draft-card">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">图片饮食识别</div>
              <div class="dynamic-card-title">\(escape(mealLabel)) · \(escape(statusLabel))</div>
            </div>
            <span class="dynamic-card-badge \(statusClass)">\(recorded ? "已写入" : "需确认")</span>
          </div>
        """
        if let photoURL {
            html += "<img class=\"diet-draft-photo\" src=\"\(escape(photoURL))\" alt=\"\(escape(mealLabel))餐食照片\"/>"
        }
        html += "<div class=\"dynamic-card-conclusion\">\(escape(foodItems))</div>"
        var metrics: [String] = []
        if let calories, !calories.isEmpty { metrics.append(metricHTML(label: "热量", value: "\(calories) kcal", risk: false)) }
        if let protein, !protein.isEmpty { metrics.append(metricHTML(label: "蛋白质", value: "\(protein) g", risk: false)) }
        if let confidence { metrics.append(metricHTML(label: "识别置信度", value: "\(Int((confidence * 100).rounded()))%", risk: false)) }
        if !metrics.isEmpty {
            html += "<div class=\"dynamic-card-metrics\">\(metrics.joined())</div>"
        }
        if let receiptMessage, !receiptMessage.isEmpty {
            html += "<div class=\"dynamic-card-detail\">\(escape(receiptMessage))</div>"
        } else {
            html += "<div class=\"dynamic-card-detail\">\(escape(boundary))</div>"
        }
        return html + "</div>"
    }

    private static func medicationDraftCardHTML(_ data: AgentDynamicCardValue) -> String? {
        guard case .object = data else { return nil }
        let items = (data["items"]?.arrayValue ?? []).compactMap { value -> (String, String?, String?)? in
            guard case .object(let item) = value,
                  let name = cardText(item["medication_name"]) else {
                return nil
            }
            return (
                name,
                cardText(item["actual_dosage"]),
                cardText(item["observed_strength"])
            )
        }
        let receipts = (data["write_receipts"]?.arrayValue ?? []).filter { value in
            guard case .object(let receipt) = value else { return false }
            return receipt["resource_type"]?.stringValue == "medication_log"
                && receipt["verified"]?.boolValue == true
                && cardText(receipt["resource_id"]) != nil
        }
        let safetyAlerts = (data["safety_alerts"]?.arrayValue ?? []).compactMap { value -> AgentDynamicCardValue? in
            guard case .object(let alert) = value,
                  cardText(alert["title"]) != nil,
                  cardText(alert["message"]) != nil else {
                return nil
            }
            return value
        }
        let rawStatus = cardText(data["decision_status"]) ?? "pending"
        let status = ["executed", "dismissed", "expired", "not_written"].contains(rawStatus)
            ? rawStatus
            : "pending"
        let reconciliationRequired = data["reconciliation_required"]?.boolValue == true
            || (status == "executed" && (receipts.isEmpty || (!items.isEmpty && receipts.count != items.count)))
        let statusMeta: (title: String, badge: String, badgeClass: String)
        if reconciliationRequired {
            statusMeta = ("用药 · 状态待核对", "核对中", "caution")
        } else {
            switch status {
            case "executed": statusMeta = ("用药 · 已记录", "已保存", "neutral")
            case "dismissed": statusMeta = ("用药 · 已取消", "未写入", "neutral")
            case "expired": statusMeta = ("用药 · 确认已过期", "未写入", "caution")
            case "not_written": statusMeta = ("用药 · 未写入", "需重新核对", "caution")
            default: statusMeta = ("用药 · 待确认", "需核对", "caution")
            }
        }

        var html = """
        <div class="dynamic-card medication-draft-card" aria-busy="\(data["action_pending"]?.boolValue == true ? "true" : "false")">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">本次服药记录</div>
              <div class="dynamic-card-title">\(escape(statusMeta.title))</div>
            </div>
            <span class="dynamic-card-badge \(statusMeta.badgeClass)">\(escape(statusMeta.badge))</span>
          </div>
        """
        if !items.isEmpty {
            html += "<ol class=\"medication-item-list\" aria-label=\"本次用药项目\">"
            for item in items {
                var details: [String] = []
                if let dosage = item.1 { details.append("本次 \(dosage)") }
                if let strength = item.2 { details.append("规格 \(strength)") }
                html += "<li class=\"medication-item\"><strong>\(escape(item.0))</strong>"
                if !details.isEmpty {
                    html += "<span>\(escape(details.joined(separator: " · ")))</span>"
                }
                html += "</li>"
            }
            html += "</ol>"
        } else {
            let fallback = cardText(data["medication_name"]) ?? "待确认用药"
            html += "<div class=\"dynamic-card-conclusion\">\(escape(fallback))</div>"
        }
        if let takenAt = cardText(data["taken_at"] ?? data["taken_time"]) {
            html += "<div class=\"dynamic-card-detail\">记录时间 \(escape(takenAt.replacingOccurrences(of: "T", with: " ")))</div>"
        }
        if data["action_pending"]?.boolValue == true {
            html += "<div class=\"dynamic-card-warning\" role=\"status\" aria-live=\"polite\">正在提交并核对服务端结果…</div>"
        } else if reconciliationRequired {
            html += "<div class=\"dynamic-card-warning\" role=\"alert\">服务端显示已执行，但逐项回执尚未完整恢复。请刷新对话后核对，系统不会据此重复写入。</div>"
        } else {
            switch status {
            case "dismissed":
                html += "<div class=\"dynamic-card-detail\" role=\"status\">这组记录已取消，没有写入。</div>"
            case "expired":
                html += "<div class=\"dynamic-card-warning\" role=\"status\">这组确认已过期，没有写入；请重新发送完整药名和本次实际服量。</div>"
            case "not_written":
                html += "<div class=\"dynamic-card-warning\" role=\"status\">服务端未接受这次确认，没有写入；请刷新对话后重新核对。</div>"
            case "pending":
                let boundary = cardText(data["boundary"])
                    ?? "确认后只记录这次已服事实；不替代医嘱，不调整剂量或频次。"
                html += "<div class=\"dynamic-card-detail\">\(escape(boundary))</div>"
            default:
                break
            }
        }
        if status == "executed" && !receipts.isEmpty {
            html += "<ol class=\"medication-receipt-list\" aria-label=\"逐项写入回执\">"
            for (index, value) in receipts.enumerated() {
                guard case .object(let receipt) = value else { continue }
                let itemLabel = items.indices.contains(index)
                    ? [items[index].0, items[index].1].compactMap { $0 }.joined(separator: " · ")
                    : "第 \(index + 1) 项用药"
                html += "<li class=\"medication-receipt\"><strong>\(escape(itemLabel))</strong><span>回执 #\(escape(cardText(receipt["resource_id"]) ?? "-")) · 已验证</span></li>"
            }
            html += "</ol>"
        }
        if status == "executed" && !safetyAlerts.isEmpty {
            html += "<ul class=\"medication-safety-list\" aria-label=\"用药安全提示\">"
            for value in safetyAlerts {
                guard case .object(let alert) = value else { continue }
                let severityValue = cardNumber(alert["severity"]?["value"] ?? alert["severity"]) ?? 0
                let severityLabel = cardText(alert["severity"]?["label_zh"])
                    ?? cardText(alert["severity"]?["label"])
                    ?? (severityValue >= 3 ? "高风险" : "提示")
                let role = severityValue >= 3 ? " role=\"alert\"" : ""
                html += "<li class=\"medication-safety-alert\"\(role)><div><strong>\(escape(cardText(alert["title"]) ?? "用药安全提示"))</strong><span>\(escape(severityLabel))</span></div><p>\(escape(cardText(alert["message"]) ?? ""))</p>"
                for action in cardStringArray(alert["action"]) {
                    html += "<p><strong>\(escape(action))</strong></p>"
                }
                html += "</li>"
            }
            html += "</ul>"
        }
        return html + "</div>"
    }

    private static func aigcMediaJobCardHTML(_ data: AgentDynamicCardValue) -> String? {
        guard case .object = data else { return nil }
        let kind = data["kind"]?.stringValue ?? ""
        let status = (data["status"]?.stringValue ?? "queued").lowercased()
        let title = cardText(data["title"]) ?? "小巴创作"
        let progress = min(max(data["progress"]?.intValue ?? 0, 0), 100)
        let kindLabel: String
        switch kind {
        case "text_to_image": kindLabel = "文生图"
        case "image_to_image": kindLabel = "图片创作"
        case "text_to_video": kindLabel = "文生短视频"
        case "image_to_video": kindLabel = "图生短视频"
        default: kindLabel = "媒体创作"
        }
        let statusLabel: String
        switch status {
        case "running": statusLabel = "生成中"
        case "succeeded": statusLabel = "已完成"
        case "failed": statusLabel = "未完成"
        case "cancelled": statusLabel = "已取消"
        case "submission_unknown": statusLabel = "提交待核验"
        default: statusLabel = "排队中"
        }
        let errorMessage = cardText(data["error_message"])
        let result = data["result"]
        let mediaType = result?["media_type"]?.stringValue?.lowercased() ?? ""
        let resultURL = privateAIGCMediaURL(result?["url"]?.stringValue)

        var html = """
        <div class="dynamic-card aigc-media-card">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">小巴创作</div>
              <div class="dynamic-card-title">\(escape(title))</div>
            </div>
            <span class="dynamic-card-badge neutral">\(escape(kindLabel))</span>
          </div>
          <div class="dynamic-card-conclusion">\(escape(statusLabel))</div>
        """
        if status == "queued" || status == "running" {
            html += "<div class=\"dynamic-card-detail\">\(escape("生成进度 \(progress)%"))</div>"
        } else if status == "succeeded" {
            html += "<div class=\"dynamic-card-detail\">结果仅对当前账号可见。</div>"
        } else if let errorMessage {
            html += "<div class=\"dynamic-card-warning\">\(escape(errorMessage))</div>"
        }
        if let resultURL {
            if mediaType.hasPrefix("image/") {
                html += "<a class=\"aigc-media-result\" href=\"\(escape(resultURL))\" target=\"_blank\" rel=\"noreferrer\"><img class=\"aigc-media-image\" src=\"\(escape(resultURL))\" alt=\"小巴生成的图片\"/></a>"
            } else if mediaType.hasPrefix("video/") {
                html += "<a class=\"dynamic-card-action primary\" href=\"\(escape(resultURL))\" target=\"_blank\" rel=\"noreferrer\">打开短视频</a>"
            }
        }
        return html + "</div>"
    }

    private static func aigcMediaConfirmationCardHTML(_ data: AgentDynamicCardValue) -> String? {
        guard case .object = data,
              let id = data["confirmation_id"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines),
              !id.isEmpty else { return nil }
        let kind = data["kind"]?.stringValue ?? ""
        let kindLabel: String
        switch kind {
        case "text_to_image": kindLabel = "文生图"
        case "image_to_image": kindLabel = "图片创作"
        case "text_to_video": kindLabel = "文生短视频"
        case "image_to_video": kindLabel = "图生短视频"
        default: kindLabel = "媒体创作"
        }
        let provider = cardText(data["provider"]) ?? "百炼 Wan"
        let sourceAttached = data["source_attached"]?.boolValue == true
        let sentContent = sourceAttached ? "你的创作描述和当前图片" : "你的创作描述"
        return """
        <div class="dynamic-card aigc-media-card">
          <div class="dynamic-card-top">
            <div><div class="dynamic-card-eyebrow">小巴创作</div><div class="dynamic-card-title">小巴创作草稿</div></div>
            <span class="dynamic-card-badge neutral">\(escape(kindLabel))</span>
          </div>
          <div class="dynamic-card-detail">将发送\(escape(sentContent))给\(escape(provider))生成。</div>
          <a class="dynamic-card-action primary" href="xiaoba-aigc-confirm://\(escape(id))">发送给百炼并生成</a>
        </div>
        """
    }

    private static func privateAIGCMediaURL(_ raw: String?) -> String? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              raw.hasPrefix("/api/v1/upload/files/aigc/") else {
            return nil
        }
        return URL(string: raw, relativeTo: APIEndpoint.resolvedBaseURL())?.absoluteURL.absoluteString
    }

    private static func privateDietPhotoURL(_ raw: String?) -> String? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              raw.hasPrefix("/api/v1/upload/files/diet/"),
              let url = URL(string: raw, relativeTo: APIEndpoint.resolvedBaseURL())?.absoluteURL,
              let scheme = url.scheme?.lowercased(),
              scheme == "https" || scheme == "http" else {
            return nil
        }
        return url.absoluteString
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

    // MARK: - menu_share card (designed GenUI 菜单卡)

    /// 渲染 `menu_share` 结构化菜单卡(暖色 Claude Design 调性)。
    /// schema: { title, items:[{name,qty?,kcal?,protein?,carbs?,fat?,fiber?}], reason?,
    ///           totals?:{kcal?,protein?,carbs?,fat?,fiber?}, shopping_list?:[str] }。
    /// 所有可选字段缺失都安全降级(不产出对应块);header 恒为 title(绝不显示 "menu_share"),
    /// body 是真菜单(菜品清单 + 营养 + 总计 + 买菜清单),不是 key-value dump。
    /// 布局确定性:菜品用固定列的 `<table>`(浏览器排版),无 SwiftUI 弹性协商,零冻结风险。
    static func menuShareCardHTML(_ data: AgentDynamicCardValue) -> String? {
        guard case .object = data else {
            return nil
        }
        let title = cardText(data["title"]) ?? "今日菜单"
        let reason = cardText(data["reason"])

        var html = """
        <div class="dynamic-card menu-share-card">
          <div class="dynamic-card-top">
            <div>
              <div class="dynamic-card-eyebrow">今日菜单</div>
              <div class="dynamic-card-title">\(escape(title))</div>
            </div>
            <span class="dynamic-card-badge neutral">可分享给家人</span>
          </div>
        """
        if let reason {
            html += "<div class=\"menu-share-reason\">\(escape(reason))</div>"
        }

        let itemsTable = menuShareItemsTableHTML(data["items"])
        if !itemsTable.isEmpty {
            html += itemsTable
        }

        let totals = menuShareTotalsHTML(data["totals"])
        if !totals.isEmpty {
            html += totals
        }

        let shopping = menuShareShoppingListHTML(data["shopping_list"])
        if !shopping.isEmpty {
            html += shopping
        }

        html += "</div>"
        return html
    }

    /// 菜品清单渲染成一张固定列的表:菜名 · 分量 · 关键营养(kcal / 蛋白 …)。
    /// 每行的营养列只在有值时拼(全缺则该列显示 "—")。items 为空/非数组 → 返回 ""。
    private static func menuShareItemsTableHTML(_ value: AgentDynamicCardValue?) -> String {
        guard case .array(let items) = value, !items.isEmpty else {
            return ""
        }
        // 是否有任一菜品带营养/分量列 —— 决定是否画对应表头(不给空列)。
        var anyQty = false
        var anyNutrient = false
        for item in items {
            if cardText(item["qty"]) != nil {
                anyQty = true
            }
            if menuShareNutrientSummary(item) != nil {
                anyNutrient = true
            }
        }

        var header = "<tr><th>菜品</th>"
        if anyQty {
            header += "<th>分量</th>"
        }
        if anyNutrient {
            header += "<th>营养</th>"
        }
        header += "</tr>"

        var rows = ""
        for item in items.prefix(12) {
            let name = cardText(item["name"]) ?? "—"
            var row = "<tr><td class=\"menu-share-dish\">\(escape(name))</td>"
            if anyQty {
                let qty = cardText(item["qty"]) ?? ""
                row += "<td class=\"menu-share-qty\">\(escape(qty))</td>"
            }
            if anyNutrient {
                let nutrient = menuShareNutrientSummary(item) ?? "—"
                row += "<td class=\"menu-share-nutrient\">\(escape(nutrient))</td>"
            }
            row += "</tr>"
            rows += row
        }

        return "<table class=\"menu-share-items\">\(header)\(rows)</table>"
    }

    /// 单个菜品的营养摘要:kcal · 蛋白Ng · 碳Ng · 脂Ng · 纤Ng(只拼有值的)。全缺 → nil。
    private static func menuShareNutrientSummary(_ item: AgentDynamicCardValue) -> String? {
        var parts: [String] = []
        if let kcal = cardNumber(item["kcal"]) {
            parts.append("\(menuShareNumberLabel(kcal))kcal")
        }
        if let protein = cardNumber(item["protein"]) {
            parts.append("蛋白\(menuShareNumberLabel(protein))g")
        }
        if let carbs = cardNumber(item["carbs"]) {
            parts.append("碳\(menuShareNumberLabel(carbs))g")
        }
        if let fat = cardNumber(item["fat"]) {
            parts.append("脂\(menuShareNumberLabel(fat))g")
        }
        if let fiber = cardNumber(item["fiber"]) {
            parts.append("纤\(menuShareNumberLabel(fiber))g")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// totals 摘要行(总计 kcal / 蛋白 / 碳 / 脂 / 纤,只显示有值的)。缺 → ""。
    private static func menuShareTotalsHTML(_ value: AgentDynamicCardValue?) -> String {
        guard let value, case .object = value else {
            return ""
        }
        var chips: [(String, String)] = []
        if let kcal = cardNumber(value["kcal"]) {
            chips.append(("总热量", "\(menuShareNumberLabel(kcal))kcal"))
        }
        if let protein = cardNumber(value["protein"]) {
            chips.append(("蛋白", "\(menuShareNumberLabel(protein))g"))
        }
        if let carbs = cardNumber(value["carbs"]) {
            chips.append(("碳水", "\(menuShareNumberLabel(carbs))g"))
        }
        if let fat = cardNumber(value["fat"]) {
            chips.append(("脂肪", "\(menuShareNumberLabel(fat))g"))
        }
        if let fiber = cardNumber(value["fiber"]) {
            chips.append(("纤维", "\(menuShareNumberLabel(fiber))g"))
        }
        guard !chips.isEmpty else {
            return ""
        }
        let cells = chips.map { label, value in
            "<div class=\"menu-share-total\"><span class=\"menu-share-total-label\">\(escape(label))</span><span class=\"menu-share-total-value\">\(escape(value))</span></div>"
        }.joined()
        return "<div class=\"menu-share-totals\">\(cells)</div>"
    }

    /// 买菜清单(chips)。空/非数组 → ""。
    private static func menuShareShoppingListHTML(_ value: AgentDynamicCardValue?) -> String {
        let items = cardStringArray(value).prefix(24)
        guard !items.isEmpty else {
            return ""
        }
        let chips = items.map { "<span class=\"menu-share-chip\">\(escape($0))</span>" }.joined()
        return """
        <div class="menu-share-shopping">
          <div class="menu-share-shopping-label">买菜清单</div>
          <div class="menu-share-chips">\(chips)</div>
        </div>
        """
    }

    /// 营养数字紧凑标签:整数去掉小数;非整数保留一位小数。
    private static func menuShareNumberLabel(_ value: Double) -> String {
        if value.rounded() == value {
            return String(Int(value))
        }
        return String(format: "%.1f", value)
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
        actions: [AgentDynamicCardActionDescriptor],
        cardType: String
    ) -> String {
        let actionBar = dynamicCardActionsHTML(actions, cardType: cardType)
        guard !actionBar.isEmpty,
              let closingRange = html.range(of: "</div>", options: .backwards) else {
            return html
        }
        var result = html
        result.replaceSubrange(closingRange, with: "\(actionBar)\n</div>")
        return result
    }

    private static func dynamicCardActionsHTML(
        _ actions: [AgentDynamicCardActionDescriptor],
        cardType: String
    ) -> String {
        let items = actions.compactMap { action -> String? in
            let label = action.label.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !label.isEmpty else {
                return nil
            }
            if action.action == "ui.inline.expand" {
                return inlineExpandActionHTML(action, label: label)
            }
            if action.action == "diet_record.create",
               action.requiresManualConfirm == true,
               action.requiredReceipt == true,
               action.capabilityID == "diet_draft.v1",
               let id = action.id,
               isSafeCardActionIdentifier(id) {
                let styleClass = action.style == "primary" ? "primary" : "secondary"
                return "<a class=\"dynamic-card-action \(styleClass)\" href=\"xiaoba-diet-confirm://\(escape(id))\">\(escape(label))</a>"
            }
            if (action.action == "write_intent.confirm" || action.action == "write_intent.dismiss"),
               cardType == "medication_draft",
               MedicationBatchCardProjection.isSafeAction(action),
               let id = action.id,
               isSafeCardActionIdentifier(id),
               let intentID = MedicationBatchCardProjection.intentID(for: action) {
                let styleClass = action.style == "primary" ? "primary" : "secondary"
                return "<a class=\"dynamic-card-action medication-batch-action \(styleClass)\" href=\"xiaoba-medication-action://\(escape(id))\" role=\"button\" aria-label=\"\(escape(label))\" data-write-intent-id=\"\(intentID)\">\(escape(label))</a>"
            }
            guard action.action == "route.open",
                  let route = action.payload?["route"]?.stringValue?
                    .trimmingCharacters(in: .whitespacesAndNewlines),
                  isSafeInternalRoute(route),
                  // mac 执行不了的路由不画按钮 —— 死键点了没反应比没有按钮更糟
                  // (Rule#1:不假装成功)。可执行 = /chat?prompt 或已映射侧边栏页。
                  DynamicCardRouting.isActionable(route: route) else {
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

    private static func isSafeCardActionIdentifier(_ value: String) -> Bool {
        guard !value.isEmpty, value.count <= 200 else { return false }
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-:")
        return value.unicodeScalars.allSatisfy { allowed.contains($0) }
    }

    private static func inlineExpandActionHTML(
        _ action: AgentDynamicCardActionDescriptor,
        label: String
    ) -> String? {
        let target = action.payload?["target"]?.stringValue?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard action.endpoint == nil,
              !target.isEmpty,
              let detail = action.payload?["patch"]?["next_meal_detail"] else {
            return nil
        }
        let title = detail["title"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        let summary = detail["summary"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        let context = detail["context"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        let continuePrompt = detail["continue_prompt"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        let options = detail["options"]?.arrayValue?.compactMap {
            $0.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.isEmpty }.prefix(6) ?? []
        let rationale = detail["rationale"]?.arrayValue?.compactMap {
            $0.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.isEmpty }.prefix(6) ?? []
        var body = "<div class=\"dynamic-inline-detail\">"
        body += "<div class=\"dynamic-inline-title\">\(escape(title?.isEmpty == false ? title! : "下一餐建议"))</div>"
        if let context, !context.isEmpty {
            body += "<div class=\"dynamic-inline-context\">\(escape(context))</div>"
        }
        if let summary, !summary.isEmpty {
            body += "<div class=\"dynamic-inline-summary\">\(escape(summary))</div>"
        }
        if !options.isEmpty {
            body += "<ol class=\"dynamic-inline-list\">"
            for option in options {
                body += "<li>\(escape(option))</li>"
            }
            body += "</ol>"
        }
        if !rationale.isEmpty {
            body += "<div class=\"dynamic-inline-rationale\">"
            for item in rationale {
                body += "<div>依据：\(escape(item))</div>"
            }
            body += "</div>"
        }
        if let continuePrompt, !continuePrompt.isEmpty {
            body += "<div class=\"dynamic-inline-context\">\(escape(continuePrompt))</div>"
        }
        body += "</div>"
        let styleClass = action.style == "primary" ? "primary" : "secondary"
        return """
        <details class="dynamic-card-inline-action \(styleClass)"><summary>\(escape(label))</summary>\(body)</details>
        """
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
        // Compound value ("A · B", e.g. 今日蛋白 "33/114g · 还差81g") stacks into a
        // primary value (nowrap) + a smaller sub-line, instead of wrapping mid-token
        // into an ugly "33/114g·还 / 差81g" inside a ~92px tile. Generic: any middot
        // (U+00B7)-joined value splits ONCE on the first separator; no separator →
        // single value as before. Primary keeps the .risk clay-ink highlight.
        if let (primary, secondary) = splitCompoundMetricValue(value) {
            return """
            <div class="dynamic-card-metric">
              <div class="dynamic-card-metric-label">\(escape(label))</div>
              <div class="dynamic-card-metric-value\(riskClass)">\(escape(primary))</div>
              <div class="dynamic-card-metric-sub">\(escape(secondary))</div>
            </div>
            """
        }
        return """
        <div class="dynamic-card-metric">
          <div class="dynamic-card-metric-label">\(escape(label))</div>
          <div class="dynamic-card-metric-value\(riskClass)">\(escape(value))</div>
        </div>
        """
    }

    /// Split a compound metric value on the FIRST middot (U+00B7) into a primary +
    /// secondary part (surrounding whitespace trimmed). Returns nil when there is no
    /// middot or either side is empty → caller renders a single value.
    static func splitCompoundMetricValue(_ value: String) -> (primary: String, secondary: String)? {
        guard let range = value.range(of: "\u{00B7}") else {
            return nil
        }
        let primary = value[..<range.lowerBound].trimmingCharacters(in: .whitespaces)
        let secondary = value[range.upperBound...].trimmingCharacters(in: .whitespaces)
        guard !primary.isEmpty, !secondary.isEmpty else {
            return nil
        }
        return (primary, secondary)
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

    private static func cleanCardIdentifier(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmed.isEmpty, trimmed.rangeOfCharacter(from: .controlCharacters) == nil else {
            return nil
        }
        return String(trimmed.prefix(80))
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
            if let title = cardString(object["title"]) {
                return title
            }
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
        /// Short hover label (HH:mm) and full tooltip/accessibility label.
        public let sentAtShort: String
        public let sentAtFull: String
        public let sentAtEpochMs: Int64?

        public init(
            id: String,
            role: String,
            bodyHTML: String,
            isStreaming: Bool,
            showCopy: Bool,
            footerHTML: String = "",
            sentAtShort: String = "",
            sentAtFull: String = "",
            sentAtEpochMs: Int64? = nil
        ) {
            self.id = id
            self.role = role
            self.bodyHTML = bodyHTML
            self.isStreaming = isStreaming
            self.showCopy = showCopy
            self.footerHTML = footerHTML
            self.sentAtShort = sentAtShort
            self.sentAtFull = sentAtFull
            self.sentAtEpochMs = sentAtEpochMs
        }

        /// 序列化为 JS 对象字面量字符串(不依赖 Foundation JSONEncoder 的键序,字段固定)。
        public var jsonObject: String {
            let sentAtEpoch = sentAtEpochMs.map(String.init) ?? "null"
            return "{\"id\":\(Self.jsString(id)),\"role\":\(Self.jsString(role)),\"html\":\(Self.jsString(bodyHTML)),\"streaming\":\(isStreaming ? "true" : "false"),\"copy\":\(showCopy ? "true" : "false"),\"footer\":\(Self.jsString(footerHTML)),\"sentAtShort\":\(Self.jsString(sentAtShort)),\"sentAtFull\":\(Self.jsString(sentAtFull)),\"sentAtEpochMs\":\(sentAtEpoch)}"
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

    /// `appendOrUpdateLast` is safe only when every message before the final
    /// slot is byte-for-byte unchanged. Interactive cards may update an older
    /// assistant row, in which case the WebView must receive a full transcript
    /// replacement instead of silently repainting only the last message.
    public static func canAppendOrUpdateLast(
        previous: [RenderedMessage],
        next: [RenderedMessage]
    ) -> Bool {
        guard !previous.isEmpty,
              next.count >= previous.count,
              next.count <= previous.count + 1 else {
            return false
        }
        if next.count == previous.count,
           next.last?.id != previous.last?.id {
            return false
        }
        let unchangedPrefixCount = next.count == previous.count
            ? max(previous.count - 1, 0)
            : previous.count
        return Array(next.prefix(unchangedPrefixCount))
            == Array(previous.prefix(unchangedPrefixCount))
    }

    // MARK: - Thinking-process trace (rendered inside the streaming assistant bubble)

    /// The "thinking process" trace as a collapsible `<details>` inside the assistant
    /// bubble, so it sits with the answer (top of a short chat, bottom of a scrolled
    /// one) and — mobile-style — stays reviewable after the answer instead of
    /// vanishing. `open` = expanded (live, during the wait) vs collapsed (answer
    /// streaming / completed). Repeated activities fold into distinct rows with a ×N
    /// count; the collapsed header briefly names what was looked at / called. Labels
    /// resolved via `L10n.text` (the `"Working: %@…"` key splices the backend zh tool
    /// label). Empty steps → "" (caller falls back to `thinkingLineHTML`).
    public static func thinkingTraceHTML(steps: [ThinkingStep], language: String, open: Bool) -> String {
        guard !steps.isEmpty else { return "" }
        let lang = AppLanguage(rawValue: language) ?? .defaultLanguage
        func composite(_ key: String, _ detail: String?) -> String { key + "\u{1}" + (detail ?? "") }
        func resolve(_ key: String, _ detail: String?) -> String {
            let template = L10n.text(key, language: lang)
            if let detail { return String(format: template, detail) }
            return template
        }
        // De-clutter: fold repeated activities (the backend often emits the same tool
        // status many times) into distinct rows in first-occurrence order, with counts.
        var order: [(key: String, detail: String?)] = []
        var count: [String: Int] = [:]
        for step in steps {
            let ck = composite(step.labelKey, step.labelDetail)
            if count[ck] == nil { order.append((step.labelKey, step.labelDetail)) }
            count[ck, default: 0] += 1
        }
        // Only the latest step's activity spins; everything else is done.
        var runningKey: String? = nil
        if let last = steps.last, last.state == .running {
            runningKey = composite(last.labelKey, last.labelDetail)
        }
        var rowsHTML = ""
        for item in order {
            let ck = composite(item.key, item.detail)
            let running = ck == runningKey
            let glyph = running
                ? "<span class=\"rv-tk-spin\"></span>"
                : "<span class=\"rv-tk-done\">✓</span>"
            let rowCls = running ? "rv-tk-row rv-tk-run" : "rv-tk-row"
            var label = resolve(item.key, item.detail)
            if let n = count[ck], n > 1 { label += " ×\(n)" }
            rowsHTML += "<div class=\"\(rowCls)\"><span class=\"rv-tk-g\">\(glyph)</span><span>\(escape(label))</span></div>"
        }
        // Brief header hint of what was looked at / called: the distinct tool-detail
        // labels (the `Working: %@` steps carry the concrete activity), capped short.
        var briefParts: [String] = []
        for item in order {
            if let d = item.detail, !d.isEmpty, !briefParts.contains(d) { briefParts.append(d) }
        }
        let brief = briefParts.prefix(4).joined(separator: "、")
        let title = escape(L10n.text("Thinking process", language: lang))
        let briefHTML = brief.isEmpty ? "" : "<span class=\"rv-tk-brief\"> · \(escape(brief))</span>"
        let openAttr = open ? " open" : ""
        let classes = open ? "thinking-trace thinking-trace-live" : "thinking-trace"
        return thinkingStyle
            + "<details class=\"\(classes)\"\(openAttr)><summary class=\"rv-tk-sum\">\(title)\(briefHTML)</summary><div class=\"rv-tk-body\">\(rowsHTML)</div></details>"
    }

    /// Single-line fallback for backends that emit no `status` steps (thinkingSteps
    /// empty). `text` is already localized. Not collapsible — there's nothing to fold.
    public static func thinkingLineHTML(_ text: String) -> String {
        thinkingStyle
            + "<div class=\"rv-tk-line\"><span class=\"rv-tk-g\"><span class=\"rv-tk-spin\"></span></span><span>\(escape(text))</span></div>"
    }

    /// Shared inline styles for the in-bubble trace. Self-contained (no dependency on
    /// chat-transcript.html CSS), legible on light/dark. The header disclosure is a
    /// pure-CSS chevron (no emoji/brain icon) that rotates open↔closed.
    private static let thinkingStyle = """
    <style>
    .rv-tk,.thinking-trace{font-size:12.5px;margin:2px 0 6px;border-left:2px solid rgba(140,143,152,.22);padding-left:10px}
    .rv-tk-sum{list-style:none;cursor:pointer;color:#8a8f98;font-weight:600;display:flex;align-items:center;gap:6px;user-select:none;-webkit-user-select:none}
    .rv-tk-sum::-webkit-details-marker{display:none}
    .rv-tk-sum::before{content:"";width:5px;height:5px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(-45deg);transition:transform .15s ease;display:inline-block;opacity:.7;margin-right:1px}
    .rv-tk[open] .rv-tk-sum::before,.thinking-trace[open] .rv-tk-sum::before{transform:rotate(45deg)}
    .rv-tk-brief{font-weight:400;color:#9aa0a8}
    .rv-tk-body{margin-top:6px}
    .rv-tk-row{display:flex;align-items:flex-start;gap:8px;color:#8a8f98;line-height:1.5;margin:3px 0}
    .rv-tk-run{color:inherit}
    .rv-tk-line{display:flex;align-items:center;gap:8px;color:#8a8f98;line-height:1.5;margin:2px 0}
    .rv-tk-g{flex:0 0 15px;display:inline-flex;justify-content:center;align-items:center;align-self:flex-start;margin-top:2px}
    .rv-tk-done{color:#3aa76d;font-size:12px}
    .rv-tk-spin{width:10px;height:10px;border:2px solid rgba(140,143,152,.4);border-top-color:#3aa76d;border-radius:50%;display:inline-block;animation:rv-tk-rot .7s linear infinite}
    @keyframes rv-tk-rot{to{transform:rotate(360deg)}}
    </style>
    """
}
