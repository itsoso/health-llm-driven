import Foundation

public enum APIError: Error, Equatable, LocalizedError {
    case unauthorized
    case invalidURL
    case httpStatus(Int, String?)
    case emptyResponse

    public var errorDescription: String? {
        switch self {
        case .unauthorized:
            "登录已过期，请重新登录。"
        case .invalidURL:
            "API 地址无效。"
        case .httpStatus(let status, let message):
            message.map { "HTTP \(status): \($0)" } ?? "HTTP \(status)"
        case .emptyResponse:
            "服务器没有返回有效响应。"
        }
    }
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

    public func delete(_ path: String) async throws {
        let request = try await makeRequest(path: path, method: "DELETE")
        let (data, response) = try await session.data(for: request)
        try await validate(data: data, response: response)
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
        try await validate(data: data, response: response)
        return try decoder.decode(T.self, from: data)
    }

    private func validate(data: Data, response: URLResponse) async throws {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.emptyResponse
        }
        if http.statusCode == 401 {
            await tokenProvider.clearToken()
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpStatus(http.statusCode, Self.errorMessage(from: data))
        }
    }

    private static func errorMessage(from data: Data) -> String? {
        guard !data.isEmpty else {
            return nil
        }
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = object["detail"] {
            if let message = detail as? String {
                return message
            }
            if JSONSerialization.isValidJSONObject(detail),
               let detailData = try? JSONSerialization.data(withJSONObject: detail),
               let message = String(data: detailData, encoding: .utf8) {
                return message
            }
            return String(describing: detail)
        }
        return String(data: data, encoding: .utf8)
    }
}
