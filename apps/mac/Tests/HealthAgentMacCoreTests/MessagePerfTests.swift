import Foundation
import XCTest
@testable import HealthAgentMacCore

final class MessagePerfTests: XCTestCase {

    // MARK: - done.data.perf decoding (snake_case → struct)

    func testDecodesFullPerfObjectFromDoneEvent() throws {
        let json = """
        {
          "total_ms": 4200, "pre_llm_ms": 2600,
          "pre_llm_stages": {"conv_ms":40,"opener_ms":20,"system_prompt_ms":900,"kb_ms":1400,"inspect_ms":120,"history_ms":80,"vision_ms":40},
          "llm_ttft_ms": 3300, "llm_full_ms": 1500,
          "rounds": [{"llm_gen_ms":1500,"tool_exec_ms":0,"tools":[]}],
          "orchestrator_tool_ms": null, "orchestrator_perf": null
        }
        """
        let perf = try JSONDecoder().decode(MessagePerf.self, from: Data(json.utf8))
        XCTAssertEqual(perf.totalMs, 4200)
        XCTAssertEqual(perf.preLLMMs, 2600)
        XCTAssertEqual(perf.llmTTFTMs, 3300)
        XCTAssertEqual(perf.llmFullMs, 1500)
        XCTAssertEqual(perf.preLLMStages?.systemPromptMs, 900)
        XCTAssertEqual(perf.preLLMStages?.kbMs, 1400)
        XCTAssertEqual(perf.rounds.count, 1)
        XCTAssertEqual(perf.rounds.first?.llmGenMs, 1500)
        XCTAssertNil(perf.orchestratorToolMs)
        XCTAssertTrue(perf.isRenderable)
    }

    func testDecodesOrchestratorToolMs() throws {
        let json = """
        {"total_ms": 45000, "pre_llm_ms": 2000, "llm_ttft_ms": 6000, "llm_full_ms": 1000,
         "rounds": [{"llm_gen_ms":1000,"tool_exec_ms":0,"tools":[]}], "orchestrator_tool_ms": 38000}
        """
        let perf = try JSONDecoder().decode(MessagePerf.self, from: Data(json.utf8))
        XCTAssertEqual(perf.orchestratorToolMs, 38000)
    }

    // MARK: - Back-compat: all fields optional

    func testDecodesEmptyPerfObject() throws {
        let perf = try JSONDecoder().decode(MessagePerf.self, from: Data("{}".utf8))
        XCTAssertNil(perf.totalMs)
        XCTAssertNil(perf.preLLMStages)
        XCTAssertTrue(perf.rounds.isEmpty)
        XCTAssertFalse(perf.isRenderable)          // no total_ms → not drawable
        XCTAssertTrue(perf.bands().isEmpty)
    }

    func testDecodesPartialStagesTolerantly() throws {
        let json = "{\"pre_llm_stages\": {\"kb_ms\": 500}}"
        let perf = try JSONDecoder().decode(MessagePerf.self, from: Data(json.utf8))
        XCTAssertEqual(perf.preLLMStages?.kbMs, 500)
        XCTAssertNil(perf.preLLMStages?.systemPromptMs)
    }

    func testAgentChatMessageRoundTripsPerf() throws {
        let perf = MessagePerf(
            totalMs: 4200, preLLMMs: 2600,
            preLLMStages: .init(systemPromptMs: 900, kbMs: 1400),
            llmTTFTMs: 3300, llmFullMs: 1500,
            rounds: [.init(llmGenMs: 1500, toolExecMs: 0, tools: [])]
        )
        let message = AgentChatMessage(role: .assistant, content: "hi", perf: perf)
        let data = try JSONEncoder().encode(message)
        let restored = try JSONDecoder().decode(AgentChatMessage.self, from: data)
        XCTAssertEqual(restored.perf?.totalMs, 4200)
        XCTAssertEqual(restored.perf?.preLLMStages?.kbMs, 1400)
        XCTAssertTrue(restored.hasMeta)            // perf alone makes the footer render
    }

