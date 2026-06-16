# 设计 · Watch 到点项一键完成 + 服药/补剂回写 + action 埋点

日期: 2026-06-16 · 来源: [apple-watch-health-opportunities-roadmap.md](plans/2026-06-16-apple-watch-health-opportunities-roadmap.md) ★下一刀(王牌① + R18★1 延伸 + Phase0 埋点地基)

> 标准流程: 系统设计(本文) → 测试先行(TDD) → 严格安全审核(blocking) → 发布。本刀**安全敏感**(写用药依从记录),必过 `safety-privacy-reviewer`。

## 四问

- **做什么**: 让腕上「到点项」(处方药/补剂/喝水/餐协议)能一键标记完成,完成事实落进**真实业务表**(MedicationLog / SupplementRecord / …),并把 shown/completed 埋点上报。
- **为什么**: 服药/补剂依从是锚点用户(12 药 + 长期 PPI)最高频、临床价值最硬的可归因变量;`adherence_watch 未评分` 是当前最大 outcome 漏点。补上它,SupplementAdvisor 的 12 周 N-of-1 才转得动。喂 per-user「干预→结果」因果账本。
- **谁用**: 腕上锚点用户。watch 不持 user_id,经 iPhone 中继携 token 到后端,后端从 token 取 user_id。
- **边界(不做)**: 腕上不诊断/不调量(R4);非 health_protocol 源(复查/training/baseline_deviation/data_quality)腕上**只读不可勾完成**;Smart Stack 原生投递(ActivityKit)、Crown 选量、taken_at 历史补记、语音记症状、离线重试队列 —— **本刀不做**(见 roadmap defer)。

## 数据流

```
Watch「一键已做」tile
   │  (action_id = agenda-{object_type}-{object_id})
   ▼
iPhone WatchPhoneBridge  ── 白名单放行 /watch/actions/* + /client-events ──▶ 携 App Group token
   ▼
POST /api/v1/watch/actions/{action_id}/complete         POST /api/v1/client-events {watch_action_completed}
   │  token→user_id;解析 action_id                          │  (埋点,已有白名单/表)
   ▼                                                         ▼
agenda_service.complete_item(db, user_id, object_type, object_id)   client_event_log
   │  仅 object_type==health_protocol 放行,否则 400
   ▼
health_protocol_service.complete_protocol(db, object_id, user_id)   ← 必须按 user_id 过滤(防 IDOR)
   │  首次「非完成→完成」才落领域记录(幂等)
   ▼
_write_domain_record:  medication_logs→MedicationLog · diet_records→DietRecord · water_records→WaterRecord
                       · supplement_records→SupplementRecord  ◀── 本刀新增分支
```

## 契约

**action_id 编码**: `agenda-{object_type}-{object_id}`(复用 `test_client_events.py:171` + `client_events` meta 既有约定,埋点 meta 与回写端点零翻译)。非全局唯一可接受:同协议每日同 id,靠 event `occurred_at` + 领域记录 `record_date` 区分。

**端点**: `POST /api/v1/watch/actions/{action_id}/complete`
- 鉴权: `get_current_user_required`;**user_id 取自 token,绝不信任客户端**。
- 解析: 正则 `^agenda-(?P<ot>[a-z_]+)-(?P<oid>\d+)$`;不匹配 → **400**(fail loud)。
- 路由: 仅 `ot == "health_protocol"` 调 `complete_item`;其余 `ot` → **400**「该来源不支持腕上完成」。
- `complete_item` 抛 `协议不存在`/`协议非本人` → **404**;抛「不支持来源」→ **400**。
- 返回: `{ "action_id", "object_type", "object_id", "status": "completed", "written": "medication_log|supplement_record|...|none" }`。

**watch_summary action_id 注入**(投影层,纯只读): `top_action`、`quick_actions`、新增 `due_items[]`(只读到点列表)各带 `action_id`(由 `source.object_type/object_id` 合成);无 source 的项 `action_id=null`(不可完成)。**不碰 builder,不进请求内 `build_twin`。**

**埋点**: watch 渲染到点 tile 时发 `watch_action_shown`,完成成功后发 `watch_action_completed`,`meta={action_id, kind, priority_tier}`(后端白名单/表/测试已就绪,本刀只接 watch 端 emit + bridge 白名单)。

## 不变量(安全 · reviewer 核对)

1. **R12 不假装完成**: 完成必落**真实领域记录**;`_write_domain_record` 写库失败 → **向上抛**(不静默报完成)。无 POST(无用户确认)→ 无完成。补剂分支同样 fail-loud。
2. **幂等**: 双击「已做」→ **恰好一条**领域记录。依赖 `complete_protocol` 的「首次非完成→完成才落记录」守卫(health_protocol_service.py:176)。**必须有双 POST → 1 条记录的回归测试**(否则依从被灌水)。
3. **防 IDOR(关键)**: `complete_protocol(db, object_id, user_id)` 必须**按 user_id 过滤协议**,否则腕上猜 object_id 可完成他人协议。**必须有「A 的 token 完成 B 的 protocol_id → 404/拒绝」测试**。
4. **health_protocol-only**: 非协议源 400 fail-loud,不静默成功也不静默忽略。
5. **请求内禁 `build_twin`**: 本端点不需 twin;`complete_item`/`complete_protocol` 只操作协议/领域表。
6. **token 边界**: watch→iPhone 中继,token 走 App Group secure storage;bridge 白名单只放行本刀两条 POST,不放开通配。
7. **埋点最小化**: meta 仅 `action_id/kind/priority_tier`,无症状/用药名等敏感内容;size limit 已有。

## 测试计划(TDD,先红后绿)

后端:
1. `agenda-health_protocol-{pid}` complete → 200 + 协议置完成 + 落 1 条 MedicationLog。
2. **幂等**: 同 action_id 连续 POST 两次 → 仍只 1 条 MedicationLog,第二次 200 幂等(不报错也不重复)。
3. **IDOR**: 用户 A token 完成 用户 B 的 protocol_id → 404/拒绝,B 协议未变。
4. 非协议源 `agenda-training_decision-{uid}` → 400「不支持腕上完成」。
5. 畸形 action_id(`foo`、`agenda-x`、`agenda-health_protocol-abc`)→ 400。
6. 不存在的 protocol_id → 404。
7. **补剂分支**: source_model=supplement_records 的协议完成 → 落 1 条 `SupplementRecord(taken=True, taken_time≈now)`;写失败向上抛(mock 触发)。
8. watch_summary: top_action/quick_actions/due_items 各项带 `action_id`,格式 `agenda-{ot}-{oid}`;无 source 项 action_id=null。
9. 鉴权: 无 token → 401。

bridge/watch(tsc/swift 编译 + 单测可达者):
10. WatchPhoneBridge 白名单含 `/watch/actions/` + `/client-events`,其余 POST 仍拒。
11. Watch `completeAction(actionId:)` builder 产出 `path=/watch/actions/{id}/complete`,method=POST。

## 范围与延后

**本刀**: 后端端点 + 补剂分支 + action_id 注入 + 幂等/IDOR 守卫 + bridge 白名单 + watch「一键已做」tile + shown/completed 埋点。后端全本地 TDD;watch/bridge Swift 写好但**真机验证走 EAS 异步**(不阻塞后端发布)。

**延后(roadmap defer)**: snooze/skip 端点与 UI · Smart Stack 原生多条投递(ActivityKit native 欠债)· Crown 选量 + taken_at 历史 · 语音记症状(王牌⑤,单独安全刀)· 离线重试队列 · Complication 多尺寸 · Haptic 震型 · nudge_policy 降噪表 · data-freshness/sync-ledger。
