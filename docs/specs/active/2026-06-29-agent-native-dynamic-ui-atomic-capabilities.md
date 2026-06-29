# Agent Native Dynamic UI Atomic Capabilities

> Status: active paradigm v1
> Date: 2026-06-29
> Owner: Reva / Personal Health OS
> Related: `docs/specs/reva-product-governance-spec.md` · `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` · `docs/dossiers/2026-06-29-today-dynamic-view.md` · `mobile/components/chat/cards/types.ts`

## 1. Decision

Reva 的未来产品形态不再围绕固定页面堆功能。每一个用户可见功能都必须沉淀为一个 `AtomicCapability`: 符合 Reva 设计规范、拥有完整输入/状态/动作/安全边界的闭合组件。阿衡只负责编排这些已注册能力,根据时间、地点、天气、用户健康状态、计划、执行反馈和当前意图动态组合成 `DynamicView`。

页面和端不再是功能的所有者。Today、Chat、Watch、Mac、Web 都只是 surface shell:

- Chat 承接意图、解释、追问和决策沟通。
- Dynamic GUI 承接当下最该做的行动、确认、复盘和证据。
- Agent 选择能力、排序、分组、解释为什么现在出现。
- 确定性系统负责安全门、权限门、写入门和医疗边界。

## 2. AtomicCapability Contract

一个能力不是“一个漂亮卡片”。它是一个可被 Agent 安全调用的闭合产品单元。

```yaml
AtomicCapability:
  id: sleep_recovery_review
  version: v1
  first_class_objects:
    - HealthTwin
    - HealthAgendaItem
    - InterventionCycle
  surfaces:
    - mobile.today
    - mobile.chat
    - watch.summary
  input_projection:
    source: backend service or runtime projection
    required_fields: stable schema
    stale_after_seconds: 1800
  card_descriptor:
    type: sleep_recovery_review
    data_schema: explicit, additive-only after release
    actions: allowlisted descriptors only
  renderer:
    owner: mobile/components or shared surface component
    states:
      - normal
      - loading
      - empty
      - degraded
      - error
  safety:
    boundary: suggest_only | medical_boundary | manual_confirm_write
    escalation: deterministic rule or none
    disallowed_claims: no diagnosis, no dose change, no causal verdict without review
  execution:
    writes: none or WriteIntent/manual-confirm endpoint
    idempotency: required for any completion path
  telemetry:
    impression: required
    action: required for visible actions
    skip_or_dismiss_reason: required when applicable
  tests:
    backend_contract: required when backend emits data
    renderer: required
    action_dispatch: required when actions exist
```

最小可接受版本可以很小,但字段必须显式。Agent 可以组合能力,不能补造缺失的 schema、endpoint 或医疗判断。

## 3. Closure Rules

1. 输入闭合: 组件需要的数据由 `data_schema` 或明确的本地 query 声明,不得隐式依赖某个页面先拉过的全局状态。
2. 状态闭合: 组件自己处理 normal、empty、degraded、error,未知数据不导致页面崩溃。
3. 动作闭合: 组件暴露的是 `ChatCardActionDescriptor` / surface action descriptor,不暴露任意 URL 或任意函数。
4. 安全闭合: 医疗边界、写入权限、证据等级和 claim boundary 随 card data 一起下发或可由确定性系统推出。
5. 设计闭合: 组件使用 Reva 设计 token、间距、字体、radius 和可访问性规则,不把临时页面样式塞进内部。
6. 验证闭合: 能力有自己的合同测试和 renderer 测试,不只依赖整页 snapshot。

闭合不代表组件可以自作主张。业务排序、是否展示、何时推送、是否允许写入,仍由 backend composer、SafetyGuardian 和 action dispatcher 控制。

## 4. DynamicView Contract

`DynamicView` 是 Agent 编排结果,不是 UI 自由生成结果。它只能引用已注册能力。

```yaml
DynamicView:
  view_id: stable generated id
  surface: mobile.today
  trigger: open | resume | pull_refresh | proactive | action_completed
  generated_by: aheng_dynamic_view_v1
  generated_at: timestamp
  expires_at: timestamp
  context_hash: deterministic context digest
  safety_boundary: root boundary summary
  sections:
    - id: hero
      title: optional
      priority: 100
      cards:
        - type: daily_artifact
          data: validated capability payload
          actions: allowlisted actions
```

Surface shell 的职责只有四个:

1. 拉取或接收 `DynamicView`。
2. 按 `sections[].priority` 和注册表渲染能力。
3. 对未知 card type 安全降级,不崩溃。
4. 将 action 交给统一 dispatcher,由 dispatcher 做 allowlist、manual confirm 和 endpoint 限制。

## 5. Agent Composer Permissions

阿衡可以做:

- 选择哪些 `AtomicCapability` 进入当前视图。
- 决定 section、优先级、分组和解释文案。
- 根据用户主动问题生成 Chat 回答,并附带相关 card。
- 根据时间、地点、天气、数据新鲜度、计划和执行反馈触发 proactive view 或 push。
- 在安全边界内生成非医疗诊断式的摘要和建议语气。

阿衡不可以做:

- 生成任意 JSX、HTML、React Native 组件或未注册 card type。
- 下发任意 endpoint、任意 write payload 或绕过 action allowlist。
- 提升自治等级,例如把 suggest-only 变成自动执行。
- 诊断、处方、改药量、清除红旗症状或输出未验证因果结论。
- 因为模型“觉得重要”就越过 `SafetyGuardian` 排序和展示规则。

## 6. Implementation Rule For New Features

以后新增非平凡用户功能,默认按以下顺序实现:

1. 写清它映射的一等对象和 Health OS loop 位置。
2. 定义 `AtomicCapability` spec: id、输入、输出、actions、safety、telemetry、tests。
3. 后端提供稳定 projection 或 composer builder,输出 `ServerCardDescriptor` / `DynamicView` card data。
4. 前端实现闭合 renderer,注册到 card/capability registry。
5. surface shell 只消费 `DynamicView`,不直接新增长逻辑 dashboard。
6. 所有写动作走现有 action dispatcher、`WriteIntent` 或 agenda completion 合同。
7. 增加 focused contract tests、renderer tests、action allowlist tests。
8. 如果替代旧页面或旧入口,在 spec 里写明 keep、deprecate、hide、merge 或 delete。

## 7. First Application

`Today DynamicView` 是该范式的第一个落点:

- backend `/dynamic-views/today` 生成 `mobile.today` 视图。
- `daily_artifact` 是 Today hero 的原子能力。
- `runtime_agenda` 是滚动 7 天运行时的只读原子能力。
- Mobile Today 作为 shell 优先渲染 DynamicView,不可用时回退旧首页。
- Chat card registry 和 action allowlist 是后续 capability registry 的前身。

后续应把饮食、睡眠、训练、药物/补剂、慢病提醒、复查、预测回测和连接健康都按此范式登记为 `AtomicCapability`,再交给阿衡在 Today、Chat、Watch、Mac、Web 中动态组合。
