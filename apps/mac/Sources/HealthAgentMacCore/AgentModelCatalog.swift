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
        AgentModelOption(id: "claude-opus-4.7", title: "Claude Opus 4.7", provider: "LangBridge", tier: "Top"),
        AgentModelOption(id: "gemini-3.1-pro", title: "Gemini 3.1 Pro", provider: "LangBridge", tier: "Top"),
        AgentModelOption(id: "gpt-5.5", title: "GPT-5.5", provider: "LangBridge", tier: "Top"),
        // 阿里 TokenPlan 套餐对话模型 — id 必须与后端 model_registry 对齐。
        // 图像生成模型 (qwen-image-2.0 / wan2.7-image) 非对话, 不进 picker。
        AgentModelOption(id: "qwen3.8-max-preview", title: "Qwen3.8 Max Preview", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "qwen3.7-plus", title: "Qwen3.7 Plus", provider: "阿里 TokenPlan", tier: "Vision"),
        AgentModelOption(id: "qwen3.7-max", title: "Qwen3.7 Max", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "deepseek-v4-pro", title: "DeepSeek V4 Pro", provider: "阿里 TokenPlan", tier: "Reasoning"),
        AgentModelOption(id: "deepseek-v4-flash", title: "DeepSeek V4 Flash", provider: "阿里 TokenPlan", tier: "Flash"),
        AgentModelOption(id: "kimi-k2.7-code", title: "Kimi K2.7 Code", provider: "阿里 TokenPlan", tier: "Vision"),
        AgentModelOption(id: "glm-5.2", title: "GLM-5.2", provider: "阿里 TokenPlan", tier: "Balanced"),
        AgentModelOption(id: "minimax-m2.5", title: "MiniMax M2.5", provider: "阿里 TokenPlan", tier: "Reasoning"),
    ]

    public static func canonicalID(for id: String) -> String {
        switch id {
        case "commercial/Claude-Opus-4.7":
            return "claude-opus-4.7"
        case "commercial/Gemini-3.1-Pro-Preview":
            return "gemini-3.1-pro"
        case "commercial/GPT-5.5":
            return "gpt-5.5"
        case "tokenplan/Qwen3.8-Max-Preview", "qwen-3.8-max-preview", "qwen3.8", "qwen-3.8":
            return "qwen3.8-max-preview"
        default:
            return id
        }
    }
}
