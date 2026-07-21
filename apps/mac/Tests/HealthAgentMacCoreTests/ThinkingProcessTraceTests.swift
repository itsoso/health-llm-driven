import Foundation
import XCTest
@testable import HealthAgentMacCore

/// 思考过程(reviewable thinking-process trace)回归。守三件事:
///  1. 后端 `done.thinking_steps` / `message.meta.thinking_steps` 被解析进模型;
///  2. `thinkingTraceHTML` 的 live(展开+running)与 finished(折叠+全 done)两态,
///     且**永不**出现 brain/emoji glyph(founder 硬约束);
///  3. `renderedTranscript` 在流式态渲染 live trace、完成态渲染折叠 trace,
///     且 live 与持久化列表读起来一致(live step mapper 镜像后端 label)。
final class ThinkingProcessTraceTests: XCTestCase {

    // MARK: - SSE done.thinking_steps

    func testParserExtractsThinkingStepsFromDone() throws {
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3,"thinking_steps":["正在理解你的问题","读取健康数据","整理回复中"]}}

        """
        let events = try AgentStreamParser.parse(payload)
        guard case .done(_, _, _, _, _, _, _, _, _, _, _, _, _, _, _, let steps, _) = events.first else {
            return XCTFail("expected done event")
        }
        XCTAssertEqual(steps, ["正在理解你的问题", "读取健康数据", "整理回复中"])
    }

    func testParserThinkingStepsAbsentDefaultsEmpty() throws {
        let payload = """
        data: {"event":"done","data":{"conversation_id":5,"message_id":3}}

        """
        let events = try AgentStreamParser.parse(payload)
        guard case .done(_, _, _, _, _, _, _, _, _, _, _, _, _, _, _, let steps, _) = events.first else {
            return XCTFail("expected done event")
        }
        XCTAssertEqual(steps, [], "老后端缺 thinking_steps → 空数组,不是 crash")
    }

    // MARK: - thinkingTraceHTML rendering + icon constraint

    func testTraceEmptyStepsRendersNothing() {
        XCTAssertEqual(ChatTranscriptHTML.thinkingTraceHTML(steps: [], language: "zh", live: false), "")
        XCTAssertEqual(ChatTranscriptHTML.thinkingTraceHTML(steps: ["   "], language: "zh", live: true), "")
    }

    func testFinishedTraceIsCollapsedDisclosureWithHeader() {
        let html = ChatTranscriptHTML.thinkingTraceHTML(
            steps: ["正在理解你的问题", "整理回复中"], language: "zh", live: false
        )
        XCTAssertTrue(html.contains("<details class=\"thinking-trace\""), "finished 态应是 <details>")
        XCTAssertFalse(html.contains(" open>"), "finished 态默认折叠(无 open)")
        XCTAssertTrue(html.contains("思考过程"), "header 用本地化 key 思考过程")
        XCTAssertTrue(html.contains("正在理解你的问题"))
        XCTAssertTrue(html.contains("整理回复中"))
        // 全部 done glyph,无 running spinner。
        XCTAssertTrue(html.contains("tp-check"))
        XCTAssertFalse(html.contains("tp-spinner"), "finished 态不应有 running spinner")
    }

    func testLiveTraceIsOpenWithRunningLastStep() {
        let html = ChatTranscriptHTML.thinkingTraceHTML(
            steps: ["正在理解你的问题", "读取健康数据", "正在思考"], language: "zh", live: true
        )
        XCTAssertTrue(html.contains("thinking-trace-live"))
        XCTAssertTrue(html.contains(" open>"), "live 态默认展开,步骤可见")
        // 只有最后一步是 running;前面都是 done。
        XCTAssertEqual(occurrences(of: "tp-spinner", in: html), 1, "只有当前步是 running")
        XCTAssertEqual(occurrences(of: "tp-check", in: html), 2, "前两步已完成")
    }

    func testTraceNeverUsesBrainOrEmojiGlyph() {
        let html = ChatTranscriptHTML.thinkingTraceHTML(
            steps: ["正在理解你的问题", "整理回复中"], language: "zh", live: true
        )
        // Founder 硬约束:思考/AI 不用 brain/emoji。
        for banned in ["brain", "🧠", "🤖", "💡"] {
            XCTAssertFalse(html.contains(banned), "trace 不得含 \(banned)")
        }
    }

    func testTraceEscapesStepText() {
        let html = ChatTranscriptHTML.thinkingTraceHTML(
            steps: ["<script>alert(1)</script>"], language: "zh", live: false
        )
        XCTAssertFalse(html.contains("<script>"), "步骤文本必须转义,防 XSS")
        XCTAssertTrue(html.contains("&lt;script&gt;"))
    }

    func testEnglishHeaderPassesThrough() {
        let html = ChatTranscriptHTML.thinkingTraceHTML(steps: ["step"], language: "en", live: false)
        XCTAssertTrue(html.contains("Thinking process"))
    }

    // MARK: - Live step mapper mirrors backend labels

    func testLiveThinkingStepMirrorsBackendLabels() {
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "accepted", detail: nil, round: nil), "正在理解你的问题")
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "vision", detail: nil, round: nil), "识别图片中")
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "thinking", detail: nil, round: 1), "正在思考")
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "thinking", detail: nil, round: 2), "整理思路")
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "tool", detail: "查询健康数据", round: nil), "正在查询健康数据")
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "tool", detail: nil, round: nil), "调用工具中")
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "synthesis", detail: nil, round: nil), "整理回复中")
        XCTAssertNil(AgentChatViewModel.liveThinkingStep(stage: "unknown_stage", detail: nil, round: nil))
    }

    func testLiveThinkingStepThinkingUsesRealtimeReasoningDetail() {
        // 新后端在首 token 前把模型实时推理的清洗片段作为 thinking.detail 下发(每 ~1.5s
        // 一条)。有片段就原样作为 live step —— 镜像 tool 阶段对 detail 的处理,verbatim,
        // 不加 正在 前缀(片段本身已是完整短语)。
        XCTAssertEqual(
            AgentChatViewModel.liveThinkingStep(stage: "thinking", detail: "先看最近的睡眠与压力趋势", round: 1),
            "先看最近的睡眠与压力趋势"
        )
        // round≥2 也优先用片段(有真实推理就显示真实推理,不退回固定「整理思路」)。
        XCTAssertEqual(
            AgentChatViewModel.liveThinkingStep(stage: "thinking", detail: "再对比训练负荷", round: 2),
            "再对比训练负荷"
        )
        // 空白 / nil detail(老后端)→ 回退到 round 分级的固定标签(向后兼容,行为不变)。
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "thinking", detail: "   ", round: 1), "正在思考")
        XCTAssertEqual(AgentChatViewModel.liveThinkingStep(stage: "thinking", detail: nil, round: 2), "整理思路")
    }

    // MARK: - renderedTranscript wiring (live streaming + persisted finished)

    @MainActor
    func testStreamingBubbleRendersLiveTrace() {
        let vm = AgentChatViewModel()
        let id = UUID()
        vm.messages = [AgentChatMessage(id: id, role: .assistant, content: "")]
        vm.isStreaming = true
        vm.liveThinkingSteps = ["正在理解你的问题", "读取健康数据"]

        let rendered = vm.renderedTranscript(language: "zh")
        XCTAssertEqual(rendered.count, 1, "有 live step 时空正文气泡也要渲染(trace 接管)")
        let body = rendered[0].bodyHTML
        XCTAssertTrue(body.contains("thinking-trace-live"))
        XCTAssertTrue(body.contains("读取健康数据"))
        XCTAssertTrue(rendered[0].isStreaming)
    }

    @MainActor
    func testPreFirstStepEmptyBubbleStillSuppressed() {
        let vm = AgentChatViewModel()
        let id = UUID()
        vm.messages = [AgentChatMessage(id: id, role: .assistant, content: "")]
        vm.isStreaming = true
        vm.liveThinkingSteps = []  // 首步之前:ThinkingStatusLine 是唯一等待提示

        XCTAssertEqual(vm.renderedTranscript(language: "zh").count, 0, "无正文/卡片/步骤 → 不发气泡")
    }

    @MainActor
    func testFinishedMessageRendersCollapsedPersistedTrace() {
        let vm = AgentChatViewModel()
        let id = UUID()
        vm.messages = [
            AgentChatMessage(
                id: id, role: .assistant, content: "这是回答。",
                thinkingSteps: ["正在理解你的问题", "整理回复中"]
            )
        ]
        vm.isStreaming = false

        let rendered = vm.renderedTranscript(language: "zh")
        let body = rendered[0].bodyHTML
        XCTAssertTrue(body.contains("<details class=\"thinking-trace\""), "完成消息带折叠 trace")
        XCTAssertFalse(body.contains("thinking-trace-live"), "完成态不是 live")
        XCTAssertTrue(body.contains("思考过程"))
        XCTAssertTrue(body.contains("这是回答。"), "答案正文仍渲染在 trace 之下")
    }

    @MainActor
    func testFinishedMessageWithoutStepsHasNoTrace() {
        let vm = AgentChatViewModel()
        vm.messages = [AgentChatMessage(role: .assistant, content: "无步骤回答")]
        vm.isStreaming = false
        let body = vm.renderedTranscript(language: "zh")[0].bodyHTML
        XCTAssertFalse(body.contains("thinking-trace"), "无 thinkingSteps → 不渲染 trace(向后兼容)")
    }

    // MARK: - persisted meta decode (conversation reload)

    func testBackendMetaDecodesThinkingSteps() throws {
        let json = """
        {"id":1,"role":"assistant","content":"回答","meta":{"thinking_steps":["正在理解你的问题","整理回复中"]}}
        """
        let dto = try JSONDecoder().decode(BackendConversationMessage.self, from: Data(json.utf8))
        let message = try XCTUnwrap(AgentConversationClient.message(from: dto))
        XCTAssertEqual(message.thinkingSteps, ["正在理解你的问题", "整理回复中"])
    }

    func testBackendMetaMissingThinkingStepsDefaultsEmpty() throws {
        let json = """
        {"id":2,"role":"assistant","content":"回答","meta":{"model":"claude"}}
        """
        let dto = try JSONDecoder().decode(BackendConversationMessage.self, from: Data(json.utf8))
        let message = try XCTUnwrap(AgentConversationClient.message(from: dto))
        XCTAssertEqual(message.thinkingSteps, [], "老消息缺字段 → 空,不 crash")
    }

    // MARK: - message Codable round-trip (local cache)

    func testMessageCodableRoundTripsThinkingSteps() throws {
        let original = AgentChatMessage(
            role: .assistant, content: "x", thinkingSteps: ["a", "b"]
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AgentChatMessage.self, from: data)
        XCTAssertEqual(decoded.thinkingSteps, ["a", "b"])
    }

    // MARK: - helpers

    private func occurrences(of needle: String, in haystack: String) -> Int {
        guard !needle.isEmpty else { return 0 }
        var count = 0
        var range = haystack.startIndex..<haystack.endIndex
        while let found = haystack.range(of: needle, range: range) {
            count += 1
            range = found.upperBound..<haystack.endIndex
        }
        return count
    }
}
