import Foundation

/// Watch 独立联网客户端。优先用于展示/打点;WatchConnectivity 只作为 token 未同步或网络失败时的兜底。
final class WatchDirectAPIClient {
    enum DirectError: Error {
        case missingToken
        case badResponse
        case httpStatus(Int)
        case requestBuildFailed
    }

    static let shared = WatchDirectAPIClient()

    private let credentials: WatchCredentialStore
    private let session: URLSession

    init(credentials: WatchCredentialStore = .shared, session: URLSession = .shared) {
        self.credentials = credentials
        self.session = session
    }

    func fetchSummary() async throws -> Data {
        let request = try authorizedRequest { token, apiBase in
            try WatchBackendRequest.summary(apiBase: apiBase, token: token)
        }
        return try await data(for: request)
    }

    func sendQuickRecord(_ quick: QuickRecordRequest) async throws -> Data? {
        let request = try authorizedRequest { token, apiBase in
            try WatchBackendRequest.quickRecord(quick, apiBase: apiBase, token: token)
        }
        let data = try await data(for: request)
        return data.isEmpty ? nil : data
    }

    func sendEvent(name: String, meta: [String: String]) async throws {
        let request = try authorizedRequest { token, apiBase in
            try WatchBackendRequest.event(name: name, meta: meta, apiBase: apiBase, token: token)
        }
        _ = try await data(for: request)
    }

    private func authorizedRequest(_ build: (String, String) throws -> URLRequest) throws -> URLRequest {
        guard let token = credentials.token(), !token.isEmpty else { throw DirectError.missingToken }
        do {
            return try build(token, credentials.apiBase())
        } catch {
            throw DirectError.requestBuildFailed
        }
    }

    private func data(for request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw DirectError.badResponse }
        guard (200..<300).contains(http.statusCode) else {
            if http.statusCode == 401 { credentials.deleteToken() }
            throw DirectError.httpStatus(http.statusCode)
        }
        return data
    }
}