    func testOldMessageWithoutPerfStillDecodes() throws {
        // A snapshot persisted before the perf contract shipped: no `perf` key.
        let json = "{\"id\":\"\(UUID().uuidString)\",\"role\":\"assistant\",\"content\":\"hi\"}"
        let message = try JSONDecoder().decode(AgentChatMessage.self, from: Data(json.utf8))
        XCTAssertNil(message.perf)
        XCTAssertFalse(message.hasMeta)            // no meta at all → footer hidden
    }

    // MARK: - Band split (the waterfall math)

    func testBandsSplitProportionalToTimeline() {
        // total 4200, pre 2600, ttft 3300 → firstToken 3300, wait 700, gen 900.
        let perf = MessagePerf(
            totalMs: 4200, preLLMMs: 2600,
            llmTTFTMs: 3300, llmFullMs: 1500,
            rounds: [.init(llmGenMs: 1500, toolExecMs: 0, tools: [])]
        )
        let bands = perf.bands()
        XCTAssertEqual(bands.map(\.kind), [.preLLM, .ttftWait, .generation])
        XCTAssertEqual(bands.first { $0.kind == .preLLM }?.ms, 2600)
        XCTAssertEqual(bands.first { $0.kind == .ttftWait }?.ms, 700)
        XCTAssertEqual(bands.first { $0.kind == .generation }?.ms, 900)
        // Bands sum to total_ms.
        XCTAssertEqual(bands.reduce(0) { $0 + $1.ms }, 4200)
    }

    func testBandsIncludeToolAndOrchestrator() {
        // total 45000, pre 2000, ttft 6000 → wait 4000, tool 3000, orch 38000,
        // gen = 45000 - 6000 - 3000 - 38000 = -2000 → clamped to 0 (dropped).
        let perf = MessagePerf(
            totalMs: 45000, preLLMMs: 2000,
            llmTTFTMs: 6000, llmFullMs: 1000,
            rounds: [.init(llmGenMs: 1000, toolExecMs: 3000, tools: ["twin_lookup"])],
            orchestratorToolMs: 38000
        )
        let bands = perf.bands()
        XCTAssertTrue(bands.contains { $0.kind == .toolExec && $0.ms == 3000 })
        XCTAssertTrue(bands.contains { $0.kind == .orchestrator && $0.ms == 38000 })
        XCTAssertFalse(bands.contains { $0.kind == .generation })   // clamped away
    }

    func testTTFTMissingTreatedAsPreLLM() {
        // No llm_ttft_ms → firstToken = pre_llm_ms, so no amber wait band.
        let perf = MessagePerf(totalMs: 3000, preLLMMs: 1000, rounds: [])
        let bands = perf.bands()
        XCTAssertFalse(bands.contains { $0.kind == .ttftWait })
        XCTAssertEqual(bands.first { $0.kind == .generation }?.ms, 2000)
    }

    // MARK: - Waterfall HTML generation

    func testWaterfallHTMLRendersSegmentsAndTotal() {
        let perf = MessagePerf(
            totalMs: 4200, preLLMMs: 2600,
            preLLMStages: .init(systemPromptMs: 900, kbMs: 1400),
            llmTTFTMs: 3300, llmFullMs: 1500,
            rounds: [.init(llmGenMs: 1500, toolExecMs: 0, tools: [])]
        )
        let html = ChatTranscriptHTML.latencyWaterfallHTML(perf)
        XCTAssertTrue(html.contains("latency-waterfall"))
        XCTAssertTrue(html.contains("wf-bar"))
        XCTAssertTrue(html.contains("wf-prellm"))
        XCTAssertTrue(html.contains("wf-ttft"))
        XCTAssertTrue(html.contains("wf-gen"))
        XCTAssertTrue(html.contains("4.2s"))       // total label
        XCTAssertTrue(html.contains("<details"))   // tap-to-expand
        XCTAssertTrue(html.contains("知识检索"))    // kb stage label in detail
        XCTAssertTrue(html.contains("系统提示"))    // system_prompt stage label
    }

