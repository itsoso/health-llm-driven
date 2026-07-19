import Foundation
import XCTest
@testable import HealthAgentMacCore

private struct SuccessfulDietDraftClient: DietDraftConfirming {
    func confirmDietDraft(action: AgentDynamicCardActionDescriptor) async throws -> DietDraftConfirmationReceipt {
        guard action.id == "confirm-diet-draft" else { throw APIError.emptyResponse }
        return DietDraftConfirmationReceipt(id: 73, displayMessage: "已记录午餐")
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
}
