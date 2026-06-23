import Foundation

// MARK: - Backend DTOs (GET /agent/conversations, GET /agent/conversations/{id})

/// One row from `GET /agent/conversations`'s `items` array. Mirrors the backend
/// shape in `backend/app/api/agent.py` (`list_conversations`). `id` is the
/// durable backend conversation id (Int); the timestamps arrive as Python
/// `str(datetime)` and are parsed leniently.
struct BackendConversationListItem: Decodable, Sendable {
    let id: Int
    let title: String?
    let last_message: String?
    let created_at: String?
    let updated_at: String?
    let mode: String?
}

struct BackendConversationList: Decodable, Sendable {
    let items: [BackendConversationListItem]
    let total: Int?
    let limit: Int?
    let offset: Int?
}

/// One message from `GET /agent/conversations/{id}`'s `messages` array.
struct BackendConversationMessage: Decodable, Sendable {
    let id: Int?
    let role: String
    let content: String?
    let image_url: String?
    let created_at: String?
}

struct BackendConversationDetail: Decodable, Sendable {
    let id: Int
    let title: String?
    let total_messages: Int?
    let mode: String?
    let messages: [BackendConversationMessage]
}

// MARK: - Remote source protocol

/// Reads conversation history from the backend so Mac matches web/mobile (which
/// both read `/agent/conversations`). The Mac stream already persists through the
/// same `OpenClawService`, so the durable list is the single source of truth;
/// the local `UserDefaultsAgentConversationStore` is only an offline cache.
public protocol AgentConversationRemoteSourcing: Sendable {
    /// Fetches the conversation list (most-recent first), mapped to snapshots.
    /// Snapshots carry no messages yet — call `fetchDetail` when one is opened.
    func fetchConversations(limit: Int, offset: Int) async throws -> [AgentConversationSnapshot]
    /// Fetches a single conversation's full message list.
    func fetchDetail(conversationID: Int) async throws -> [AgentChatMessage]
    /// Deletes a conversation on the backend. No-op-safe to call before syncing
    /// local cache.
    func deleteConversation(conversationID: Int) async throws
    /// Renames a conversation on the backend.
    func renameConversation(conversationID: Int, title: String) async throws
}

// MARK: - Client

