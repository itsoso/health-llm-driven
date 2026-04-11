"""
Agent 舰队 —— 所有专家 agent 的父目录。

每个 agent 应当：
- 以 Digital Health Twin 为唯一输入
- 返回结构化输出（Alert / Recommendation / Plan）
- 永不持久化副作用（只读 + 分析）
- 失败降级，不抛异常到 orchestrator
"""
