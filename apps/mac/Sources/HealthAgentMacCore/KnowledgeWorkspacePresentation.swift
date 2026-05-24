import Foundation

public enum KnowledgeDocumentFilter: String, CaseIterable, Identifiable, Sendable {
    case all
    case claims
    case articles
    case entities

    public var id: String { rawValue }

    public func matches(_ document: KnowledgeDocumentSummary) -> Bool {
        switch self {
        case .all:
            true
        case .claims:
            document.docType == "claim"
        case .articles:
            document.docType == "article"
        case .entities:
            document.docType == "entity"
        }
    }
}

public enum KnowledgeWorkspacePresentation {
    public static func filteredDocuments(
        _ documents: [KnowledgeDocumentSummary],
        query: String,
        filter: KnowledgeDocumentFilter
    ) -> [KnowledgeDocumentSummary] {
        let normalizedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return documents.filter { document in
            guard filter.matches(document) else {
                return false
            }
            guard !normalizedQuery.isEmpty else {
                return true
            }
            return [
                document.docID,
                document.docType,
                document.title,
                document.summary,
                document.evidenceLevel,
                document.sources.joined(separator: " ")
            ]
                .compactMap { $0?.lowercased() }
                .contains { $0.contains(normalizedQuery) }
        }
    }
}
