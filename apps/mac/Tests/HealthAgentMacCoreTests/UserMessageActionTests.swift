import XCTest
@testable import HealthAgentMacCore

@MainActor
final class UserMessageActionTests: XCTestCase {
    func testUserPromptCanBeCopiedWhileAnAnswerIsStreaming() {
        let model = AgentChatViewModel()
        model.messages = [
            .init(role: .user, content: "第一行\n第二行 <原文>"),
            .init(role: .assistant, content: "正在回答")
        ]
        model.isStreaming = true
        let messages = model.renderedTranscript()
        XCTAssertTrue(messages[0].showCopy)
        XCTAssertTrue(messages[0].showEdit)
        XCTAssertTrue(messages[0].jsonObject.contains("\"edit\":true"))
        XCTAssertFalse(messages[1].showEdit)
        XCTAssertFalse(messages[1].showCopy)
        XCTAssertTrue(messages[0].bodyHTML.contains("&lt;原文&gt;"))
    }

    func testCopyAndEditReturnOriginalUserTextWithoutChangingHistory() {
        let model = AgentChatViewModel()
        let prompt = AgentChatMessage(role: .user, content: "  **原始文字**\n<script>literal</script> 😀  ")
        let answer = AgentChatMessage(role: .assistant, content: "回答")
        model.messages = [prompt, answer]
        XCTAssertEqual(model.copyableText(messageID: prompt.id.uuidString), prompt.content)
        XCTAssertEqual(model.editableUserMessage(messageID: prompt.id.uuidString), prompt)
        XCTAssertNil(model.editableUserMessage(messageID: answer.id.uuidString))
        XCTAssertNil(model.editableUserMessage(messageID: UUID().uuidString))
        XCTAssertNil(model.copyableText(messageID: UUID().uuidString))
        XCTAssertEqual(model.messages, [prompt, answer])
    }

    func testImageOnlyMessageDoesNotOfferAnEmptyTextEditor() {
        let model = AgentChatViewModel()
        let message = AgentChatMessage(role: .user, content: "", remoteImageURLs: ["https://example.test/image.png"])
        model.messages = [message]
        XCTAssertNil(model.editableUserMessage(messageID: message.id.uuidString))
        XCTAssertFalse(model.renderedTranscript()[0].showEdit)
    }
}
