import Foundation

public struct DataConnectionsResponse: Codable, Equatable, Sendable {
    public let connections: [DataConnection]

    public init(connections: [DataConnection]) {
        self.connections = connections
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.connections = try container.decodeIfPresent([DataConnection].self, forKey: .connections) ?? []
    }
}

public struct DataConnection: Codable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let provider: String
    public let providerType: String
    public let displayName: String
    public let connectionStatus: String
    public let tokenStatus: String
    public let scopes: [String]
    public let lastSyncAt: String?
    public let sourceRef: String?
    public let policy: ConnectorPolicy?
    public let connectionHealth: DataConnectionHealth?

    public var health: DataConnectionHealth {
        connectionHealth ?? DataConnectionHealth.fallback(
            connectionStatus: connectionStatus,
            tokenStatus: tokenStatus,
            degradedBehavior: policy?.degradedBehavior
        )
    }

    enum CodingKeys: String, CodingKey {
        case id
        case provider
        case providerType = "provider_type"
        case displayName = "display_name"
        case connectionStatus = "connection_status"
        case tokenStatus = "token_status"
        case scopes
        case lastSyncAt = "last_sync_at"
        case sourceRef = "source_ref"
        case policy
        case connectionHealth = "connection_health"
    }

    public init(
        id: Int,
        provider: String,
        providerType: String,
        displayName: String,
        connectionStatus: String,
        tokenStatus: String,
        scopes: [String],
        lastSyncAt: String? = nil,
        sourceRef: String? = nil,
        policy: ConnectorPolicy? = nil,
        connectionHealth: DataConnectionHealth? = nil
    ) {
        self.id = id
        self.provider = provider
        self.providerType = providerType
        self.displayName = displayName
        self.connectionStatus = connectionStatus
        self.tokenStatus = tokenStatus
        self.scopes = scopes
        self.lastSyncAt = lastSyncAt
        self.sourceRef = sourceRef
        self.policy = policy
        self.connectionHealth = connectionHealth
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decode(Int.self, forKey: .id)
        self.provider = try container.decodeIfPresent(String.self, forKey: .provider) ?? "unknown"
        self.providerType = try container.decodeIfPresent(String.self, forKey: .providerType) ?? "unknown"
        self.displayName = try container.decodeIfPresent(String.self, forKey: .displayName) ?? self.provider
        self.connectionStatus = try container.decodeIfPresent(String.self, forKey: .connectionStatus) ?? "unknown"
        self.tokenStatus = try container.decodeIfPresent(String.self, forKey: .tokenStatus) ?? "none"
        self.scopes = try container.decodeIfPresent([String].self, forKey: .scopes) ?? []
        self.lastSyncAt = try container.decodeIfPresent(String.self, forKey: .lastSyncAt)
        self.sourceRef = try container.decodeIfPresent(String.self, forKey: .sourceRef)
        self.policy = try container.decodeIfPresent(ConnectorPolicy.self, forKey: .policy)
        self.connectionHealth = try container.decodeIfPresent(DataConnectionHealth.self, forKey: .connectionHealth)
    }
}

public struct ConnectorPolicy: Codable, Equatable, Sendable {
    public let degradedBehavior: String?
    public let retryIntervalMinutes: Int?
    public let rateLimitPerHour: Int?

    enum CodingKeys: String, CodingKey {
        case degradedBehavior = "degraded_behavior"
        case retryIntervalMinutes = "retry_interval_minutes"
        case rateLimitPerHour = "rate_limit_per_hour"
    }

    public init(
        degradedBehavior: String? = nil,
        retryIntervalMinutes: Int? = nil,
        rateLimitPerHour: Int? = nil
    ) {
        self.degradedBehavior = degradedBehavior
        self.retryIntervalMinutes = retryIntervalMinutes
        self.rateLimitPerHour = rateLimitPerHour
    }
}

public struct DataConnectionHealth: Codable, Equatable, Sendable {
    public let status: String
    public let severity: String
    public let messageCode: String
    public let canAttemptSync: Bool
    public let canUseCachedData: Bool
    public let needsReconnect: Bool
    public let userAction: String
    public let connectionStatus: String?
    public let tokenStatus: String?
    public let degradedBehavior: String?
    public let lastSuccessAt: String?
    public let lastAttemptAt: String?
    public let syncError: String?

    enum CodingKeys: String, CodingKey {
        case status
        case severity
        case messageCode = "message_code"
        case canAttemptSync = "can_attempt_sync"
        case canUseCachedData = "can_use_cached_data"
        case needsReconnect = "needs_reconnect"
        case userAction = "user_action"
        case connectionStatus = "connection_status"
        case tokenStatus = "token_status"
        case degradedBehavior = "degraded_behavior"
        case lastSuccessAt = "last_success_at"
        case lastAttemptAt = "last_attempt_at"
        case syncError = "sync_error"
    }

