import Foundation

public enum MedicationBatchDecisionStatus: String, Codable, Equatable, Sendable {
    case executed
    case dismissed
    case expired
    /// A 409 that is not the server's expiry case. The server confirmed that
    /// this gesture wrote nothing, but did not authorize us to call it expired.
    case notWritten = "not_written"
}

public struct MedicationBatchActionOutcome: Equatable, Sendable {
    public let decisionStatus: MedicationBatchDecisionStatus
    public let writeReceipts: [AgentDynamicCardValue]
    public let safetyAlerts: [AgentDynamicCardValue]
    public let reconciliationRequired: Bool

    public init(
        decisionStatus: MedicationBatchDecisionStatus,
        writeReceipts: [AgentDynamicCardValue],
        safetyAlerts: [AgentDynamicCardValue],
        reconciliationRequired: Bool = false
    ) {
        self.decisionStatus = decisionStatus
        self.writeReceipts = writeReceipts
        self.safetyAlerts = safetyAlerts
        self.reconciliationRequired = reconciliationRequired
    }
}

public protocol MedicationBatchWriteIntentActing: Sendable {
    func confirmMedicationBatch(intentID: Int) async throws -> MedicationBatchActionOutcome
    func dismissMedicationBatch(intentID: Int) async throws -> MedicationBatchActionOutcome
}

public enum MedicationBatchWriteIntentError: LocalizedError, Equatable {
    case invalidIntentID
    case invalidTerminalResponse
    case missingWriteReceipts
    case invalidWriteReceipt
    case invalidSafetyAlert

    public var errorDescription: String? {
        switch self {
        case .invalidIntentID:
            "用药确认标识无效，没有写入。"
        case .invalidTerminalResponse:
            "服务端没有返回可核对的终态，请刷新对话后重试。"
        case .missingWriteReceipts:
            "服务端显示已执行，但逐项回执缺失；请刷新对话核对，系统不会据此重复写入。"
        case .invalidWriteReceipt:
            "逐项写入回执不完整，请刷新对话核对。"
        case .invalidSafetyAlert:
            "用药安全提示不完整，请刷新对话核对。"
        }
    }
}

public final class MedicationBatchWriteIntentClient: MedicationBatchWriteIntentActing, @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func confirmMedicationBatch(intentID: Int) async throws -> MedicationBatchActionOutcome {
        let id = try Self.requireIntentID(intentID)
        do {
            let response: MedicationBatchIntentResponse = try await apiClient.post(
                "write-intents/\(id)/confirm",
                body: MedicationBatchEmptyRequest()
            )
            let decisionStatus = try Self.resolvedDecisionStatus(response)
            if decisionStatus == .dismissed || decisionStatus == .expired {
                return Self.noWrite(decisionStatus)
            }
            guard decisionStatus == .executed else {
                throw MedicationBatchWriteIntentError.invalidTerminalResponse
            }
            let receipts = try Self.validatedReceipts(response.writeReceipts)
            guard !receipts.isEmpty else {
                throw MedicationBatchWriteIntentError.missingWriteReceipts
            }
            return MedicationBatchActionOutcome(
                decisionStatus: .executed,
                writeReceipts: receipts,
                safetyAlerts: try Self.validatedSafetyAlerts(response.safetyAlerts)
            )
        } catch APIError.httpStatus(409, let detail) {
            return Self.noWrite(Self.conflictStatus(detail: detail))
        }
    }

    public func dismissMedicationBatch(intentID: Int) async throws -> MedicationBatchActionOutcome {
        let id = try Self.requireIntentID(intentID)
        do {
            let response: MedicationBatchIntentResponse = try await apiClient.post(
                "write-intents/\(id)/dismiss",
                body: MedicationBatchEmptyRequest()
            )
            let decisionStatus = try Self.resolvedDecisionStatus(response)
            if decisionStatus == .dismissed || decisionStatus == .expired {
                return Self.noWrite(decisionStatus)
            }
            if decisionStatus == .executed {
                // Confirm won the server race. Dismiss returns no receipts, so
                // only the source-assistant terminal meta may supply them.
                return MedicationBatchActionOutcome(
                    decisionStatus: .executed,
                    writeReceipts: [],
                    safetyAlerts: [],
                    reconciliationRequired: true
                )
            }
            throw MedicationBatchWriteIntentError.invalidTerminalResponse
        } catch APIError.httpStatus(409, let detail) {
            return Self.noWrite(Self.conflictStatus(detail: detail))
        }
    }

    /// `status` is the persisted write-intent state. `decision_status` is the
    /// medication-batch business terminal state and may refine a persisted
    /// dismissal into expiry. Missing `decision_status` is a legacy response;
    /// every unknown or contradictory pair fails closed.
    private static func resolvedDecisionStatus(
        _ response: MedicationBatchIntentResponse
    ) throws -> MedicationBatchDecisionStatus {
        let persistedStatus: MedicationBatchDecisionStatus
        switch response.status {
        case MedicationBatchDecisionStatus.executed.rawValue:
            persistedStatus = .executed
        case MedicationBatchDecisionStatus.dismissed.rawValue:
            persistedStatus = .dismissed
        default:
            throw MedicationBatchWriteIntentError.invalidTerminalResponse
        }

        guard let rawDecisionStatus = response.decisionStatus else {
            return persistedStatus
        }
        guard let decisionStatus = MedicationBatchDecisionStatus(rawValue: rawDecisionStatus) else {
            throw MedicationBatchWriteIntentError.invalidTerminalResponse
        }

        switch (persistedStatus, decisionStatus) {
        case (.executed, .executed), (.dismissed, .dismissed), (.dismissed, .expired):
            return decisionStatus
        default:
            throw MedicationBatchWriteIntentError.invalidTerminalResponse
        }
    }

    private static func requireIntentID(_ value: Int) throws -> Int {
        guard value > 0 else { throw MedicationBatchWriteIntentError.invalidIntentID }
        return value
    }

    private static func noWrite(_ status: MedicationBatchDecisionStatus) -> MedicationBatchActionOutcome {
        MedicationBatchActionOutcome(
            decisionStatus: status,
            writeReceipts: [],
            safetyAlerts: []
        )
    }

    private static func conflictStatus(detail: String?) -> MedicationBatchDecisionStatus {
        detail?.contains("过期") == true ? .expired : .notWritten
    }

    private static func validatedReceipts(
        _ raw: [AgentDynamicCardValue]?
    ) throws -> [AgentDynamicCardValue] {
        let values = raw ?? []
        guard values.allSatisfy(isVerifiedMedicationReceipt) else {
            throw MedicationBatchWriteIntentError.invalidWriteReceipt
        }
        return values
    }

    private static func isVerifiedMedicationReceipt(_ value: AgentDynamicCardValue) -> Bool {
        guard case .object(let receipt) = value,
              receipt["operation_id"]?.stringValue?.isEmpty == false,
              receipt["status"]?.stringValue == "verified",
              receipt["resource_type"]?.stringValue == "medication_log",
              receipt["resource_id"]?.stringValue?.isEmpty == false,
              receipt["completed_at"]?.stringValue?.isEmpty == false,
              receipt["verified"]?.boolValue == true else {
            return false
        }
        return true
    }

    private static func validatedSafetyAlerts(
        _ raw: [AgentDynamicCardValue]?
    ) throws -> [AgentDynamicCardValue] {
        let values = raw ?? []
        let valid = values.allSatisfy { value in
            guard case .object(let alert) = value else { return false }
            return alert["rule_id"]?.stringValue != nil
                && alert["category"]?.stringValue != nil
                && alert["title"]?.stringValue != nil
                && alert["message"]?.stringValue != nil
        }
        guard valid else { throw MedicationBatchWriteIntentError.invalidSafetyAlert }
        return values
    }
}

