import Foundation
import XCTest
@testable import HealthAgentMacCore

/// `AgentChatViewModel.renderedTranscript()` 的内容缓存测试。
///
/// 背景:composer 的 draft 是 View 的 @State,每次按键都重算 body → renderedTranscript()
/// 被反复调用。缓存只在 messages / isStreaming / proposedActions 真正变化时重渲,否则返回
/// 上次结果(消除按键卡顿)。这里守的是「缓存不能返回过期数据」—— 三个 key 各自的失效契约
/// 都要成立,否则一改输入还显示旧内容就是静默 bug。
@MainActor
final class AgentTranscriptCacheTests: XCTestCase {

    private func assistant(_ content: String, id: UUID = UUID()) -> AgentChatMessage {
        AgentChatMessage(id: id, role: .assistant, content: content)
    }

    private func user(
        _ content: String,
        id: UUID = UUID(),
        remoteImageURLs: [String] = []
    ) -> AgentChatMessage {
        AgentChatMessage(id: id, role: .user, content: content, remoteImageURLs: remoteImageURLs)
    }

    // 同样输入重复渲染 → 结果一致(缓存命中不破坏内容)。
    func testIdempotentOnUnchangedInputs() {
        let vm = AgentChatViewModel()
        vm.messages = [assistant("# Hello")]
        let first = vm.renderedTranscript()
        let second = vm.renderedTranscript()
        XCTAssertEqual(first, second)
        XCTAssertEqual(first.count, 1)
        XCTAssertTrue(first[0].bodyHTML.contains("Hello"))
        XCTAssertEqual(first[0].role, "assistant")
    }

    // content 变了 → 缓存必须失效,不能返回旧渲染(这是最危险的 stale 回归)。
    func testContentChangeInvalidatesCache() {
        let vm = AgentChatViewModel()
        let id = UUID()
        vm.messages = [assistant("# Hello", id: id)]
        let before = vm.renderedTranscript()
        XCTAssertTrue(before[0].bodyHTML.contains("Hello"))

        vm.messages = [assistant("# Goodbye", id: id)]
        let after = vm.renderedTranscript()
        XCTAssertTrue(after[0].bodyHTML.contains("Goodbye"))
        XCTAssertFalse(after[0].bodyHTML.contains("Hello"), "缓存未随 content 失效 → 返回了过期渲染")
    }

    // isStreaming 是 key 之一:翻转后最后一条助手消息走 plain streaming 分支(无复制按钮)。
    func testStreamingKeyInvalidates() {
        let vm = AgentChatViewModel()
        vm.messages = [assistant("# Title")]
        vm.isStreaming = false
        let still = vm.renderedTranscript()[0]
        XCTAssertFalse(still.isStreaming)
        XCTAssertTrue(still.showCopy)
        XCTAssertFalse(still.bodyHTML.contains("streaming-text"))

        vm.isStreaming = true
        let live = vm.renderedTranscript()[0]
        XCTAssertTrue(live.isStreaming, "isStreaming 变化未让缓存失效")
        XCTAssertFalse(live.showCopy)
        XCTAssertTrue(live.bodyHTML.contains("streaming-text"))
    }

    // proposedActions 是 key 之一:空正文 + 出现待确认动作 → 正文换成占位文案。
    func testProposedActionKeyInvalidates() {
        let vm = AgentChatViewModel()
        let id = UUID()
        vm.messages = [assistant("", id: id)]
        let placeholder = "已生成需要确认的结构化动作。"

        let before = vm.renderedTranscript()[0]
        XCTAssertFalse(before.bodyHTML.contains(placeholder))

        vm.proposedActions = [
            AgentProposedAction(
                id: "\(id.uuidString):0",
                messageID: id,
                toolName: "health_record",
                title: "记录",
                summary: "示例",
                rawCommand: "{}",
                parameters: [:],
                status: .pending
            )
        ]
        let after = vm.renderedTranscript()[0]
        XCTAssertTrue(after.bodyHTML.contains(placeholder), "proposedActions 变化未让缓存失效")
    }

    // messages 增减 → 缓存失效且顺序保持。
    func testAppendGrowsTranscript() {
        let vm = AgentChatViewModel()
        let first = assistant("first")
        vm.messages = [first]
        XCTAssertEqual(vm.renderedTranscript().count, 1)

        vm.messages = [first, assistant("second")]
        let grown = vm.renderedTranscript()
        XCTAssertEqual(grown.count, 2)
        XCTAssertTrue(grown[0].bodyHTML.contains("first"))
        XCTAssertTrue(grown[1].bodyHTML.contains("second"))
    }

    func testUserMessageRendersRemoteImageThumbnails() {
        let vm = AgentChatViewModel()
        vm.messages = [
            user("记录晚餐\n[附图: 1张]", remoteImageURLs: [
                "https://example.test/api/v1/upload/files/chat/dinner.jpg"
            ])
        ]

        let html = vm.renderedTranscript()[0].bodyHTML

        XCTAssertTrue(html.contains("attachment-images"))
        XCTAssertTrue(html.contains("<img"))
        XCTAssertTrue(html.contains("src=\"https://example.test/api/v1/upload/files/chat/dinner.jpg\""))
        XCTAssertTrue(html.contains("记录晚餐"))
    }

    func testAIGCResultURLIsRemovedBeforeConversationPersistence() {
        let signedURL = "/api/v1/upload/files/aigc/7/output.mp4?expires=1&signature=secret"
        let message = AgentChatMessage(
            role: .assistant,
            content: "创作已完成",
            cardType: "aigc_media_job",
            cardData: .object([
                "job_id": .string("aigc_1"),
                "status": .string("succeeded"),
                "result": .object([
                    "media_type": .string("video/mp4"),
                    "url": .string(signedURL),
                ]),
            ])
        )

        let persisted = AgentChatViewModel.redactedMessagesForLocalPersistence([message])

        XCTAssertEqual(try XCTUnwrap(persisted[0].cardData?["result"]?["url"]), .null)
        XCTAssertFalse(String(describing: persisted).contains("signature=secret"))
    }

    func testDietDraftPhotoURLIsRemovedBeforeConversationPersistence() {
        let signedURL = "/api/v1/upload/files/diet/7/lunch.jpg?expires=1&signature=secret"
        let message = AgentChatMessage(
            role: .assistant,
            content: "请确认这顿午餐",
            cardType: "diet_draft",
            cardData: .object([
                "photo_asset_id": .string("photo-1"),
                "photo_url": .string(signedURL),
                "food_items": .string("鸡胸肉和杂粮饭"),
            ])
        )

        let persisted = AgentChatViewModel.redactedMessagesForLocalPersistence([message])

        XCTAssertEqual(try XCTUnwrap(persisted[0].cardData?["photo_url"]), .null)
        XCTAssertEqual(persisted[0].cardData?["photo_asset_id"], .string("photo-1"))
        XCTAssertFalse(String(describing: persisted).contains("signature=secret"))
    }
}