    public init(
        status: String,
        severity: String,
        messageCode: String,
        canAttemptSync: Bool,
        canUseCachedData: Bool,
        needsReconnect: Bool,
        userAction: String,
        connectionStatus: String? = nil,
        tokenStatus: String? = nil,
        degradedBehavior: String? = nil,
        lastSuccessAt: String? = nil,
        lastAttemptAt: String? = nil,
        syncError: String? = nil
    ) {
        self.status = status
        self.severity = severity
        self.messageCode = messageCode
        self.canAttemptSync = canAttemptSync
        self.canUseCachedData = canUseCachedData
        self.needsReconnect = needsReconnect
        self.userAction = userAction
        self.connectionStatus = connectionStatus
        self.tokenStatus = tokenStatus
        self.degradedBehavior = degradedBehavior
        self.lastSuccessAt = lastSuccessAt
        self.lastAttemptAt = lastAttemptAt
        self.syncError = syncError
    }

    public static func fallback(
        connectionStatus: String,
        tokenStatus: String,
        degradedBehavior: String? = nil
    ) -> DataConnectionHealth {
        let normalizedConnection = connectionStatus.lowercased()
        let normalizedToken = tokenStatus.lowercased()
        let canUseCached = degradedBehavior == "read_only"

        if normalizedConnection == "revoked" {
            return DataConnectionHealth(
                status: "revoked",
                severity: "blocked",
                messageCode: "connection_revoked",
                canAttemptSync: false,
                canUseCachedData: false,
                needsReconnect: true,
                userAction: "reconnect",
                connectionStatus: connectionStatus,
                tokenStatus: tokenStatus,
                degradedBehavior: degradedBehavior
            )
        }

        if ["auth_failed", "expired", "invalid", "error"].contains(normalizedToken) {
            return DataConnectionHealth(
                status: "degraded",
                severity: "warning",
                messageCode: "connector_auth_failed_read_only",
                canAttemptSync: false,
                canUseCachedData: canUseCached,
                needsReconnect: true,
                userAction: "reconnect",
                connectionStatus: connectionStatus,
                tokenStatus: tokenStatus,
                degradedBehavior: degradedBehavior
            )
        }

        if normalizedConnection == "active" {
            return DataConnectionHealth(
                status: "healthy",
                severity: "ok",
                messageCode: "connection_healthy",
                canAttemptSync: true,
                canUseCachedData: true,
                needsReconnect: false,
                userAction: "none",
                connectionStatus: connectionStatus,
                tokenStatus: tokenStatus,
                degradedBehavior: degradedBehavior
            )
        }

        return DataConnectionHealth(
            status: "unknown",
            severity: "warning",
            messageCode: "connection_unknown",
            canAttemptSync: false,
            canUseCachedData: canUseCached,
            needsReconnect: false,
            userAction: "retry_later",
            connectionStatus: connectionStatus,
            tokenStatus: tokenStatus,
            degradedBehavior: degradedBehavior
        )
    }
}

public struct DataConnectionHealthDisplay: Equatable, Sendable {
    public let statusLabel: String
    public let actionLabel: String
    public let detail: String
    public let cachedDataLabel: String
    public let tint: String

    public static func display(for connection: DataConnection) -> DataConnectionHealthDisplay {
        let health = connection.health
        let cached = health.canUseCachedData ? "缓存可只读使用" : "缓存不可用"

        switch health.status {
        case "healthy":
            return DataConnectionHealthDisplay(
                statusLabel: "可用",
                actionLabel: "无需操作",
                detail: "数据连接正常，可参与健康运行时判断。",
                cachedDataLabel: cached,
                tint: "ok"
            )
        case "degraded":
            return DataConnectionHealthDisplay(
                statusLabel: "需重连",
                actionLabel: "重新授权",
                detail: "连接已降级，暂不继续同步；如策略允许，可继续只读使用缓存数据。",
                cachedDataLabel: cached,
                tint: "warning"
            )
        case "revoked":
            return DataConnectionHealthDisplay(
                statusLabel: "已撤权",
                actionLabel: "重新连接",
                detail: "授权已撤销，Reva 不再使用该连接的缓存数据。",
                cachedDataLabel: cached,
                tint: "blocked"
            )
        default:
            return DataConnectionHealthDisplay(
                statusLabel: "未知",
                actionLabel: "稍后重试",
                detail: "连接状态暂时不完整，请稍后刷新。",
                cachedDataLabel: cached,
                tint: "warning"
            )
        }
    }
}

public final class DataConnectionsClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchMyConnections() async throws -> DataConnectionsResponse {
        try await apiClient.get("data-connections/me")
    }
}