public final class AgentConversationClient: AgentConversationRemoteSourcing, @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchConversations(limit: Int = 30, offset: Int = 0) async throws -> [AgentConversationSnapshot] {
        let response: BackendConversationList = try await apiClient.get(
            "agent/conversations?limit=\(limit)&offset=\(offset)"
        )
        return response.items.map { Self.snapshot(from: $0) }
    }

    public func fetchDetail(conversationID: Int) async throws -> [AgentChatMessage] {
        let response: BackendConversationDetail = try await apiClient.get(
            "agent/conversations/\(conversationID)"
        )
        return response.messages.compactMap { Self.message(from: $0, baseURL: apiClient.resourceBaseURL) }
    }

    public func deleteConversation(conversationID: Int) async throws {
        try await apiClient.delete("agent/conversations/\(conversationID)")
    }

    public func renameConversation(conversationID: Int, title: String) async throws {
        struct TitleBody: Encodable { let title: String }
        // PATCH returns a body, but the View Model only needs success; decode into
        // a permissive shape so a missing/extra field never fails the rename.
        let _: BackendConversationDetailTitle = try await apiClient.patch(
            "agent/conversations/\(conversationID)",
            body: TitleBody(title: title)
        )
    }

    // MARK: Mapping

    /// Maps a backend list item to a snapshot with no messages loaded yet. The
    /// snapshot's local `id` is derived deterministically from the backend
    /// conversation id so selection / "currently open" tracking survives a
    /// refresh (same backend id → same UUID).
    static func snapshot(from item: BackendConversationListItem) -> AgentConversationSnapshot {
        AgentConversationSnapshot(
            id: deterministicID(forConversationID: item.id),
            conversationID: item.id,
            title: resolvedTitle(item.title, fallback: item.last_message),
            messages: [],
            updatedAt: parseDate(item.updated_at) ?? parseDate(item.created_at) ?? Date()
        )
    }

    static func message(from dto: BackendConversationMessage, baseURL: URL = APIEndpoint.defaultBaseURL) -> AgentChatMessage? {
        guard let role = mapRole(dto.role) else {
            // Skip system / tool rows the desktop transcript doesn't render.
            return nil
        }
        return AgentChatMessage(
            id: deterministicID(forMessageID: dto.id),
            role: role,
            content: dto.content ?? "",
            remoteImageURLs: imageURLStrings(from: dto.image_url, baseURL: baseURL)
        )
    }

    static func imageURLStrings(from raw: String?, baseURL: URL) -> [String] {
        let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmed.isEmpty else { return [] }

        let candidates: [String]
        if let data = trimmed.data(using: .utf8),
           let json = try? JSONSerialization.jsonObject(with: data) {
            if let array = json as? [String] {
                candidates = array
            } else if let string = json as? String {
                candidates = [string]
            } else {
                candidates = []
            }
        } else {
            candidates = [trimmed]
        }

        var seen = Set<String>()
        return candidates.compactMap { candidate in
            guard let resolved = resolveImageURL(candidate, baseURL: baseURL),
                  seen.insert(resolved).inserted else {
                return nil
            }
            return resolved
        }
    }

    private static func resolveImageURL(_ raw: String, baseURL: URL) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        if let absolute = URL(string: trimmed), absolute.scheme != nil {
            return allowedHTTPURLString(absolute)
        }

        let referenceBase: URL
        if trimmed.hasPrefix("/") {
            referenceBase = originURL(from: baseURL)
        } else {
            referenceBase = baseURL.absoluteString.hasSuffix("/")
                ? baseURL
                : baseURL.appendingPathComponent("")
        }
        guard let resolved = URL(string: trimmed, relativeTo: referenceBase)?.absoluteURL else {
            return nil
        }
        return allowedHTTPURLString(resolved)
    }

    private static func originURL(from url: URL) -> URL {
        var components = URLComponents()
        components.scheme = url.scheme
        components.host = url.host
        components.port = url.port
        return components.url ?? url
    }

    private static func allowedHTTPURLString(_ url: URL) -> String? {
        guard let scheme = url.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              url.host != nil else {
            return nil
        }
        return url.absoluteString
    }

    private static func mapRole(_ raw: String) -> AgentChatRole? {
        switch raw.lowercased() {
        case "user": return .user
        case "assistant", "ai", "bot": return .assistant
        default: return nil
        }
    }

    private static func resolvedTitle(_ title: String?, fallback: String?) -> String {
        let trimmed = title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !trimmed.isEmpty { return trimmed }
        let fallbackTrimmed = fallback?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !fallbackTrimmed.isEmpty {
            return fallbackTrimmed.count <= 28 ? fallbackTrimmed : "\(fallbackTrimmed.prefix(28))…"
        }
        return "对话"
    }

    /// Stable UUID for a backend conversation id (namespaced so it never collides
    /// with a message-derived UUID). Lets the View Model match the open
    /// conversation across list refreshes without holding the int everywhere.
    static func deterministicID(forConversationID id: Int) -> UUID {
        uuid(seed: "conversation:\(id)")
    }

    static func deterministicID(forMessageID id: Int?) -> UUID {
        guard let id else { return UUID() }
        return uuid(seed: "message:\(id)")
    }

    /// Builds a deterministic UUID from a seed string. Not cryptographic — only
    /// needs to be stable and collision-free across the small id space.
    private static func uuid(seed: String) -> UUID {
        var bytes = [UInt8](repeating: 0, count: 16)
        var hash: UInt64 = 0xcbf29ce484222325 // FNV-1a offset basis
        for byte in seed.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x100000001b3 // FNV prime
        }
        var mixed = hash
        for i in 0..<16 {
            bytes[i] = UInt8(truncatingIfNeeded: mixed)
            mixed = mixed &* 0x100000001b3 &+ 0x9e3779b97f4a7c15
        }
        return UUID(uuid: (
            bytes[0], bytes[1], bytes[2], bytes[3],
            bytes[4], bytes[5], bytes[6], bytes[7],
            bytes[8], bytes[9], bytes[10], bytes[11],
            bytes[12], bytes[13], bytes[14], bytes[15]
        ))
    }

    /// Parses the backend's `str(datetime)` timestamps. Tries ISO-8601 (with and
    /// without fractional seconds) and Python's space-separated form. Returns nil
    /// rather than guessing so the caller can fall back to another field.
    static func parseDate(_ raw: String?) -> Date? {
        guard let raw, !raw.isEmpty else { return nil }
        let isoFractional = ISO8601DateFormatter()
        isoFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = isoFractional.date(from: raw) { return date }
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        if let date = iso.date(from: raw) { return date }
        // Python "2026-06-15 10:30:00+00:00" / "2026-06-15 10:30:00.123456+00:00".
        for format in ["yyyy-MM-dd HH:mm:ssZZZZZ", "yyyy-MM-dd HH:mm:ss.SSSSSSZZZZZ", "yyyy-MM-dd HH:mm:ss"] {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(identifier: "UTC")
            formatter.dateFormat = format
            if let date = formatter.date(from: raw) { return date }
        }
        return nil
    }
}

/// Permissive decode target for the PATCH rename response.
struct BackendConversationDetailTitle: Decodable, Sendable {
    let id: Int?
    let title: String?
}
