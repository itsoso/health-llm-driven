import Foundation

public enum MarkdownRenderBlock: Equatable, Sendable {
    case heading(level: Int, text: String)
    case paragraph(String)
    case bullet(String)
    case numbered(index: String, text: String)
    case tableRow([String])
    case divider
}

public enum MarkdownRenderSupport {
    // markdown → blocks 解析缓存。SwiftUI 的 MarkdownMessageText.body 每次求值都调
    // blocks();聊天列表逐 token 重渲染时,会把每条消息全量重解析(O(消息数×长度)/token,
    // 长回复尤其卡)。按内容字符串缓存后,未变消息(流式中已完成的、字体/滚动等无关状态
    // 变化)直接命中,不再重解析。NSCache 内部线程安全 + countLimit 有界,不会无限增长。
    private final class BlocksBox {
        let blocks: [MarkdownRenderBlock]
        init(_ blocks: [MarkdownRenderBlock]) { self.blocks = blocks }
    }
    nonisolated(unsafe) private static let blocksCache: NSCache<NSString, BlocksBox> = {
        let cache = NSCache<NSString, BlocksBox>()
        cache.countLimit = 512
        return cache
    }()

    public static func sanitizedForSwiftUI(_ markdown: String) -> String {
        markdown
            .replacingOccurrences(of: "\r\n", with: "\n")
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { sanitizeLine(String($0)) }
            .joined(separator: "\n")
    }

    public static func blocks(from markdown: String) -> [MarkdownRenderBlock] {
        let key = markdown as NSString
        if let cached = blocksCache.object(forKey: key) {
            return cached.blocks
        }
        let parsed = parseBlocks(from: markdown)
        blocksCache.setObject(BlocksBox(parsed), forKey: key)
        return parsed
    }

    private static func parseBlocks(from markdown: String) -> [MarkdownRenderBlock] {
        var blocks: [MarkdownRenderBlock] = []
        var paragraphLines: [String] = []

        func flushParagraph() {
            let text = paragraphLines
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
                .joined(separator: " ")
            if !text.isEmpty {
                blocks.append(.paragraph(text))
            }
            paragraphLines = []
        }

        let lines = sanitizedForSwiftUI(markdown)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map(String.init)

        for rawLine in lines {
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            if line.isEmpty {
                flushParagraph()
                continue
            }
            if line == "---" || line == "***" || line == "___" {
                flushParagraph()
                blocks.append(.divider)
                continue
            }
            if let heading = headingBlock(from: line) {
                flushParagraph()
                blocks.append(heading)
                continue
            }
            if let bullet = bulletBlock(from: line) {
                flushParagraph()
                blocks.append(bullet)
                continue
            }
            if let numbered = numberedBlock(from: line) {
                flushParagraph()
                blocks.append(numbered)
                continue
            }
            if let table = tableRowBlock(from: line) {
                flushParagraph()
                blocks.append(table)
                continue
            }
            paragraphLines.append(line)
        }
        flushParagraph()
        return blocks
    }

    public static func readableFallback(_ markdown: String) -> String {
        sanitizedForSwiftUI(markdown)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { readableLine(String($0)) }
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public static func compactPreview(from markdown: String, maxLines: Int = 3) -> String {
        let lineLimit = max(1, maxLines)
        let lines = readableFallback(markdown)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { compactLine(String($0)) }
            .filter { !$0.isEmpty }
        return lines.prefix(lineLimit).joined(separator: "\n")
    }

    private static func compactLine(_ line: String) -> String {
        var text = line.trimmingCharacters(in: .whitespacesAndNewlines)
        while text.hasPrefix("- ") || text.hasPrefix("* ") {
            text = String(text.dropFirst(2)).trimmingCharacters(in: .whitespaces)
        }
        return text
    }

    private static func readableLine(_ line: String) -> String {
        var text = line.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else {
            return ""
        }
        if text == "---" || text == "***" || text == "___" {
            return ""
        }
        if text.hasPrefix("|"), text.hasSuffix("|") {
            return text
                .split(separator: "|")
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
                .joined(separator: "  ")
        }
        while text.hasPrefix("#") {
            text.removeFirst()
        }
        text = text.trimmingCharacters(in: .whitespaces)
        if text.hasPrefix(">") {
            text.removeFirst()
            text = text.trimmingCharacters(in: .whitespaces)
        }
        return text
            .replacingOccurrences(of: "**", with: "")
            .replacingOccurrences(of: "__", with: "")
            .replacingOccurrences(of: "`", with: "")
    }

    private static func headingBlock(from line: String) -> MarkdownRenderBlock? {
        let hashes = line.prefix { $0 == "#" }.count
        guard hashes > 0, hashes <= 4 else {
            return nil
        }
        let text = line.dropFirst(hashes).trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else {
            return nil
        }
        return .heading(level: hashes, text: text)
    }

    private static func bulletBlock(from line: String) -> MarkdownRenderBlock? {
        if line.hasPrefix("- ") || line.hasPrefix("* ") {
            return .bullet(String(line.dropFirst(2)).trimmingCharacters(in: .whitespaces))
        }
        return nil
    }

    private static func numberedBlock(from line: String) -> MarkdownRenderBlock? {
        guard let dotIndex = line.firstIndex(of: ".") else {
            return nil
        }
        let prefix = String(line[..<dotIndex])
        guard !prefix.isEmpty, prefix.allSatisfy(\.isNumber) else {
            return nil
        }
        let text = line[line.index(after: dotIndex)...].trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else {
            return nil
        }
        return .numbered(index: prefix, text: text)
    }

    private static func tableRowBlock(from line: String) -> MarkdownRenderBlock? {
        guard line.hasPrefix("|"), line.hasSuffix("|") else {
            return nil
        }
        let columns = line
            .split(separator: "|")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        guard !columns.isEmpty else {
            return nil
        }
        return .tableRow(columns)
    }

    private static func sanitizeLine(_ line: String) -> String {
        if isLikelyMarkdownTableSeparator(line) {
            return ""
        }
        if let normalized = normalizeIndentedList(line) {
            return normalized
        }
        return line
    }

    private static func normalizeIndentedList(_ line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("- ") || trimmed.hasPrefix("* ") else {
            return nil
        }
        return trimmed
    }

    private static func isLikelyMarkdownTableSeparator(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("|"), trimmed.hasSuffix("|") else {
            return false
        }
        let body = trimmed.dropFirst().dropLast()
        let allowed = CharacterSet(charactersIn: " |-:")
        return !body.isEmpty && body.unicodeScalars.allSatisfy { allowed.contains($0) } && body.contains("-")
    }
}
