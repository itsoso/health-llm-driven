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
    let meta: BackendConversationMessageMeta?
}

struct BackendConversationMessageMeta: Decodable, Sendable {
    let model: String?
    let selectedModel: String?
    let answerModel: String?
    let toolModels: [String]
    let fallbackReasons: [String]
    let elapsedMs: Int?
    let llmRounds: Int?
    let llmUsage: LLMUsageProfile?
    let sourcesUsed: [String]
    let toolsUsed: [String]
    let completionStatus: String?
    /// 每回复级阶段耗时(后端 message.meta.perf)。老消息缺失 → nil → footer 不变。
    let perf: MessagePerf?
    /// 「思考过程」步骤(后端 message.meta.thinking_steps)。历史恢复时驱动可折叠的
    /// 思考过程披露;老消息缺失 → 空 → 不渲染该披露。
    let thinkingSteps: [String]
    let cards: [AgentDynamicCardDescriptor]
    let cardType: String?
    let cardData: AgentDynamicCardValue?
    let medicationBatchDecision: AgentDynamicCardValue?
    let writeReceipts: [AgentDynamicCardValue]
    let safetyAlerts: [AgentDynamicCardValue]

    var firstCard: AgentDynamicCardDescriptor? {
        var sourceCards = cards
        if sourceCards.isEmpty, let cardType, let cardData {
            sourceCards = [AgentDynamicCardDescriptor(type: cardType, data: cardData)]
        }
        if let intentID = medicationBatchDecision?["intent_id"]?.intValue,
           let rawStatus = medicationBatchDecision?["status"]?.stringValue,
           let status = MedicationBatchDecisionStatus(rawValue: rawStatus),
           status == .executed || status == .dismissed || status == .expired {
            // The top-level arrays aggregate every write performed in the same
            // assistant turn. Prefer the decision-scoped arrays so an unrelated
            // water/vitals write cannot appear inside this medication batch.
            // Older persisted turns predate the namespaced arrays, so fall back
            // only when the nested key itself is absent (an explicit [] is truth).
            let exactReceipts = exactMedicationBatchValues(
                key: "write_receipts",
                legacyValues: writeReceipts
            )
            let exactAlerts = exactMedicationBatchValues(
                key: "safety_alerts",
                legacyValues: safetyAlerts
            )
            sourceCards = MedicationBatchCardProjection.restoringTerminal(
                cards: sourceCards,
                intentID: intentID,
                status: status,
                writeReceipts: exactReceipts,
                safetyAlerts: exactAlerts
            )
        }
        if let grouped = AgentDynamicCardDescriptor.grouped(sourceCards) {
            return grouped
        }
        return nil
    }

