---
doc: performance-governance
last-reviewed: 2026-10-27
---

# 性能治理

## 验收口径

性能改动先建立同一批真实请求的基线，再比较效果、端到端长尾时延和成本。至少记录样本、环境、分段耗时、P50/P95/P99、质量底线和回退条件；平均值不能代替长尾。

## 默认目标

| 操作 | 目标 | 最大值 |
|---|---:|---:|
| 简单查询 | 100ms | 500ms |
| 复杂查询 | 500ms | 2s |
| 列表接口 | 300ms | 1s |
| AI 分析 | 5s | 30s |
| 文件上传 | 2s | 10s |

目标是产品预算，不等于任何单点调用的无条件承诺；超限要用 trace/分段证据定位。

## 实现约束

- 批量 I/O 使用有上限的并发、超时和取消；避免无界 `gather`。
- 常用查询检查索引与执行计划，避免 N+1；索引收益必须结合写放大和选择性评估。
- 缓存明确 key、TTL、容量、一致性、失效和故障策略；缓存错误不得伪装成权威数据。
- 先优化工具循环、扇出、重复 I/O、SSE 缓冲和 UI 阻塞，再考虑扩大资源。

## 验证

保留改动前后可复现数据。若质量下降、成本越界、长尾恶化或错误率上升，按预设阈值回退。


## CI / 发布耗时：跨 Agent 复用流程

仅在优化 CI / 发布耗时或核验其效果时加载本节。沿用 Router 选定的 controller、已有 Dossier 和 Gate，不新建一套性能 Harness。最近一轮完整交接见 [发布耗时优化 Dossier](../dossiers/2026-10-27-release-latency-optimization.md)，其中数字是历史样本，不是当前基线或固定 SLA。

1. **接手与基线。** 检查工作树、当前 main 精确 SHA、开放 PR 与发布归属；读取已有 Dossier 的断点和机器证据。使用 GitHub 上绑定 SHA / run_id / attempt 的完整 run、jobs、steps 和 JUnit 清单建立新基线，记录失败与重试；不要把文档专用 CI 与完整 CI 混比，也不要挑选最快一次或把重跑成功算首轮成功。
2. **分段定位。** 分开统计创建至 job 启动的延迟、环境准备、依赖安装、测试、聚合收尾，以及部署中的源码准备、依赖、schema、服务启动、健康闸。启动延迟包含依赖等待和调度，不冒充纯排队或账户配额。并发 job 秒数之和与端到端墙钟耗时分别报告；比较安装加测试总耗时，避免把成本后移当作收益。样本不足时明确不能建立 P95/P99。
3. **复用现有工具。** `python3 scripts/release_performance_report.py --runs <runs.json> --jobs-dir <jobs-dir>` 汇总完整导出，输入格式见脚本说明。分片权重使用 `python3 scripts/refresh_ci_pytest_timings.py --help` 所列参数，从完整、首轮成功的进程日志更新 `.github/ci/backend-pytest-shards.json`；独立核对 GitHub run 身份与结论，不能仅信任手工传入的 SHA。多轮逐分片最大值和留一回放用于评估波动；回放不得冒充新 CI。调度复用 `backend/scripts/build_ci_pytest_matrix.py` 和 `backend/scripts/run_ci_pytest_worker.py`，不要另写平行调度器。
4. **固定质量底线。** 一次只改变可归因的瓶颈，先写下目标、代价和停止条件。保持测试选择、既有 skip、首轮执行、失败传播、超时、重试、权限和发布安全闸；仅为提速不得删检查、放宽时限或补造缺失计时。验证 `scripts/test_release_ci_contract.py`、`scripts/test_ci_timing_refresh.py` 及实际涉及的契约；需要改变上述边界时，单独设计、审查并建立新对照。
5. **真实验收。** 候选提交必须运行对应范围的新鲜 CI；工作流 / 分片 / 测试执行策略变化必须核验该精确 SHA 的完整 CI 和 JUnit 覆盖、skip、attempt。记录前后 run 链接、SHA、分段结果、测试集合、资源代价和样本限制。质量退化或触发停止条件时停止推广，不能靠重跑挑样本掩盖。部署验收按 `deploy.md` 复用已满足条件的同 SHA CI，保留锁、回执和健康闸；失败按原事务恢复，禁止重复发布未知结果或自动恢复旧配置。
6. **共享交接。** 将结论、未决项和脱敏机器证据提交到原 Dossier 与 `docs/reviews/`，本地 `docs/_generated/harness-runs/` 只作执行轨迹。其他 Agent 接手时同步并核验目标 revision，按已提交入口继续；运行中的旧 checkout 不会自动获得新规则。CI 配置进入 main 后由后续 CI 自动执行；仅 CI / 治理改动不触发无关后端部署或 OTA。分别报告“本地通过、main 生效、真实 CI 验证、生产部署”，不得混称已上线。

共同入口由 `AGENTS.md` 和两端 Health Harness adapter 引用；adapter 的性能治理引用与整文件摘要受 `check_agent_skill_governance.py check` 校验。该闸防止入口漂移，运行契约测试防止已覆盖的策略退化；二者不能代替对实际运行证据的审查，也不能保证所有 Agent 每次都能找到新的提速空间。
