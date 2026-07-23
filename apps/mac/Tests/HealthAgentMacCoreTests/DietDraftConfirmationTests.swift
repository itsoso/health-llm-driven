import Foundation
import XCTest
@testable import HealthAgentMacCore

private struct SuccessfulDietDraftClient: DietDraftConfirming {
    func confirmDietDraft(action: AgentDynamicCardActionDescriptor) async throws -> DietDraftConfirmationReceipt {
        guard action.id == "confirm-diet-draft" else { throw APIError.emptyResponse }
        return DietDraftConfirmationReceipt(id: 73, displayMessage: "已记录午餐")
    }
}

private struct SuccessfulAIGCMediaClient: AIGCMediaJobLoading {
    func getJob(id: String) async throws -> AIGCMediaJobProjection {
        AIGCMediaJobProjection(
            id: id,
            kind: "text_to_image",
            status: "succeeded",
            progress: 100,
            result: nil,
            errorMessage: nil
        )
    }

    func getConfirmation(id: String) async throws -> AIGCMediaConfirmationProjection {
        AIGCMediaConfirmationProjection(
            id: id,
            status: "pending",
            canConfirm: true,
            requiresReconfirmation: false,
            job: nil
        )
    }

    func confirmDraft(id: String) async throws -> AIGCMediaJobProjection {
        AIGCMediaJobProjection(
            id: "job-1",
            kind: "text_to_image",
            status: "succeeded",
            progress: 100,
            result: nil,
            errorMessage: nil
        )
    }
}

private struct RecoveringAIGCMediaClient: AIGCMediaJobLoading {
    func getJob(id: String) async throws -> AIGCMediaJobProjection {
        throw APIError.emptyResponse
    }

    func getConfirmation(id: String) async throws -> AIGCMediaConfirmationProjection {
        AIGCMediaConfirmationProjection(
            id: id,
            status: "dispatched",
            canConfirm: false,
            requiresReconfirmation: false,
            job: AIGCMediaJobProjection(
                id: "job-reconciled",
                kind: "text_to_video",
                status: "queued",
                progress: 0,
                result: nil,
                errorMessage: nil
            )
        )
    }

    func confirmDraft(id: String) async throws -> AIGCMediaJobProjection {
        throw APIError.httpStatus(409, "确认正在处理")
    }
}

