# Rokid + Reva 架构重设计 · 三方 Council Review 最终结论

> 日期: 2026-06-23 · 方法: council-review(三方对抗,2 轮)
> 审查对象:① Codex 原设计 [`2026-06-23-rokid-reva-end-to-end-architecture-redesign.md`](2026-06-23-rokid-reva-end-to-end-architecture-redesign.md) ② Claude A 落地增量版 [`2026-06-23-rokid-reva-delta-design-and-mvp-plan.md`](2026-06-23-rokid-reva-delta-design-and-mvp-plan.md)
> 评审:Codex(gpt-5.5)· Claude B(opus-4-8,独立 session)· Claude A(作者)。三方均**独立 read/grep 核实代码**,非凭文档自述。

## 终裁:✅ COUNCIL ACCEPT(一致通过)

| 成员 | Round 1 | Round 2 | 最终 |
|---|---|---|---|
| Codex | CONDITIONAL_ACCEPT | **ACCEPT**(operation_id 🔄 改主意) | ✅ |
| Claude B | CONDITIONAL_ACCEPT | **ACCEPT**(立场强化) | ✅ |
| Claude A | — | **ACCEPT**(operation_id 🔄 改主意) | ✅ |

2 轮收敛:Round 1 两位评审都 CONDITIONAL_ACCEPT、高度一致;唯一真分歧(operation_id 锚点)在 Round 2 经 Claude B 的 meal-sessions 实证收敛——**Codex 改主意、Claude A 改主意**,三方落到同一答案。

## 一致共识(3/3,高置信)

1. **「非 greenfield、~60% 已建」方向正确**——两位评审独立核了 cited 代码,7-8 项属实(Claude B 评价「甚至偏保守」)。
2. **+3 不变量方向对**:`native-call-timeout` **完全成立且确被原文漏**(实测只 photo 有 Promise.race);companion / 眼镜网络 是「**加固已有**」而非「补空白」。
3. **operation_id ≠ 泛化 pushup,≠ 17 列新大表 → 薄关联账本层**(见下,这是 council 的核心产出,两位评审都从各自原立场改到这里)。
4. **飞轮排序正确**:食物领头(被动采集 + 手机兜底 + R4 草稿,~80% 已建)· 俯卧撑最后(APK 分发 + 眼镜网络 + 姿态 ingest 多重不确定)。
5. **1 天计划塞不下**,需重排(见下)。

## Council 核心产出:operation_id = 薄关联账本层

> 两位评审独立确认了 Claude A 增量版**漏掉**的既有食物会话系统,并据此推翻「泛化 pushup」。

**实证(代码已部署)**:
- 食物 capture session **已存在**:`POST /meal-sessions` start · `/frames` append · `/finish` · `/confirm` · `/abort` · `GET`(`backend/app/api/ambient.py:280-421`)。模型 `MealMonitoringSession`(`backend/app/models/ambient_wearable.py:139-195`,14+ 列)含 `source='rokid_glasses'`、**`write_intent_id` FK 到 WriteIntent**(= 原设计 §3 一等 Health OS 对象)、`target_type/target_id` 泛型关联、`frame_count`、`privacy_class`、`summary/meta` JSONB;frame 经 `VisualInputEvent.meta.meal_session_id` 软关联。
- 俯卧撑 `RokidPushupSession/Event`(`models/rokid_pushup.py`)是**另一条产品语义**:event 有 6 个姿态专属列(`elbow_angle_deg`/`shoulder_hip_ankle_angle_deg`/`visibility`/`quality_score`/`reps`/`phase`,已 13 列)、session 有 `target_reps`/`ingest_token_hash`。