    func testWaterfallHTMLShowsRedOrchestratorBand() {
        let perf = MessagePerf(
            totalMs: 45000, preLLMMs: 2000,
            llmTTFTMs: 6000, llmFullMs: 1000,
            rounds: [.init(llmGenMs: 1000, toolExecMs: 3000, tools: ["twin_lookup"])],
            orchestratorToolMs: 38000
        )
        let html = ChatTranscriptHTML.latencyWaterfallHTML(perf)
        XCTAssertTrue(html.contains("wf-orch"))    // the red "silent 30-60s" band
        XCTAssertTrue(html.contains("wf-tool"))
        XCTAssertTrue(html.contains("twin_lookup")) // tool name in round detail
        XCTAssertTrue(html.contains("45.0s"))
    }

    func testWaterfallHTMLEmptyWhenNoTotal() {
        let perf = MessagePerf(preLLMMs: 2600)      // no total_ms
        XCTAssertEqual(ChatTranscriptHTML.latencyWaterfallHTML(perf), "")
    }

    func testMetaFooterOmitsWaterfallWhenPerfNil() {
        // Full back-compat: without perf, footer output is byte-identical to before.
        let withoutPerf = ChatTranscriptHTML.metaFooterHTML(
            model: "gpt-5.5", elapsedMs: 4200, llmRounds: 1, sourcesUsed: [], toolsUsed: []
        )
        XCTAssertFalse(withoutPerf.contains("latency-waterfall"))
    }

    func testMetaFooterIncludesWaterfallWhenPerfPresent() {
        let perf = MessagePerf(totalMs: 4200, preLLMMs: 2600, llmTTFTMs: 3300, llmFullMs: 1500)
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "gpt-5.5", elapsedMs: 4200, llmRounds: 1, sourcesUsed: [], toolsUsed: [], perf: perf
        )
        XCTAssertTrue(html.contains("latency-waterfall"))
        XCTAssertTrue(html.contains("meta-line"))   // existing footer content still present
    }

    // MARK: - Stream parser integration

    func testParserDecodesPerfPreLLMEvent() throws {
        let payload = "data: {\"event\":\"perf_pre_llm\",\"data\":{\"pre_llm_ms\":2600,\"stages\":{\"kb_ms\":1400,\"system_prompt_ms\":900}}}\n\n"
        let events = try AgentStreamParser.parse(payload)
        guard case .perfPreLLM(let preLLMMs, let stages) = events.first else {
            return XCTFail("expected perfPreLLM event, got \(String(describing: events.first))")
        }
        XCTAssertEqual(preLLMMs, 2600)
        XCTAssertEqual(stages?.kbMs, 1400)
        XCTAssertEqual(stages?.systemPromptMs, 900)
    }

    func testParserDecodesPerfOnDoneEvent() throws {
        let payload = "data: {\"event\":\"done\",\"data\":{\"conversation_id\":7,\"elapsed_ms\":4200,\"llm_rounds\":1,\"perf\":{\"total_ms\":4200,\"pre_llm_ms\":2600,\"llm_ttft_ms\":3300,\"llm_full_ms\":1500,\"rounds\":[{\"llm_gen_ms\":1500,\"tool_exec_ms\":0,\"tools\":[]}]}}}\n\n"
        let events = try AgentStreamParser.parse(payload)
        guard case .done(_, _, _, _, _, _, _, _, _, _, _, _, _, let perf, _, _, _) = events.first else {
            return XCTFail("expected done event, got \(String(describing: events.first))")
        }
        XCTAssertEqual(perf?.totalMs, 4200)
        XCTAssertEqual(perf?.llmTTFTMs, 3300)
    }

    func testParserDoneWithoutPerfKeepsNil() throws {
        // Old backend: done event has no `perf` object.
        let payload = "data: {\"event\":\"done\",\"data\":{\"conversation_id\":7,\"elapsed_ms\":4200}}\n\n"
        let events = try AgentStreamParser.parse(payload)
        guard case .done(_, _, _, _, _, _, _, _, _, _, _, _, _, let perf, _, _, _) = events.first else {
            return XCTFail("expected done event")
        }
        XCTAssertNil(perf)
    }
}
