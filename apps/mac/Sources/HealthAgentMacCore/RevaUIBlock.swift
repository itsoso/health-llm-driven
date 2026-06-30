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
    /// 只识别 info string 恰为 `reva-ui`(去空白后)的围栏;其它语言的代码围栏(```json 等)
    /// 不拦截,留给普通 markdown 路径(当前解析器会按文本展示,行为不变)。
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
            if isRevaUIFenceOpen(line) {
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
                    segments.append(.revaUI(jsonLines.joined(separator: "\n")))
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
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("```") else { return false }
        let info = trimmed.dropFirst(3).trimmingCharacters(in: .whitespaces)
        return info == "reva-ui"
    }

    /// 一行是否是代码围栏的闭合:仅由 ``` 与空白组成(info string 必须为空)。
    static func isFenceClose(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("```") else { return false }
        return trimmed.dropFirst(3).trimmingCharacters(in: .whitespaces).isEmpty
    }
}
