# P5 后端:D2 复购下单 —— 财务一等对象 `ReorderIntent`(**SCAFFOLD**,不真下单)

- 状态:已实现(backend SCAFFOLD)。**需过财务安全评审后方可对接真实下单。**
- 范围:`backend/` only。不触 `apps/` / `mobile/`。
- 关联 PRD:`docs/prd/2026-06-19-proactive-planning-prd.md` §3.D2 + §5。
- 关联治理:`docs/specs/reva-product-governance-spec.md` §8(一等对象准入 Gate)。
- 自治层级:**T3**(替你做外部动作:调快手电商 skill 下单)+ **财务硬门**(逐笔强确认)。

## ⚠️ 财务硬边界(评审重点)

**本期 = SCAFFOLD:搭建到「调快手电商 skill」的接缝为止就 STOP。**

- 真正下单由另一团队开发的**快手电商 OpenClaw skill** 执行,在用户**已授权的、自有的
  快手账号**下运行。后端**永不**处理支付凭据、**永不**扣款、**永不**无逐笔确认下单。
- 该 skill 契约**未就绪** → `kuaishou_skill_gateway.place_order` 恒抛 `NotImplementedError`;
  `confirm` 走到此处 → service 抛 `ReorderSkillNotReady` → API 返回 **HTTP 501**,
  意图停在安全态 `user_confirmed`(已确认未下单),**绝不**标 `order_placed`。
- 无任何「自动 / 影子(shadow)下单」层。每单 = `manual_confirm`,human-in-the-loop。
- `auto_reorder_enabled` + `monthly_cap_cents`(「常驻自动复购」)本期**不放开**:仅落
  月额上限的**确定性 cap-check 结构** + 测试守门;无任何真单触发它。

**可证惰性(代码锚点)**:
- `backend/app/services/kuaishou_skill_gateway.py:place_order` —— body 即 `raise NotImplementedError`。
- `backend/app/services/reorder_intent_service.py` `confirm_reorder_intent` —— 捕获
  `NotImplementedError` → `ReorderSkillNotReady`,意图保持 `user_confirmed`,不进 `order_placed`。
- `backend/app/api/reorder_intents.py` confirm 端点 —— `ReorderSkillNotReady` → 501。
- 测试 `tests/test_reorder_intent.py::test_place_order_stub_raises_not_implemented` +
  `::test_api_confirm_returns_501_skill_stubbed`(断言全库无 `order_placed` 行)。
- 无价格 / 支付凭据 / 银行卡 / 扣款字段或代码路径(模型与 service 均无)。

## 一等对象准入 Gate(governance-spec §8)

```yaml
RequirementAdmission:
  request: 复购下单 —— 用户确认 → 调快手电商 skill 用其自有账号下单(SCAFFOLD)
  classification: new_product_behavior
  first_user_fit: 中产慢病早期用户,补剂快用完时一键复购(省去手动找货/下单)
  core_loop_step: 执行迁移(T3)—— 把「该补货」的提议落成真实补货动作
  first_class_objects: ReorderIntent(财务下单意图,独立于 WriteIntent/提醒)
  target_surface: backend API(/api/v1/reorder-intents);mobile/web 后续对接
  source_of_truth: reorder_intents 表(状态机 + 时间戳 + 审计日志)
  safety_level: privacy_sensitive + red_flag   # 财务动作 + 外部账号
  prescription_or_causal_verdict: none          # 纯物流/财务,非医疗建议、不开方
  autonomy_tier: manual_confirm                 # 逐笔强确认,无 auto/shadow
  evidence_provenance: 用户登记库存 + 依从消耗(P3 检测);下单由用户确认触发
  claim_hedging: n/a                            # 非健康声明
  verification_window: 下单后由 skill 回参订单态;本期 SCAFFOLD 无真单
  success_metric: (对接后)确认→成功下单率;本期 = 501 接缝可证惰性 + 全测试绿
  added_user_burden: 每单一次确认(财务硬门,刻意保留,不可省)
  burden_justification: 财务动作 human-in-the-loop 是不可退让的安全边界
  non_goals:
    - 不自动扣款 / 不存储或传输任何支付凭据
    - 不实现任何 auto / shadow / 静默循环下单层
    - 后端不代用户输入支付凭据;skill 用用户自有账号
    - 本期不真下单(skill 契约未就绪 → 501)
  smallest_end_to_end_slice: 单品、一次性、manual_confirm,skill 打桩(place_order 抛
    NotImplementedError;confirm→501)—— 证明对象 + 状态机 + 财务边界 + 审计,不碰钱
  stale_surface_to_remove_or_archive: 无(P3 reorder_nudge 仍是独立的提醒路径)
  spec_required: yes
```

