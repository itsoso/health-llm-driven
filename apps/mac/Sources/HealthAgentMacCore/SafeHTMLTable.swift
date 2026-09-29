import Foundation

/// A closed, text-only table grammar, not a browser HTML sanitizer.
/// Untrusted tags/attributes never cross into the generated DOM or native bridges.
enum SafeHTMLTable {
    struct Cell: Equatable {
        var text: String
        let header: Bool
    }
    struct Table: Equatable {
        let caption: String?
        let rows: [[Cell]]
    }
    enum Segment {
        case markdown(String)
        case code(String)
        case source(String)
        case table(Table, source: String)
    }
    private static let attributes: Set<String> = [
        "style", "border", "cellpadding", "cellspacing", "width", "height", "align", "valign", "class",
    ]
    private static let inline: Set<String> = ["b", "strong", "i", "em", "span"]
    private static let groups: Set<String> = ["thead", "tbody", "tfoot"]
    private static let htmlWhitespace = CharacterSet(charactersIn: " \t\n\r\u{0c}")

    static func containsHTMLCandidate(_ source: String) -> Bool {
        source.range(of: "<table\\b", options: [.regularExpression, .caseInsensitive]) != nil
            || source.components(separatedBy: "\n").contains { line in
                guard let fence = openingFence(line) else { return false }
                return fence.language == "html" || fence.language == "htm"
            }
    }

