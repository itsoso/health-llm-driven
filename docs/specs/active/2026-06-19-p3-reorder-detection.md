# P3 后端:D1 补剂复购检测 + 提醒(**不下单**)

- 状态:已实现(backend)。配套 mobile 并行开发,对齐下方 API 契约。
- 范围:`backend/` only。不触 `apps/rokid-*` / `apps/watch` / `mobile/`。
- 关联 PRD:`docs/prd/2026-06-19-proactive-planning-prd.md` §3.D1。
- 自治层级:**T2**(系统检测 → 提议补货 write_intent → 用户一键确认)。

## 硬边界(safety / 财务面)

**P3 = 检测 + 提醒,绝不下单。** 本期实现严禁触及:下单 / 购买 / 支付 / 任何电商
(快手)skill 调用 / 财务一等对象 `ReorderIntent`。那是 PRD §3.D2(P5),要单独过
governance 一等对象 Gate + 财务安全评审。

- `reorder_nudge` write_intent 的 **confirm 只 acknowledge**(`executed_ref="acknowledged"`),
  不建任何订单、不调任何外部动作(见 `write_intent_service._execute` 的 reorder_nudge 分支,
  含「D2 才接快手 skill」的注释)。
- 库存模型 `SupplementInventory` 只承载**物流事实**(剩余量 / 一包多少 / 上次补货何时 /
  品牌 / 规格),无价格 / 支付 / 订单字段。
- 措辞全 hedged、纯物流提醒,非医疗建议、非处方(守 R4:不出「基因型→剂量」、不开方)。
- 无 LLM 路径(确定性算术),无 PII 进任何 agent / LLM;日志只记 user_id int。

## 数据流

```
GET /supplements/inventory
        ▼
  活跃 SupplementDefinition(用户域)
   + SupplementInventory(剩余量, 一行/补剂)
   + SupplementRecord 近 30 天 taken 打卡(估日消耗)
        ▼
  estimate_daily_consumption(taken_days / window)   ← 打卡≥3 用依从率, 否则回退每日 1 单位, 都无→None
        ▼
  compute_status(units_remaining, daily)            ← days_remaining = units/daily; ≤7→low, 否则 ok, 缺数据→unknown
        ▼
  InventoryItem[](端点直接返回)

每日 09:10(Asia/Shanghai) scan_reorder_nudges
        ▼
  对有库存登记的用户 → low_items_for_user
        ▼
  generate_reorder_nudges → propose(kind=reorder_nudge)  ← 幂等: 同(user,supplement,当天)已提过不重复
        ▼
  proactive_coordinator.can_notify_proactively(P1) 稀缺门 → 每人至多一条汇总推送
        ▼
  log_proactive_trigger(reorder_watch, P1)

POST /write-intents/{id}/confirm  (reorder_nudge)
        ▼
  _execute → return "acknowledged"   ← **不下单**, 仅标记已知悉
```

## 估算口径

- 回看窗口 30 天(`CONSUMPTION_WINDOW_DAYS`),低于 3 天打卡(`MIN_LOGS_FOR_ESTIMATE`)
  视为样本不足。
- 本仓 `SupplementDefinition` 无显式 frequency 字段 → prescribed 回退取每日 1 单位
  (`DEFAULT_DAILY_UNITS`)。
- 低库存阈值 `LOW_DAYS_THRESHOLD = 7` 天。`days_remaining` 是小数(不取整)。

## 幂等

1. 库存:一补剂一行(`UniqueConstraint supplement_id`)。restock 累加 / manual set 覆盖;
   并发建行撞约束 → 回滚重读再累加(不静默丢补货)。
2. write_intent:`propose` 自带 (user,kind,target) pending 去重 + `generate_reorder_nudges`
   的「同补剂当天已提过(任何状态)→ 跳过」双层防同日刷屏。
3. 每日扫描重跑当天 → `proposed=0`,write_intent 行数不翻倍(测试守门)。

## API 契约(已 pin,mobile 对齐)

- `GET  /api/v1/supplements/inventory` → `{"items": [InventoryItem]}`
  - `InventoryItem = {supplement_id:int, name:str, brand:str, spec:str,
    units_remaining:int|null, daily_consumption:number|null,
    days_remaining:number|null, status:"ok"|"low"|"unknown"}`
  - 一项/活跃补剂;缺库存 → units_remaining=null, status="unknown";brand/spec 缺省 ""。
- `POST /api/v1/supplements/inventory/{supplement_id}/restock`
  body `{units_added:int(必填,>0), brand?:str, spec?:str, package_units?:int}`
  → 累加 units_added,记今天 last_restock_date,更新非空 brand/spec/package_units;返回 InventoryItem。
  - `units_added` 缺失 / ≤0 → **422**(无静默默认)。
  - IDOR:supplement_id 非调用方 → **404**(且不创建库存行)。
- `PUT  /api/v1/supplements/inventory/{supplement_id}`
  body `{units_remaining:int(>=0)}` → 覆盖剩余量(修正);返回 InventoryItem。IDOR → 404。

字段精确 shape 见 `backend/app/api/supplement_inventory.py` 的 Pydantic model。

### reorder_nudge write_intent shape

```
kind        = "reorder_nudge"
title       = "{name} 还剩约 N 天,该补货了"   (估不出天数时 "快用完了")
description = "{name} 库存约 N 天,可以补货了。上次:{brand} {spec}。确认即标记已知悉(不会自动下单)。"
source      = "reorder_detection"
target_type = "supplement"
target_id   = <supplement_id>
payload     = {name, brand, spec, days_remaining, units_remaining}
confirm → executed, executed_ref="acknowledged"  (不下单)
```

## 文件

- 模型:`backend/app/models/supplement_inventory.py`(注册于 `models/__init__.py`)
- 迁移:`backend/migrations/managed/20260620_120000_create_supplement_inventory.{postgresql,sqlite}.sql`
- 检测 service:`backend/app/services/reorder_detection.py`(纯核 + DB 包装)
- write_intent kind:`backend/app/services/write_intent_service.py`
  (`generate_reorder_nudges` + `_execute` 的 reorder_nudge no-op 分支)
- 路由:`backend/app/api/supplement_inventory.py`(挂 `app/api/main.py`,前缀 `/supplements`)
- Celery 任务:`backend/app/tasks/reorder_scan.py`(`celery_app.py` include + beat `reorder-scan-daily` 09:10)
- 测试:`backend/tests/test_reorder_detection.py`

## 已知后续(本期不做)

- D2(P5):`reorder_nudge` confirm → 调快手电商 OpenClaw skill 下单(财务面,新增
  `ReorderIntent` 一等对象,逐笔强确认 + 月额上限 + 每单通知)。先定 skill 契约 + 过安全评审。
