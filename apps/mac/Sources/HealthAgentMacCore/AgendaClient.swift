import Foundation

public struct AgendaSource: Codable, Equatable, Sendable {
    public let objectType: String
    public let objectID: Int

    enum CodingKeys: String, CodingKey {
        case objectType = "object_type"
        case objectID = "object_id"
    }

    public init(objectType: String, objectID: Int) {
        self.objectType = objectType
        self.objectID = objectID
    }
}

public struct AgendaItem: Codable, Equatable, Identifiable, Sendable {
    public let type: String
    public let title: String
    public let status: String
    public let timeWindow: String?
    public let priority: Int
    public let canDefaultComplete: Bool?
    public let detail: String?
    public let responsible: String?
    public let nextDue: String?
    public let light: String?
    public let zone: String?
    public let readinessScore: Int?
    public let confidence: String?
    public let source: AgendaSource

    public var id: String { "\(source.objectType)-\(source.objectID)-\(type)" }

    enum CodingKeys: String, CodingKey {
        case type
        case title
        case status
        case timeWindow = "time_window"
        case priority
        case canDefaultComplete = "can_default_complete"
        case detail
        case responsible
        case nextDue = "next_due"
        case light
        case zone
        case readinessScore = "readiness_score"
        case confidence
        case source
    }

    public init(
        type: String,
        title: String,
        status: String,
        timeWindow: String? = nil,
        priority: Int,
        canDefaultComplete: Bool? = nil,
        detail: String? = nil,
        responsible: String? = nil,
        nextDue: String? = nil,
        light: String? = nil,
        zone: String? = nil,
        readinessScore: Int? = nil,
        confidence: String? = nil,
        source: AgendaSource
    ) {
        self.type = type
        self.title = title
        self.status = status
        self.timeWindow = timeWindow
        self.priority = priority
        self.canDefaultComplete = canDefaultComplete
        self.detail = detail
        self.responsible = responsible
        self.nextDue = nextDue
        self.light = light
        self.zone = zone
        self.readinessScore = readinessScore
        self.confidence = confidence
        self.source = source
    }
}

public struct AgendaToday: Codable, Equatable, Sendable {
    public let agendaDate: String
    public let count: Int
    public let items: [AgendaItem]

    enum CodingKeys: String, CodingKey {
        case agendaDate = "agenda_date"
        case count
        case items
    }

    public init(agendaDate: String, count: Int, items: [AgendaItem]) {
        self.agendaDate = agendaDate
        self.count = count
        self.items = items
    }
}

public struct AgendaCompleteRequest: Encodable, Equatable, Sendable {
    public let objectType: String
    public let objectID: Int
    public let track: String
    public let value: [String: JSONValue]?

    enum CodingKeys: String, CodingKey {
        case objectType = "object_type"
        case objectID = "object_id"
        case track
        case value
    }

    public init(objectType: String, objectID: Int, track: String = "protocol", value: [String: JSONValue]? = nil) {
        self.objectType = objectType
        self.objectID = objectID
        self.track = track
        self.value = value
    }
}

public struct AgendaSummary: Equatable, Sendable {
    public let total: Int
    public let actionable: Int
    public let overdue: Int
    public let info: Int

    public init(today: AgendaToday) {
        self.total = today.items.count
        self.actionable = today.items.filter { $0.source.objectType == "health_protocol" && $0.status == "pending" }.count
        self.overdue = today.items.filter { $0.status == "overdue" }.count
        self.info = today.items.filter { $0.status == "info" }.count
    }
}

public enum AgendaTone: Equatable, Sendable {
    case green
    case yellow
    case red
    case blue
    case gray
}

public struct AgendaItemPresentation: Equatable, Sendable {
    public let statusLabel: String
    public let tone: AgendaTone
    public let metaLine: String
    public let canComplete: Bool
    public let systemImage: String

    public init(item: AgendaItem) {
        if item.type == "training" {
            let light = item.light ?? "yellow"
            self.statusLabel = "Training \(light)"
            self.tone = Self.tone(forLight: light)
            self.metaLine = [item.readinessScore.map { "Readiness \($0)" }, item.confidence]
                .compactMap { $0 }
                .joined(separator: " · ")
            self.canComplete = false
            self.systemImage = "figure.run"
            return
        }

        if item.type == "data_quality" {
            self.statusLabel = "Device check"
            self.tone = .yellow
            self.metaLine = item.detail ?? ""
            self.canComplete = false
            self.systemImage = "arrow.triangle.2.circlepath"
            return
        }

        self.statusLabel = Self.statusLabel(for: item.status)
        self.tone = item.status == "overdue" ? .red : item.status == "completed" ? .green : .blue
        self.metaLine = [item.nextDue, item.responsible].compactMap { $0 }.joined(separator: " · ")
        self.canComplete = item.source.objectType == "health_protocol" && item.status == "pending"
        self.systemImage = Self.systemImage(for: item.type)
    }

    private static func tone(forLight light: String) -> AgendaTone {
        if light == "green" { return .green }
        if light == "red" { return .red }
        return .yellow
    }

    private static func statusLabel(for status: String) -> String {
        switch status {
        case "pending": "Pending"
        case "completed": "Completed"
        case "skipped": "Skipped"
        case "due": "Due"
        case "overdue": "Overdue"
        case "info": "Info"
        default: status
        }
    }

    private static func systemImage(for type: String) -> String {
        switch type {
        case "hydration": "drop"
        case "medication": "pills"
        case "diet": "fork.knife"
        case "sleep": "moon"
        case "checkup": "calendar.badge.exclamationmark"
        case "correction": "wrench.and.screwdriver"
        default: "circle"
        }
    }
}

public final class AgendaClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchToday() async throws -> AgendaToday {
        try await apiClient.get("agenda/today")
    }

    public func complete(_ source: AgendaSource, track: String = "protocol", value: [String: JSONValue]? = nil) async throws -> JSONValue {
        try await apiClient.post(
            "agenda/complete",
            body: AgendaCompleteRequest(
                objectType: source.objectType,
                objectID: source.objectID,
                track: track,
                value: value
            )
        )
    }
}
