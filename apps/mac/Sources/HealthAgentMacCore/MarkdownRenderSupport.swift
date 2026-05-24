import Foundation

public enum MarkdownRenderSupport {
    public static func sanitizedForSwiftUI(_ markdown: String) -> String {
        markdown
            .replacingOccurrences(of: "\r\n", with: "\n")
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { sanitizeLine(String($0)) }
            .joined(separator: "\n")
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
