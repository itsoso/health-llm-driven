import Foundation

public struct QuickRecordResult: Decodable, Equatable, Sendable {
    public let type: String
    public let message: String
    public let success: Bool
}

private struct QuickRecordRequest: Encodable {
    let text: String
}

public final class RecordClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func quickRecord(text: String) async throws -> QuickRecordResult {
        try await apiClient.post("quick-record", body: QuickRecordRequest(text: text))
    }
}
