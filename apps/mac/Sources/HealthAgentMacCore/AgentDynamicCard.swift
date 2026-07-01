import Foundation

public struct AgentDynamicCardDescriptor: Codable, Equatable, Sendable {
    public let type: String
    public let data: AgentDynamicCardValue
    public let actions: [AgentDynamicCardActionDescriptor]

    public init(type: String, data: AgentDynamicCardValue, actions: [AgentDynamicCardActionDescriptor] = []) {
        self.type = type
        self.data = data
        self.actions = actions
    }

    private enum CodingKeys: String, CodingKey {
        case type, data, actions
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decode(String.self, forKey: .type)
        data = try c.decode(AgentDynamicCardValue.self, forKey: .data)
        actions = (try? c.decode([AgentDynamicCardActionDescriptor].self, forKey: .actions)) ?? []
    }
}

public struct AgentDynamicCardActionDescriptor: Codable, Equatable, Sendable {
    public let id: String?
    public let label: String
    public let action: String
    public let endpoint: String?
    public let payload: AgentDynamicCardValue?
    public let style: String?
    public let requiresManualConfirm: Bool?
    public let disabledReason: String?

    public init(
        id: String? = nil,
        label: String,
        action: String,
        endpoint: String? = nil,
        payload: AgentDynamicCardValue? = nil,
        style: String? = nil,
        requiresManualConfirm: Bool? = nil,
        disabledReason: String? = nil
    ) {
        self.id = id
        self.label = label
        self.action = action
        self.endpoint = endpoint
        self.payload = payload
        self.style = style
        self.requiresManualConfirm = requiresManualConfirm
        self.disabledReason = disabledReason
    }

    private enum CodingKeys: String, CodingKey {
        case id, label, action, endpoint, payload, style
        case requiresManualConfirm = "requires_manual_confirm"
        case disabledReason = "disabled_reason"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try? c.decode(String.self, forKey: .id)
        label = ((try? c.decode(String.self, forKey: .label)) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        action = ((try? c.decode(String.self, forKey: .action)) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        endpoint = try? c.decode(String.self, forKey: .endpoint)
        payload = try? c.decode(AgentDynamicCardValue.self, forKey: .payload)
        style = try? c.decode(String.self, forKey: .style)
        requiresManualConfirm = try? c.decode(Bool.self, forKey: .requiresManualConfirm)
        disabledReason = try? c.decode(String.self, forKey: .disabledReason)
    }
}

public enum AgentDynamicCardValue: Codable, Equatable, Sendable {
    case null
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case object([String: AgentDynamicCardValue])
    case array([AgentDynamicCardValue])

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() {
            self = .null
        } else if let value = try? c.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? c.decode(Int.self) {
            self = .int(value)
        } else if let value = try? c.decode(Double.self) {
            self = .double(value)
        } else if let value = try? c.decode(String.self) {
            self = .string(value)
        } else if let value = try? c.decode([String: AgentDynamicCardValue].self) {
            self = .object(value)
        } else if let value = try? c.decode([AgentDynamicCardValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: c,
                debugDescription: "Unsupported dynamic card JSON value"
            )
        }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null:
            try c.encodeNil()
        case .string(let value):
            try c.encode(value)
        case .int(let value):
            try c.encode(value)
        case .double(let value):
            try c.encode(value)
        case .bool(let value):
            try c.encode(value)
        case .object(let value):
            try c.encode(value)
        case .array(let value):
            try c.encode(value)
        }
    }

    public subscript(key: String) -> AgentDynamicCardValue? {
        guard case .object(let object) = self else {
            return nil
        }
        return object[key]
    }

    public var stringValue: String? {
        switch self {
        case .string(let value):
            return value
        case .int(let value):
            return String(value)
        case .double(let value):
            return String(value)
        case .bool(let value):
            return value ? "true" : "false"
        case .null, .object, .array:
            return nil
        }
    }

    public var intValue: Int? {
        switch self {
        case .int(let value):
            return value
        case .double(let value) where value.rounded() == value:
            return Int(value)
        case .string(let value):
            return Int(value)
        case .null, .double, .bool, .object, .array:
            return nil
        }
    }

    public var boolValue: Bool? {
        switch self {
        case .bool(let value):
            return value
        case .string(let value):
            let lowered = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if ["true", "yes", "1"].contains(lowered) { return true }
            if ["false", "no", "0"].contains(lowered) { return false }
            return nil
        case .null, .int, .double, .object, .array:
            return nil
        }
    }

    public var arrayValue: [AgentDynamicCardValue]? {
        guard case .array(let value) = self else {
            return nil
        }
        return value
    }
}