Gate result: **accepted(SCAFFOLD;真实下单待 skill 契约 + 财务安全评审)**
- Object mapping: `ReorderIntent`(财务一等对象,状态机 proposed→user_confirmed→order_placed|order_failed|cancelled)
- Surface: `POST/GET /api/v1/reorder-intents` + `/{id}/confirm` + `/{id}/cancel`
- Safety boundary: red-flag(财务)+ privacy(外部账号)—— 逐笔强确认 + 不碰支付凭据 + skill 用户自有账号
- Verification: `pytest tests/test_reorder_intent.py`(22 例,含财务惰性);confirm→501 可证

## 状态机

```
propose                 confirm(逐笔强确认)            快手 skill 下单
  │                          │                              │
  ▼                          ▼                              ▼
proposed ──────────▶ user_confirmed ──place_order──┬─▶ order_placed   (成功: kuaishou_order_id + placed_at)
  │   (rowcount 原子门)        │                     ├─▶ order_failed   (KuaishouSkillError / 业务 failed)
  │                          │                     └─▶ [本期] NotImplementedError → 501,停在 user_confirmed
  └──cancel──▶ cancelled ◀───┘ (proposed/user_confirmed → cancelled)
```

## 数据流

```
POST /api/v1/reorder-intents {supplement_id, quantity>0, brand?, spec?, auto_reorder_enabled?, monthly_cap_cents?}
        ▼
  _assert_owned_supplement (IDOR: supplement_id 非本人 → 404,不建意图)
        ▼
  propose_reorder_intent  ← 幂等: 同 (user,supplement,proposed) 已有 → 返回既有
        ▼
  ReorderIntent(status=proposed)

POST /api/v1/reorder-intents/{id}/confirm
        ▼
  _check_monthly_cap (auto_reorder_enabled+cap → 确定性护栏; 超限 409)
        ▼
  原子推进 proposed → user_confirmed (rowcount==1 守 + confirmed_at)
        ▼
  kuaishou_skill_gateway.place_order(...)   ← **本期恒抛 NotImplementedError**
        ▼
  NotImplementedError → ReorderSkillNotReady → API 501 (停 user_confirmed, 不下单)
  + audit.log_reorder_intent(outcome="skill_not_ready")

POST /api/v1/reorder-intents/{id}/cancel
        ▼
  cancel_reorder_intent  ← 仅 proposed/user_confirmed → cancelled
```

## API 契约(已 pin)

- `POST /api/v1/reorder-intents`
  body `{supplement_id:int(必填), quantity:int(必填,>0), brand?:str, spec?:str,
  auto_reorder_enabled?:bool=false, monthly_cap_cents?:int(>=0)}`
  → `ReorderIntentView`。`quantity` 缺失/≤0 → **422**;supplement 非本人 → **404**(不建意图)。
  幂等:同 (user,supplement,proposed) 已有 → 返回既有(不重复建)。
