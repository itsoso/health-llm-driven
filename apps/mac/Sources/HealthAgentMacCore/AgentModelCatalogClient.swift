import Foundation

public protocol AgentModelCatalogLoading: Sendable {
    func loadModels() async throws -> [AgentModelOption]
}

/// The authenticated, consent-filtered user directory is the source of truth.
/// Do not use the admin directory or merge retired offline entries back in.
public struct AgentModelCatalogClient: AgentModelCatalogLoading {
    private let apiClient: APIClient

    public init(apiClient: APIClient) { self.apiClient = apiClient }

    public func loadModels() async throws -> [AgentModelOption] {
        let response: Directory = try await apiClient.get("me/llm-preference")
        var seen = Set<String>()
        return try response.options.map { option in
            guard !option.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  seen.insert(option.id).inserted else { throw APIError.emptyResponse }
            return AgentModelOption(id: option.id, title: option.label,
                                    provider: option.provider, tier: option.speedTier)
        }
    }

    private struct Directory: Decodable {
        let options: [Option]
    }

    private struct Option: Decodable {
        let id: String
        let label: String
        let provider: String
        let speedTier: String
        enum CodingKeys: String, CodingKey {
            case id, label, provider
            case speedTier = "speed_tier"
        }
    }
}
