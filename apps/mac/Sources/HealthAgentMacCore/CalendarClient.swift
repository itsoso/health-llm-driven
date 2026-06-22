import Foundation

/// 一条外部日历事件(GET /calendar/events)。start/end 是 ISO datetime;all_day 时
/// 进顶部 strip 而非时间网格。字段宽松,后端多给的忽略。
public struct CalendarEvent: Codable, Equatable, Identifiable, Sendable {
    public let id: String
    public let title: String?
    public let start: String?
    public let end: String?
    public let allDay: Bool
    public let location: String?
    public let sourceID: Int?

    private enum CodingKeys: String, CodingKey {
        case id
        case title
        case start
        case end
        case allDay = "all_day"
        case location
        case sourceID = "source_id"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let intID = try? container.decode(Int.self, forKey: .id) {
            self.id = String(intID)
        } else {
            self.id = (try? container.decode(String.self, forKey: .id)) ?? UUID().uuidString
        }
        self.title = try? container.decodeIfPresent(String.self, forKey: .title)
        self.start = try? container.decodeIfPresent(String.self, forKey: .start)
        self.end = try? container.decodeIfPresent(String.self, forKey: .end)
        self.allDay = (try? container.decode(Bool.self, forKey: .allDay)) ?? false
        self.location = try? container.decodeIfPresent(String.self, forKey: .location)
        self.sourceID = try? container.decodeIfPresent(Int.self, forKey: .sourceID)
    }

    public init(
        id: String,
        title: String?,
        start: String?,
        end: String?,
        allDay: Bool = false,
        location: String? = nil,
        sourceID: Int? = nil
    ) {
        self.id = id
        self.title = title
        self.start = start
        self.end = end
        self.allDay = allDay
        self.location = location
        self.sourceID = sourceID
    }
}

public struct CalendarSource: Codable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let provider: String
    public let name: String
    public let color: String?
    public let writable: Bool
    public let syncEnabled: Bool
    public let lastSyncAt: String?
    public let lastError: String?

    enum CodingKeys: String, CodingKey {
        case id
        case provider
        case name
        case color
        case writable
        case syncEnabled = "sync_enabled"
        case lastSyncAt = "last_sync_at"
        case lastError = "last_error"
    }

    public init(
        id: Int,
        provider: String,
        name: String,
        color: String? = nil,
        writable: Bool = false,
        syncEnabled: Bool,
        lastSyncAt: String? = nil,
        lastError: String? = nil
    ) {
        self.id = id
        self.provider = provider
        self.name = name
        self.color = color
        self.writable = writable
        self.syncEnabled = syncEnabled
        self.lastSyncAt = lastSyncAt
        self.lastError = lastError
    }
}

public struct CalendarSourceCreateRequest: Encodable, Equatable, Sendable {
    public let provider: String
    public let name: String
    public let url: String
    public let color: String?
    public let username: String?
    public let password: String?

    public init(
        provider: String,
        name: String,
        url: String,
        color: String? = nil,
        username: String? = nil,
        password: String? = nil
    ) {
        self.provider = provider
        self.name = name
        self.url = url
        self.color = color
        self.username = username
        self.password = password
    }
}

public struct CalendarSourceUpdateRequest: Encodable, Equatable, Sendable {
    public let name: String?
    public let color: String?
    public let syncEnabled: Bool?

    enum CodingKeys: String, CodingKey {
        case name
        case color
        case syncEnabled = "sync_enabled"
    }

    public init(name: String? = nil, color: String? = nil, syncEnabled: Bool? = nil) {
        self.name = name
        self.color = color
        self.syncEnabled = syncEnabled
    }
}

public struct CalendarSourceSyncResult: Codable, Equatable, Sendable {
    public let synced: Int?
    public let error: String?
}

public struct CalendarSyncResult: Codable, Equatable, Sendable {
    public let sources: [String: CalendarSourceSyncResult]
    public let count: Int
}

public final class CalendarClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// 拉一个日期区间的事件。`from`/`to` 是 "YYYY-MM-DD"(含两端)。
    public func fetchEvents(from: String, to: String) async throws -> [CalendarEvent] {
        let query = "calendar/events?from=\(from)&to=\(to)"
        return try await apiClient.get(query)
    }

    public func listSources() async throws -> [CalendarSource] {
        try await apiClient.get("calendar/sources")
    }

    public func addSource(_ request: CalendarSourceCreateRequest) async throws -> CalendarSource {
        try await apiClient.post("calendar/sources", body: request)
    }

    public func updateSource(id: Int, patch: CalendarSourceUpdateRequest) async throws -> CalendarSource {
        try await apiClient.put("calendar/sources/\(id)", body: patch)
    }

    public func deleteSource(id: Int) async throws {
        try await apiClient.delete("calendar/sources/\(id)")
    }

    public func sync() async throws -> CalendarSyncResult {
        try await apiClient.post("calendar/sync", body: CalendarEmptyRequest())
    }
}

private struct CalendarEmptyRequest: Encodable {}
