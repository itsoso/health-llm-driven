import Foundation

public struct AuthLoginRequest: Encodable, Equatable, Sendable {
    public let username: String
    public let password: String
}

public struct AuthLoginResponse: Decodable, Equatable, Sendable {
    public let accessToken: String
    public let tokenType: String
    public let user: AuthUser

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case user
    }
}

public struct AuthUser: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let username: String
    public let email: String?
    public let name: String?
}

public final class AuthClient: Sendable {
    private let apiClient: APIClient
    private let tokenStore: AuthTokenStoring

    public init(apiClient: APIClient, tokenStore: AuthTokenStoring) {
        self.apiClient = apiClient
        self.tokenStore = tokenStore
    }

    public func login(username: String, password: String) async throws -> AuthLoginResponse {
        let response: AuthLoginResponse = try await apiClient.post(
            "auth/login/json",
            body: AuthLoginRequest(username: username, password: password)
        )
        try await tokenStore.setToken(response.accessToken)
        return response
    }

    public func logout() async {
        await tokenStore.clearToken()
    }

    public func currentUser() async throws -> AuthUser {
        try await apiClient.get("auth/me")
    }

    public func hasToken() async -> Bool {
        guard let token = await tokenStore.getToken() else {
            return false
        }
        return !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func hasValidSession() async -> Bool {
        guard await hasToken() else {
            return false
        }
        do {
            _ = try await currentUser()
            return true
        } catch APIError.unauthorized {
            return false
        } catch {
            // Network / transient failure: keep the existing session optimistically and let later requests retry.
            // Logged so a chain of these doesn't go unnoticed (e.g. server actually down vs. flaky wifi).
            AppLogger.auth.error("hasValidSession check failed, assuming session still valid: \(error.localizedDescription, privacy: .public)")
            return true
        }
    }
}
