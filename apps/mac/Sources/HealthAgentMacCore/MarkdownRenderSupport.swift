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
    public static func sanitizedForSwiftUI(_ markdown: String) -> String {
        markdown
            .replacingOccurrences(of: "\r\n", with: "\n")
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { sanitizeLine(String($0)) }
            .joined(separator: "\n")
    }

    public static func blocks(from markdown: String) -> [MarkdownRenderBlock] {
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
