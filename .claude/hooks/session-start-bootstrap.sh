#!/usr/bin/env bash
# SessionStart hook —— 把最强治理不变量从 CLAUDE.md 散文(advisory,新 subagent 可能没读)
# 变成每个 session/subagent 开工就被注入的 context。stdout 即注入内容。
# (行业对标缺口 #1:最强不变量只在散文层;hook 是把它往上抬一档的最便宜方式。)
cat <<'EOF'
[harness bootstrap · 治理不变量 · 违反=bug,不是风格问题]
- 先读 docs/system-map/INDEX.md 秒懂现状。架构计数只准引用 docs/_generated/system-map.json;
  绝不手打 live 数字进叙事(改了代码跑 scripts/dump_system_map.py 重生成)。
- R4:LLM 永不发出不可逆动作(写库/下单/预约/部署)—— 只 draft/解释,确定性代码或人执行。
- fail-closed + fail-loud:吞异常 = 静默绿 = bug;安全/风控评估每个吞点暴露 failed_count + 注入兜底。
- 加层不减层:去重/合并绝不丢告警;覆盖只 TIGHTEN。
- 测试绝不 `| tail`(吞退出码);改共享渲染/序列化必全量跑 + 直读 passed/failed。
- 评 code-derived 结论对 origin/main 核,别信工作树(可落后几十 commit)。
- 硬规范权威 = AGENTS.md;走完整研发流程用 product-pipeline skill;开工前看 docs/system-map/INDEX.md。
EOF
