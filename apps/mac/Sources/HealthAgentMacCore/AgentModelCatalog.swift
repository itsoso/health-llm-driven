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
        // 阿里 TokenPlan 套餐对话模型 (2026-06-22) — id 必须与后端 model_registry 对齐。
        // 图像生成模型 (qwen-image-2.0 / wan2.7-image) 非对话, 不进 picker。
        AgentModelOption(id: "qwen3.7-plus", title: "Qwen3.7 Plus", provider: "阿里 TokenPlan", tier: "Vision"),
        AgentModelOption(id: "qwen3.7-max", title: "Qwen3.7 Max", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "qwen3.6-plus", title: "Qwen3.6 Plus", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "qwen3.6-flash", title: "Qwen3.6 Flash", provider: "阿里 TokenPlan", tier: "Flash"),
        AgentModelOption(id: "deepseek-v4-pro", title: "DeepSeek V4 Pro", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "deepseek-v4-flash", title: "DeepSeek V4 Flash", provider: "阿里 TokenPlan", tier: "Flash"),
        AgentModelOption(id: "deepseek-v3.2", title: "DeepSeek V3.2", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "kimi-k2.7-code", title: "Kimi K2.7 Code", provider: "阿里 TokenPlan", tier: "Vision"),
        AgentModelOption(id: "kimi-k2.6", title: "Kimi K2.6", provider: "阿里 TokenPlan", tier: "Vision"),
        AgentModelOption(id: "kimi-k2.5", title: "Kimi K2.5", provider: "阿里 TokenPlan", tier: "Vision"),
        AgentModelOption(id: "glm-5.2", title: "GLM-5.2", provider: "阿里 TokenPlan", tier: "Balanced"),
        AgentModelOption(id: "glm-5.1", title: "GLM-5.1", provider: "阿里 TokenPlan", tier: "Balanced"),
        AgentModelOption(id: "glm-5", title: "GLM-5", provider: "阿里 TokenPlan", tier: "Balanced"),
        AgentModelOption(id: "minimax-m2.5", title: "MiniMax M2.5", provider: "阿里 TokenPlan", tier: "Reasoning"),
    ]
}