    /// Preserve the old JSON-only display cleanup, but never let it erase a
    /// Markdown boundary around HTML, nested code samples or malformed input.
    static func isLegacyJSONCode(_ source: String) -> Bool {
        guard !containsHTMLCandidate(source) else { return false }
        let lines = source.components(separatedBy: "\n")
        guard let first = lines.first, let fence = openingFence(first),
              fence.marker == "`", fence.count == 3,
              fence.language == "json" || fence.language.isEmpty else { return false }
        let nonemptyEnd = lines.lastIndex { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        guard let end = nonemptyEnd, end > 0, closesFence(lines[end], fence) else { return false }
        let payload = lines[1..<end].joined(separator: "\n")
        return (try? JSONSerialization.jsonObject(with: Data(payload.utf8))) != nil
    }

    /// Fence scanning happens before Markdown parsing. Other-language fences are
    /// opaque, so an apparent raw table inside one cannot acquire preview status.
    static func segments(from source: String) -> [Segment] {
        let allowBodyProtocols = !containsHTMLCandidate(source)
        let lines = source.components(separatedBy: "\n")
        var result: [Segment] = []
        var plain: [String] = []
        var i = 0
        func originalLines(_ first: Int, _ last: Int) -> String {
            lines[first...last].joined(separator: "\n") + (last < lines.count - 1 ? "\n" : "")
        }
        func flush() {
            if !plain.isEmpty { result.append(.markdown(plain.joined())) }
            plain = []
        }
        while i < lines.count {
            let legacyProtocol = allowBodyProtocols ? nil : RevaUIBlock.fenceOpenInfo(lines[i])
            let opaqueLegacyFence: Fence? = (legacyProtocol == "reva-ui" || legacyProtocol == "menu_share")
                ? Fence(marker: "`", count: 3, language: legacyProtocol!) : nil
            if let fence = openingFence(lines[i]) ?? opaqueLegacyFence {
                var end = i + 1
                while end < lines.count && !closesFence(lines[end], fence) { end += 1 }
                let closed = end < lines.count
                let last = closed ? end : lines.count - 1
                let original = originalLines(i, last)
                if fence.language == "html" || fence.language == "htm" {
                    flush()
                    let payload = lines[(i + 1)..<(closed ? end : lines.count)].joined(separator: "\n")
                    if closed, let table = parse(payload) {
                        result.append(.table(table, source: original))
                    } else {
                        result.append(.source(original))
                    }
                } else if allowBodyProtocols && (fence.language == "reva-ui" || fence.language == "menu_share") {
                    plain.append(original)
                } else {
                    flush()
                    result.append(.code(original))
                }
                i = last + 1
                continue
            }
            if let start = unindented(lines[i]), start.lowercased().range(
                of: "^<table(?:[\\s>])", options: .regularExpression
            ) != nil {
                var end = i
                while end < lines.count && lines[end].range(
                    of: "</table\\s*>", options: [.regularExpression, .caseInsensitive]
                ) == nil { end += 1 }
                let last = min(end, lines.count - 1)
                let original = originalLines(i, last)
                flush()
                if end < lines.count, let table = parse(original) {
                    result.append(.table(table, source: original))
                } else {
                    result.append(.source(original))
                }
                i = last + 1
                continue
            }
            plain.append(originalLines(i, i))
            i += 1
        }
        flush()
        return result
    }

    private struct Fence {
        let marker: Character
        let count: Int
        let language: String
    }
    private static func unindented(_ line: String) -> String? {
        let spaces = line.prefix { $0 == " " }.count
        guard spaces <= 3 else { return nil }
        return String(line.dropFirst(spaces)).trimmingCharacters(in: .newlines)
    }
    private static func openingFence(_ line: String) -> Fence? {
        guard let text = unindented(line), let first = text.first, first == "`" || first == "~" else { return nil }
        let count = text.prefix { $0 == first }.count
        guard count >= 3 else { return nil }
        let info = text.dropFirst(count).trimmingCharacters(in: .whitespacesAndNewlines)
        return Fence(marker: first, count: count, language: info.lowercased())
    }
    private static func closesFence(_ line: String, _ fence: Fence) -> Bool {
        guard let text = unindented(line) else { return false }
        let count = text.prefix { $0 == fence.marker }.count
        return count >= fence.count && text.dropFirst(count).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private struct Tag {
        let name: String
        let closing: Bool
        let selfClosing: Bool
    }
    /// Parse every byte of a tag; accepting only a prefix would erase unsafe
    /// attributes. Even allowed presentation attributes are discarded entirely.
    private static func tag(_ source: String) -> Tag? {
        let chars = Array(source)
        var i = 0
        func space() { while i < chars.count && chars[i].isWhitespace { i += 1 } }
        func name() -> String {
            let start = i
            while i < chars.count && chars[i].isASCII && (chars[i].isLetter || chars[i].isNumber || chars[i] == "-" || chars[i] == "_") { i += 1 }
            return String(chars[start..<i]).lowercased()
        }
        let closing = i < chars.count && chars[i] == "/"
        if closing { i += 1 }
        let tagName = name()
        guard !tagName.isEmpty else { return nil }
        if closing {
            space()
            return i == chars.count ? Tag(name: tagName, closing: true, selfClosing: false) : nil
        }
        var seen: Set<String> = []
        while i < chars.count {
            let before = i
            space()
            if i == chars.count { break }
            if chars[i] == "/" {
                i += 1
                return i == chars.count ? Tag(name: tagName, closing: false, selfClosing: true) : nil
            }
            guard i > before else { return nil }
            let attribute = name()
            guard attributes.contains(attribute), seen.insert(attribute).inserted else { return nil }
            space()
            guard i < chars.count && chars[i] == "=" else { return nil }
            i += 1
            space()
            guard i < chars.count else { return nil }
            if chars[i] == "\"" || chars[i] == "'" {
                let quote = chars[i]
                i += 1
                while i < chars.count && chars[i] != quote { i += 1 }
                guard i < chars.count else { return nil }
                i += 1
            } else {
                let start = i
                while i < chars.count && !chars[i].isWhitespace {
                    guard !["\"", "'", "<", ">", "=", "`"].contains(chars[i]) else { return nil }
                    i += 1
                }
                guard i > start else { return nil }
            }
        }
        return Tag(name: tagName, closing: false, selfClosing: false)
    }

    static func parse(_ source: String) -> Table? {
        guard source.utf16.count <= 32_000 else { return nil }
        let chars = Array(source)
        var i = 0
        var stack: [String] = []
        var rows: [[Cell]] = []
        var row: [Cell] = []
        var cell: Cell?
        var caption: String?
        var started = false
        var finished = false
        func append(_ text: String) -> Bool {
            guard cell != nil || stack.contains("caption") else {
                // Entities/Unicode space outside cells are actual content, not
                // structural indentation: never silently discard them.
                return text.unicodeScalars.allSatisfy { htmlWhitespace.contains($0) }
            }
            var decoded = decodeEntities(text).replacingOccurrences(
                of: "[ \\t\\n\\r\\x{000C}]+", with: " ", options: .regularExpression
            )
            let previous = cell?.text ?? caption ?? ""
            if (previous.hasSuffix(" ") || previous.hasSuffix("\n")), decoded.hasPrefix(" ") {
                decoded.removeFirst()
            }
            if cell != nil {
                cell!.text += decoded
                return cell!.text.utf16.count <= 2_000
            }
            if stack.contains("caption") {
                caption = (caption ?? "") + decoded
                return (caption?.utf16.count ?? 0) <= 2_000
            }
            return decoded.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        while i < chars.count {
            if chars[i] != "<" {
                let start = i
                while i < chars.count && chars[i] != "<" { i += 1 }
                guard append(String(chars[start..<i])) else { return nil }
                continue
            }
            i += 1
            let start = i
            var quote: Character?
            while i < chars.count {
                if let active = quote {
                    if chars[i] == active { quote = nil }
                } else if chars[i] == "\"" || chars[i] == "'" {
                    quote = chars[i]
                } else if chars[i] == ">" { break }
                i += 1
            }
            guard i < chars.count, let token = tag(String(chars[start..<i])) else { return nil }
            i += 1
            let name = token.name
            if token.closing {
                guard !token.selfClosing, stack.last == name else { return nil }
                stack.removeLast()
                if name == "td" || name == "th" {
                    guard let value = cell else { return nil }
                    row.append(Cell(text: value.text.trimmingCharacters(in: htmlWhitespace), header: value.header))
                    cell = nil
                    guard row.count <= 20 else { return nil }
                } else if name == "tr" {
                    guard !row.isEmpty, rows.first == nil || rows.first!.count == row.count else { return nil }
                    rows.append(row)
                    row = []
                    guard rows.count <= 100 else { return nil }
                } else if name == "caption" {
                    caption = caption?.trimmingCharacters(in: htmlWhitespace)
                } else if name == "table" { finished = true }
                continue
            }
            guard !finished, !token.selfClosing || name == "br" else { return nil }
            let parent = stack.last
            switch name {
            case "table":
                guard !started, stack.isEmpty else { return nil }
                started = true
            case "caption":
                guard parent == "table", caption == nil, rows.isEmpty else { return nil }
                caption = ""
            case "thead", "tbody", "tfoot":
                guard parent == "table" else { return nil }
            case "tr":
                guard parent == "table" || groups.contains(parent ?? "") else { return nil }
            case "th", "td":
                guard parent == "tr", cell == nil else { return nil }
                cell = Cell(text: "", header: name == "th")
            case "br":
                guard cell != nil || stack.contains("caption") else { return nil }
                if cell != nil {
                    while cell!.text.hasSuffix(" ") { cell!.text.removeLast() }
                    cell!.text += "\n"
                    guard cell!.text.utf16.count <= 2_000 else { return nil }
                } else {
                    while caption?.hasSuffix(" ") == true { caption!.removeLast() }
                    caption = (caption ?? "") + "\n"
                    guard (caption?.utf16.count ?? 0) <= 2_000 else { return nil }
                }
                continue
            default:
                guard inline.contains(name), cell != nil || stack.contains("caption") else { return nil }
            }
            stack.append(name)
            guard stack.count <= 32 else { return nil }
        }
        guard started, finished, stack.isEmpty, !rows.isEmpty else { return nil }
        return Table(caption: caption, rows: rows)
    }

    /// One decoding pass only. Encoded markup remains cell text and is escaped
    /// again on output; unknown entities and illegal scalars stay verbatim.
    private static func decodeEntities(_ text: String) -> String {
        let pattern = /&(?:amp|lt|gt|quot|apos|nbsp|#[0-9]+|#[xX][0-9a-fA-F]+);/
        return text.replacing(pattern) { match in
            let token = String(match.output.dropFirst().dropLast())
            let named = ["amp": "&", "lt": "<", "gt": ">", "quot": "\"", "apos": "'", "nbsp": "\u{00a0}"]
            if let value = named[token] { return value }
            let hex = token.hasPrefix("#x") || token.hasPrefix("#X")
            let number = String(token.dropFirst(hex ? 2 : 1))
            guard let value = UInt32(number, radix: hex ? 16 : 10), value > 0,
                  let scalar = UnicodeScalar(value) else { return String(match.output) }
            return String(scalar)
        }
    }
}