- `GET /api/v1/reorder-intents?status=` → `{"items": [ReorderIntentView]}`(按 user 过滤;可选 status)。
- `POST /api/v1/reorder-intents/{id}/confirm`
  → **本期 501**(skill 未就绪;意图停 user_confirmed)。不存在/非本人 → 404;月额超限 → 409;
  (契约就绪后)下单业务失败 → 200 + status=order_failed。
- `POST /api/v1/reorder-intents/{id}/cancel` → `ReorderIntentView`(cancelled)。不存在/非本人 → 404。

```
ReorderIntentView = {
  id:int, supplement_id:int, quantity:int, brand:str|null, spec:str|null,
  status:"proposed"|"user_confirmed"|"order_placed"|"order_failed"|"cancelled",
  kuaishou_order_id:str|null,           # 本期恒 null
  auto_reorder_enabled:bool, monthly_cap_cents:int|null, notes:str|null,
  created_at:str, confirmed_at:str|null, placed_at:str|null,   # 本期 placed_at 恒 null
  idempotent?:bool                       # confirm/双击时附带
}
```

## 快手电商 skill 契约(交接 —— 团队需提供)

源:`backend/app/services/kuaishou_skill_gateway.py` 模块 docstring(权威)。

- 调用方向:backend(网关)──▶ OpenClaw Gateway ──▶ 快手电商 skill(用户自有账号)。
- **入参**:`supplement_id:int`、`quantity:int(>0)`、`user_kuaishou_account_ref:str`
  (用户已授权快手账号引用 / openid,非密码非支付凭据)、`confirmation_token:str`
  (本次逐笔确认的一次性 token,绑 ReorderIntent.id+user_id,服务端签发,防重放)、
  `brand?:str`、`spec?:str`。
- **出参**:`{"status":"placed"|"failed", "order_id":str|null,
  "estimated_delivery":str|null(ISO), "error":str|null}`。
- **鉴权**:skill 以用户自有快手账号身份运行(OpenClaw 账号绑定);后端只传 account_ref +
  一次性 token,**不传**支付密码/银行卡/任何支付凭据。
- **回调**(异步落单时):`POST /api/v1/reorder-intents/{id}/order-callback`(本期未实现;
  同步返回即可。回调需带 confirmation_token 校验 + 幂等)。
- **失败语义**:网关/契约层不可恢复错误 → 抛 `KuaishouSkillError`(service 记 order_failed);
  业务下单失败 → 返回 `{"status":"failed", "error":...}`(service 同上)。

## 文件

- 模型:`backend/app/models/reorder_intent.py`(注册于 `models/__init__.py`)
- 迁移:`backend/migrations/managed/20260622_120000_create_reorder_intents.{postgresql,sqlite}.sql`
- skill 网关 STUB:`backend/app/services/kuaishou_skill_gateway.py`(`place_order` + `KuaishouSkillError`)
- service:`backend/app/services/reorder_intent_service.py`
  (propose/confirm/cancel/list + `ReorderSkillNotReady`/`ReorderCapExceeded`)
- 路由:`backend/app/api/reorder_intents.py`(挂 `app/api/main.py`,前缀 `/reorder-intents`)
- 审计:`backend/app/agents/audit.py::log_reorder_intent`(旁路,无 PII,只记 user_id + 对象 id)
- 测试:`backend/tests/test_reorder_intent.py`(22 例)

## 已知后续(本期不做 / 待评审)

- 真实下单:把 `place_order` STUB 换成真 OpenClaw skill 调用(需 skill 契约 + 财务安全评审)。
- 异步下单回调端点 `/{id}/order-callback`(confirmation_token 校验 + 幂等)。
- 「常驻自动复购」放开:显式开关 UI + 月额上限默认值 + 允许常驻的品类白名单 + 每单通知(不静默)。
- 月额已花金额的真实来源(skill 回参成交价 → `_monthly_spent_cents` 接入;本期恒 0)。
- mobile/web 前端对接(对齐上方 API 契约;写出口用生成 schema 标注防漂移)。
