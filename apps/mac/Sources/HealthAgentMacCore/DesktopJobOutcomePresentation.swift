import Foundation

public struct DesktopJobOutcomePresentation: Equatable, Sendable {
    public enum State: Equatable, Sendable {
        case completed
        case failed
        case pending
        case unknown
    }

    public let state: State
    public let title: String
    public let diagnostic: String
    public let summaryItems: [DesktopJobOutcomeSummaryItem]
    public let nextActions: [DesktopJobOutcomeAction]
    public let conversationID: Int?

    public init(job: DesktopJobSummary) {
        let normalizedStatus = job.status.lowercased()
        let payload = job.resultPayload ?? [:]
        let conversationID = payload["conversation_id"]?.intValue
        let sourceName = job.sourceName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let sourceLabel = sourceName?.isEmpty == false ? sourceName! : job.jobType

        self.conversationID = conversationID
        self.summaryItems = Self.makeSummaryItems(payload: payload, job: job)

        switch normalizedStatus {
        case "completed", "succeeded", "success":
            self.state = .completed
            self.title = "Job completed"
            self.diagnostic = "Results are ready for \(sourceLabel). Review the generated output before using it as Agent context."
            var actions = [
                DesktopJobOutcomeAction(title: "Review generated results", systemImage: "doc.text.magnifyingglass"),
                DesktopJobOutcomeAction(title: "Add results to Agent context", systemImage: "bubble.left.and.text.bubble.right")
            ]
            if conversationID != nil {
                actions.append(DesktopJobOutcomeAction(title: "Open trace", systemImage: "point.3.connected.trianglepath.dotted"))
            }
            self.nextActions = actions
        case "failed", "error":
            self.state = .failed
            self.title = "Job failed"
            let error = job.errorMessage?.trimmingCharacters(in: .whitespacesAndNewlines)
            self.diagnostic = error?.isEmpty == false ? error! : "The job failed before returning a usable result."
            self.nextActions = [
                DesktopJobOutcomeAction(title: "Review error", systemImage: "exclamationmark.triangle"),
                DesktopJobOutcomeAction(title: "Check source hash", systemImage: "number"),
                DesktopJobOutcomeAction(title: "Retry job", systemImage: "arrow.clockwise")
            ]
        case "queued", "running", "processing":
            self.state = .pending
            self.title = "Job still running"
            self.diagnostic = "\(sourceLabel) is \(job.progress)% complete. Keep the app open or return from the menu bar to review results."
            self.nextActions = [
                DesktopJobOutcomeAction(title: "Wait for completion", systemImage: "clock.arrow.circlepath"),
                DesktopJobOutcomeAction(title: "Review source context", systemImage: "folder")
            ]
        default:
            self.state = .unknown
            self.title = "Job status unknown"
            self.diagnostic = "Status \(job.status) is not recognized yet. Inspect the raw result before acting on it."
            self.nextActions = [
                DesktopJobOutcomeAction(title: "Review raw result", systemImage: "curlybraces")
            ]
        }
    }

    private static func makeSummaryItems(payload: [String: JSONValue], job: DesktopJobSummary) -> [DesktopJobOutcomeSummaryItem] {
        var items: [DesktopJobOutcomeSummaryItem] = []

        if let conversationID = payload["conversation_id"]?.intValue {
            items.append(.init(title: "Trace", value: "#\(conversationID)"))
        }
        appendFirstInt(
            from: payload,
            keys: ["action_cards_created", "created_action_cards", "action_card_count"],
            title: "Action cards",
            into: &items
        )
        appendFirstInt(
            from: payload,
            keys: ["records_imported", "imported_records", "record_count"],
            title: "Imported records",
            into: &items
        )
        appendFirstInt(
            from: payload,
            keys: ["documents_indexed", "document_count", "indexed_documents"],
            title: "Documents",
            into: &items
        )
        appendFirstInt(
            from: payload,
            keys: ["findings_created", "finding_count", "variant_count"],
            title: "Findings",
            into: &items
        )

        if let sourceHash = job.sourceHash, !sourceHash.isEmpty {
            items.append(.init(title: "Source hash", value: shortenedHash(sourceHash)))
        }

        return items
    }

    private static func appendFirstInt(
        from payload: [String: JSONValue],
        keys: [String],
        title: String,
        into items: inout [DesktopJobOutcomeSummaryItem]
    ) {
        guard let value = keys.compactMap({ payload[$0]?.numericIntValue }).first else { return }
        items.append(.init(title: title, value: formattedInteger(value)))
    }

    private static func formattedInteger(_ value: Int) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
    }

    private static func shortenedHash(_ value: String) -> String {
        guard value.count > 18 else { return value }
        let prefix = value.prefix(12)
        let suffix = value.suffix(6)
        return "\(prefix)...\(suffix)"
    }
}

public struct DesktopJobOutcomeSummaryItem: Equatable, Sendable {
    public let title: String
    public let value: String

    public init(title: String, value: String) {
        self.title = title
        self.value = value
    }
}

public struct DesktopJobOutcomeAction: Equatable, Sendable {
    public let title: String
    public let systemImage: String

    public init(title: String, systemImage: String) {
        self.title = title
        self.systemImage = systemImage
    }
}

private extension JSONValue {
    var numericIntValue: Int? {
        switch self {
        case .int(let value):
            value
        case .double(let value):
            Int(value)
        case .string(let value):
            Int(value)
        default:
            nil
        }
    }
}
