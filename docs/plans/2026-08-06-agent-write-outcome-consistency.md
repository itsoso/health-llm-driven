# Plan: Agent 健康写入终态一致性

> Date: 2026-08-06
> Spec: `docs/specs/active/2026-08-06-agent-write-outcome-consistency.md`
> Dossier: `docs/dossiers/2026-08-06-agent-write-outcome-consistency.md`

## 1. Goal

在不重写 Agent 总状态机、不迁移数据库的前提下，修复两条生产故障，并用一个共享终态卡片闸防止同类“正文、卡片、持久化结果互相矛盾”的问题再次出现。

## 2. Safety Invariants

1. `write_receipts` 是“已记录”的唯一依据。
2. “待确认”必须对应服务端待确认工具结果或 durable `WriteIntent`。
3. 用药解析仅接受受控药名、明确肯定摄入、当前时点和正数服量。
4. 图片草稿与资产必须原子持久化；失败后不得创建无图 DietRecord。
5. 不新增剂量建议、诊断、处方或自动确认。

## 3. Data Flow

```text
source message
  -> deterministic intake classification / contextual photo capture
  -> verified receipt | durable pending plan | failed
  -> turn_outcome + server cards
  -> API terminal intake-card suppression
  -> Web/Mobile truthful presentation
```

## 4. Tasks

### T1 · Medication production sentence (Backend)

- 先补 RED：`记录我吃了两粒阿奇霉素` 的 parser、intent 和 zero-LLM Agent flow。
- 扩展单个受控药物的“服量在药名前”语法；重复数量、疑问、否定、历史时间继续拒绝。
- Agent 主分类器复用确定性摄入分类的 medication/supplement 结论，避免“吃了”抢成 diet。
- 验证 pending plan、确认写入和幂等回执。

### T2 · Shared terminal card gate (Backend)

- 先补 RED：失败/阻断/对账终态不得追加 query 派生摄入卡；真实 pending/verified 继续压制旧卡。
- 在 API card composition choke point 依据 `turn_outcome` 与原句的确定性摄入 kind 形成 suppression。
- route-only medication/supplement 旧卡增加 `presentation_state=suggestion` 与准确边界文案。

### T3 · Truthful card presentation (Web/Mobile)

- 先补 Web/Mobile RED：`presentation_state=suggestion` 不显示“待确认”。
- Web medication 与 Mobile medication/supplement 渲染“待核对/去记录”，保留真实服务端 pending card 的既有行为。
- 不改 diet 真正可确认卡的语义。

### T4 · Contextual meal photo atomicity (Backend)

- 先补 RED：草稿父记录必须在资产前 flush；失败/待确认阻断通用饮食 fallback。
- `DietPhotoDraft` 先 add+flush，再 add assets，最后一次 commit。
- contextual capture 失败或 pending 时设置本轮确定性 block reason；`health_record`/`health_manage` 共用现有拦截点。
- 验证失败时零 DietRecord，成功时图片草稿/资产完整。

### T5 · Gates and delivery

- G3：focused tests -> Backend/Web/Mobile 增量集成 -> doc drift/dossier consistency -> main CI。
- G4：独立安全评审，重点审用药误解析、确认绕过、重复写入、图片失败后的静默降级。
- S6：后端部署；Web 部署；Mobile OTA 仅在 production OTA freeze 尚未开始时发布，否则纳入 1.3.3 原生候选。
- G5/G6：健康分、服务 smoke、合成账号生产原句、真实设备回归；失败即回滚并阻断 App Store。

## 5. Verification Matrix

| State | Text | Card | Database |
|---|---|---|---|
| verified | 可显示已记录 | receipt/executed | exactly one verified record |
| confirmation_required | 确认文案 | actionable server plan | zero record before confirm |
| suggestion | 尚未写入/去记录 | 不得标待确认 | zero record |
| failed/blocked | 明确未执行 | 不附加 query 写入卡 | zero new record |
| reconciliation_required | 明确需核对 | 不提供重复写入口 | no retry write |

## 6. Release Route

- Backend: `deploy.sh` 后端路径。
- Web: `deploy.sh` 前端路径。
- Mobile: 纯 JS/TS，可 OTA；若 App Store production OTA freeze 已开启，则不单独 OTA，随同 exact-build 1.3.3 候选。
- Native/schema: 无变化，不因本修复单独触发 EAS native build。
