# Dossier: 饮食编辑重算与聚餐个人份额

| 字段 | 值 |
| --- | --- |
| 创建日期 | 2026-09-21 |
| 当前阶段 | S5 |
| 状态 | building |
| 分支 | main |
| Run Ledger | `docs/_generated/harness-runs/e9532f2b53f3.jsonl` |

## S0 用户需求

> 更新代码 饮食编辑页面 修改文字之后 不能更新热量和营养 思考更好的交互模式 尤其是聚餐模式下 我拍全桌菜后 希望支持我只吃了1/5 这种能力

## S1 Discovery

聊天 inline editor 已调用重算，但没有明确重算状态，仍呈现可编辑旧数值。Backend 有重算原子命令、份额聊天修正与 canonical 后缀；没有公开结构化份额请求，第一人称附图语法漏接。独立只读调查: diet_portion_discovery。

## G1 / G2

裁决: PASS。既有 R5/R10/R11 手工录入纠正；手动确认，HealthTwin/WriteIntent/ExecutionEvent，Mobile + Backend；新非平凡交互需 spec。用户明确授权修改；没有待确认的新外部能力或医学自动化。

- [PRD](../prd/2026-09-21-diet-edit-shared-portion.md)
- [Spec](../specs/active/2026-09-21-diet-edit-shared-portion.md)
- [Plan](../plans/2026-09-21-diet-edit-shared-portion.md)
- 硬阻断已纳入：重复缩放、CAS、旧营养冒充新结果、跨 owner、含酒边界、失败伪成功。

## S4 / S5

Health Harness delegate，同一父流程。任务 T1 后端、T2 Mobile、T3 验证、安全评审、T4 发布。开工 main 干净，09a30dc7f；开放 PR 未命中新范围。无可用 karpathy/TDD 外部技能源，遵守 AGENTS red-first，不启用被禁用的 superpowers。

## G3 / G4

- RED：backend 新聚餐份额 12 failed / 6 passed；Mobile inline/helper 缺能力 4 failed；补充的精度保留与同帧双击 2 failed。实现后对应定向回归通过；独立饮食页 26 项通过。
- PostgreSQL 17.11 隔离库：195 passed / 0 skipped，包含真实竞争事务 CAS 单赢家；无生产数据写入。
- Mobile 首轮全回归 308 suites / 2960 passed / 1 skipped；补充锁定与精度修正后全量复跑中。TypeScript 检查通过。
- API 类型已同步 Mobile/Web；System Map、dossier consistency、skill governance、secret scan 通过。
- Live LLM gate 使用生产同 provider/model 配置，仅合成 ephemeral SQLite/test consent：invariants 12/12、core 50/50、orchestrator 5/5（avg .96）、trajectory 12/12、golden 9/9 通过。初次缺本机配置失败未视为通过；随后仅加载模型配置重跑成功。测试环境 usage 表缺失有旁路警告，不影响业务 gate，但不作为用量审计完整性证据。
- CI-mode 增量集成闸首轮 844 passed / 3 PostgreSQL-only skipped；最终 Mobile 308 suites / 2964 passed / 1 skipped。
- G4 首次固定提交 `ffd88da8b` **NO-GO**：自然语言份额与结构化份额可能双重缩放；仅凭可写文字后缀不能反推整桌基准。保持未 push/deploy。
- 整改：模型/快速路径前拒绝混写份额，前端保留输入并给出可操作提示；增加 owner/record/base/fraction/五营养 HMAC，旧/伪造/跨记录/跨用户/改营养的基准重新估算整桌。新增失败测试后定向 242 passed / 1 PG-only skipped；PG、CI-mode、Mobile 全量与独立复审继续运行。
- 模拟器：当前源码真实 RN 组件在单独合成 fixture App 中验证选择 1/5→1/3、文字输入后重算按钮与五营养只读，未发现截断。截图 `/tmp/reva-diet-portion-ui.png`；不把合成组件验收声称为生产 App 全路径或真机验收。

## S6 / G5 / G6

待部署与 production OTA；目标 revision CI 绿后进行。模拟器默认验收；真实相机与用户线上路径尚未验证。
