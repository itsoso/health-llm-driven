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
}
