import Foundation

/// GenUI 契约 v0 §3.2:从 assistant 消息文本里抽出 ```reva-ui 围栏块。
///
/// 为什么在 markdown 解析**之前**抽:`MarkdownRenderSupport.blocks` 会把空行间的多行折成
/// 一段、把 `---` 判成分割线、把 `|...|` 判成表格——这些都会毁掉块内 JSON。所以必须先按
/// 原始行扫描、整段切出围栏块,再分别渲染。
///
/// 解析 + SVG 绘制不在 Swift 做(契约要求渲染在 WebView JS shell,离线自绘);Swift 只负责
/// **可靠地切出原始 JSON 文本**。流式安全:只切「闭合」围栏(开/闭 ``` 都在);
/// 未闭合的 reva-ui 围栏(流式尚未到 close,或 LLM 漏写)当作普通 markdown 文本保留——
/// 它会被 escape 后原样显示,绝不半解析、绝不崩。
public enum RevaUIBlock: Equatable, Sendable {
    case markdown(String)
    case revaUI(String)

    /// 把原始 markdown 切成「普通 markdown 段」与「reva-ui JSON 段」的有序序列。
    ///
    /// 两类受控围栏在 markdown 解析**之前**处理:
    ///  - ```reva-ui  → 抽成 `.revaUI(rawJSON)` 段(WebView JS shell 自绘图表)。
    ///  - ```menu_share → **整段剥离**(不产出任何段)。菜单卡的规范表示是后端 `done`
    ///    事件里的结构化 dynamic card,prose 里的原始 JSON 只会重复且泄漏;因此这里只
    ///    负责把它从文本里删干净(mirror reva-ui 的 pre-parse 抽取,只是落点是丢弃)。
    ///
    /// 其它语言的代码围栏(```json 等)不拦截,留给普通 markdown 路径(行为不变)。
    public static func split(from markdown: String) -> [RevaUIBlock] {
        let normalized = markdown.replacingOccurrences(of: "\r\n", with: "\n")
        let lines = normalized.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)

        var segments: [RevaUIBlock] = []
        var markdownLines: [String] = []
        var i = 0

        func flushMarkdown() {
            guard !markdownLines.isEmpty else { return }
            segments.append(.markdown(markdownLines.joined(separator: "\n")))
            markdownLines = []
        }

