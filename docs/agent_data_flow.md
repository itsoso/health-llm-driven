"""
Agent Orchestrator 数据流与 Token 成本可视化

用 Mermaid 画出当前生产系统的数据流，标出：
1. Memory Fact 流（输入 → extractor → fact）
2. Twin 流（facts + entities + KG → builder → Twin blob）
3. Orchestration 流（Twin + Specialist findings → LLM 合成 → message）
4. LLM Call 流（provider.chat 调用点 + set_caller 埋点 + 输出）

目标：识别性能瓶颈、冗余调用、Token 成本优化点。

适用：向团队/CTO/投资人/自己复盘"我们现在的 AI Agent 系统长什么样"。
"""