private struct MedicationBatchIntentResponse: Decodable {
    let status: String
    let decisionStatus: String?
    let writeReceipts: [AgentDynamicCardValue]?
    let safetyAlerts: [AgentDynamicCardValue]?

    enum CodingKeys: String, CodingKey {
        case status
        case decisionStatus = "decision_status"
        case writeReceipts = "write_receipts"
        case safetyAlerts = "safety_alerts"
    }
}

private struct MedicationBatchEmptyRequest: Encodable {}

/// Pure transformations shared by live action handling and history recovery.
/// Every transform recurses through `cards_group`, preserving unrelated cards.
public enum MedicationBatchCardProjection {
    public static func intentID(for action: AgentDynamicCardActionDescriptor) -> Int? {
        guard action.action == "write_intent.confirm" || action.action == "write_intent.dismiss",
              let raw = action.payload?["write_intent_id"]?.stringValue,
              let intentID = Int(raw), intentID > 0 else {
            return nil
        }
        return intentID
    }

    public static func isSafeAction(_ action: AgentDynamicCardActionDescriptor) -> Bool {
        guard let intentID = intentID(for: action),
              action.requiresManualConfirm == true,
              action.requiredReceipt == true,
              action.capabilityID == "medication_draft.v1",
              action.autonomyTier == "manual_confirm",
              action.policyReason == "manual_confirm_write" else {
            return false
        }
        let command = action.action == "write_intent.confirm" ? "confirm" : "dismiss"
        return action.endpoint == "/write-intents/\(intentID)/\(command)"
    }

    public static func action(
        in descriptor: AgentDynamicCardDescriptor,
        actionID: String
    ) -> AgentDynamicCardActionDescriptor? {
        if descriptor.type == "cards_group",
           case .array(let rawCards)? = descriptor.data["cards"] {
            return rawCards
                .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
                .compactMap { action(in: $0, actionID: actionID) }
                .first
        }
        guard descriptor.type == "medication_draft" else { return nil }
        return descriptor.actions.first { $0.id == actionID && isSafeAction($0) }
    }

