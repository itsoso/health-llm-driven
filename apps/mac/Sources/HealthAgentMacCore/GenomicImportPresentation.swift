import Foundation

public enum GenomicImportPhase: Equatable, Sendable {
    case pending
    case running
    case complete
    case failed
    case unknown
}

public enum GenomicImportPresentation {
    public static func phase(for summary: GenomicImportSummary) -> GenomicImportPhase {
        let status = (summary.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch status {
        case "queued":
            return .pending
        case "processing", "running", "started":
            return .running
        case "done", "complete", "completed", "succeeded", "success":
            return .complete
        case "failed", "error":
            return .failed
        case "":
            return (summary.matchedCount ?? 0) > 0 ? .complete : .running
        default:
            return .unknown
        }
    }

    public static func statusLabel(for summary: GenomicImportSummary) -> String {
        switch phase(for: summary) {
        case .pending:
            return "Queued"
        case .running:
            return "Processing"
        case .complete:
            return "Done"
        case .failed:
            return "Failed"
        case .unknown:
            return "Unknown"
        }
    }

    public static func detailText(for summary: GenomicImportSummary) -> String? {
        switch phase(for: summary) {
        case .pending:
            return "Import file received; waiting for parser."
        case .running:
            let matched = summary.matchedCount ?? 0
            if matched > 0 {
                return "\(matched) matched markers; coverage is still being finalized."
            }
            return "Parser is extracting genetic markers."
        case .complete:
            let matched = summary.matchedCount ?? 0
            if let known = summary.knownTotal, known > 0 {
                let missing = summary.missingCount ?? max(known - matched, 0)
                var text = "\(matched) of \(known) known health markers matched; \(missing) missing"
                if let unmapped = summary.unmappedCount, unmapped > 0 {
                    text += "; \(unmapped) raw rows unmapped"
                }
                return text + "."
            }
            return "\(matched) matched health markers."
        case .failed:
            return "Import failed; retry with raw TXT data when possible."
        case .unknown:
            return "Import status is not recognized yet."
        }
    }

    public static func isTerminal(_ summary: GenomicImportSummary) -> Bool {
        switch phase(for: summary) {
        case .complete, .failed:
            return true
        case .pending, .running, .unknown:
            return false
        }
    }
}