**结论(3/3)**:这两张表分形不同,**合一比加一层关联更脏**。正解 = 建一张**薄 `rokid_operations` 关联层,只做 observability anchor,不做业务 source-of-truth**:
```
rokid_operations
  operation_id          -- 外部稳定 ID
  user_id
  type                  -- capture_food / voice_command / pushup_session / install_app / open_custom_view / ...
  state                 -- queued|running|succeeded|degraded|failed|cancelled
  primary_surface
  started_at / finished_at
  meta_json
  entity_refs_json      -- 引用既有 domain 对象,不复制其字段:
                        --   meal_session_id · rokid_pushup_session_id · client_event_id
                        --   · agent_audit_log_id · write_intent_id
```
- **domain lifecycle 继续留在 meal-sessions / pushup-sessions**,不迁不改名。
- `entity_refs_json` 引用既有 `client_event`、`agent_audit_log`(都已存在)→ 不开第三套并行事件/审计系统(正是 delta 自己警告的反模式)。
- **加 `write_intent_id` 引用**(Claude B 补)→ 账本接回原设计 §3「Rokid 能力映射到 Health OS 一等对象」初衷。

## 必须修正(应用到 delta 文档)

| 项 | delta 写的 | 实况(评审核实) |
|---|---|---|
| sdkLinked 阻断 | `nativeState='blocked'` | 实为 `'degraded'`(`index.ts:412-413`);硬停靠 `captureState/voiceState='blocked'`(`:478-490`)+ UI 按钮禁用(`rokid-health.tsx:2081`),非 nativeState 本身 |
| 俯卧撑 | 「已建」 | 「session/event/app **scaffold 已有,非 E2E verified**」 |
| native-timeout | 「只 photo 做了」 | photo + pushup query/open/stop/install **部分**已有;要求**沉到 bridge wrapper 层统一**(`openCustomView/queryApp/installBundledApp/startRecord` 仍裸调) |
| companion 引证 | `:626-636` | **错**(那是 voice fallback 调试项);真证据 `rokid-health.tsx:483/499/501` |
| #10/#11 措辞 | 「补空白」 | 「**加固已有**」:companion 引导文案 + 网络检测(`index.ts:315-326`+`:480`)已存在;真缺口 = 升成显式状态 + **仅俯卧撑 POST 腿**(`RevaPushupEventClient.kt`)无 reachability preflight |
| operation_id | 泛化 pushup → 6-8 列 | 改薄关联账本层(见上);delta 此条自相矛盾(pushup event 已 13 列) |
| 漏掉对象 | 只引 visual-inputs | **补 meal-sessions(已部署)+ WriteIntent** |
| cited 行号 | 多处 | 已漂移,落地前需刷新 |

补充(🟡):`ble_blocked_by_companion` 设计成「**suspected**」态(证据 = authorized=true + companion 近期打开 + iosBleConnected=false + pending retry),别假装系统能直接证明 Hi Rokid 抢占;诊断上传剥 photo/audio 原文必须**服务端**强制,不只客户端裁剪。

## 重排后的最小可用计划(council 一致)

- **Day-1(廉价止血,全是低风险高价值)**:① `native-call-timeout` 普适化到 5 个 bridge wrapper(机械、防 UI 永挂——从 delta 的 day-3 提上来)② 诊断上传端点(服务端剥 PII)③ companion `suspected` 检测状态 ④ 本地 operation_id 串联。
- **Day-3(账本下沉)**:① 先出**一页纸 schema 关系决策**(rokid_operations × meal-sessions × pushup-sessions × client_event × audit × WriteIntent)② 薄 `rokid_operations` 表 + 手写迁移 + 部署(无 Alembic)③ 食物 operation timeline 可靠 ④ 俯卧撑 POST 腿区分「眼镜没网」vs「ingest 失败」。
- **Week-1(俯卧撑最后)**:① 眼镜端 Android App 补发 `session_state`(现仅发 pose/rep,`MainViewModel.kt:91`;schema 已允许)② APK 安装写清 CXR-L 限制 + fallback(manual ADB / 官方分发)③ 端到端事件验证。

## 残留(IMPORTANT,非 BLOCKING)
schema 命名 · `entity_refs` 格式 · event vocabulary subset 选取 · 迁移顺序 · 账本与 client_event/audit 的写入边界(避免重复旁路)。

---

*Council 方法:两个不同模型家族(Claude × GPT)独立 review + 实勘核证 + 2 轮对抗到共识。最高置信项 = 两家独立都命中的(非 greenfield、operation_id 不泛化 pushup、native-timeout 漏)。主分歧(operation_id 锚点)经一方的 meal-sessions 实证发现,另两方均改主意收敛。*
