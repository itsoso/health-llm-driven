import Foundation

public enum APIError: Error, Equatable {
    case unauthorized
    case invalidURL
    case httpStatus(Int)
    case emptyResponse
}

public protocol AuthTokenProviding: AnyObject, Sendable {
    func getToken() async -> String?
    func clearToken() async
}

public protocol AuthTokenStoring: AuthTokenProviding {
    func setToken(_ token: String) async throws
}

public final class APIClient: @unchecked Sendable {
    private let baseURL: URL
    private let tokenProvider: AuthTokenProviding
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    public init(
        baseURL: URL = APIEndpoint.defaultBaseURL,
        tokenProvider: AuthTokenProviding,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.tokenProvider = tokenProvider
        self.session = session
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }

    public func get<T: Decodable>(_ path: String) async throws -> T {
        let request = try await makeRequest(path: path, method: "GET")
        let (data, response) = try await session.data(for: request)
        return try await decode(data: data, response: response)
    }

    public func post<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T {
        var request = try await makeRequest(path: path, method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        let (data, response) = try await session.data(for: request)
        return try await decode(data: data, response: response)
    }

    private func makeRequest(path: String, method: String) async throws -> URLRequest {
        let normalizedBaseURL = baseURL.absoluteString.hasSuffix("/")
            ? baseURL
            : baseURL.appendingPathComponent("")
        guard let url = URL(string: path, relativeTo: normalizedBaseURL)?.absoluteURL else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = await tokenProvider.getToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func decode<T: Decodable>(data: Data, response: URLResponse) async throws -> T {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.emptyResponse
        }
        if http.statusCode == 401 {
            await tokenProvider.clearToken()
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpStatus(http.statusCode)
        }
        return try decoder.decode(T.self, from: data)
    }
}
