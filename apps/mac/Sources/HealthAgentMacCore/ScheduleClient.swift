import Foundation

/// 处方明细(movement/diet/sleep 才有)。后端字段宽松,只取展示需要的几项,
/// 其余忽略 —— 新增后端字段不会让解码红。
public struct SchedulePrescription: Codable, Equatable, Sendable {
    public let durationMin: Int?
    public let intensity: String?
    public let summary: String?
    public let note: String?

    enum CodingKeys: String, CodingKey {
        case durationMin = "duration_min"
        case intensity
        case summary
        case note
    }

    public init(durationMin: Int? = nil, intensity: String? = nil, summary: String? = nil, note: String? = nil) {
        self.durationMin = durationMin
        self.intensity = intensity
        self.summary = summary
        self.note = note
    }

    /// 一行处方摘要(用于块副标题 / 详情)。优先 summary,其次拼时长+强度。
    public var displaySummary: String? {
        if let summary, !summary.isEmpty { return summary }
        if let note, !note.isEmpty { return note }
        var parts: [String] = []
        if let durationMin { parts.append("\(durationMin)min") }
        if let intensity, !intensity.isEmpty { parts.append(intensity) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// 一条已排程的健康日程项(GET /schedule/today 的 scheduled[])。
public struct ScheduleItem: Codable, Equatable, Identifiable, Sendable {
    public let id: String
    public let domain: String           // medication/supplement/movement/diet/sleep
    public let time: String             // "HH:MM"
    public let title: String
    public let prescription: SchedulePrescription?

    private enum CodingKeys: String, CodingKey {
        case id
        case domain
        case time
        case title
        case prescription
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        // 后端 id 可能是 int 或 string —— 两种都接,统一成 string。
        if let intID = try? container.decode(Int.self, forKey: .id) {
            self.id = String(intID)
        } else {
            self.id = (try? container.decode(String.self, forKey: .id)) ?? UUID().uuidString
        }
        self.domain = (try? container.decode(String.self, forKey: .domain)) ?? "other"
        self.time = (try? container.decode(String.self, forKey: .time)) ?? ""
        self.title = (try? container.decode(String.self, forKey: .title)) ?? ""
        self.prescription = try? container.decodeIfPresent(SchedulePrescription.self, forKey: .prescription)
    }

    public init(id: String, domain: String, time: String, title: String, prescription: SchedulePrescription? = nil) {
        self.id = id
        self.domain = domain
        self.time = time
        self.title = title
        self.prescription = prescription
    }
}

/// GET /schedule/today 响应。rejected/deferred 桌面只读视图暂不展示,忽略即可。
public struct TodaySchedule: Codable, Equatable, Sendable {
    public let scheduled: [ScheduleItem]
    public let disclaimer: String?

    enum CodingKeys: String, CodingKey {
        case scheduled
        case disclaimer
    }

    public init(scheduled: [ScheduleItem], disclaimer: String? = nil) {
        self.scheduled = scheduled
        self.disclaimer = disclaimer
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.scheduled = (try? container.decode([ScheduleItem].self, forKey: .scheduled)) ?? []
        self.disclaimer = try? container.decodeIfPresent(String.self, forKey: .disclaimer)
    }
}

public final class ScheduleClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchToday() async throws -> TodaySchedule {
        try await apiClient.get("schedule/today")
    }
}
