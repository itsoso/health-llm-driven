# 我的补剂组合与整组确认

| Field | Value |
| --- | --- |
| status | building |
| current_stage | S5 implementation |
| Controller | product-pipeline |
| Overlay | safety-gate |

用户同意“我的补剂组合＋整组确认”。

## G1
裁决: PASS。本人确认的执行记录，持续部署及OTA授权。

## G2
裁决: GO。独立 cold_recovery_safety 只读审查，复用协议及事件，不新增schema；全通用入口防护、原子事务、PG竞争与不可变快照为实现条件。见 docs/specs/2026-10-16-supplement-groups.md。

## Discovery
HealthProtocol.implied_quantity 与 HealthProtocolEvent.value 支持组合/历史；原batch handler自行commit，禁止复用作组合事务。地图无该路径索引，使用源码及邻近测试，完整System Map检查在补足.venv PATH后通过。

## Delivery
实现完成，待固定提交G4、完整CI与发布。只保存明确选择，不自动推断剂量；不做硬件或真实数据测试。后续精确CI/G4/部署/OTA分别留证。

运行 ledger: `docs/_generated/harness-runs/79f6714190c3.jsonl`（本地，不提交）。当前主干候选起点 24ef58b76；开放 PR 无本功能重叠任务。

发布准备将在任何撤销/轮换前检查 API 剩余额度与恢复时间，避免上轮在中途等待；不降低既有阈值或重放已执行阶段。

## S5 verification
后端合成 PostgreSQL 28项通过（包含两个连接并发确认、账户时区与不可变JSON）；补充通用archive拒绝从500修正400，专项45通过1个SQLite下PG并发跳过。Mobile 52项通过，完整TypeScript通过。PG CI shard已加入组合测试，catalog脚本37通过3跳过。API双端生成类型及System Map检查通过。

独立初审无BLOCK：后端28通过1跳过，Mobile38通过；最终GO待绑定SHA。RNWeb真实组件+合成服务验证新建/勾选/保存不打卡/核对/整组确认及390px布局；不是原生或真实账户验收。历史快照保留在数据库，当前只展示今日确认，尚无归档历史浏览入口。
