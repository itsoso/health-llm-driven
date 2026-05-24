import Foundation

public struct AgentModelOption: Equatable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let provider: String
    public let tier: String

    public init(id: String, title: String, provider: String, tier: String) {
        self.id = id
        self.title = title
        self.provider = provider
        self.tier = tier
    }
}

public enum AgentModelCatalog {
    public static let defaultOptions: [AgentModelOption] = [
        AgentModelOption(id: "commercial/Claude-Opus-4.7", title: "Claude Opus 4.7", provider: "LangBridge", tier: "Top"),
        AgentModelOption(id: "commercial/Gemini-3.1-Pro-Preview", title: "Gemini 3.1 Pro", provider: "LangBridge", tier: "Top"),
        AgentModelOption(id: "commercial/GPT-5.5", title: "GPT-5.5", provider: "LangBridge", tier: "Top"),
        AgentModelOption(id: "commercial/GPT-5.4", title: "GPT-5.4", provider: "LangBridge", tier: "Top"),
        AgentModelOption(id: "commercial/GPT-5.1", title: "GPT-5.1", provider: "LangBridge", tier: "Mid"),
        AgentModelOption(id: "commercial/DeepSeek-R1", title: "DeepSeek R1", provider: "LangBridge", tier: "Mid"),
        AgentModelOption(id: "commercial/DeepSeek-V3.2", title: "DeepSeek V3.2", provider: "LangBridge", tier: "Mid"),
        AgentModelOption(id: "qwen3.6-plus", title: "Qwen3.6 Plus", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "minimax-m2.5", title: "MiniMax M2.5", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "glm-5", title: "GLM-5", provider: "阿里 TokenPlan", tier: "Balanced"),
        AgentModelOption(id: "deepseek-v3.2", title: "DeepSeek V3.2", provider: "阿里 TokenPlan", tier: "Reasoning"),
    ]
}