final class DietDraftConfirmationTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    @MainActor
    func testConfirmationUsesKnownCardActionAndOnlyMarksRecordedAfterReceipt() async {
        let action = AgentDynamicCardActionDescriptor(
            id: "confirm-diet-draft",
            label: "确认记录",
            action: "diet_record.create",
            endpoint: "/diet/records",
            payload: .object([
                "record": .object([
                    "record_date": .string("2026-07-19"),
                    "meal_type": .string("lunch"),
                    "food_items": .string("鸡胸肉和杂粮饭"),
                    "photo_draft_token": .string("photo-draft-token"),
                ]),
            ]),
            style: "primary",
            requiresManualConfirm: true,
            capabilityID: "diet_draft.v1",
            requiredReceipt: true,
            autonomyTier: "manual_confirm"
        )
        let viewModel = AgentChatViewModel(dietDraftClient: SuccessfulDietDraftClient())
        viewModel.messages = [
            AgentChatMessage(
                role: .assistant,
                content: "请核对后确认",
                cardType: "diet_draft",
                cardData: .object(["food_items": .string("鸡胸肉和杂粮饭")]),
                cardActions: [action]
            ),
        ]

        await viewModel.confirmDietDraft(actionID: "confirm-diet-draft")

        XCTAssertEqual(viewModel.messages[0].cardData?["recorded"]?.boolValue, true)
        XCTAssertEqual(viewModel.messages[0].cardData?["record_id"]?.intValue, 73)
        XCTAssertTrue(viewModel.messages[0].cardActions.isEmpty)
        XCTAssertNil(viewModel.errorMessage)
    }

    func testRecordClientSendsOnlyServerBoundDietDraftFields() async throws {
        let action = AgentDynamicCardActionDescriptor(
            id: "confirm-diet-draft",
            label: "确认记录",
            action: "diet_record.create",
            endpoint: "/diet/records",
            payload: .object([
                "record": .object([
                    "record_date": .string("2026-07-19"),
                    "meal_type": .string("lunch"),
                    "food_items": .string("鸡胸肉和杂粮饭"),
                    "source": .string("chat_photo"),
                    "calories": .double(428),
                    "ai_recognized": .int(1),
                    "ai_raw_result": .object(["version": .string("food-v1")]),
                    "photo_draft_token": .string("photo-draft-token"),
                ]),
            ]),
            style: "primary",
            requiresManualConfirm: true,
            capabilityID: "diet_draft.v1",
            requiredReceipt: true,
            autonomyTier: "manual_confirm"
        )
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/diet/records")
            let body = try XCTUnwrap(request.bodyDataForTesting)
            let object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(object["photo_draft_token"] as? String, "photo-draft-token")
            XCTAssertEqual(object["source"] as? String, "chat_photo")
            XCTAssertEqual(object["ai_recognized"] as? Int, 1)
            XCTAssertNil(object["image_base64"])
            XCTAssertNil(object["photo_url"])
            let data = #"{"id":73,"display_message":"已记录午餐"}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = RecordClient(apiClient: APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: URLSession(configuration: .ephemeralWithStub)
        ))

        let receipt = try await client.confirmDietDraft(action: action)

        XCTAssertEqual(receipt, DietDraftConfirmationReceipt(id: 73, displayMessage: "已记录午餐"))
    }

    @MainActor
    func testGroupedDietDraftConfirmationKeepsItsActionReachable() async throws {
        let action = AgentDynamicCardActionDescriptor(
            id: "confirm-diet-draft",
            label: "确认记录",
            action: "diet_record.create",
            endpoint: "/diet/records",
            payload: .object([
                "record": .object([
                    "record_date": .string("2026-07-19"),
                    "meal_type": .string("lunch"),
                    "food_items": .string("鸡胸肉"),
                    "photo_draft_token": .string("draft-token"),
                ]),
            ]),
            style: "primary",
            requiresManualConfirm: true,
            capabilityID: "diet_draft.v1",
            requiredReceipt: true
        )
        let diet = AgentDynamicCardDescriptor(
            type: "diet_draft",
            data: .object(["food_items": .string("鸡胸肉")]),
            actions: [action]
        )
        let media = AgentDynamicCardDescriptor(
            type: "aigc_media_job",
            data: .object(["job_id": .string("job-1")])
        )
        let group = try XCTUnwrap(AgentDynamicCardDescriptor.grouped([media, diet]))
        let viewModel = AgentChatViewModel(dietDraftClient: SuccessfulDietDraftClient())
        viewModel.messages = [
            AgentChatMessage(
                role: .assistant,
                content: "",
                cardType: group.type,
                cardData: group.data
            ),
        ]

        await viewModel.confirmDietDraft(actionID: "confirm-diet-draft")

        let rawCards = try XCTUnwrap(viewModel.messages[0].cardData?["cards"]?.arrayValue)
        let savedDiet = try XCTUnwrap(
            rawCards.compactMap(AgentDynamicCardDescriptor.fromGroupValue)
                .first(where: { $0.type == "diet_draft" })
        )
        XCTAssertEqual(savedDiet.data["recorded"]?.boolValue, true)
        XCTAssertEqual(savedDiet.data["record_id"]?.intValue, 73)
        XCTAssertTrue(savedDiet.actions.isEmpty)
    }

    @MainActor
    func testGroupedAIGCConfirmationPreservesSiblingDietReceipt() async throws {
        let confirmation = AgentDynamicCardDescriptor(
            type: "aigc_media_confirmation",
            data: .object(["confirmation_id": .string("confirm-1")])
        )
        let diet = AgentDynamicCardDescriptor(
            type: "diet_draft",
            data: .object([
                "food_items": .string("鸡胸肉"),
                "recorded": .bool(true),
                "receipt_message": .string("已记录午餐"),
            ])
        )
        let group = try XCTUnwrap(AgentDynamicCardDescriptor.grouped([confirmation, diet]))
        let viewModel = AgentChatViewModel(aigcMediaClient: SuccessfulAIGCMediaClient())
        viewModel.messages = [
            AgentChatMessage(role: .assistant, content: "", cardType: group.type, cardData: group.data),
        ]

        await viewModel.confirmAIGCMediaDraft(id: "confirm-1")

        let cards = try XCTUnwrap(viewModel.messages[0].cardData?["cards"]?.arrayValue)
            .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
        let media = try XCTUnwrap(cards.first(where: { $0.type == "aigc_media_job" }))
        let preservedDiet = try XCTUnwrap(cards.first(where: { $0.type == "diet_draft" }))
        XCTAssertEqual(media.data["job_id"]?.stringValue, "job-1")
        XCTAssertEqual(preservedDiet.data["recorded"]?.boolValue, true)
        XCTAssertEqual(preservedDiet.data["receipt_message"]?.stringValue, "已记录午餐")
    }

    @MainActor
    func testAIGCConfirmationReconcilesExistingJobAfterLostConfirmResponse() async throws {
        let viewModel = AgentChatViewModel(aigcMediaClient: RecoveringAIGCMediaClient())
        viewModel.messages = [
            AgentChatMessage(
                role: .assistant,
                content: "",
                cardType: "aigc_media_confirmation",
                cardData: .object([
                    "confirmation_id": .string("confirm-reconcile"),
                    "kind": .string("text_to_video"),
                ])
            ),
        ]

        await viewModel.confirmAIGCMediaDraft(id: "confirm-reconcile")

        XCTAssertEqual(viewModel.messages[0].cardType, "aigc_media_job")
        XCTAssertEqual(viewModel.messages[0].cardData?["job_id"]?.stringValue, "job-reconciled")
        XCTAssertEqual(viewModel.messages[0].cardData?["status"]?.stringValue, "queued")
    }
}
