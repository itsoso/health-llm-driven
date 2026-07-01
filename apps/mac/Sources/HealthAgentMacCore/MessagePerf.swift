import Foundation

/// Per-answer stage-timing perf emitted by the backend for every assistant reply.
///
/// Two delivery paths, one shape:
///  - Live stream: the `done` SSE event carries `data.perf` (see `AgentStreamParser`).
///  - Reload: the persisted `message.meta.perf` from `/agent/conversations/{id}`.
///
/// **Back-compat is load-bearing**: every field is optional and decoded with
/// `decodeIfPresent`. Old messages (persisted before the perf contract shipped)
/// simply carry no `perf`, and the footer renders unchanged. A `done` event on an
/// old backend has no `perf` object → `MessagePerf?` stays nil.
public struct MessagePerf: Codable, Equatable, Sendable {
    /// The seven prompt-assembly stages (all ms). Any may be absent.
    public struct PreLLMStages: Codable, Equatable, Sendable {
        public let convMs: Int?
        public let openerMs: Int?
        public let systemPromptMs: Int?
        public let kbMs: Int?
        public let inspectMs: Int?
        public let historyMs: Int?
        public let visionMs: Int?

        public init(
            convMs: Int? = nil,
            openerMs: Int? = nil,
            systemPromptMs: Int? = nil,
            kbMs: Int? = nil,
            inspectMs: Int? = nil,
            historyMs: Int? = nil,
            visionMs: Int? = nil
        ) {
            self.convMs = convMs
            self.openerMs = openerMs
            self.systemPromptMs = systemPromptMs
            self.kbMs = kbMs
            self.inspectMs = inspectMs
            self.historyMs = historyMs
            self.visionMs = visionMs
        }

        private enum CodingKeys: String, CodingKey {
            case convMs = "conv_ms"
            case openerMs = "opener_ms"
            case systemPromptMs = "system_prompt_ms"
            case kbMs = "kb_ms"
            case inspectMs = "inspect_ms"
            case historyMs = "history_ms"
            case visionMs = "vision_ms"
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            convMs = try c.decodeIfPresent(Int.self, forKey: .convMs)
            openerMs = try c.decodeIfPresent(Int.self, forKey: .openerMs)
            systemPromptMs = try c.decodeIfPresent(Int.self, forKey: .systemPromptMs)
            kbMs = try c.decodeIfPresent(Int.self, forKey: .kbMs)
            inspectMs = try c.decodeIfPresent(Int.self, forKey: .inspectMs)
            historyMs = try c.decodeIfPresent(Int.self, forKey: .historyMs)
            visionMs = try c.decodeIfPresent(Int.self, forKey: .visionMs)
        }

        /// The seven stages as ordered (labelZH, ms) pairs, skipping absent/zero
        /// entries. Order mirrors the pipeline: conv → opener → system prompt →
        /// KB → inspect → history → vision.
        public var orderedNonZero: [(label: String, ms: Int)] {
            let entries: [(String, Int?)] = [
                ("对话记忆", convMs),
                ("开场判定", openerMs),
                ("系统提示", systemPromptMs),
                ("知识检索", kbMs),
                ("数据审视", inspectMs),
                ("历史回填", historyMs),
                ("图像理解", visionMs)
            ]
            return entries.compactMap { label, value in
                guard let value, value > 0 else { return nil }
                return (label, value)
            }
        }
    }

    /// One LLM generation round (a generation phase optionally followed by tool
    /// execution). `tools` is the list of tool names invoked in that round.
    public struct Round: Codable, Equatable, Sendable {
        public let llmGenMs: Int?
        public let toolExecMs: Int?
        public let tools: [String]

        public init(llmGenMs: Int? = nil, toolExecMs: Int? = nil, tools: [String] = []) {
            self.llmGenMs = llmGenMs
            self.toolExecMs = toolExecMs
            self.tools = tools
        }

        private enum CodingKeys: String, CodingKey {
            case llmGenMs = "llm_gen_ms"
            case toolExecMs = "tool_exec_ms"
            case tools
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            llmGenMs = try c.decodeIfPresent(Int.self, forKey: .llmGenMs)
            toolExecMs = try c.decodeIfPresent(Int.self, forKey: .toolExecMs)
            tools = try c.decodeIfPresent([String].self, forKey: .tools) ?? []
        }
    }

    public let totalMs: Int?
    public let preLLMMs: Int?
    public let preLLMStages: PreLLMStages?
    public let llmTTFTMs: Int?
    public let llmFullMs: Int?
    public let rounds: [Round]
    public let orchestratorToolMs: Int?

