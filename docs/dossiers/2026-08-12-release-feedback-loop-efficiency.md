# Dossier: 研发与发布反馈环提效

| 字段 | 值 |
|---|---|
| slug | `release-feedback-loop-efficiency` |
| 创建日期 | 2026-08-12 |
| 当前阶段 | S7（验证） |
| 状态 | validating |
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

- [x] 快速前置闸。
- [x] 锁定 OpenAPI 类型生成。
- [x] CI 变更范围分流。
- [x] 慢测试分片重平衡。
- [x] OTA artifact 复用与超时熔断。
- [x] 并发 main 运行树摘要保护。
- [x] 后端依赖与 System KB 安全内容摘要。
- [x] 完整代码 CI 验证与耗时复测。
- [ ] 文档轻量 CI 实跑与记录。

## G3 · 测试闸

- 本地跨项回归: `359 passed in 1123.66s`，覆盖 CI 路由、类型生成、部署、
  rollback、OTA 和 release contract。
- 安全评审修复后的部署/rollback 完整回归: `172 passed in 702.12s`；最终发布
  contract 回归: `367 passed in 441.48s`。
- Mobile fast-feedback 聚焦回归: `22 passed in 15.78s`；release preflight 自检
  `21 passed`，System Map、dossier consistency、API type drift 均通过。
- GitHub Ubuntu Runner 暴露并修复三项只在异构环境出现的契约问题:
  macOS-only `stat` 测试桩、拆分前 shard 标签断言、dry-run 提前要求 Xcode。
- `main@9b57c689b1b0f9fe21e648914c9380eb9154afdc` 完整 CI
  [run 31580857216](https://github.com/itsoso/health-llm-driven/actions/runs/31580857216)
  `52/52` jobs PASS，墙钟 `554s`（08:59:22–09:08:36 UTC）。
- 裁决: PASS。

## G4 · 安全闸

- 独立 release review 首轮发现 rollback 依赖 marker 可能陈旧、marker
  ownership/symlink 证明不足、缺少真实 harness；均已修复并加回归测试。
- 最终复核结论: GO，无剩余 Critical/Important。
- 依赖和 System KB 复用均 fail closed；marker 必须是 root-owned、固定 mode、
  非 symlink、单硬链接并原子替换；rollback 精确校验锁版本并使 KB marker 失效。
- 不触及用户健康内容、写权限或锁屏推送数据。
- 裁决: PASS。

## S6/G5 · 部署与健康

- 修改范围是研发/发布脚本、CI 与文档，不改变后端/前端/Mobile/macOS 运行包；
  无需执行生产部署或 OTA。
- 部署脚本的备份、迁移、服务健康、revision、contract 和 rollback 证明仍由
  release invariant 覆盖，未因缓存命中而跳过。
- 裁决: N/A（无运行时发布），工程交付健康检查 PASS。

## S7/G6 · 验证

- 完整代码 CI: PASS，`52/52` jobs，墙钟 `554s`。
- 拆分后的目标慢分片: agent executor 四片分别 `92s/117s/101s/104s`；
  q/r 四片分别 `98s/105s/110s/175s`。
- 类型漂移 `84s`、release invariants `117s`、Mobile `111s`、Frontend
  `122s`、macOS `112s`；这些闸已不再构成完整 CI 长尾。
- 当前长尾转移到 `backend-test-k-m=530s` 与 `backend-test-agent-i-z=515s`，
  作为下一轮可量化优化候选，不扩大本次已确认范围。
- 文档轻量 CI: 待本 dossier 提交触发后记录。

## S8 · 沉淀

- 将反馈耗时拆成四类分别治理: 前置发现、CI 选择、单 job 长尾、发布重复工作；
  避免把“测试慢”笼统当作单一问题。
- 默认安全边界不变: 未知路径走 full、类型环境必须匹配 lock、OTA 无标识不落锚、
  部署缓存无完整证明不命中、生产数据库与服务健康证明永不省略。
- 待文档轻量 CI 实测通过后进入 S8 complete。
