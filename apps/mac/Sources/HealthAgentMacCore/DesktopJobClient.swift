import Foundation

public struct DesktopJobCreateRequest: Encodable, Equatable, Sendable {
    public let jobType: String
    public let sourceKind: String
    public let sourceName: String
    public let sourceHash: String?

    public init(jobType: String, sourceKind: String, sourceName: String, sourceHash: String?) {
        self.jobType = jobType
        self.sourceKind = sourceKind
        self.sourceName = sourceName
        self.sourceHash = sourceHash
    }

    enum CodingKeys: String, CodingKey {
        case jobType = "job_type"
        case sourceKind = "source_kind"
        case sourceName = "source_name"
        case sourceHash = "source_hash"
    }
}

public final class DesktopJobClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func createJob(_ request: DesktopJobCreateRequest) async throws -> DesktopJobSummary {
        try await apiClient.post("desktop/import-jobs", body: request)
    }

    public func listJobs() async throws -> [DesktopJobSummary] {
        try await apiClient.get("desktop/jobs")
    }

    public func retryJob(id: Int) async throws -> DesktopJobSummary {
        try await apiClient.post("desktop/jobs/\(id)/retry", body: EmptyRequest())
    }
}

private struct EmptyRequest: Encodable {}
