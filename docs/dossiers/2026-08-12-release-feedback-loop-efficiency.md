# Dossier: 研发与发布反馈环提效

| 字段 | 值 |
|---|---|
| slug | `release-feedback-loop-efficiency` |
| 创建日期 | 2026-08-12 |
| 当前阶段 | S3（规划） |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | Local preflight → CI → release contract verification |

## S0 · 用户需求（逐字）

> 分析为啥执行这么久，在研发过程中，是否还有提效空间？分析当前任务的耗时构成，思考如何优化。
>
> 按顺序执行

- 使用者: 本仓库研发与发布操作者。
- 问题: 重复全量 CI、环境漂移、慢分片和重复发布构建拉长反馈环。
- 当前绕行: 人工判断应跑哪些检查、临时创建依赖环境、重复执行完整流水线。

## S1 · Discovery

- 四轮相关 main CI 的墙钟时间合计约 50 分钟；其中发布结果文档提交仍执行完整运行时矩阵。
- 本地长期虚拟环境与 `backend/requirements.lock` 不一致，导致 API 类型在本地无漂移、CI 有漂移。
- 历史慢 job 集中在 q-r、agent executor 和 agent i-z 分片。
- OTA 发生资产处理超时时重复 bundle/upload；失败未改写生产锚点，但等待不可复用。
- `deploy.sh` 的数据库保护和健康证明不可削减；依赖安装和 System KB 写入存在内容寻址优化空间。
- 并发 `main` 的文档变化也会触发 OTA 精确 SHA 拒绝，保护正确但粒度偏粗。

## G1 · 准入裁决

- 类型: 内部 Operating Harness 改进，不新增用户产品对象、健康写路径或自治行为。
- 核心价值: 缩短研发反馈并降低带红发布概率。
- 安全级: 发布基础设施高风险；所有不确定分类必须 fail closed。
- 最小切片: 快速前置闸 + 锁定类型生成 + 文档轻量 CI。
- 裁决: PASS；用户以“按顺序执行”确认实施顺序。

## S2/S3 · 设计与规划

- 设计: `docs/plans/2026-08-12-release-feedback-loop-efficiency-design.md`
- 实施计划: `docs/plans/2026-08-12-release-feedback-loop-efficiency.md`
- 选择渐进式改造现有 CI/发布脚本；拒绝仅靠人工纪律或新建独立编排服务。

## G2 · 可行性与安全压测

- 文档轻量路由只允许被确定性分类器明确识别的文档路径；未知、工作流、依赖和发布脚本改动均走 full。
- 锁定类型生成失败必须显式失败，不能回退旧虚拟环境。
- OTA 没有 EAS 标识不得写 manifest/anchor。
- 部署缓存 marker 缺失、损坏或不一致必须走原完整路径。
- 数据库备份、恢复演练、迁移、服务健康、revision 和 KB serving contract 永不跳过。
- 裁决: PASS；无待拍板分叉。

## S4 · 研发任务

- [ ] 快速前置闸。
- [ ] 锁定 OpenAPI 类型生成。
- [ ] CI 变更范围分流。
- [ ] 慢测试分片重平衡。
- [ ] OTA artifact 复用与超时熔断。
- [ ] 并发 main 运行树摘要保护。
- [ ] 后端依赖与 System KB 安全内容摘要。
- [ ] 完整验证与耗时复测。

## G3 · 测试闸

- pending。

## G4 · 安全闸

- 生产发布基础设施变更需要 release invariant 复核；不触及用户健康内容或写权限。
- pending。

## S6/G5 · 部署与健康

- 该任务修改研发/发布脚本和 CI，不直接改变线上运行包；最终根据实际 diff 决定是否需要部署。
- pending。

## S7/G6 · 验证

- 以一次完整代码 CI 和一次文档轻量 CI 的实际耗时、job 选择与 Gate 结果验收。
- pending。

## S8 · 沉淀

- pending。
