import Foundation

public struct SafetyAlert: Decodable, Identifiable, Sendable, Equatable {
    public let rule_id: String
    public let category: String?
    public let severity: Int
    public let title: String
    public let message: String?
    public let action: String?

    public var id: String { rule_id }

    public var severityLabel: String {
        switch severity {
        case 4: return "Critical"
        case 3: return "High"
        case 2: return "Medium"
        case 1: return "Low"
        default: return "Info"
        }
    }
}

public struct SafetyReport: Decodable, Sendable {
    public let alerts: [SafetyAlert]
}

public final class SafetyClient: @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchReport() async throws -> SafetyReport {
        try await apiClient.get("safety/me?severity_min=2&limit=8&dedup_by_rule=true")
    }
}
