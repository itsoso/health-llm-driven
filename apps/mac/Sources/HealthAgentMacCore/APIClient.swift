import Foundation

extension Notification.Name {
    /// Posted when the API rejects a request with 401 and the token has been
    /// cleared. The app root observes this to drop back to the login screen,
    /// so an expired session never leaves the UI in a "logged-in but every
    /// request fails" limbo.
    public static let authSessionExpired = Notification.Name("HealthAgentAuthSessionExpired")
}

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
            Self.httpStatusMessage(code: status, detail: message)
        case .emptyResponse:
            "服务器没有返回有效响应。"
        }
    }

    /// User-facing copy for an HTTP error. 5xx is always generic (the raw body
    /// is often an nginx HTML page — never show it). 4xx keeps a short sanitized
    /// server detail when one is available.
    private static func httpStatusMessage(code: Int, detail: String?) -> String {
        if (500...599).contains(code) {
            return "服务暂时不可用，请稍后再试。"
        }
        if let detail, !detail.isEmpty {
            return "请求失败（HTTP \(code)）：\(detail)"
        }
        return "请求失败（HTTP \(code)）。"
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

    public func patch<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T {
        var request = try await makeRequest(path: path, method: "PATCH")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        let (data, response) = try await session.data(for: request)
        return try await decode(data: data, response: response)
    }

    /// Uploads a single file as `multipart/form-data` and decodes the JSON
    /// response. Used by endpoints like `/prescriptions/recognize` that take an
    /// image file under one form field. The boundary is generated per-call so
    /// concurrent uploads never collide.
    public func uploadFile<T: Decodable>(
        _ path: String,
        fileData: Data,
        fileName: String,
        fieldName: String = "file",
        mimeType: String = "application/octet-stream"
    ) async throws -> T {
        var request = try await makeRequest(path: path, method: "POST")
        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = Self.multipartBody(
            boundary: boundary,
            fieldName: fieldName,
            fileName: fileName,
            mimeType: mimeType,
            fileData: fileData
        )
        let (data, response) = try await session.data(for: request)
        return try await decode(data: data, response: response)
    }

    /// Builds a single-file multipart body. Pure and static so it can be unit
    /// tested without a live session.
    static func multipartBody(
        boundary: String,
        fieldName: String,
        fileName: String,
        mimeType: String,
        fileData: Data
    ) -> Data {
        var body = Data()
        let dashes = "--"
        body.append(Data("\(dashes)\(boundary)\r\n".utf8))
        let disposition = "Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(fileName)\"\r\n"
        body.append(Data(disposition.utf8))
        body.append(Data("Content-Type: \(mimeType)\r\n\r\n".utf8))
        body.append(fileData)
        body.append(Data("\r\n".utf8))
        body.append(Data("\(dashes)\(boundary)\(dashes)\r\n".utf8))
        return body
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
            await MainActor.run {
                NotificationCenter.default.post(name: .authSessionExpired, object: nil)
            }
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpStatus(http.statusCode, Self.errorMessage(from: data))
        }
    }

    /// Extracts a short, safe server-provided detail from an error body.
    /// Only trusts the structured FastAPI `detail` string; raw HTML bodies
    /// (e.g. an nginx 502 page) and overlong text are dropped so they never
    /// reach the UI.
    private static func errorMessage(from data: Data) -> String? {
        guard !data.isEmpty else {
            return nil
        }
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = object["detail"] {
            if let message = detail as? String {
                return sanitizedDetail(message)
            }
            if JSONSerialization.isValidJSONObject(detail),
               let detailData = try? JSONSerialization.data(withJSONObject: detail),
               let message = String(data: detailData, encoding: .utf8) {
                return sanitizedDetail(message)
            }
            return sanitizedDetail(String(describing: detail))
        }
        // Non-JSON body (HTML error page, plain text, etc.) — not safe to show.
        return nil
    }

    private static func sanitizedDetail(_ raw: String) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        // Drop anything that looks like markup or is too long to be a real message.
        if trimmed.contains("<") || trimmed.contains(">") || trimmed.count > 200 {
            return nil
        }
        return trimmed
    }
}