    public static func settingPending(
        descriptor: AgentDynamicCardDescriptor,
        intentID: Int,
        pending: Bool
    ) -> AgentDynamicCardDescriptor {
        map(descriptor: descriptor, intentID: intentID) { card in
            guard case .object(var data) = card.data else { return card }
            data["action_pending"] = .bool(pending)
            return AgentDynamicCardDescriptor(
                type: card.type,
                render: card.render,
                data: .object(data),
                actions: card.actions
            )
        }
    }

    public static func projectingTerminal(
        descriptor: AgentDynamicCardDescriptor,
        intentID: Int,
        outcome: MedicationBatchActionOutcome
    ) -> AgentDynamicCardDescriptor {
        map(descriptor: descriptor, intentID: intentID) { card in
            guard case .object(var data) = card.data else { return card }
            data["action_pending"] = .bool(false)
            data["decision_status"] = .string(outcome.decisionStatus.rawValue)
            data["write_receipts"] = .array(
                outcome.decisionStatus == .executed ? outcome.writeReceipts : []
            )
            data["safety_alerts"] = .array(
                outcome.decisionStatus == .executed ? outcome.safetyAlerts : []
            )
            data["reconciliation_required"] = .bool(outcome.reconciliationRequired)
            return AgentDynamicCardDescriptor(
                type: card.type,
                render: card.render,
                data: .object(data),
                actions: []
            )
        }
    }

    public static func restoringTerminal(
        cards: [AgentDynamicCardDescriptor],
        intentID: Int,
        status: MedicationBatchDecisionStatus,
        writeReceipts: [AgentDynamicCardValue],
        safetyAlerts: [AgentDynamicCardValue]
    ) -> [AgentDynamicCardDescriptor] {
        let outcome = MedicationBatchActionOutcome(
            decisionStatus: status,
            writeReceipts: writeReceipts,
            safetyAlerts: safetyAlerts
        )
        return cards.map {
            projectingTerminal(descriptor: $0, intentID: intentID, outcome: outcome)
        }
    }

    public static func targets(
        descriptor: AgentDynamicCardDescriptor,
        intentID: Int
    ) -> Bool {
        if descriptor.type == "cards_group",
           case .array(let rawCards)? = descriptor.data["cards"] {
            return rawCards
                .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
                .contains { targets(descriptor: $0, intentID: intentID) }
        }
        guard descriptor.type == "medication_draft" else { return false }
        if descriptor.data["write_intent_id"]?.intValue == intentID { return true }
        return descriptor.actions.contains { self.intentID(for: $0) == intentID }
    }

    public static func terminalOutcome(
        in descriptor: AgentDynamicCardDescriptor,
        intentID: Int
    ) -> MedicationBatchActionOutcome? {
        if descriptor.type == "cards_group",
           case .array(let rawCards)? = descriptor.data["cards"] {
            return rawCards
                .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
                .compactMap { terminalOutcome(in: $0, intentID: intentID) }
                .first
        }
        guard targets(descriptor: descriptor, intentID: intentID),
              let rawStatus = descriptor.data["decision_status"]?.stringValue,
              let status = MedicationBatchDecisionStatus(rawValue: rawStatus) else {
            return nil
        }
        let receipts = descriptor.data["write_receipts"]?.arrayValue ?? []
        let alerts = descriptor.data["safety_alerts"]?.arrayValue ?? []
        let expectedCount = descriptor.data["items"]?.arrayValue?.count ?? 0
        let incompleteReceipts = status == .executed
            && (receipts.isEmpty || (expectedCount > 0 && receipts.count != expectedCount))
        return MedicationBatchActionOutcome(
            decisionStatus: status,
            writeReceipts: status == .executed ? receipts : [],
            safetyAlerts: status == .executed ? alerts : [],
            reconciliationRequired: incompleteReceipts
        )
    }

    public static func itemCount(
        in descriptor: AgentDynamicCardDescriptor,
        intentID: Int
    ) -> Int? {
        if descriptor.type == "cards_group",
           case .array(let rawCards)? = descriptor.data["cards"] {
            return rawCards
                .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
                .compactMap { itemCount(in: $0, intentID: intentID) }
                .first
        }
        guard targets(descriptor: descriptor, intentID: intentID) else { return nil }
        return descriptor.data["items"]?.arrayValue?.count
    }

    private static func map(
        descriptor: AgentDynamicCardDescriptor,
        intentID: Int,
        transform: (AgentDynamicCardDescriptor) -> AgentDynamicCardDescriptor
    ) -> AgentDynamicCardDescriptor {
        if descriptor.type == "cards_group",
           case .object(var group) = descriptor.data,
           case .array(let rawCards)? = group["cards"] {
            group["cards"] = .array(rawCards.map { raw in
                guard let child = AgentDynamicCardDescriptor.fromGroupValue(raw) else { return raw }
                return map(descriptor: child, intentID: intentID, transform: transform).groupValue() ?? raw
            })
            return AgentDynamicCardDescriptor(
                type: descriptor.type,
                render: descriptor.render,
                data: .object(group),
                actions: descriptor.actions
            )
        }
        return targets(descriptor: descriptor, intentID: intentID)
            ? transform(descriptor)
            : descriptor
    }
}
