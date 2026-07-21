import Foundation
import XCTest
@testable import HealthAgentMacCore

private actor MedicationBatchClientSpy: MedicationBatchWriteIntentActing {
    private(set) var calls: [String] = []
    let outcome: MedicationBatchActionOutcome
    let delay: Duration

    init(
        outcome: MedicationBatchActionOutcome,
        delay: Duration = .zero
    ) {
        self.outcome = outcome
        self.delay = delay
    }

    func confirmMedicationBatch(intentID: Int) async throws -> MedicationBatchActionOutcome {
        calls.append("confirm:\(intentID)")
        if delay > .zero { try await Task.sleep(for: delay) }
        return outcome
    }

    func dismissMedicationBatch(intentID: Int) async throws -> MedicationBatchActionOutcome {
        calls.append("dismiss:\(intentID)")
        if delay > .zero { try await Task.sleep(for: delay) }
        return outcome
    }
}

final class MedicationBatchConfirmationTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    func testClientConfirmsOwnerScopedIntentAndKeepsEveryReceiptAndSafetyAlert() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(
                request.url?.absoluteString,
                "https://example.test/api/v1/write-intents/41/confirm"
            )
            let data = Data(#"""
            {
              "id":41,
              "status":"executed",
              "idempotent":false,
              "write_receipts":[
                {"operation_id":"medication_log:101","status":"verified","resource_type":"medication_log","resource_id":101,"completed_at":"2026-07-21T10:00:00Z","verified":true},
                {"operation_id":"medication_log:102","status":"verified","resource_type":"medication_log","resource_id":102,"completed_at":"2026-07-21T10:00:00Z","verified":true}
              ],
              "safety_alerts":[
                {"rule_id":"ddi-1","category":"ddi","severity":{"value":4,"label":"high"},"title":"提示一","message":"内容一"},
                {"rule_id":"pgx-2","category":"pgx","severity":{"value":3,"label":"medium"},"title":"提示二","message":"内容二"}
              ]
            }
            """#.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        let outcome = try await client.confirmMedicationBatch(intentID: 41)

        XCTAssertEqual(outcome.decisionStatus, .executed)
        XCTAssertEqual(outcome.writeReceipts.count, 2)
        XCTAssertEqual(outcome.safetyAlerts.count, 2)
        XCTAssertFalse(outcome.reconciliationRequired)
    }

    func testConfirmUsesExpiredDecisionStatusWhenStorageStatusIsDismissed() async throws {
        URLProtocolStub.handler = { request in
            let data = Data(#"{"id":41,"status":"dismissed","decision_status":"expired"}"#.utf8)
            return (
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: nil
                )!,
                data
            )
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        let outcome = try await client.confirmMedicationBatch(intentID: 41)

        XCTAssertEqual(outcome.decisionStatus, .expired)
        XCTAssertTrue(outcome.writeReceipts.isEmpty)
        XCTAssertTrue(outcome.safetyAlerts.isEmpty)
    }

    func testDismissUsesExpiredDecisionStatusWhenStorageStatusIsDismissed() async throws {
        URLProtocolStub.handler = { request in
            let data = Data(#"{"id":41,"status":"dismissed","decision_status":"expired"}"#.utf8)
            return (
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: nil
                )!,
                data
            )
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        let outcome = try await client.dismissMedicationBatch(intentID: 41)

        XCTAssertEqual(outcome.decisionStatus, .expired)
        XCTAssertTrue(outcome.writeReceipts.isEmpty)
        XCTAssertTrue(outcome.safetyAlerts.isEmpty)
    }

    func testConfirmFailsClosedForContradictoryTerminalStatuses() async {
        URLProtocolStub.handler = { request in
            let data = Data(#"{"id":41,"status":"executed","decision_status":"expired"}"#.utf8)
            return (
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: nil
                )!,
                data
            )
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        do {
            _ = try await client.confirmMedicationBatch(intentID: 41)
            XCTFail("Contradictory terminal states must fail closed")
        } catch let error as MedicationBatchWriteIntentError {
            XCTAssertEqual(error, .invalidTerminalResponse)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testConfirmFailsClosedForUnknownDecisionStatus() async {
        URLProtocolStub.handler = { request in
            let data = Data(#"{"id":41,"status":"dismissed","decision_status":"archived"}"#.utf8)
            return (
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: nil
                )!,
                data
            )
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        do {
            _ = try await client.confirmMedicationBatch(intentID: 41)
            XCTFail("Unknown decision states must fail closed")
        } catch let error as MedicationBatchWriteIntentError {
            XCTAssertEqual(error, .invalidTerminalResponse)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testConfirmFailsClosedForUnknownStorageStatus() async {
        URLProtocolStub.handler = { request in
            let data = Data(#"{"id":41,"status":"archived","decision_status":"dismissed"}"#.utf8)
            return (
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: nil
                )!,
                data
            )
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        do {
            _ = try await client.confirmMedicationBatch(intentID: 41)
            XCTFail("Unknown storage states must fail closed")
        } catch let error as MedicationBatchWriteIntentError {
            XCTAssertEqual(error, .invalidTerminalResponse)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testClientMapsExpired409ToTerminalNotWrittenOutcome() async throws {
        URLProtocolStub.handler = { request in
            let data = Data(#"{"detail":"确认计划已过期，请重新提交记录"}"#.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 409, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        let outcome = try await client.confirmMedicationBatch(intentID: 41)

        XCTAssertEqual(outcome.decisionStatus, .expired)
        XCTAssertTrue(outcome.writeReceipts.isEmpty)
        XCTAssertTrue(outcome.safetyAlerts.isEmpty)
    }

    func testClientMapsNonExpiry409ToTruthfulNotWrittenOutcome() async throws {
        URLProtocolStub.handler = { request in
            let data = Data(#"{"detail":"确认计划尚未完整展示，请等待当前回复完成后重试"}"#.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 409, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        let outcome = try await client.confirmMedicationBatch(intentID: 41)

        XCTAssertEqual(outcome.decisionStatus, .notWritten)
        XCTAssertTrue(outcome.writeReceipts.isEmpty)
        XCTAssertTrue(outcome.safetyAlerts.isEmpty)
    }

    func testDismissNeverFabricatesAWriteReceipt() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(
                request.url?.absoluteString,
                "https://example.test/api/v1/write-intents/41/dismiss"
            )
            let data = Data(#"{"id":41,"status":"dismissed"}"#.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        let outcome = try await client.dismissMedicationBatch(intentID: 41)

        XCTAssertEqual(outcome.decisionStatus, .dismissed)
        XCTAssertTrue(outcome.writeReceipts.isEmpty)
        XCTAssertTrue(outcome.safetyAlerts.isEmpty)
    }

    func testDismissLosingServerRaceRequiresAuthoritativeTerminalReconciliation() async throws {
        URLProtocolStub.handler = { request in
            let data = Data(#"{"id":41,"status":"executed"}"#.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = MedicationBatchWriteIntentClient(apiClient: stubbedAPIClient())

        let outcome = try await client.dismissMedicationBatch(intentID: 41)

        XCTAssertEqual(outcome.decisionStatus, .executed)
        XCTAssertTrue(outcome.writeReceipts.isEmpty)
        XCTAssertTrue(outcome.reconciliationRequired)
    }

    func testConversationHistoryRestoresExactNamespacedBatchResultWithoutSameTurnPollution() async throws {
        URLProtocolStub.handler = { request in
            let data = Data(#"""
            {
              "id": 9,
              "messages": [{
                "id": 91,
                "role": "assistant",
                "content": "已处理",
                "meta": {
                  "completion_status": "complete",
                  "medication_batch_decision": {
                    "intent_id": 41,
                    "status": "executed",
                    "write_receipts": [
                      {"operation_id":"medication_log:101","status":"verified","resource_type":"medication_log","resource_id":101,"completed_at":"2026-07-21T10:00:00Z","verified":true},
                      {"operation_id":"medication_log:102","status":"verified","resource_type":"medication_log","resource_id":102,"completed_at":"2026-07-21T10:00:00Z","verified":true}
                    ],
                    "safety_alerts": [
                      {"rule_id":"ddi-1","category":"ddi","severity":{"value":4},"title":"提示一","message":"内容一"},
                      {"rule_id":"pgx-2","category":"pgx","severity":{"value":3},"title":"提示二","message":"内容二"}
                    ]
                  },
                  "write_receipts": [
                    {"operation_id":"water_record:999","status":"verified","resource_type":"water_record","resource_id":999,"completed_at":"2026-07-21T09:59:00Z","verified":true},
                    {"operation_id":"medication_log:101","status":"verified","resource_type":"medication_log","resource_id":101,"completed_at":"2026-07-21T10:00:00Z","verified":true},
                    {"operation_id":"medication_log:102","status":"verified","resource_type":"medication_log","resource_id":102,"completed_at":"2026-07-21T10:00:00Z","verified":true}
                  ],
                  "safety_alerts": [
                    {"rule_id":"hydration-0","category":"vitals","severity":{"value":2},"title":"饮水提示","message":"同回合无关提示"},
                    {"rule_id":"ddi-1","category":"ddi","severity":{"value":4},"title":"提示一","message":"内容一"},
                    {"rule_id":"pgx-2","category":"pgx","severity":{"value":3},"title":"提示二","message":"内容二"}
                  ],
                  "cards": [{
                    "type": "medication_draft",
                    "data": {
                      "write_intent_id": 41,
                      "items": [
                        {"medication_name":"伊托必利","actual_dosage":"1粒"},
                        {"medication_name":"替普瑞酮","actual_dosage":"1粒"}
                      ]
                    },
                    "actions": [{
                      "id":"medication-batch-confirm:41",
                      "label":"确认记录",
                      "action":"write_intent.confirm",
                      "endpoint":"/write-intents/41/confirm",
                      "payload":{"write_intent_id":41},
                      "requires_manual_confirm":true,
                      "required_receipt":true,
                      "capability_id":"medication_draft.v1",
                      "autonomy_tier":"manual_confirm",
                      "policy_reason":"manual_confirm_write"
                    }]
                  }]
                }
              }]
            }
            """#.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = AgentConversationClient(apiClient: stubbedAPIClient())

        let messages = try await client.fetchDetail(conversationID: 9)

        let message = try XCTUnwrap(messages.first)
        XCTAssertEqual(message.cardData?["decision_status"]?.stringValue, "executed")
        XCTAssertEqual(message.cardData?["write_receipts"]?.arrayValue?.count, 2)
        XCTAssertEqual(message.cardData?["safety_alerts"]?.arrayValue?.count, 2)
        XCTAssertEqual(
            message.cardData?["write_receipts"]?.arrayValue?.first?["operation_id"]?.stringValue,
            "medication_log:101"
        )
        XCTAssertEqual(
            message.cardData?["safety_alerts"]?.arrayValue?.first?["rule_id"]?.stringValue,
            "ddi-1"
        )
        XCTAssertTrue(message.cardActions.isEmpty)
    }

    func testConversationHistoryFallsBackToLegacyTopLevelBatchResultOnlyWhenNestedFieldsAreMissing() async throws {
        URLProtocolStub.handler = { request in
            let data = Data(#"""
            {
              "id": 9,
              "messages": [{
                "id": 91,
                "role": "assistant",
                "content": "已处理",
                "meta": {
                  "medication_batch_decision": {"intent_id": 41, "status": "executed"},
                  "write_receipts": [
                    {"operation_id":"medication_log:101","status":"verified","resource_type":"medication_log","resource_id":101,"completed_at":"2026-07-21T10:00:00Z","verified":true}
                  ],
                  "safety_alerts": [
                    {"rule_id":"legacy-ddi","category":"ddi","title":"旧提示","message":"旧投影"}
                  ],
                  "cards": [{
                    "type": "medication_draft",
                    "data": {"write_intent_id": 41, "items": [{"medication_name":"伊托必利","actual_dosage":"1粒"}]},
                    "actions": []
                  }]
                }
              }]
            }
            """#.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = AgentConversationClient(apiClient: stubbedAPIClient())

        let messages = try await client.fetchDetail(conversationID: 9)

        let message = try XCTUnwrap(messages.first)
        XCTAssertEqual(message.cardData?["write_receipts"]?.arrayValue?.count, 1)
        XCTAssertEqual(
            message.cardData?["safety_alerts"]?.arrayValue?.first?["rule_id"]?.stringValue,
            "legacy-ddi"
        )
    }

    func testConversationHistoryTreatsExplicitEmptyNamespacedArraysAsAuthoritative() async throws {
        URLProtocolStub.handler = { request in
            let data = Data(#"""
            {
              "id": 9,
              "messages": [{
                "id": 91,
                "role": "assistant",
                "content": "已取消",
                "meta": {
                  "medication_batch_decision": {
                    "intent_id": 41,
                    "status": "dismissed",
                    "write_receipts": [],
                    "safety_alerts": []
                  },
                  "write_receipts": [{"operation_id":"water_record:999"}],
                  "safety_alerts": [{"rule_id":"unrelated"}],
                  "cards": [{
                    "type": "medication_draft",
                    "data": {"write_intent_id": 41, "items": [{"medication_name":"伊托必利","actual_dosage":"1粒"}]},
                    "actions": [{"id":"medication-batch-dismiss:41","label":"取消","action":"write_intent.dismiss"}]
                  }]
                }
              }]
            }
            """#.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = AgentConversationClient(apiClient: stubbedAPIClient())

        let messages = try await client.fetchDetail(conversationID: 9)

        let message = try XCTUnwrap(messages.first)
        XCTAssertEqual(message.cardData?["decision_status"]?.stringValue, "dismissed")
        XCTAssertEqual(message.cardData?["write_receipts"]?.arrayValue, [])
        XCTAssertEqual(message.cardData?["safety_alerts"]?.arrayValue, [])
        XCTAssertTrue(message.cardActions.isEmpty)
    }

    @MainActor
    func testIntentGroupLockAllowsOnlyOneSiblingActionAndProjectsAllReceipts() async throws {
        let outcome = MedicationBatchActionOutcome(
            decisionStatus: .executed,
            writeReceipts: [receipt(id: 101), receipt(id: 102)],
            safetyAlerts: [alert(ruleID: "ddi-1"), alert(ruleID: "pgx-2")]
        )
        let spy = MedicationBatchClientSpy(outcome: outcome, delay: .milliseconds(80))
        let viewModel = AgentChatViewModel(medicationBatchClient: spy)
        viewModel.messages = [pendingMedicationMessage(intentID: 41)]

        let first = Task { @MainActor in
            await viewModel.performMedicationBatchAction(actionID: "medication-batch-confirm:41")
        }
        for _ in 0..<50 {
            if !(await spy.calls).isEmpty { break }
            await Task.yield()
        }
        let startedCalls = await spy.calls
        XCTAssertEqual(startedCalls, ["confirm:41"])
        let sibling = Task { @MainActor in
            await viewModel.performMedicationBatchAction(actionID: "medication-batch-dismiss:41")
        }
        await first.value
        await sibling.value

        let calls = await spy.calls
        XCTAssertEqual(calls, ["confirm:41"])
        XCTAssertEqual(viewModel.messages[0].cardData?["decision_status"]?.stringValue, "executed")
        XCTAssertEqual(viewModel.messages[0].cardData?["write_receipts"]?.arrayValue?.count, 2)
        XCTAssertEqual(viewModel.messages[0].cardData?["safety_alerts"]?.arrayValue?.count, 2)
        XCTAssertTrue(viewModel.messages[0].cardActions.isEmpty)
    }

    @MainActor
    func testDismissProjectsNotWrittenTerminalWithoutReceipt() async {
        let spy = MedicationBatchClientSpy(outcome: MedicationBatchActionOutcome(
            decisionStatus: .dismissed,
            writeReceipts: [],
            safetyAlerts: []
        ))
        let viewModel = AgentChatViewModel(medicationBatchClient: spy)
        viewModel.messages = [pendingMedicationMessage(intentID: 41)]

        await viewModel.performMedicationBatchAction(actionID: "medication-batch-dismiss:41")

        XCTAssertEqual(viewModel.messages[0].cardData?["decision_status"]?.stringValue, "dismissed")
        XCTAssertEqual(viewModel.messages[0].cardData?["write_receipts"]?.arrayValue?.count, 0)
        XCTAssertTrue(viewModel.messages[0].cardActions.isEmpty)
    }

    @MainActor
    func testGroupedMedicationActionRemainsReachableAndPreservesSiblingCard() async throws {
        let spy = MedicationBatchClientSpy(outcome: MedicationBatchActionOutcome(
            decisionStatus: .dismissed,
            writeReceipts: [],
            safetyAlerts: []
        ))
        let pending = pendingMedicationMessage(intentID: 41)
        let medication = AgentDynamicCardDescriptor(
            type: pending.cardType!, data: pending.cardData!, actions: pending.cardActions
        )
        let evidence = AgentDynamicCardDescriptor(
            type: "system_knowledge_evidence",
            data: .object(["entity": .object(["title": .string("胃肠用药")])])
        )
        let group = try XCTUnwrap(AgentDynamicCardDescriptor.grouped([evidence, medication]))
        let viewModel = AgentChatViewModel(medicationBatchClient: spy)
        viewModel.messages = [AgentChatMessage(
            role: .assistant,
            content: "请核对",
            cardType: group.type,
            cardData: group.data
        )]

        await viewModel.performMedicationBatchAction(actionID: "medication-batch-dismiss:41")

        let cards = try XCTUnwrap(viewModel.messages[0].cardData?["cards"]?.arrayValue)
            .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
        XCTAssertEqual(cards.count, 2)
        XCTAssertEqual(
            cards.first(where: { $0.type == "system_knowledge_evidence" })?
                .data["entity"]?["title"]?.stringValue,
            "胃肠用药"
        )
        let terminalMedication = try XCTUnwrap(cards.first(where: { $0.type == "medication_draft" }))
        XCTAssertEqual(terminalMedication.data["decision_status"]?.stringValue, "dismissed")
        XCTAssertTrue(terminalMedication.actions.isEmpty)
    }

    @MainActor
    func testTextConfirmationDoneWithoutCardsProjectsPriorPendingMedicationDraft() async throws {
        let stream = medicationTerminalStream(
            status: .executed,
            writeReceipts: [receipt(id: 101), receipt(id: 102)],
            safetyAlerts: [alert(ruleID: "ddi-1"), alert(ruleID: "pgx-2")]
        )
        let viewModel = AgentChatViewModel(
            streamService: MedicationBatchStaticStreamService(stream: stream)
        )
        viewModel.messages = [pendingMedicationMessage(intentID: 41)]

        await viewModel.send("确认")

        XCTAssertEqual(viewModel.messages[0].cardData?["decision_status"]?.stringValue, "executed")
        XCTAssertEqual(viewModel.messages[0].cardData?["write_receipts"]?.arrayValue?.count, 2)
        XCTAssertEqual(viewModel.messages[0].cardData?["safety_alerts"]?.arrayValue?.count, 2)
        XCTAssertTrue(viewModel.messages[0].cardActions.isEmpty)
        XCTAssertNil(viewModel.messages.last?.cardType, "done.cards=[] must not fabricate a new card")
    }

    @MainActor
    func testTextNoWriteDoneStatusesRecursivelyClosePendingGroupAndPreserveSibling() async throws {
        for status in [MedicationBatchDecisionStatus.dismissed, .expired] {
            let stream = medicationTerminalStream(
                status: status,
                writeReceipts: [],
                safetyAlerts: []
            )
            let pending = pendingMedicationMessage(intentID: 41)
            let medication = AgentDynamicCardDescriptor(
                type: try XCTUnwrap(pending.cardType),
                data: try XCTUnwrap(pending.cardData),
                actions: pending.cardActions
            )
            let evidence = AgentDynamicCardDescriptor(
                type: "system_knowledge_evidence",
                data: .object(["entity": .object(["title": .string("胃肠用药")])])
            )
            let group = try XCTUnwrap(AgentDynamicCardDescriptor.grouped([evidence, medication]))
            let viewModel = AgentChatViewModel(
                streamService: MedicationBatchStaticStreamService(stream: stream)
            )
            viewModel.messages = [AgentChatMessage(
                role: .assistant,
                content: "请核对",
                cardType: group.type,
                cardData: group.data
            )]

            await viewModel.send(status == .dismissed ? "取消" : "确认")

            let cards = try XCTUnwrap(viewModel.messages[0].cardData?["cards"]?.arrayValue)
                .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
            XCTAssertEqual(cards.count, 2)
            XCTAssertEqual(
                cards.first(where: { $0.type == "system_knowledge_evidence" })?
                    .data["entity"]?["title"]?.stringValue,
                "胃肠用药"
            )
            let terminalMedication = try XCTUnwrap(
                cards.first(where: { $0.type == "medication_draft" })
            )
            XCTAssertEqual(terminalMedication.data["decision_status"]?.stringValue, status.rawValue)
            XCTAssertEqual(terminalMedication.data["write_receipts"]?.arrayValue, [])
            XCTAssertEqual(terminalMedication.data["safety_alerts"]?.arrayValue, [])
            XCTAssertTrue(terminalMedication.actions.isEmpty)
        }
    }

    func testMedicationCardRendersItemizedActionsReceiptsAlertsAndAccessibleSemantics() throws {
        let message = pendingMedicationMessage(intentID: 41)
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: try XCTUnwrap(message.cardType),
            data: try XCTUnwrap(message.cardData),
            actions: message.cardActions
        ))

        XCTAssertTrue(html.contains("伊托必利"))
        XCTAssertTrue(html.contains("替普瑞酮"))
        XCTAssertTrue(html.contains("本次 1粒"))
        XCTAssertTrue(html.contains("xiaoba-medication-action://medication-batch-confirm:41"))
        XCTAssertTrue(html.contains("xiaoba-medication-action://medication-batch-dismiss:41"))
        XCTAssertTrue(html.contains("role=\"button\""))
        XCTAssertTrue(html.contains("aria-label=\"确认记录\""))

        let terminal = MedicationBatchCardProjection.projectingTerminal(
            descriptor: AgentDynamicCardDescriptor(
                type: message.cardType!, data: message.cardData!, actions: message.cardActions
            ),
            intentID: 41,
            outcome: MedicationBatchActionOutcome(
                decisionStatus: .executed,
                writeReceipts: [receipt(id: 101), receipt(id: 102)],
                safetyAlerts: [alert(ruleID: "ddi-1"), alert(ruleID: "pgx-2")]
            )
        )
        let terminalHTML = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: terminal.type,
            data: terminal.data,
            actions: terminal.actions
        ))
        XCTAssertEqual(terminalHTML.components(separatedBy: "已验证").count - 1, 2)
        XCTAssertTrue(terminalHTML.contains("提示 ddi-1"))
        XCTAssertTrue(terminalHTML.contains("提示 pgx-2"))
        XCTAssertTrue(terminalHTML.contains("aria-label=\"逐项写入回执\""))
        XCTAssertTrue(terminalHTML.contains("aria-label=\"用药安全提示\""))
    }

    func testPendingProjectionHidesBothSiblingActions() throws {
        let message = pendingMedicationMessage(intentID: 41)
        let pending = MedicationBatchCardProjection.settingPending(
            descriptor: AgentDynamicCardDescriptor(
                type: message.cardType!, data: message.cardData!, actions: message.cardActions
            ),
            intentID: 41,
            pending: true
        )

        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: pending.type,
            data: pending.data,
            actions: pending.actions
        ))

        XCTAssertTrue(html.contains("aria-busy=\"true\""))
        XCTAssertTrue(html.contains("aria-live=\"polite\""))
        XCTAssertFalse(html.contains("xiaoba-medication-action://"))
    }

    func testIncompleteTerminalReceiptSetRequiresReconciliation() throws {
        let pending = pendingMedicationMessage(intentID: 41)
        let descriptor = AgentDynamicCardDescriptor(
            type: pending.cardType!, data: pending.cardData!, actions: pending.cardActions
        )
        let incomplete = MedicationBatchCardProjection.projectingTerminal(
            descriptor: descriptor,
            intentID: 41,
            outcome: MedicationBatchActionOutcome(
                decisionStatus: .executed,
                writeReceipts: [receipt(id: 101)],
                safetyAlerts: []
            )
        )

        let restored = try XCTUnwrap(MedicationBatchCardProjection.terminalOutcome(
            in: incomplete,
            intentID: 41
        ))

        XCTAssertTrue(restored.reconciliationRequired)
    }

    func testWriteIntentActionIsRejectedOutsideMedicationCardCapability() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "system_knowledge_evidence",
            data: .object(["entity": .object(["title": .string("证据")])]),
            actions: [medicationAction(intentID: 41, command: "confirm", label: "确认记录")]
        ))

        XCTAssertFalse(html.contains("xiaoba-medication-action://"))
        XCTAssertFalse(html.contains(">确认记录</a>"))
    }

    func testBundledBridgeLocksIntentSiblingsBeforePostingAction() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let resourceURL = packageRoot
            .appendingPathComponent("Sources/HealthAgentMac/Resources/chat-transcript.html")
        let source = try String(contentsOf: resourceURL, encoding: .utf8)

        XCTAssertTrue(source.contains("messageHandlers.medicationBatchAction"))
        XCTAssertTrue(source.contains("xiaoba-medication-action://"))
        XCTAssertTrue(source.contains("medication-batch-action[data-write-intent-id="))
        XCTAssertTrue(source.contains("setAttribute(\"aria-disabled\", \"true\")"))
        XCTAssertTrue(source.contains("ev.key === \" \""))
    }

    func testOlderMedicationCardMutationForcesFullTranscriptSync() {
        let first = ChatTranscriptHTML.RenderedMessage(
            id: "first", role: "assistant", bodyHTML: "pending", isStreaming: false, showCopy: false
        )
        let last = ChatTranscriptHTML.RenderedMessage(
            id: "last", role: "user", bodyHTML: "ok", isStreaming: false, showCopy: false
        )
        let terminalFirst = ChatTranscriptHTML.RenderedMessage(
            id: "first", role: "assistant", bodyHTML: "executed", isStreaming: false, showCopy: false
        )
        let updatedLast = ChatTranscriptHTML.RenderedMessage(
            id: "last", role: "user", bodyHTML: "ok!", isStreaming: false, showCopy: false
        )
        let switchedConversation = ChatTranscriptHTML.RenderedMessage(
            id: "other", role: "assistant", bodyHTML: "new chat", isStreaming: false, showCopy: false
        )

        XCTAssertFalse(ChatTranscriptHTML.canAppendOrUpdateLast(
            previous: [first, last],
            next: [terminalFirst, last]
        ))
        XCTAssertTrue(ChatTranscriptHTML.canAppendOrUpdateLast(
            previous: [first, last],
            next: [first, updatedLast]
        ))
        XCTAssertFalse(ChatTranscriptHTML.canAppendOrUpdateLast(
            previous: [last],
            next: [switchedConversation]
        ))
    }

    private func stubbedAPIClient() -> APIClient {
        APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )
    }
}

private func pendingMedicationMessage(intentID: Int) -> AgentChatMessage {
    let actions = [
        medicationAction(intentID: intentID, command: "confirm", label: "确认记录"),
        medicationAction(intentID: intentID, command: "dismiss", label: "取消"),
    ]
    return AgentChatMessage(
        role: .assistant,
        content: "请核对",
        cardType: "medication_draft",
        cardData: .object([
            "write_intent_id": .int(intentID),
            "items": .array([
                .object([
                    "medication_name": .string("伊托必利"),
                    "actual_dosage": .string("1粒"),
                    "observed_strength": .string("50mg"),
                ]),
                .object([
                    "medication_name": .string("替普瑞酮"),
                    "actual_dosage": .string("1粒"),
                ]),
            ]),
            "taken_at": .string("2026-07-21 10:00"),
            "boundary": .string("确认后只记录这次已服事实。"),
        ]),
        cardActions: actions
    )
}

private func medicationAction(intentID: Int, command: String, label: String) -> AgentDynamicCardActionDescriptor {
    AgentDynamicCardActionDescriptor(
        id: "medication-batch-\(command):\(intentID)",
        label: label,
        action: "write_intent.\(command)",
        endpoint: "/write-intents/\(intentID)/\(command)",
        payload: .object(["write_intent_id": .int(intentID)]),
        style: command == "confirm" ? "primary" : "secondary",
        requiresManualConfirm: true,
        capabilityID: "medication_draft.v1",
        requiredReceipt: true,
        autonomyTier: "manual_confirm",
        policyReason: "manual_confirm_write"
    )
}

private func receipt(id: Int) -> AgentDynamicCardValue {
    .object([
        "operation_id": .string("medication_log:\(id)"),
        "status": .string("verified"),
        "resource_type": .string("medication_log"),
        "resource_id": .int(id),
        "completed_at": .string("2026-07-21T10:00:00Z"),
        "verified": .bool(true),
    ])
}

private func alert(ruleID: String) -> AgentDynamicCardValue {
    .object([
        "rule_id": .string(ruleID),
        "category": .string("ddi"),
        "severity": .object(["value": .int(3), "label": .string("high")]),
        "title": .string("提示 \(ruleID)"),
        "message": .string("请咨询医生或药师"),
    ])
}

private func medicationTerminalStream(
    status: MedicationBatchDecisionStatus,
    writeReceipts: [AgentDynamicCardValue],
    safetyAlerts: [AgentDynamicCardValue]
) -> AsyncThrowingStream<AgentStreamEvent, Error> {
    AsyncThrowingStream { continuation in
        continuation.yield(.done(
            conversationID: 9,
            messageID: 92,
            completionStatus: "complete",
            model: nil,
            sourcesUsed: [],
            toolsUsed: [],
            elapsedMs: nil,
            llmRounds: nil,
            cards: [],
            medicationBatchDecision: AgentMedicationBatchDecision(
                intentID: 41,
                status: status,
                writeReceipts: writeReceipts,
                safetyAlerts: safetyAlerts
            )
        ))
        continuation.finish()
    }
}

private struct MedicationBatchStaticStreamService: AgentStreamServicing {
    let stream: AsyncThrowingStream<AgentStreamEvent, Error>

    func stream(
        message: String,
        conversationID: Int?,
        extraContext: String?,
        images: [AgentChatImage]
    ) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        stream
    }
}