    private func exactMedicationBatchValues(
        key: String,
        legacyValues: [AgentDynamicCardValue]
    ) -> [AgentDynamicCardValue] {
        guard let scoped = medicationBatchDecision?[key] else {
            return legacyValues
        }
        return scoped.arrayValue ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case model
        case selectedModel = "selected_model"
        case answerModel = "answer_model"
        case toolModels = "tool_models"
        case fallbackReasons = "fallback_reasons"
        case elapsedMs = "elapsed_ms"
        case llmRounds = "llm_rounds"
        case llmUsage = "llm_usage"
        case sourcesUsed = "sources_used"
        case toolsUsed = "tools_used"
        case completionStatus = "completion_status"
        case perf
        case thinkingSteps = "thinking_steps"
        case cards
        case cardType = "card_type"
        case cardData = "card_data"
        case medicationBatchDecision = "medication_batch_decision"
        case writeReceipts = "write_receipts"
        case safetyAlerts = "safety_alerts"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        model = try? c.decode(String.self, forKey: .model)
        selectedModel = try? c.decode(String.self, forKey: .selectedModel)
        answerModel = try? c.decode(String.self, forKey: .answerModel)
        toolModels = (try? c.decode([String].self, forKey: .toolModels)) ?? []
        fallbackReasons = (try? c.decode([String].self, forKey: .fallbackReasons)) ?? []
        elapsedMs = try? c.decode(Int.self, forKey: .elapsedMs)
        llmRounds = try? c.decode(Int.self, forKey: .llmRounds)
        llmUsage = try? c.decode(LLMUsageProfile.self, forKey: .llmUsage)
        sourcesUsed = (try? c.decode([String].self, forKey: .sourcesUsed)) ?? []
        toolsUsed = (try? c.decode([String].self, forKey: .toolsUsed)) ?? []
        completionStatus = try? c.decode(String.self, forKey: .completionStatus)
        perf = try? c.decode(MessagePerf.self, forKey: .perf)
        thinkingSteps = (try? c.decode([String].self, forKey: .thinkingSteps)) ?? []
        cards = (try? c.decode([AgentDynamicCardDescriptor].self, forKey: .cards)) ?? []
        cardType = try? c.decode(String.self, forKey: .cardType)
        cardData = try? c.decode(AgentDynamicCardValue.self, forKey: .cardData)
        medicationBatchDecision = try? c.decode(
            AgentDynamicCardValue.self,
            forKey: .medicationBatchDecision
        )
        writeReceipts = (try? c.decode(
            [AgentDynamicCardValue].self,
            forKey: .writeReceipts
        )) ?? []
        safetyAlerts = (try? c.decode(
            [AgentDynamicCardValue].self,
            forKey: .safetyAlerts
        )) ?? []
    }
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
/// same Agent conversation store, so the durable list is the single source of truth;
/// the local `UserDefaultsAgentConversationStore` is only an offline cache.
public protocol AgentConversationRemoteSourcing: Sendable {
    /// Fetches the conversation list (most-recent first), mapped to snapshots.
    /// Snapshots carry no messages yet — call `fetchDetail` when one is opened.
    /// `search` matches title ∪ message content (backend EXISTS subquery); nil = all.
    func fetchConversations(limit: Int, offset: Int, search: String?) async throws -> [AgentConversationSnapshot]
    /// Fetches a single conversation's full message list.
    func fetchDetail(conversationID: Int) async throws -> [AgentChatMessage]
    /// Deletes a conversation on the backend. No-op-safe to call before syncing
    /// local cache.
    func deleteConversation(conversationID: Int) async throws
    /// Renames a conversation on the backend.
    func renameConversation(conversationID: Int, title: String) async throws
    /// Creates (or refreshes) a public share link for a conversation and returns
    /// the shareable URL (`https://…/shared/<token>`).
    func shareConversation(conversationID: Int) async throws -> URL
}

// MARK: - Client

public final class AgentConversationClient: AgentConversationRemoteSourcing, @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchConversations(limit: Int = 30, offset: Int = 0, search: String? = nil) async throws -> [AgentConversationSnapshot] {
        var path = "agent/conversations?limit=\(limit)&offset=\(offset)"
        if let term = search?.trimmingCharacters(in: .whitespacesAndNewlines), !term.isEmpty {
            let encoded = term.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? term
            path += "&search=\(encoded)"
        }
        let response: BackendConversationList = try await apiClient.get(path)
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

    public func shareConversation(conversationID: Int) async throws -> URL {
        // Mac history rows are Agent conversations → source_type "agent". Backend
        // reuses an existing active share (refreshing its snapshot) or mints one.
        struct ShareBody: Encodable {
            let conversation_id: Int
            let source_type: String
        }
        struct ShareResponse: Decodable { let share_url: String }
        let response: ShareResponse = try await apiClient.post(
            "shared/create",
            body: ShareBody(conversation_id: conversationID, source_type: "agent")
        )
        guard let url = URL(string: response.share_url) else {
            throw APIError.emptyResponse
        }
        return url
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
        let meta = dto.meta
        let card = meta?.firstCard
        let remoteImageURLs = imageURLStrings(from: dto.image_url, baseURL: baseURL)
        return AgentChatMessage(
            id: deterministicID(forMessageID: dto.id),
            role: role,
            content: dto.content ?? "",
            createdAt: parseDate(dto.created_at),
            model: meta?.model,
            selectedModel: meta?.selectedModel,
            answerModel: meta?.answerModel,
            toolModels: meta?.toolModels ?? [],
            fallbackReasons: meta?.fallbackReasons ?? [],
            elapsedMs: meta?.elapsedMs,
            llmRounds: meta?.llmRounds,
            llmUsage: meta?.llmUsage,
            sourcesUsed: meta?.sourcesUsed ?? [],
            toolsUsed: meta?.toolsUsed ?? [],
            completionStatus: meta?.completionStatus,
            perf: meta?.perf,
            thinkingSteps: meta?.thinkingSteps ?? [],
            cardType: card?.type,
            cardRender: card?.render,
            cardData: card?.data,
            cardActions: card?.actions ?? [],
            remoteImageURLs: remoteImageURLs
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