    public init(
        totalMs: Int? = nil,
        preLLMMs: Int? = nil,
        preLLMStages: PreLLMStages? = nil,
        llmTTFTMs: Int? = nil,
        llmFullMs: Int? = nil,
        rounds: [Round] = [],
        orchestratorToolMs: Int? = nil
    ) {
        self.totalMs = totalMs
        self.preLLMMs = preLLMMs
        self.preLLMStages = preLLMStages
        self.llmTTFTMs = llmTTFTMs
        self.llmFullMs = llmFullMs
        self.rounds = rounds
        self.orchestratorToolMs = orchestratorToolMs
    }

    private enum CodingKeys: String, CodingKey {
        case totalMs = "total_ms"
        case preLLMMs = "pre_llm_ms"
        case preLLMStages = "pre_llm_stages"
        case llmTTFTMs = "llm_ttft_ms"
        case llmFullMs = "llm_full_ms"
        case rounds
        case orchestratorToolMs = "orchestrator_tool_ms"
        // orchestrator_perf is intentionally ignored (opaque nested object,
        // "usually null"); decoding it would add surface with no render use.
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        totalMs = try c.decodeIfPresent(Int.self, forKey: .totalMs)
        preLLMMs = try c.decodeIfPresent(Int.self, forKey: .preLLMMs)
        preLLMStages = try c.decodeIfPresent(PreLLMStages.self, forKey: .preLLMStages)
        llmTTFTMs = try c.decodeIfPresent(Int.self, forKey: .llmTTFTMs)
        llmFullMs = try c.decodeIfPresent(Int.self, forKey: .llmFullMs)
        rounds = try c.decodeIfPresent([Round].self, forKey: .rounds) ?? []
        orchestratorToolMs = try c.decodeIfPresent(Int.self, forKey: .orchestratorToolMs)
    }

    // MARK: - Waterfall band computation

    /// Sum of `tool_exec_ms` across all rounds (the blue "tool exec" band).
    public var toolExecMsTotal: Int {
        rounds.reduce(0) { $0 + ($1.toolExecMs ?? 0) }
    }

    /// A single colored band in the waterfall timeline. `ms` drives the segment's
    /// proportional width; `kind` selects the color class.
    public struct Band: Equatable, Sendable {
        public enum Kind: String, Sendable {
            case preLLM = "prellm"       // gray — prompt assembly
            case ttftWait = "ttft"       // amber — first-token latency
            case generation = "gen"      // green — token generation
            case toolExec = "tool"       // blue — tool execution
            case orchestrator = "orch"   // red — orchestrator subtree ("silent 30-60s")
        }

        public let kind: Kind
        public let ms: Int
        public let label: String

        public init(kind: Kind, ms: Int, label: String) {
            self.kind = kind
            self.ms = ms
            self.label = label
        }
    }

    /// Whether there's enough signal to draw a waterfall at all. Requires a
    /// positive `total_ms` — everything else derives from it.
    public var isRenderable: Bool {
        (totalMs ?? 0) > 0
    }

    /// Splits `total_ms` into 3-5 proportional bands along the timeline:
    ///  - pre-LLM (gray)      = `pre_llm_ms`
    ///  - TTFT wait (amber)   = `max(0, (llm_ttft_ms ?? pre_llm_ms) - pre_llm_ms)`
    ///  - tool exec (blue)    = `sum(rounds[].tool_exec_ms)` (only if > 0)
    ///  - orchestrator (red)  = `orchestrator_tool_ms` (only if present & > 0) — the "silent 30-60s"
    ///  - generation (green)  = the remainder up to `total_ms`, i.e.
    ///    `total_ms - firstToken - toolExec - orchestrator`, floored at 0.
    ///
    /// Zero-width bands are dropped so the bar only shows real time.
    public func bands() -> [Band] {
        guard let total = totalMs, total > 0 else { return [] }
        let pre = max(0, preLLMMs ?? 0)
        let firstToken = max(pre, llmTTFTMs ?? pre)   // absolute ms at first token
        let ttftWait = max(0, firstToken - pre)
        let tool = max(0, toolExecMsTotal)
        let orch = max(0, orchestratorToolMs ?? 0)
        // Generation is whatever's left after assembly, first-token wait, and the
        // (blue/red) work bands. Never negative — clamp so widths stay sane even
        // when backend rounding makes the parts overshoot `total_ms`.
        let generation = max(0, total - firstToken - tool - orch)

        var result: [Band] = []
        if pre > 0 { result.append(Band(kind: .preLLM, ms: pre, label: "组装")) }
        if ttftWait > 0 { result.append(Band(kind: .ttftWait, ms: ttftWait, label: "首字节")) }
        if generation > 0 { result.append(Band(kind: .generation, ms: generation, label: "生成")) }
        if tool > 0 { result.append(Band(kind: .toolExec, ms: tool, label: "工具")) }
        if orch > 0 { result.append(Band(kind: .orchestrator, ms: orch, label: "分析")) }
        return result
    }
}
