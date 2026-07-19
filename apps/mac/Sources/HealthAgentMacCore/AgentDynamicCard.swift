import Foundation

public struct AgentDynamicCardDescriptor: Codable, Equatable, Sendable {
    public let type: String
    public let render: AgentDynamicCardRenderDescriptor?
    public let data: AgentDynamicCardValue
    public let actions: [AgentDynamicCardActionDescriptor]

    public init(
        type: String,
        render: AgentDynamicCardRenderDescriptor? = nil,
        data: AgentDynamicCardValue,
        actions: [AgentDynamicCardActionDescriptor] = []
    ) {
        self.type = type
        self.render = render
        self.data = data
        self.actions = actions
    }

    private enum CodingKeys: String, CodingKey {
        case type, render, data, actions
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decode(String.self, forKey: .type)
        render = try? c.decode(AgentDynamicCardRenderDescriptor.self, forKey: .render)
        data = try c.decode(AgentDynamicCardValue.self, forKey: .data)
        actions = (try? c.decode([AgentDynamicCardActionDescriptor].self, forKey: .actions)) ?? []
    }

    /// The backend can return more than one atomic capability for one reply.
    /// Preserve them as a renderable group rather than letting the client drop
    /// every descriptor after the first one.
    public static func grouped(_ cards: [AgentDynamicCardDescriptor]) -> AgentDynamicCardDescriptor? {
        guard !cards.isEmpty else { return nil }
        if cards.count == 1 { return cards[0] }
        let encodedCards = cards.compactMap { $0.groupValue() }
        guard !encodedCards.isEmpty else { return nil }
        return AgentDynamicCardDescriptor(
            type: "cards_group",
            data: .object(["cards": .array(encodedCards)])
        )
    }

    static func fromGroupValue(_ value: AgentDynamicCardValue) -> AgentDynamicCardDescriptor? {
        guard let data = try? JSONEncoder().encode(value) else { return nil }
        return try? JSONDecoder().decode(AgentDynamicCardDescriptor.self, from: data)
    }

    func groupValue() -> AgentDynamicCardValue? {
        guard let data = try? JSONEncoder().encode(self) else { return nil }
        return try? JSONDecoder().decode(AgentDynamicCardValue.self, from: data)
    }
}

public struct AgentDynamicCardRenderDescriptor: Codable, Equatable, Sendable {
    public let atom: String?
    public let reason: String?
    public let dedupeKey: String?

    public init(atom: String? = nil, reason: String? = nil, dedupeKey: String? = nil) {
        self.atom = atom
        self.reason = reason
        self.dedupeKey = dedupeKey
    }

    private enum CodingKeys: String, CodingKey {
        case atom
        case reason
        case dedupeKey = "dedupe_key"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        atom = Self.clean(try? c.decode(String.self, forKey: .atom))
        reason = Self.clean(try? c.decode(String.self, forKey: .reason))
        dedupeKey = Self.clean(try? c.decode(String.self, forKey: .dedupeKey))
    }

    private static func clean(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
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
    public let capabilityID: String?
    public let requiredReceipt: Bool?
    public let autonomyTier: String?
    public let policyReason: String?

    public init(
        id: String? = nil,
        label: String,
        action: String,
        endpoint: String? = nil,
        payload: AgentDynamicCardValue? = nil,
        style: String? = nil,
        requiresManualConfirm: Bool? = nil,
        disabledReason: String? = nil,
        capabilityID: String? = nil,
        requiredReceipt: Bool? = nil,
        autonomyTier: String? = nil,
        policyReason: String? = nil
    ) {
        self.id = id
        self.label = label
        self.action = action
        self.endpoint = endpoint
        self.payload = payload
        self.style = style
        self.requiresManualConfirm = requiresManualConfirm
        self.disabledReason = disabledReason
        self.capabilityID = capabilityID
        self.requiredReceipt = requiredReceipt
        self.autonomyTier = autonomyTier
        self.policyReason = policyReason
    }

    private enum CodingKeys: String, CodingKey {
        case id, label, action, endpoint, payload, style
        case requiresManualConfirm = "requires_manual_confirm"
        case disabledReason = "disabled_reason"
        case capabilityID = "capability_id"
        case requiredReceipt = "required_receipt"
        case autonomyTier = "autonomy_tier"
        case policyReason = "policy_reason"
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
        capabilityID = try? c.decode(String.self, forKey: .capabilityID)
        requiredReceipt = try? c.decode(Bool.self, forKey: .requiredReceipt)
        autonomyTier = try? c.decode(String.self, forKey: .autonomyTier)
        policyReason = try? c.decode(String.self, forKey: .policyReason)
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