        while i < lines.count {
            let line = lines[i]
            if let info = fenceOpenInfo(line), info == "reva-ui" || info == "menu_share" {
                // 向后找闭合围栏(单独一行的 ``` 或带尾随空白)。
                var j = i + 1
                var found = false
                var jsonLines: [String] = []
                while j < lines.count {
                    if isFenceClose(lines[j]) {
                        found = true
                        break
                    }
                    jsonLines.append(lines[j])
                    j += 1
                }
                if found {
                    flushMarkdown()
                    if info == "reva-ui" {
                        segments.append(.revaUI(jsonLines.joined(separator: "\n")))
                    }
                    // menu_share: 闭合围栏找到即整段剥离(不产段),原始 JSON 不进 prose。
                    i = j + 1
                    continue
                } else {
                    // 未闭合:把开围栏这一行连同其后内容当普通文本保留,逐行交回 markdown 流。
                    // (不在这里吞掉——交给后续普通行处理,保证流式 partial 不丢字。)
                    markdownLines.append(line)
                    i += 1
                    continue
                }
            }
            markdownLines.append(line)
            i += 1
        }
        flushMarkdown()
        return segments
    }

    /// 一行是否是 reva-ui 围栏的开始:```reva-ui(允许前导空白与围栏后的尾随空白)。
    static func isRevaUIFenceOpen(_ line: String) -> Bool {
        fenceOpenInfo(line) == "reva-ui"
    }

    /// 一行若是代码围栏的开始,返回其 info string(去空白);否则 nil。
    ///
    /// 主路径:去空白后以 ``` 起头(与旧 `isRevaUIFenceOpen` 完全一致的严格判定,
    /// 保证 reva-ui 与普通代码围栏的既有行为**零变化**)。
    /// 容错路径:围栏前只允许**非字母数字的短前缀**(emoji / 符号,如 founder 实测的
    /// 「🍽 ```menu_share」)。前缀里出现任何字母/数字就当普通 prose 行,不误判成围栏——
    /// 避免把「用 ```json 包一下」这类叙述句错当围栏剥掉。
    static func fenceOpenInfo(_ line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard let fenceRange = trimmed.range(of: "```") else { return nil }
        let prefix = trimmed[..<fenceRange.lowerBound]
        // 前缀必须不含字母/数字(允许空、或纯 emoji/符号 + 空白)。
        let hasAlnum = prefix.unicodeScalars.contains {
            CharacterSet.alphanumerics.contains($0)
        }
        guard !hasAlnum else { return nil }
        let info = trimmed[fenceRange.upperBound...].trimmingCharacters(in: .whitespaces)
        return info
    }

    /// 一行是否是代码围栏的闭合:仅由 ``` 与空白组成(info string 必须为空)。
    static func isFenceClose(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("```") else { return false }
        return trimmed.dropFirst(3).trimmingCharacters(in: .whitespaces).isEmpty
    }

    /// 防御性收尾:剥离 prose 里**未被围栏包裹**的 menu_share 残片,再交给 markdown 渲染。
    ///
    /// `split(from:)` 只吃 ```menu_share fenced block。但 founder 实测到的畸形形态还包括:
    ///  - 单行 inline code span:`` `menu_share { … }` ``(单/多反引号,非三围栏)
    ///  - 裸文本:`🍽 menu_share { … }`(连围栏都没有)
    /// 这两种都会漏进 prose 泄漏原始 JSON。这里用「定位 `menu_share` token → 从其后第一个
    /// `{` 起做括号配平 → 连同前导反引号/emoji 一起删」的方式删干净;找不到配平的 `}`
    /// (流式未完整)则保守不删,避免误伤。菜单卡的规范表示是结构化 dynamic card,删掉
    /// prose 残片不会丢信息。
    static func stripInlineMenuShareRemnants(_ text: String) -> String {
        guard text.contains("menu_share") else { return text }
        var result = text
        // 反复扫描,直到没有可删的 menu_share {…} 片段(一条消息可能多次泄漏)。
        while let tokenRange = result.range(of: "menu_share") {
            // 从 token 之后找第一个 '{'。
            guard let braceStart = result[tokenRange.upperBound...].firstIndex(of: "{") else {
                break
            }
            // 括号配平找到匹配的 '}'。
            var depth = 0
            var braceEnd: String.Index? = nil
            var idx = braceStart
            while idx < result.endIndex {
                let ch = result[idx]
                if ch == "{" {
                    depth += 1
                } else if ch == "}" {
                    depth -= 1
                    if depth == 0 {
                        braceEnd = idx
                        break
                    }
                }
                idx = result.index(after: idx)
            }
            guard let end = braceEnd else {
                // 未配平(流式 partial):保守不删,留给下次完整时处理。
                break
            }
            // 向前吃掉紧邻的 emoji / 符号 / 反引号 / 空白前缀(如「🍽 」「`」)。
            var deleteStart = tokenRange.lowerBound
            while deleteStart > result.startIndex {
                let prev = result.index(before: deleteStart)
                let scalar = result[prev].unicodeScalars.first
                let isAlnum = scalar.map { CharacterSet.alphanumerics.contains($0) } ?? false
                let isNewline = result[prev] == "\n"
                if isAlnum || isNewline { break }
                deleteStart = prev
            }
            // 向后吃掉紧邻的反引号(闭合 inline code span)。
            var deleteEnd = result.index(after: end)
            while deleteEnd < result.endIndex, result[deleteEnd] == "`" {
                deleteEnd = result.index(after: deleteEnd)
            }
            result.replaceSubrange(deleteStart..<deleteEnd, with: "")
        }
        return result
    }
}
