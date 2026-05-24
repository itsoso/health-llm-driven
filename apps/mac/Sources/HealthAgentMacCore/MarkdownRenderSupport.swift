import Foundation

public enum MarkdownRenderSupport {
    public static func sanitizedForSwiftUI(_ markdown: String) -> String {
        markdown
            .replacingOccurrences(of: "\r\n", with: "\n")
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { sanitizeLine(String($0)) }
            .joined(separator: "\n")
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
