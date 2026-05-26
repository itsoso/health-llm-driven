import Foundation

public struct BriefingSection: Decodable, Identifiable, Sendable, Equatable {
    public let title: String
    public let status: String?
    public let items: [String]

    public var id: String { title }

    public enum Status: String, Sendable {
        case good
        case warning
        case poor
        case info

        public init(raw: String?) {
            switch raw?.lowercased() {
            case "good": self = .good
            case "warning": self = .warning
            case "poor": self = .poor
            default: self = .info
            }
        }
    }

    public var statusKind: Status { Status(raw: status) }
}

public struct DailyBriefing: Decodable, Sendable, Equatable {
    public let date: String?
    public let greeting: String?
    public let sections: [BriefingSection]
}

public final class BriefingClient: @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchMorningBriefing() async throws -> DailyBriefing {
        try await apiClient.get("ai-scheduler/morning-briefing")
    }
}
