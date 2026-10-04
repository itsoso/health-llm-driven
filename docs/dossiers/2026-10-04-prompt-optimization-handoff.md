# 跨机器接手：Prompt、Laya 与流式体验优化

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | 本地验证完成，分支交接；未发布 |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 范围准入

裁决：PASS。范围是用户授权的既有体验、路由和上下文传输优化及其分支交接，不新增产品入口、健康对象、用户数据权限或自动发布行为。权限、质量地板、写入回执和安全输出边界继续由原系统负责；失败候选不得进入运行路径。本文记录本地实现与证据，不代表全量 CI、生产效果或发布准入。

日期：2026-10-04。接手分支：`codex/reva-prompt-optimization`。本文件是各阶段 dossier 的最新索引；旧文档中的“未授权提交/推送”是当时状态，用户现已授权保存远端分支以便换机继续。未合并 main，未部署，不授权自动发布。

## 当前代码

分支基于已 fetch 的 `origin/main`：`f201d85b4f0d726b09ff0f8b16acf403d70f3e57`。此前隔离工作树 HEAD `a8853dea1` 与该主干只差发布文档，运行时代码相同。不要以旧本地 checkout 替代 fetch 后的比较，也不要覆盖其他工作树修改。

已保留：

- Markdown 流式渲染稳定性及其测试。
- Laya 可信档位与 partial 能力建议分离、写意图否决、质量地板；未降低置信度阈值。
- provider 按服务端任务范围选择工具说明、公共任务工具选择、最终回答材料投影、工具 JSON 保真紧凑化。
- 历史中严格相同旧长答的引用与摘要窗口缺口补回；用户原话、待办与安全信息保留。
- 完整分析报告复用的进程内回执及公共输出护栏，默认 off。
- food recognition 用量调用方作用域修复。
- 固定合成质量评测与失败留证工具。

明确否决：health_record 写入示例精简。真实 API 上虽约减少 10.77% 输入，但 qwen3.8-flash 对 0.5升，以及收窄后的350毫升/250ml再次追问已知量。所有生产接线和触发 flag 已撤回；候选仅在 `backend/eval/experimental_record_projection.py`，由 benchmark 的独立实例注入。不能因 max 样本通过就重新启用，也不能把该收益算作已交付。应用未新增开关，已有优化开关默认值未改变。

## 先读的证据

1. [最终质量与撤回](2026-10-04-prompt-quality-preserving.md)：实验失败、回退和 387 项最终关联检查、独立33项检查。
2. [架构优化](2026-10-04-scoped-prompt-architecture.md)：读工具、历史与报告复用的边界；固定合成 API 的局部收益，不代表全量平均。
3. [Laya](2026-10-04-laya-routing-coverage.md)：本机真实适配器、部分建议和质量地板；无整体聊天提速结论。
4. [输入审计](../reviews/2026-10-04-prompt-token-audit.md) 与 [流式体验](../reviews/2026-10-04-web-streaming-ux-performance.md)。
5. [可携带 harness 轨迹](../reviews/2026-10-04-prompt-optimization-harness-traces.json)。原 `docs/_generated/harness-runs` 为本机忽略文件，已导出轨迹；旧文档的 `/tmp` 日志和本机服务地址不保证换机可用，仓库中的 JSON 证据可用。

证据全部是聚合指标或固定合成样本，不包含真实健康原文、运行凭证或 .env。另一台机器自行使用其已有私有环境；不要复制密钥进 Git。

## 下一步

先按 AGENTS.md 跑 router，根据最新远端比较本分支；继续在此分支优化。优先处理仍反复传输的大工具 schema、system 固定材料和多次模型调用，但先建立同批基线，分清 API 输入、缓存、输出、调用次数与耗时。不能用字符数代替 token，不能只跑强模型或只看静态测试。

`backend/eval/prompt_projection_quality.py` 冻结合成输入、日期及确定性契约；`scripts/benchmark_record_prompt_projection.py` 默认 dry-run，显式 `--include-live-llm` 才会调用 API。当前 candidate 是已否决实验，真实运行退出非零是可能且应保留的结果，不要为了绿色而放宽 oracle。完整临床/语义非劣、真实持久化及生产效果仍是 Unknown。

已知独立问题：原版“昨晚睡眠”在一条 API 提案中返回 days=1，不符合固定日期契约；两侧请求完全相同，不归因本次精简。若修复，应从服务端窗口解析与实际执行证据入手，不能只放宽评测。

## 可复现入口

使用仓库要求的 Python 3.12、后端开发依赖和 Node 依赖（含仓库 Pi runtime）；遵循现有安装入口。以下为离线测试环境，不使用生产数据库：

```bash
export SECRET_KEY=local-synthetic-test-key-only-000000
export DATABASE_URL=sqlite:///:memory:
export REDIS_URL=redis://127.0.0.1:1/15
python -m pytest backend/tests/test_agent_record_tool_prompt_projection.py backend/tests/test_agent_record_prompt_provider.py backend/tests/test_agent_tool_prompt_projection.py backend/tests/test_record_prompt_benchmark.py backend/tests/test_prompt_projection_quality.py backend/tests/test_scoped_prompt_provider.py backend/tests/test_agent_prompt_budget_execution.py backend/tests/test_agent_executor_fast_routing.py -q --no-cov
python scripts/benchmark_record_prompt_projection.py --output /tmp/record-prompt-dry-run.json
./scripts/system-map-check.sh
```

以上局部测试不是全量 CI 或 PostgreSQL 语义证明。提交已验证分支不等于发布验收；若继续产生改动，补相称测试及独立安全检查，更新 dossier。合并、部署与启用生产开关须单独授权及对应 Gate。

换机提交前补验：前端流式测试 5 passed、1 skipped；秘密扫描通过；仅格式收尾移除实验模块末尾空行，应用代码未改。
